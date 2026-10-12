"""ncRNA endpoints."""
from flask import Blueprint, request
from sqlalchemy import func, select

from ..api_utils import APIError, get_choice, get_str, ok, paginate, pagination_params
from ..extensions import db
from ..models import Association, AssociationPublication, NcRNA, NcRNAGeneInteraction, Publication
from ..models.constants import HUMAN, NCRNA_TYPES
from ..schemas import serializers as ser
from ..services import queries

bp = Blueprint("ncrnas", __name__)

SORTS = {"name": func.lower(NcRNA.canonical_name), "id": NcRNA.id, "type": NcRNA.ncrna_type}


def get_ncrna_or_404(ncrna_id):
    n = db.session.get(NcRNA, ncrna_id)
    if n is None:
        raise APIError(404, f"ncRNA {ncrna_id} not found")
    return n


@bp.get("/ncrnas")
def list_ncrnas():
    page, per_page = pagination_params()
    q = get_str("q")
    ncrna_type = get_choice("type", NCRNA_TYPES) or get_choice("ncrna_type", NCRNA_TYPES)
    organism = get_str("organism", HUMAN)
    resolution = get_choice("resolution_status", {"resolved", "ambiguous", "unresolved", "not_attempted"})
    sort = get_choice("sort", set(SORTS) | {"associations"}, "associations")
    order = get_choice("order", {"asc", "desc"}, "desc" if sort == "associations" else "asc")

    assoc_count = (select(func.count(Association.id)).where(Association.ncrna_id == NcRNA.id)
                   .correlate(NcRNA).scalar_subquery())
    stmt = select(NcRNA)
    if q:
        stmt = stmt.where(NcRNA.id.in_(queries.search_ncrnas(q, limit=None).with_only_columns(NcRNA.id).order_by(None)))
    if ncrna_type:
        stmt = stmt.where(NcRNA.ncrna_type == ncrna_type)
    clause = queries.organism_clause(NcRNA.organism, organism)
    if clause is not None:
        stmt = stmt.where(clause)
    if resolution:
        stmt = stmt.where(NcRNA.resolution_status == resolution)
    key = assoc_count if sort == "associations" else SORTS[sort]
    stmt = stmt.order_by(key.desc() if order == "desc" else key.asc(), NcRNA.id)
    items, meta = paginate(stmt, page, per_page)
    counts = queries.association_counts(Association.ncrna_id, [n.id for n in items])
    data = [{**ser.ncrna_summary(n), "association_count": counts[n.id]} for n in items]
    return ok(data, pagination=meta, filters={"q": q, "type": ncrna_type, "organism": organism,
                                              "resolution_status": resolution, "sort": sort, "order": order})


@bp.get("/ncrnas/<int:ncrna_id>")
def ncrna_detail(ncrna_id):
    n = get_ncrna_or_404(ncrna_id)
    data = ser.ncrna_detail(n)
    data["counts"] = {
        "associations": db.session.execute(
            select(func.count(Association.id)).where(Association.ncrna_id == n.id)).scalar(),
        "diseases": db.session.execute(
            select(func.count(func.distinct(Association.disease_id))).where(Association.ncrna_id == n.id)).scalar(),
        "gene_relationships": db.session.execute(
            select(func.count(NcRNAGeneInteraction.id)).where(NcRNAGeneInteraction.ncrna_id == n.id)).scalar(),
        "publications": db.session.execute(
            select(func.count(func.distinct(AssociationPublication.publication_id))).join(Association)
            .where(Association.ncrna_id == n.id)).scalar(),
    }
    return ok(data)


@bp.get("/ncrnas/<int:ncrna_id>/associations")
def ncrna_associations(ncrna_id):
    get_ncrna_or_404(ncrna_id)
    args = dict(request.args)
    args["ncrna_id"] = ncrna_id
    args.setdefault("organism", "all")
    return _association_page(args)


def _association_page(args):
    page, per_page = pagination_params()
    f = queries.association_filters(args)
    sort = get_choice("sort", set(queries.ASSOCIATION_SORTS) | {"publications"}, "publications")
    order = get_choice("order", {"asc", "desc"}, "desc" if sort == "publications" else "asc")
    items, meta = paginate(queries.association_select(f, sort, order), page, per_page)
    return ok([ser.association_summary(a) for a in items], pagination=meta,
              filters={k: v for k, v in f.items()}, sort={"by": sort, "order": order})


@bp.get("/ncrnas/<int:ncrna_id>/genes")
def ncrna_genes(ncrna_id):
    n = get_ncrna_or_404(ncrna_id)
    page, per_page = pagination_params()
    relationship = get_str("relationship")
    stmt = select(NcRNAGeneInteraction).where(NcRNAGeneInteraction.ncrna_id == n.id)
    if relationship:
        stmt = stmt.where(NcRNAGeneInteraction.relationship == relationship)
    items, meta = paginate(stmt.order_by(NcRNAGeneInteraction.relationship, NcRNAGeneInteraction.id), page, per_page)
    general = [ser.interaction(i) for i in items]
    # Genes linked to this ncRNA within a specific disease association.
    links = db.session.execute(
        select(Association).where(Association.ncrna_id == n.id)
    ).scalars().all()
    association_links = []
    for a in links:
        for link in a.gene_links:
            association_links.append({**ser.association_gene(link), "association_id": a.id,
                                      "disease": ser.disease_summary(a.disease)})
    return ok({"interactions": general, "association_gene_links": association_links}, pagination=meta,
              notes="'interactions' are general ncRNA–gene relationships (not disease-specific); "
                    "'association_gene_links' are genes named by a source record for a specific association.")


@bp.get("/ncrnas/<int:ncrna_id>/pathways")
def ncrna_pathways(ncrna_id):
    n = get_ncrna_or_404(ncrna_id)
    gene_ids = queries.ncrna_gene_ids(n.id)
    return ok({
        "pathways": queries.pathways_for_genes(gene_ids, basis="Genes with a stored relationship to this ncRNA"),
        "genes_without_mapping": queries.genes_without_mapping(gene_ids),
        "gene_count": len(gene_ids),
        "notes": "Pathways are inferred through related genes; KEGG does not link ncRNAs to these pathways directly.",
    })


@bp.get("/ncrnas/<int:ncrna_id>/publications")
def ncrna_publications(ncrna_id):
    n = get_ncrna_or_404(ncrna_id)
    page, per_page = pagination_params()
    stmt = (select(Publication).join(AssociationPublication).join(Association)
            .where(Association.ncrna_id == n.id).distinct()
            .order_by(Publication.publication_year.desc().nulls_last(), Publication.id))
    items, meta = paginate(stmt, page, per_page)
    return ok([ser.publication(p) for p in items], pagination=meta)
