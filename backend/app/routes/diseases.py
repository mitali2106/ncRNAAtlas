"""Disease endpoints."""
from flask import Blueprint, request
from sqlalchemy import func, select

from ..api_utils import APIError, get_choice, get_str, ok, paginate, pagination_params
from ..extensions import db
from ..models import Association, AssociationGene, AssociationPublication, Disease, NcRNA, Publication
from ..schemas import serializers as ser
from ..services import queries
from .ncrnas import _association_page

bp = Blueprint("diseases", __name__)

SORTS = {"name": func.lower(Disease.canonical_name), "id": Disease.id}


def get_disease_or_404(disease_id):
    d = db.session.get(Disease, disease_id)
    if d is None:
        raise APIError(404, f"Disease {disease_id} not found")
    return d


@bp.get("/diseases")
def list_diseases():
    page, per_page = pagination_params()
    q = get_str("q")
    resolution = get_choice("resolution_status", {"resolved", "ambiguous", "unresolved"})
    sort = get_choice("sort", set(SORTS) | {"associations"}, "associations")
    order = get_choice("order", {"asc", "desc"}, "desc" if sort == "associations" else "asc")
    assoc_count = (select(func.count(Association.id)).where(Association.disease_id == Disease.id)
                   .correlate(Disease).scalar_subquery())
    stmt = select(Disease)
    if q:
        stmt = stmt.where(Disease.id.in_(queries.search_diseases(q, limit=None).with_only_columns(Disease.id)
                                         .order_by(None)))
    if resolution:
        stmt = stmt.where(Disease.resolution_status == resolution)
    key = assoc_count if sort == "associations" else SORTS[sort]
    stmt = stmt.order_by(key.desc() if order == "desc" else key.asc(), Disease.id)
    items, meta = paginate(stmt, page, per_page)
    counts = queries.association_counts(Association.disease_id, [d.id for d in items])
    return ok([{**ser.disease_summary(d), "association_count": counts[d.id]} for d in items], pagination=meta,
              filters={"q": q, "resolution_status": resolution, "sort": sort, "order": order})


@bp.get("/diseases/<int:disease_id>")
def disease_detail(disease_id):
    d = get_disease_or_404(disease_id)
    data = ser.disease_detail(d)
    by_type = dict(db.session.execute(
        select(NcRNA.ncrna_type, func.count(func.distinct(NcRNA.id))).join(Association)
        .where(Association.disease_id == d.id).group_by(NcRNA.ncrna_type)
    ).all())
    evidence = dict(db.session.execute(
        select(Association.evidence_level, func.count(Association.id)).where(Association.disease_id == d.id)
        .group_by(Association.evidence_level)
    ).all())
    data["counts"] = {
        "associations": sum(evidence.values()),
        "mirnas": by_type.get("miRNA", 0),
        "lncrnas": by_type.get("lncRNA", 0),
        "publications": db.session.execute(
            select(func.count(func.distinct(AssociationPublication.publication_id))).join(Association)
            .where(Association.disease_id == d.id)).scalar(),
        "evidence_levels": evidence,
    }
    return ok(data)


@bp.get("/diseases/<int:disease_id>/associations")
def disease_associations(disease_id):
    get_disease_or_404(disease_id)
    args = dict(request.args)
    args["disease_id"] = disease_id
    args.setdefault("organism", "all")
    return _association_page(args)


@bp.get("/diseases/<int:disease_id>/genes")
def disease_genes(disease_id):
    d = get_disease_or_404(disease_id)
    links = db.session.execute(
        select(AssociationGene).join(Association).where(Association.disease_id == d.id)
        .order_by(AssociationGene.gene_relationship, AssociationGene.id)
    ).scalars().all()
    return ok([{**ser.association_gene(l), "association_id": l.association_id,
                "ncrna": ser.ncrna_summary(l.association.ncrna)} for l in links],
              notes="Only genes named by a source record for an association with this disease are listed.")


@bp.get("/diseases/<int:disease_id>/pathways")
def disease_pathways(disease_id):
    d = get_disease_or_404(disease_id)
    gene_ids = queries.disease_gene_ids(d.id)
    return ok({
        "pathways": queries.pathways_for_genes(gene_ids, basis="Genes linked to this disease's associations"),
        "genes_without_mapping": queries.genes_without_mapping(gene_ids),
        "gene_count": len(gene_ids),
        "notes": "Pathways are inferred through genes linked to this disease's ncRNA associations.",
    })


@bp.get("/diseases/<int:disease_id>/publications")
def disease_publications(disease_id):
    d = get_disease_or_404(disease_id)
    page, per_page = pagination_params()
    stmt = (select(Publication).join(AssociationPublication).join(Association)
            .where(Association.disease_id == d.id).distinct()
            .order_by(Publication.publication_year.desc().nulls_last(), Publication.id))
    items, meta = paginate(stmt, page, per_page)
    return ok([ser.publication(p) for p in items], pagination=meta)
