"""Reusable database queries: association filtering, inferred pathways, search."""
from collections import defaultdict

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import selectinload

from ..api_utils import APIError
from ..extensions import db
from ..models import (
    Alias,
    Association,
    AssociationGene,
    AssociationPublication,
    AssociationSource,
    Disease,
    Gene,
    GenePathway,
    NcRNA,
    NcRNAGeneInteraction,
    Pathway,
    Publication,
)
from ..models.constants import ASSOCIATION_TYPES, EVIDENCE_LEVELS, HUMAN, NCRNA_TYPES, VALIDATION_STATUSES
from ..normalization.text import like_escape

ASSOCIATION_SORTS = {
    "id": Association.id,
    "ncrna": func.lower(NcRNA.canonical_name),
    "disease": func.lower(Disease.canonical_name),
    "evidence": Association.evidence_level,
    "type": Association.association_type,
}


def like(term):
    return f"%{like_escape(term.lower())}%"


def organism_clause(column, organism):
    if organism in (None, "", "all"):
        return None
    return column == organism


def association_filters(args):
    """Validate association filter parameters from a dict-like ``args``."""
    f = {}
    for key, choices in (("ncrna_type", NCRNA_TYPES), ("evidence_level", EVIDENCE_LEVELS),
                         ("validation_status", VALIDATION_STATUSES), ("association_type", ASSOCIATION_TYPES)):
        values = [v.strip() for v in (args.get(key) or "").split(",") if v.strip()]
        bad = [v for v in values if v not in choices]
        if bad:
            raise APIError(400, f"Invalid {key}: {', '.join(bad)}. Allowed: {', '.join(choices)}")
        if values:
            f[key] = values
    for key in ("ncrna_id", "disease_id", "gene_id", "target_gene_id", "year_from", "year_to"):
        raw = args.get(key)
        if raw not in (None, ""):
            try:
                f[key] = int(raw)
            except ValueError:
                raise APIError(400, f"Parameter '{key}' must be an integer")
    for key in ("source", "q", "disease", "gene"):
        raw = (args.get(key) or "").strip()
        if len(raw) > 100:
            raise APIError(400, f"Parameter '{key}' exceeds 100 characters")
        if raw:
            f[key] = raw
    f["organism"] = (args.get("organism") or HUMAN).strip()
    return f


def association_select(f, sort="id", order="asc"):
    pub_count = (
        select(func.count(AssociationPublication.id))
        .where(AssociationPublication.association_id == Association.id)
        .correlate(Association).scalar_subquery()
    )
    stmt = select(Association).join(NcRNA, Association.ncrna_id == NcRNA.id).join(
        Disease, Association.disease_id == Disease.id
    )
    clause = organism_clause(NcRNA.organism, f.get("organism"))
    if clause is not None:
        stmt = stmt.where(clause)
    if "ncrna_type" in f:
        stmt = stmt.where(NcRNA.ncrna_type.in_(f["ncrna_type"]))
    if "evidence_level" in f:
        stmt = stmt.where(Association.evidence_level.in_(f["evidence_level"]))
    if "validation_status" in f:
        stmt = stmt.where(Association.validation_status.in_(f["validation_status"]))
    if "association_type" in f:
        stmt = stmt.where(Association.association_type.in_(f["association_type"]))
    if "ncrna_id" in f:
        stmt = stmt.where(Association.ncrna_id == f["ncrna_id"])
    if "disease_id" in f:
        stmt = stmt.where(Association.disease_id == f["disease_id"])
    if "disease" in f:
        stmt = stmt.where(func.lower(Disease.canonical_name).like(like(f["disease"]), escape="\\"))
    if "gene_id" in f:
        stmt = stmt.where(select(AssociationGene.id).where(
            AssociationGene.association_id == Association.id, AssociationGene.gene_id == f["gene_id"]).exists())
    if "gene" in f:
        gene_ids = select(Gene.id).where(func.lower(Gene.approved_gene_symbol) == f["gene"].lower())
        stmt = stmt.where(select(AssociationGene.id).where(
            AssociationGene.association_id == Association.id, AssociationGene.gene_id.in_(gene_ids)).exists())
    if "target_gene_id" in f:
        stmt = stmt.where(Association.ncrna_id.in_(
            select(NcRNAGeneInteraction.ncrna_id).where(NcRNAGeneInteraction.gene_id == f["target_gene_id"])))
    if "source" in f:
        stmt = stmt.where(select(AssociationSource.id).where(
            AssociationSource.association_id == Association.id,
            func.lower(AssociationSource.source_database) == f["source"].lower()).exists())
    if "q" in f:
        stmt = stmt.where(or_(func.lower(NcRNA.canonical_name).like(like(f["q"]), escape="\\"),
                              func.lower(Disease.canonical_name).like(like(f["q"]), escape="\\")))
    if "year_from" in f or "year_to" in f:
        cond = [AssociationPublication.association_id == Association.id]
        if "year_from" in f:
            cond.append(Publication.publication_year >= f["year_from"])
        if "year_to" in f:
            cond.append(Publication.publication_year <= f["year_to"])
        stmt = stmt.where(select(AssociationPublication.id).join(Publication).where(and_(*cond)).exists())

    if sort == "publications":
        key = pub_count
    else:
        key = ASSOCIATION_SORTS.get(sort)
        if key is None:
            raise APIError(400, f"Invalid sort. Allowed: {', '.join([*ASSOCIATION_SORTS, 'publications'])}")
    key = key.desc() if order == "desc" else key.asc()
    tiebreak = Association.id.desc() if order == "desc" else Association.id.asc()
    return stmt.options(
        selectinload(Association.ncrna), selectinload(Association.disease),
        selectinload(Association.sources), selectinload(Association.publication_links),
    ).order_by(key, tiebreak)


