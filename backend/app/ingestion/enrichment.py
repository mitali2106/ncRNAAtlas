"""Post-import enrichment: KEGG pathways, sequences, PubMed metadata, re-resolution.

Every function works from either a live service or a local cache file, and
reports what it could not do instead of guessing.
"""
import logging

from sqlalchemy import select

from ..extensions import db
from ..models import Alias, Disease, Gene, GenePathway, NcRNA, Pathway, utcnow
from ..services.http_client import ExternalServiceError
from ..services.kegg import pathway_url
from ..services.mirbase import mirbase_url, parse_mirna_dat
from ..validation.publications import enrich_publications, pending_publications

log = logging.getLogger(__name__)


def map_kegg_pathways(kegg_service=None, cache=None, only_unmapped=True):
    """Map genes with an NCBI Gene ID to KEGG pathways.

    ``cache`` (``{"links": {entrez: [pid]}, "pathway_names": {pid: name}}``) is
    used when ``kegg_service`` is ``None`` or fails.
    """
    genes = db.session.execute(
        select(Gene).where(Gene.organism == "Homo sapiens", Gene.stable_gene_identifier.is_not(None),
                           Gene.identifier_namespace == "NCBIGene")
    ).scalars().all()
    if only_unmapped:
        mapped = set(db.session.execute(select(GenePathway.gene_id)).scalars())
        genes = [g for g in genes if g.id not in mapped]
    report = {"genes_considered": len(genes), "genes_mapped": 0, "genes_without_pathways": [],
              "links_created": 0, "pathways_created": 0, "mode": "live" if kegg_service else "cache",
              "errors": []}
    if not genes:
        return report
    entrez = [g.stable_gene_identifier for g in genes]
    names, links = {}, {}
    if kegg_service is not None:
        try:
            names = kegg_service.list_human_pathways()
            links = kegg_service.link_genes(entrez)
        except ExternalServiceError as exc:
            report["errors"].append(f"KEGG unavailable: {exc.message}")
            report["mode"] = "cache" if cache else "failed"
            names, links = {}, {}
    if not links and cache:
        names = cache.get("pathway_names", {})
        links = {k: v for k, v in cache.get("links", {}).items() if k in set(entrez)}
    if not links and report["mode"] == "failed":
        return report

    source = "KEGG REST API" if report["mode"] == "live" else f"KEGG REST API (cached {cache.get('retrieved_at', '')})"
    existing = {p.pathway_identifier: p for p in db.session.execute(select(Pathway)).scalars()}
    now = utcnow()
    for g in genes:
        pids = links.get(g.stable_gene_identifier, [])
        if not pids:
            report["genes_without_pathways"].append(g.approved_gene_symbol)
            continue
        report["genes_mapped"] += 1
        for pid in pids:
            p = existing.get(pid)
            if p is None:
                p = Pathway(pathway_identifier=pid, pathway_name=names.get(pid), pathway_database="KEGG",
                            organism="Homo sapiens", pathway_url=pathway_url(pid))
                db.session.add(p)
                db.session.flush()
                existing[pid] = p
                report["pathways_created"] += 1
            elif not p.pathway_name and names.get(pid):
                p.pathway_name = names[pid]
            if db.session.get(GenePathway, (g.id, p.id)) is None:
                db.session.add(GenePathway(gene_id=g.id, pathway_id=p.id, mapping_source=source,
                                           mapping_type="direct", source_gene_identifier=f"hsa:{g.stable_gene_identifier}",
                                           mapping_timestamp=now))
                report["links_created"] += 1
    db.session.commit()
    return report


def enrich_pubmed(pubmed_service, limit=None, batch=200):
    pubs = pending_publications(limit)
    totals = {"requested": len(pubs), "fetched": 0, "not_found": 0, "error": None}
    for i in range(0, len(pubs), batch):
        fetched, missing, error = enrich_publications(pubs[i:i + batch], pubmed_service)
        totals["fetched"] += fetched
        totals["not_found"] += missing
        db.session.commit()
        if error:
            totals["error"] = error
            break
    return totals


