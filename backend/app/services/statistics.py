"""Dataset statistics computed live from the database (never hard-coded).

Synthetic demonstration records (``is_synthetic``) are excluded from every
scientific count and reported separately.
"""
from sqlalchemy import distinct, func, select

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
    Publication,
)
from ..models.constants import HUMAN


def _scalar(stmt):
    return db.session.execute(stmt).scalar() or 0


def compute_statistics(top_n=10):
    real_assoc = Association.is_synthetic.is_(False)
    human_assoc = select(Association.id).join(NcRNA).where(real_assoc, NcRNA.organism == HUMAN)

    totals = {
        "ncrnas": _scalar(select(func.count(NcRNA.id)).where(NcRNA.is_synthetic.is_(False))),
        "associations": _scalar(select(func.count(Association.id)).where(real_assoc)),
        "human_associations": _scalar(select(func.count()).select_from(human_assoc.subquery())),
        "diseases": _scalar(select(func.count(Disease.id)).where(Disease.is_synthetic.is_(False))),
        "genes": _scalar(select(func.count(Gene.id)).where(Gene.is_synthetic.is_(False))),
        "ncrna_gene_interactions": _scalar(
            select(func.count(NcRNAGeneInteraction.id)).where(NcRNAGeneInteraction.is_synthetic.is_(False))),
        "publications": _scalar(select(func.count(distinct(AssociationPublication.publication_id)))
                                .join(Association).where(real_assoc)),
        # Same population as "publications": PMIDs cited by (non-synthetic) associations.
        "publications_with_metadata": _scalar(
            select(func.count(distinct(AssociationPublication.publication_id)))
            .join(Association).join(Publication, Publication.id == AssociationPublication.publication_id)
            .where(real_assoc, Publication.metadata_status == "fetched")),
        "mapped_pathways": _scalar(select(func.count(distinct(GenePathway.pathway_id)))),
        "genes_with_pathway_mapping": _scalar(select(func.count(distinct(GenePathway.gene_id)))),
    }

    def grouped(column, where=None, join=None):
        stmt = select(column, func.count(Association.id)).select_from(Association)
        if join is not None:
            stmt = stmt.join(join)
        stmt = stmt.where(real_assoc)
        if where is not None:
            stmt = stmt.where(where)
        return {k or "unspecified": v for k, v in db.session.execute(stmt.group_by(column)).all()}

    type_dist = {k: v for k, v in db.session.execute(
        select(NcRNA.ncrna_type, func.count(NcRNA.id)).where(NcRNA.is_synthetic.is_(False)).group_by(NcRNA.ncrna_type)
    ).all()}
    assoc_by_rna_type = grouped(NcRNA.ncrna_type, join=NcRNA)

    top_diseases = db.session.execute(
        select(Disease.id, Disease.canonical_name, func.count(Association.id).label("n"))
        .join(Association, Association.disease_id == Disease.id).join(NcRNA, Association.ncrna_id == NcRNA.id)
        .where(real_assoc, NcRNA.organism == HUMAN)
        .group_by(Disease.id, Disease.canonical_name).order_by(func.count(Association.id).desc(), Disease.id)
        .limit(top_n)
    ).all()
    top_ncrnas = db.session.execute(
        select(NcRNA.id, NcRNA.canonical_name, NcRNA.ncrna_type, func.count(Association.id).label("n"))
        .join(Association, Association.ncrna_id == NcRNA.id)
        .where(real_assoc, NcRNA.organism == HUMAN)
        .group_by(NcRNA.id, NcRNA.canonical_name, NcRNA.ncrna_type)
        .order_by(func.count(Association.id).desc(), NcRNA.id).limit(top_n)
    ).all()
    source_dist = {k: v for k, v in db.session.execute(
        select(AssociationSource.source_database, func.count(distinct(AssociationSource.association_id)))
        .join(Association).where(real_assoc).group_by(AssociationSource.source_database)
    ).all()}
    recent_imports = db.session.execute(
        select(ImportJob).where(ImportJob.status.in_(["completed", "completed_with_errors"]))
        .order_by(ImportJob.completed_at.desc(), ImportJob.id.desc()).limit(5)
    ).scalars().all()
    synthetic = {
        "associations": _scalar(select(func.count(Association.id)).where(Association.is_synthetic.is_(True))),
        "ncrnas": _scalar(select(func.count(NcRNA.id)).where(NcRNA.is_synthetic.is_(True))),
    }
    dataset_labels = sorted({j.dataset_label for j in db.session.execute(
        select(ImportJob).where(ImportJob.status.like("completed%"))).scalars()})

    from ..schemas.serializers import import_job

    return {
        "totals": totals,
        "is_empty": totals["associations"] == 0 and totals["ncrnas"] == 0,
        "dataset_labels": dataset_labels,
        "ncrna_type_distribution": type_dist,
        "associations_by_ncrna_type": assoc_by_rna_type,
        "evidence_level_distribution": grouped(Association.evidence_level),
        "validation_status_distribution": grouped(Association.validation_status),
        "association_type_distribution": grouped(Association.association_type),
        "organism_distribution": grouped(NcRNA.organism, join=NcRNA),
        "source_distribution": source_dist,
        "top_diseases": [{"id": r[0], "canonical_name": r[1], "association_count": r[2]} for r in top_diseases],
        "top_ncrnas": [{"id": r[0], "canonical_name": r[1], "ncrna_type": r[2], "association_count": r[3]}
                       for r in top_ncrnas],
        "recent_imports": [import_job(j) for j in recent_imports],
        "synthetic_records_excluded": synthetic,
        "scope_note": "Top diseases and ncRNAs count human associations only. Synthetic records are excluded.",
    }