# ----------------------------------------------------------------- pathways
def pathways_for_genes(gene_ids, basis):
    """Pathways for a set of genes, grouped, each labelled with how it was derived."""
    if not gene_ids:
        return []
    rows = db.session.execute(
        select(Pathway, Gene.id, Gene.approved_gene_symbol, GenePathway.mapping_source, GenePathway.mapping_timestamp)
        .join(GenePathway, GenePathway.pathway_id == Pathway.id).join(Gene, Gene.id == GenePathway.gene_id)
        .where(Gene.id.in_(gene_ids)).order_by(Pathway.pathway_identifier, Gene.approved_gene_symbol)
    ).all()
    grouped = {}
    for p, gid, symbol, source, ts in rows:
        entry = grouped.setdefault(p.id, {"pathway": p, "genes": [], "mapping_source": source, "mapped_at": ts})
        entry["genes"].append({"id": gid, "approved_gene_symbol": symbol})
    out = []
    from ..schemas.serializers import iso, pathway as ser_pathway

    for entry in sorted(grouped.values(), key=lambda e: (-len(e["genes"]), e["pathway"].pathway_identifier)):
        data = ser_pathway(entry["pathway"])
        data.update({"mapping_type": "inferred_via_genes", "basis": basis, "genes": entry["genes"],
                     "mapping_source": entry["mapping_source"], "mapped_at": iso(entry["mapped_at"])})
        out.append(data)
    return out


def ncrna_gene_ids(ncrna_id):
    ids = set(db.session.execute(
        select(NcRNAGeneInteraction.gene_id).where(NcRNAGeneInteraction.ncrna_id == ncrna_id)).scalars())
    ids |= set(db.session.execute(
        select(AssociationGene.gene_id).join(Association).where(Association.ncrna_id == ncrna_id)).scalars())
    return ids


def disease_gene_ids(disease_id):
    return set(db.session.execute(
        select(AssociationGene.gene_id).join(Association).where(Association.disease_id == disease_id)).scalars())


def genes_without_mapping(gene_ids):
    if not gene_ids:
        return []
    mapped = set(db.session.execute(select(GenePathway.gene_id).where(GenePathway.gene_id.in_(gene_ids))).scalars())
    rows = db.session.execute(
        select(Gene.id, Gene.approved_gene_symbol, Gene.stable_gene_identifier)
        .where(Gene.id.in_(set(gene_ids) - mapped)).order_by(Gene.approved_gene_symbol)
    ).all()
    return [{"id": r[0], "approved_gene_symbol": r[1],
             "reason": "No KEGG pathway returned for this gene" if r[2] else "No NCBI Gene ID; not mapped"}
            for r in rows]


# ------------------------------------------------------------------- search
def _rank(column, q):
    ql = q.lower()
    return case((func.lower(column) == ql, 0), (func.lower(column).like(f"{like_escape(ql)}%", escape="\\"), 1),
                else_=2)


def _alias_ids(entity_type, q):
    return select(Alias.entity_id).where(Alias.entity_type == entity_type,
                                         Alias.alias_normalized.like(like(q), escape="\\"))


def search_ncrnas(q, limit=10, ncrna_type=None, organism=None):
    stmt = select(NcRNA).where(or_(
        func.lower(NcRNA.canonical_name).like(like(q), escape="\\"),
        func.lower(NcRNA.stable_identifier).like(like(q), escape="\\"),
        NcRNA.id.in_(_alias_ids("ncrna", q)),
    ))
    if ncrna_type:
        stmt = stmt.where(NcRNA.ncrna_type == ncrna_type)
    clause = organism_clause(NcRNA.organism, organism)
    if clause is not None:
        stmt = stmt.where(clause)
    return stmt.order_by(_rank(NcRNA.canonical_name, q), func.length(NcRNA.canonical_name), NcRNA.id).limit(limit)


def search_diseases(q, limit=10):
    stmt = select(Disease).where(or_(
        func.lower(Disease.canonical_name).like(like(q), escape="\\"),
        func.lower(Disease.disease_identifier).like(like(q), escape="\\"),
        Disease.id.in_(_alias_ids("disease", q)),
    ))
    return stmt.order_by(_rank(Disease.canonical_name, q), func.length(Disease.canonical_name), Disease.id).limit(limit)


def search_genes(q, limit=10):
    stmt = select(Gene).where(or_(
        func.lower(Gene.approved_gene_symbol).like(like(q), escape="\\"),
        Gene.stable_gene_identifier == q,
        func.lower(Gene.full_name).like(like(q), escape="\\"),
        Gene.id.in_(_alias_ids("gene", q)),
    ))
    return stmt.order_by(_rank(Gene.approved_gene_symbol, q), func.length(Gene.approved_gene_symbol),
                         Gene.id).limit(limit)


def search_publications(q, limit=10):
    if q.isdigit():
        return select(Publication).where(Publication.pmid == q).limit(limit)
    return select(Publication).where(
        func.lower(Publication.publication_title).like(like(q), escape="\\")
    ).order_by(Publication.publication_year.desc(), Publication.id).limit(limit)


def search_pathways(q, limit=10):
    return select(Pathway).where(or_(
        func.lower(Pathway.pathway_name).like(like(q), escape="\\"),
        func.lower(Pathway.pathway_identifier).like(like(q), escape="\\"),
    )).order_by(_rank(Pathway.pathway_name, q), Pathway.id).limit(limit)


def association_counts(column, ids):
    """``{entity_id: association_count}`` for ncRNA or disease ids."""
    if not ids:
        return {}
    rows = db.session.execute(
        select(column, func.count(Association.id)).where(column.in_(ids)).group_by(column)
    ).all()
    return defaultdict(int, {r[0]: r[1] for r in rows})
