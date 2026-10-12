"""JSON serializers. Every association-level claim carries its provenance."""
from collections import defaultdict

from ..models import Alias
from ..models.constants import (
    ASSOCIATION_TYPES,
    EVIDENCE_LEVELS,
    GENE_RELATIONSHIPS,
    REVIEW_OUTCOMES,
    VALIDATION_STATUSES,
)
from ..services.kegg import pathway_url
from ..services.mesh import mesh_url
from ..services.mirbase import mirbase_url
from ..services.rnacentral import rnacentral_url


def iso(dt):
    return dt.isoformat() if dt else None


def identifier_url(namespace, identifier):
    if not identifier:
        return None
    if namespace == "miRBase":
        return mirbase_url(identifier)
    if namespace == "HGNC":
        return f"https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/{identifier}"
    if namespace == "MeSH":
        return mesh_url(identifier)
    if namespace == "NCBIGene":
        return f"https://www.ncbi.nlm.nih.gov/gene/{identifier}"
    if namespace == "RNAcentral":
        return rnacentral_url(identifier)
    return None


def aliases_for(entity_type, entity_id):
    rows = Alias.query.filter_by(entity_type=entity_type, entity_id=entity_id).order_by(Alias.alias).all()
    out = defaultdict(list)
    seen = set()
    for a in rows:
        key = (a.alias, a.alias_type, a.namespace)
        if key in seen:
            continue
        seen.add(key)
        out["identifiers" if a.alias_type == "identifier" else "names"].append({
            "alias": a.alias, "alias_type": a.alias_type, "namespace": a.namespace,
            "source_database": a.source_database, "url": identifier_url(a.namespace, a.alias)
            if a.alias_type == "identifier" else None,
        })
    return {"names": out.get("names", []), "identifiers": out.get("identifiers", [])}


def ncrna_summary(n):
    return {
        "id": n.id,
        "canonical_name": n.canonical_name,
        "stable_identifier": n.stable_identifier,
        "identifier_namespace": n.identifier_namespace,
        "identifier_url": identifier_url(n.identifier_namespace, n.stable_identifier),
        "ncrna_type": n.ncrna_type,
        "organism": n.organism,
        "resolution_status": n.resolution_status,
        "is_synthetic": n.is_synthetic,
    }


def ncrna_detail(n):
    data = ncrna_summary(n)
    data.update({
        "sequence": n.sequence,
        "sequence_length": len(n.sequence) if n.sequence else None,
        "sequence_source": n.sequence_source,
        "description": n.description,
        "source_database": n.source_database,
        "source_url": n.source_url,
        "resolution_note": n.resolution_note,
        "aliases": aliases_for("ncrna", n.id),
        "created_at": iso(n.created_at),
        "updated_at": iso(n.updated_at),
    })
    return data


def disease_summary(d):
    return {
        "id": d.id,
        "canonical_name": d.canonical_name,
        "disease_identifier": d.disease_identifier,
        "identifier_namespace": d.identifier_namespace,
        "identifier_url": identifier_url(d.identifier_namespace, d.disease_identifier),
        "resolution_status": d.resolution_status,
        "is_synthetic": d.is_synthetic,
    }


def disease_detail(d):
    data = disease_summary(d)
    data.update({"normalized_name": d.normalized_name, "description": d.description,
                 "aliases": aliases_for("disease", d.id)})
    return data


def gene_summary(g):
    return {
        "id": g.id,
        "approved_gene_symbol": g.approved_gene_symbol,
        "stable_gene_identifier": g.stable_gene_identifier,
        "identifier_namespace": g.identifier_namespace,
        "identifier_url": identifier_url(g.identifier_namespace, g.stable_gene_identifier),
        "hgnc_id": g.hgnc_id,
        "organism": g.organism,
        "full_name": g.full_name,
        "resolution_status": g.resolution_status,
    }


def gene_detail(g):
    data = gene_summary(g)
    data.update({"locus_type": g.locus_type, "hgnc_url": identifier_url("HGNC", g.hgnc_id),
                 "aliases": aliases_for("gene", g.id)})
    return data


