"""Association endpoints."""
from flask import Blueprint, request
from sqlalchemy import select

from ..api_utils import APIError, ok
from ..extensions import db
from ..models import Association, AssociationSource, LiteratureReview
from ..schemas import serializers as ser
from ..services import queries
from .ncrnas import _association_page

bp = Blueprint("associations", __name__)


def get_association_or_404(association_id):
    a = db.session.get(Association, association_id)
    if a is None:
        raise APIError(404, f"Association {association_id} not found")
    return a


@bp.get("/associations")
def list_associations():
    return _association_page(dict(request.args))


@bp.get("/associations/<int:association_id>")
def association_detail(association_id):
    a = get_association_or_404(association_id)
    data = ser.association_summary(a)
    data.update({
        "ncrna": ser.ncrna_summary(a.ncrna),
        "disease": ser.disease_summary(a.disease),
        "experimental_evidence_summary": a.experimental_evidence_summary,
        "first_reported_date": a.first_reported_date.isoformat() if a.first_reported_date else None,
        "last_verified_at": ser.iso(a.last_verified_at),
        "created_at": ser.iso(a.created_at),
        "updated_at": ser.iso(a.updated_at),
        "genes": [ser.association_gene(l) for l in a.gene_links],
        "ncrna_gene_relationships": [ser.interaction(i) for i in a.ncrna.gene_interactions[:50]],
        "reviews": [ser.review(r) for r in sorted(a.reviews, key=lambda r: r.reviewed_at, reverse=True)],
    })
    years = [l.publication.publication_year for l in a.publication_links if l.publication.publication_year]
    data["earliest_publication_year"] = min(years) if years else None
    gene_ids = {l.gene_id for l in a.gene_links}
    data["pathways"] = queries.pathways_for_genes(gene_ids, basis="Genes linked to this association by a source record")
    data["pathway_note"] = ("Pathways are inferred from genes linked to this specific association. "
                            "General ncRNA targets are listed separately and do not contribute.")
    return ok(data)


@bp.get("/associations/<int:association_id>/publications")
def association_publications(association_id):
    a = get_association_or_404(association_id)
    links = sorted(a.publication_links, key=lambda l: (-(l.publication.publication_year or 0), l.publication.pmid))
    return ok([ser.publication(l.publication, link=l) for l in links])


@bp.get("/associations/<int:association_id>/sources")
def association_sources(association_id):
    a = get_association_or_404(association_id)
    rows = db.session.execute(
        select(AssociationSource).where(AssociationSource.association_id == a.id).order_by(AssociationSource.id)
    ).scalars().all()
    return ok([ser.source_record(s) for s in rows])


@bp.get("/associations/<int:association_id>/reviews")
def association_reviews(association_id):
    a = get_association_or_404(association_id)
    rows = db.session.execute(
        select(LiteratureReview).where(LiteratureReview.association_id == a.id)
        .order_by(LiteratureReview.reviewed_at.desc(), LiteratureReview.id.desc())
    ).scalars().all()
    return ok([ser.review(r) for r in rows], validation_status=a.validation_status)