def enrich_sequences(rnacentral_service, hgnc_index, ncrna_type="miRNA", limit=None):
    """Fill missing sequences from RNAcentral using HGNC-recorded RNAcentral IDs."""
    stmt = select(NcRNA).where(NcRNA.sequence.is_(None), NcRNA.resolution_status == "resolved",
                               NcRNA.organism == "Homo sapiens")
    if ncrna_type:
        stmt = stmt.where(NcRNA.ncrna_type == ncrna_type)
    rnas = db.session.execute(stmt.order_by(NcRNA.id).limit(limit)).scalars().all()
    report = {"considered": len(rnas), "updated": 0, "no_rnacentral_id": 0, "errors": 0}
    for n in rnas:
        urs = db.session.execute(
            select(Alias.alias).filter_by(entity_type="ncrna", entity_id=n.id, namespace="RNAcentral")
        ).scalars().first()
        if not urs:
            report["no_rnacentral_id"] += 1
            continue
        try:
            info = rnacentral_service.get_sequence(urs)
        except ExternalServiceError as exc:
            report["errors"] += 1
            log.warning("RNAcentral failed for %s: %s", urs, exc.message)
            if report["errors"] >= 5:
                break
            continue
        if info and info.get("sequence"):
            n.sequence = info["sequence"]
            n.sequence_source = f"RNAcentral {info['rnacentral_id']}"
            report["updated"] += 1
    db.session.commit()
    return report


def apply_mirbase_file(path):
    """Add precursor sequences and mature-product aliases from a miRBase ``miRNA.dat`` file."""
    report = {"entries": 0, "matched": 0, "sequences_set": 0, "aliases_added": 0}
    by_acc = {n.stable_identifier: n for n in db.session.execute(
        select(NcRNA).where(NcRNA.identifier_namespace == "miRBase")).scalars()}
    for entry in parse_mirna_dat(path):
        report["entries"] += 1
        n = by_acc.get(entry["accession"])
        if n is None:
            continue
        report["matched"] += 1
        if entry["sequence"] and (not n.sequence or n.sequence_source != "miRBase"):
            n.sequence, n.sequence_source = entry["sequence"], "miRBase"
            n.source_url = mirbase_url(entry["accession"])
            report["sequences_set"] += 1
        for p in entry["products"]:
            for value, kind in ((p.get("name"), "mature_product"), (p.get("accession"), "identifier")):
                if not value:
                    continue
                exists = db.session.execute(select(Alias.id).filter_by(
                    entity_type="ncrna", entity_id=n.id, alias=value, source_database="miRBase")).first()
                if not exists:
                    db.session.add(Alias(entity_type="ncrna", entity_id=n.id, alias=value,
                                         alias_normalized=value.lower(), alias_type=kind,
                                         namespace="miRBase" if kind == "identifier" else None,
                                         source_database="miRBase"))
                    report["aliases_added"] += 1
    db.session.commit()
    return report


def _add_alias(entity_type, entity_id, alias, alias_type, namespace, source):
    exists = db.session.execute(select(Alias.id).filter_by(
        entity_type=entity_type, entity_id=entity_id, alias=alias, source_database=source)).first()
    if not exists:
        db.session.add(Alias(entity_type=entity_type, entity_id=entity_id, alias=alias,
                             alias_normalized=alias.lower(), alias_type=alias_type, namespace=namespace,
                             source_database=source))


