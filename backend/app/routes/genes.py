"""Gene endpoints. Direct association links and general ncRNA targets are kept apart."""
from flask import Blueprint
from sqlalchemy import func, select

from ..api_utils import APIError, get_str, ok, paginate, pagination_params
from ..extensions import db
from ..models import Association, AssociationGene, Gene, GenePathway, NcRNAGeneInteraction, Pathway
from ..schemas import serializers as ser
from ..services import queries

bp = Blueprint("genes", __name__)


def get_gene_or_404(gene_id):
    g = db.session.get(Gene, gene_id)
    if g is None:
        raise APIError(404, f"Gene {gene_id} not found")
    return g


@bp.get("/genes")
def list_genes():
    page, per_page = pagination_params()
    q = get_str("q")
    n_rel = (select(func.count(NcRNAGeneInteraction.id)).where(NcRNAGeneInteraction.gene_id == Gene.id)
             .correlate(Gene).scalar_subquery())
    stmt = select(Gene)
    if q:
        stmt = stmt.where(Gene.id.in_(queries.search_genes(q, limit=None).with_only_columns(Gene.id).order_by(None)))
    items, meta = paginate(stmt.order_by(n_rel.desc(), Gene.approved_gene_symbol, Gene.id), page, per_page)
    ids = [g.id for g in items]
    rel_counts = dict(db.session.execute(
        select(NcRNAGeneInteraction.gene_id, func.count(func.distinct(NcRNAGeneInteraction.ncrna_id)))
        .where(NcRNAGeneInteraction.gene_id.in_(ids)).group_by(NcRNAGeneInteraction.gene_id)).all()) if ids else {}
    pw_counts = dict(db.session.execute(
        select(GenePathway.gene_id, func.count(GenePathway.pathway_id)).where(GenePathway.gene_id.in_(ids))
        .group_by(GenePathway.gene_id)).all()) if ids else {}
    return ok([{**ser.gene_summary(g), "ncrna_count": rel_counts.get(g.id, 0), "pathway_count": pw_counts.get(g.id, 0)}
               for g in items], pagination=meta, filters={"q": q})


@bp.get("/genes/<int:gene_id>")
def gene_detail(gene_id):
    g = get_gene_or_404(gene_id)
    data = ser.gene_detail(g)
    interactions = db.session.execute(
        select(NcRNAGeneInteraction).where(NcRNAGeneInteraction.gene_id == g.id)
        .order_by(NcRNAGeneInteraction.relationship, NcRNAGeneInteraction.id)
    ).scalars().all()
    data["ncrna_relationships"] = [ser.interaction(i, include_ncrna=True, include_gene=False) for i in interactions]
    return ok(data)


@bp.get("/genes/<int:gene_id>/associations")
def gene_associations(gene_id):
    g = get_gene_or_404(gene_id)
    page, per_page = pagination_params()
    direct = db.session.execute(
        select(AssociationGene).where(AssociationGene.gene_id == g.id).order_by(AssociationGene.association_id)
    ).scalars().all()
    direct_data = [{**ser.association_gene(l), "association": ser.association_summary(l.association)}
                   for l in direct]
    f = {"target_gene_id": g.id, "organism": "all"}
    items, meta = paginate(queries.association_select(f, "publications", "desc"), page, per_page)
    return ok({
        "direct": direct_data,
        "via_ncrna_relationships": [ser.association_summary(a) for a in items],
    }, pagination=meta, notes=(
        "'direct': a source record names this gene for that specific association. "
        "'via_ncrna_relationships': diseases associated with ncRNAs that have a stored relationship to this "
        "gene — an indirect connection, not evidence that the gene is involved in the disease."))


@bp.get("/genes/<int:gene_id>/pathways")
def gene_pathways(gene_id):
    g = get_gene_or_404(gene_id)
    rows = db.session.execute(
        select(Pathway, GenePathway).join(GenePathway).where(GenePathway.gene_id == g.id)
        .order_by(Pathway.pathway_identifier)
    ).all()
    data = []
    for p, link in rows:
        item = ser.pathway(p)
        item.update({"mapping_type": "direct", "mapping_source": link.mapping_source,
                     "source_gene_identifier": link.source_gene_identifier,
                     "mapped_at": ser.iso(link.mapping_timestamp)})
        data.append(item)
    status = "mapped" if data else ("not_mappable" if not g.stable_gene_identifier else "no_mapping_available")
    return ok(data, mapping_status=status)
