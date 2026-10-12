"""KEGG pathway endpoints."""
from flask import Blueprint
from sqlalchemy import func, select

from ..api_utils import APIError, get_str, ok, paginate, pagination_params
from ..extensions import db
from ..models import Association, AssociationGene, Gene, GenePathway, NcRNA, NcRNAGeneInteraction, Pathway
from ..normalization.text import like_escape
from ..schemas import serializers as ser

bp = Blueprint("pathways", __name__)


@bp.get("/pathways")
def list_pathways():
    page, per_page = pagination_params()
    q = get_str("q")
    gene_count = (select(func.count(GenePathway.gene_id)).where(GenePathway.pathway_id == Pathway.id)
                  .correlate(Pathway).scalar_subquery())
    stmt = select(Pathway, gene_count.label("n")).where(gene_count > 0)
    if q:
        pattern = f"%{like_escape(q.lower())}%"
        stmt = stmt.where(func.lower(Pathway.pathway_name).like(pattern, escape="\\")
                          | func.lower(Pathway.pathway_identifier).like(pattern, escape="\\"))
    stmt = stmt.order_by(gene_count.desc(), Pathway.pathway_identifier)
    total = db.session.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.session.execute(stmt.limit(per_page).offset((page - 1) * per_page)).all()
    meta = {"page": page, "per_page": per_page, "total": total, "pages": -(-total // per_page) if total else 0}
    return ok([ser.pathway(p, gene_count=n) for p, n in rows], pagination=meta, filters={"q": q})


@bp.get("/pathways/<int:pathway_id>")
def pathway_detail(pathway_id):
    p = db.session.get(Pathway, pathway_id)
    if p is None:
        raise APIError(404, f"Pathway {pathway_id} not found")
    links = db.session.execute(
        select(GenePathway, Gene).join(Gene).where(GenePathway.pathway_id == p.id).order_by(Gene.approved_gene_symbol)
    ).all()
    gene_ids = [g.id for _, g in links]
    data = ser.pathway(p, gene_count=len(links))
    data["genes"] = [{**ser.gene_summary(g), "mapping_source": gp.mapping_source,
                      "mapped_at": ser.iso(gp.mapping_timestamp)} for gp, g in links]
    related = []
    if gene_ids:
        rows = db.session.execute(
            select(AssociationGene).where(AssociationGene.gene_id.in_(gene_ids)).order_by(AssociationGene.association_id)
        ).scalars().all()
        for l in rows:
            related.append({**ser.association_summary(l.association), "via_gene": l.gene.approved_gene_symbol,
                            "gene_relationship": l.gene_relationship})
        ncrnas = db.session.execute(
            select(NcRNA, Gene.approved_gene_symbol, NcRNAGeneInteraction.relationship)
            .join(NcRNAGeneInteraction, NcRNAGeneInteraction.ncrna_id == NcRNA.id)
            .join(Gene, Gene.id == NcRNAGeneInteraction.gene_id)
            .where(NcRNAGeneInteraction.gene_id.in_(gene_ids)).distinct()
            .order_by(NcRNA.canonical_name)
        ).all()
    else:
        ncrnas = []
    data["related_associations"] = related
    data["related_ncrnas"] = [{**ser.ncrna_summary(n), "via_gene": sym, "relationship": rel} for n, sym, rel in ncrnas]
    data["notes"] = ("Gene membership is as reported by KEGG. Related associations/ncRNAs are connected through "
                     "member genes and are not pathway assignments made by KEGG.")
    return ok(data)