def merge_diseases(source, target):
    """Merge disease ``source`` into ``target`` (same MeSH descriptor), keeping all provenance.

    Associations are re-pointed; where ``target`` already has the same
    (ncRNA, association type), source records, publication links, gene links
    and reviews are moved onto the existing association. Returns the IDs of
    associations whose evidence must be recomputed.
    """
    from ..models import (
        Association,
        AssociationGene,
        AssociationPublication,
        AssociationSource,
        LiteratureReview,
    )

    touched = set()
    for a in db.session.execute(select(Association).filter_by(disease_id=source.id)).scalars().all():
        twin = db.session.execute(select(Association).filter_by(
            ncrna_id=a.ncrna_id, disease_id=target.id, association_type=a.association_type)).scalars().first()
        if twin is None:
            a.disease_id = target.id
            touched.add(a.id)
            continue
        for s in db.session.execute(select(AssociationSource).filter_by(association_id=a.id)).scalars():
            dup = db.session.execute(select(AssociationSource.id).filter_by(
                association_id=twin.id, source_database=s.source_database, source_record_id=s.source_record_id)).first()
            if dup:
                db.session.delete(s)
            else:
                s.association_id = twin.id
        for link in db.session.execute(select(AssociationPublication).filter_by(association_id=a.id)).scalars():
            existing = db.session.execute(select(AssociationPublication).filter_by(
                association_id=twin.id, publication_id=link.publication_id)).scalars().first()
            if existing is None:
                link.association_id = twin.id
            else:
                merged = sorted(set(existing.source_databases.split("; ")) | set(link.source_databases.split("; ")))
                existing.source_databases = "; ".join(merged)
                db.session.delete(link)
        for g in db.session.execute(select(AssociationGene).filter_by(association_id=a.id)).scalars():
            dup = db.session.execute(select(AssociationGene.id).filter_by(
                association_id=twin.id, gene_id=g.gene_id, gene_relationship=g.gene_relationship,
                source_database=g.source_database)).first()
            if dup:
                db.session.delete(g)
            else:
                g.association_id = twin.id
        for r in db.session.execute(select(LiteratureReview).filter_by(association_id=a.id)).scalars():
            r.association_id = twin.id
        db.session.flush()
        db.session.expire(a)
        db.session.delete(a)
        touched.add(twin.id)
    for alias in db.session.execute(select(Alias).filter_by(entity_type="disease", entity_id=source.id)).scalars():
        _add_alias("disease", target.id, alias.alias, alias.alias_type, alias.namespace, alias.source_database)
        db.session.delete(alias)
    _add_alias("disease", target.id, source.canonical_name, "synonym", "MeSH", "MeSH")
    db.session.flush()
    db.session.delete(source)
    db.session.flush()
    return touched


def reresolve_diseases(resolver, limit=None):
    """Retry exact MeSH resolution for unresolved diseases.

    A name that is an exact synonym of a descriptor already used by another
    stored disease is merged into that disease (provenance preserved); see
    :func:`merge_diseases`.
    """
    from ..models import AssociationSource
    from ..validation.evidence import aggregate_evidence

    diseases = db.session.execute(
        select(Disease).where(Disease.resolution_status == "unresolved").order_by(Disease.id).limit(limit)
    ).scalars().all()
    report = {"considered": len(diseases), "resolved": 0, "merged_into_existing": 0, "merges": []}
    touched = set()
    for d in diseases:
        res = resolver.resolve_disease(d.canonical_name)
        if res is None or not res.is_resolved:
            continue
        target = db.session.execute(
            select(Disease).where(Disease.disease_identifier == res.stable_identifier, Disease.id != d.id)
        ).scalars().first()
        if target is not None:
            report["merges"].append({"from": d.canonical_name, "into": target.canonical_name,
                                     "mesh": res.stable_identifier})
            touched |= merge_diseases(d, target)
            report["merged_into_existing"] += 1
        else:
            d.disease_identifier, d.identifier_namespace = res.stable_identifier, "MeSH"
            d.resolution_status = "resolved"
            _add_alias("disease", d.id, res.stable_identifier, "identifier", "MeSH", "MeSH")
            report["resolved"] += 1
        db.session.commit()
    from ..models import Association

    from .pipeline import _summary

    for a in db.session.execute(select(Association).where(Association.id.in_(touched))).scalars():
        srcs = [{"evidence_level": s.evidence_level, "regulation_direction": s.regulation_direction,
                 "source_database": s.source_database, "pmid": s.pmid}
                for s in db.session.execute(select(AssociationSource).filter_by(association_id=a.id)).scalars()]
        a.evidence_level, a.regulation_direction = aggregate_evidence(srcs)
        a.experimental_evidence_summary = _summary(srcs)
    db.session.commit()
    return report
