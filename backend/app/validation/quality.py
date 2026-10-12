"""Data-quality report generation."""
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from ..extensions import db
from ..models import (
    Association,
    AssociationPublication,
    AssociationSource,
    Disease,
    Gene,
    GenePathway,
    ImportJob,
    NcRNA,
    NcRNAGeneInteraction,
    Pathway,
    Publication,
)

LIST_LIMIT = 500


def _count(stmt):
    return db.session.execute(stmt).scalar() or 0


def generate_quality_report(import_summary=None):
    real = Association.is_synthetic.is_(False)
    jobs = db.session.execute(select(ImportJob).where(ImportJob.status.like("completed%"))).scalars().all()
    raw_total = sum((j.summary or {}).get("raw_records", 0) for j in jobs)
    dup_in_file = sum((j.summary or {}).get("duplicates_in_file", 0) for j in jobs)
    merged = sum((j.summary or {}).get("merged_into_existing", 0) for j in jobs)

    unresolved_ncrna = db.session.execute(
        select(NcRNA.canonical_name, NcRNA.ncrna_type, NcRNA.resolution_status, NcRNA.resolution_note)
        .where(NcRNA.resolution_status.in_(["unresolved", "ambiguous"])).order_by(NcRNA.canonical_name)
    ).all()
    unresolved_disease = db.session.execute(
        select(Disease.canonical_name, Disease.resolution_status)
        .where(Disease.resolution_status.in_(["unresolved", "ambiguous"])).order_by(Disease.canonical_name)
    ).all()
    unresolved_gene = db.session.execute(
        select(Gene.approved_gene_symbol, Gene.resolution_status)
        .where(Gene.resolution_status.in_(["unresolved", "ambiguous"])).order_by(Gene.approved_gene_symbol)
    ).all()
    no_pub = select(Association.id).where(
        real, ~select(AssociationPublication.id).where(AssociationPublication.association_id == Association.id).exists()
    )
    no_src = select(Association.id).where(
        real, ~select(AssociationSource.id).where(AssociationSource.association_id == Association.id).exists()
    )
    conflicting = db.session.execute(
        select(Association.id, NcRNA.canonical_name, Disease.canonical_name, Association.association_type)
        .join(NcRNA, Association.ncrna_id == NcRNA.id).join(Disease, Association.disease_id == Disease.id)
        .where(real, Association.evidence_level == "conflicting").order_by(Association.id)
    ).all()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "raw_records_imported_all_jobs": raw_total,
            "unique_ncrnas": _count(select(func.count(NcRNA.id)).where(NcRNA.is_synthetic.is_(False))),
            "unique_diseases": _count(select(func.count(Disease.id)).where(Disease.is_synthetic.is_(False))),
            "unique_genes": _count(select(func.count(Gene.id)).where(Gene.is_synthetic.is_(False))),
            "associations": _count(select(func.count(Association.id)).where(real)),
            "human_associations": _count(
                select(func.count(Association.id)).join(NcRNA).where(real, NcRNA.organism == "Homo sapiens")
            ),
            "non_human_associations": _count(
                select(func.count(Association.id)).join(NcRNA).where(real, NcRNA.organism != "Homo sapiens")
            ),
            "ncrna_gene_interactions": _count(select(func.count(NcRNAGeneInteraction.id))),
            "publications": _count(select(func.count(Publication.id))),
            "publications_pending_metadata": _count(
                select(func.count(Publication.id)).where(Publication.metadata_status != "fetched")
            ),
            "pathways": _count(select(func.count(Pathway.id))),
            "gene_pathway_mappings": _count(select(func.count()).select_from(GenePathway)),
            "duplicate_records_in_files": dup_in_file,
            "records_merged_into_existing_associations": merged,
            "unresolved_rna_names": len(unresolved_ncrna),
            "unresolved_disease_names": len(unresolved_disease),
            "unresolved_gene_identifiers": len(unresolved_gene),
            "associations_missing_publication_evidence": _count(select(func.count()).select_from(no_pub.subquery())),
            "associations_missing_source_provenance": _count(select(func.count()).select_from(no_src.subquery())),
            "associations_with_conflicting_evidence": len(conflicting),
        },
        "lists": {
            "unresolved_rna_names": [
                {"name": r[0], "type": r[1], "status": r[2], "note": r[3]} for r in unresolved_ncrna[:LIST_LIMIT]
            ],
            "unresolved_disease_names": [{"name": r[0], "status": r[1]} for r in unresolved_disease[:LIST_LIMIT]],
            "unresolved_gene_identifiers": [{"name": r[0], "status": r[1]} for r in unresolved_gene[:LIST_LIMIT]],
            "conflicting_associations": [
                {"association_id": r[0], "ncrna": r[1], "disease": r[2], "association_type": r[3]}
                for r in conflicting[:LIST_LIMIT]
            ],
        },
        "list_limit": LIST_LIMIT,
    }
    if import_summary is not None:
        report["import"] = {k: v for k, v in import_summary.items() if k != "preview"}
    return report


def report_to_csv(report):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "item", "value", "detail"])
    for k, v in report["metrics"].items():
        w.writerow(["metric", k, v, ""])
    imp = report.get("import")
    if imp:
        for k in ("raw_records", "valid_records", "inserted", "updated", "unchanged", "skipped",
                  "duplicates_in_file", "merged_into_existing", "non_human_records", "missing_pmid"):
            w.writerow(["import", k, imp.get(k), ""])
        for reason, n in imp.get("skip_reasons", {}).items():
            w.writerow(["import_skip_reason", reason, n, ""])
        for warning in imp.get("warnings", []):
            w.writerow(["import_warning", warning.get("line"), "", warning.get("message")])
    for name, rows in report["lists"].items():
        for row in rows:
            w.writerow([name, row.get("name") or row.get("association_id"), row.get("status", ""),
                        json.dumps({k: v for k, v in row.items() if k not in ("name", "status")})])
    return buf.getvalue()


def save_report(report, directory, stem):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (directory / f"{stem}.csv").write_text(report_to_csv(report), encoding="utf-8")
    return json_path