def association_summary(a):
    sources = sorted({s.source_database for s in a.sources})
    return {
        "id": a.id,
        "ncrna": {"id": a.ncrna.id, "canonical_name": a.ncrna.canonical_name, "ncrna_type": a.ncrna.ncrna_type,
                  "organism": a.ncrna.organism},
        "disease": {"id": a.disease.id, "canonical_name": a.disease.canonical_name,
                    "disease_identifier": a.disease.disease_identifier},
        "association_type": a.association_type,
        "association_type_label": ASSOCIATION_TYPES.get(a.association_type),
        "regulation_direction": a.regulation_direction,
        "evidence_level": a.evidence_level,
        "evidence_level_label": EVIDENCE_LEVELS.get(a.evidence_level),
        "validation_status": a.validation_status,
        "validation_status_label": VALIDATION_STATUSES.get(a.validation_status),
        "confidence_score": a.confidence_score,
        "publication_count": len(a.publication_links),
        "source_record_count": len(a.sources),
        "source_databases": sources,
        "is_synthetic": a.is_synthetic,
    }


def source_record(s):
    return {
        "id": s.id,
        "source_database": s.source_database,
        "source_record_id": s.source_record_id,
        "source_url": s.source_url,
        "source_version": s.source_version,
        "import_timestamp": iso(s.import_timestamp),
        "import_job_id": s.import_job_id,
        "evidence_level": s.evidence_level,
        "regulation_direction": s.regulation_direction,
        "source_category": s.source_category,
        "experimental_methods": s.experimental_methods,
        "evidence_text": s.evidence_text,
        "pmid": s.pmid,
        "original_record": s.original_record,
    }


def publication(p, link=None):
    data = {
        "pmid": p.pmid,
        "doi": p.doi,
        "publication_title": p.publication_title,
        "authors": p.authors,
        "journal": p.journal,
        "publication_year": p.publication_year,
        "abstract": p.abstract,
        "publication_url": p.publication_url,
        "doi_url": f"https://doi.org/{p.doi}" if p.doi else None,
        "metadata_status": p.metadata_status,
        "fetched_at": iso(p.fetched_at),
    }
    if link is not None:
        data["cited_by_sources"] = link.source_databases.split("; ")
        data["evidence_notes"] = link.evidence_notes
    return data


def association_gene(link):
    return {
        "gene": gene_summary(link.gene),
        "gene_relationship": link.gene_relationship,
        "gene_relationship_label": GENE_RELATIONSHIPS.get(link.gene_relationship),
        "evidence_description": link.evidence_description,
        "source_database": link.source_database,
        "pmid": link.pmid,
        "scope": "association",
    }


def interaction(i, include_ncrna=False, include_gene=True):
    data = {
        "id": i.id,
        "relationship": i.relationship,
        "relationship_label": GENE_RELATIONSHIPS.get(i.relationship),
        "evidence_strength": i.evidence_strength,
        "experimental_methods": i.experimental_methods,
        "evidence_description": i.evidence_description,
        "source_database": i.source_database,
        "source_record_id": i.source_record_id,
        "pmid": i.pmid,
        "scope": "ncrna_general",
    }
    if include_gene:
        data["gene"] = gene_summary(i.gene)
    if include_ncrna:
        data["ncrna"] = ncrna_summary(i.ncrna)
    return data


def review(r):
    return {
        "id": r.id,
        "pmid": r.pmid,
        "review_type": r.review_type,
        "outcome": r.outcome,
        "outcome_label": REVIEW_OUTCOMES.get(r.outcome),
        "evidence_type": r.evidence_type,
        "notes": r.notes,
        "flags": r.flags,
        "reviewer": r.reviewer,
        "reviewed_at": iso(r.reviewed_at),
    }


def pathway(p, gene_count=None):
    data = {
        "id": p.id,
        "pathway_identifier": p.pathway_identifier,
        "pathway_name": p.pathway_name,
        "pathway_database": p.pathway_database,
        "organism": p.organism,
        "pathway_url": p.pathway_url or pathway_url(p.pathway_identifier),
        "description": p.description,
    }
    if gene_count is not None:
        data["gene_count"] = gene_count
    return data


def import_job(j):
    return {
        "id": j.id,
        "source_database": j.source_database,
        "job_type": j.job_type,
        "dataset_label": j.dataset_label,
        "source_file": j.source_file,
        "source_version": j.source_version,
        "started_at": iso(j.started_at),
        "completed_at": iso(j.completed_at),
        "status": j.status,
        "records_processed": j.records_processed,
        "records_inserted": j.records_inserted,
        "records_updated": j.records_updated,
        "records_skipped": j.records_skipped,
        "error_summary": j.error_summary,
        "has_report": bool(j.report_path),
        "summary": j.summary,
    }
