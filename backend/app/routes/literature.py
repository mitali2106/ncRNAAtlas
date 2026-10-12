"""Publication and literature-search endpoints."""
import re

from flask import Blueprint, current_app
from sqlalchemy import select

from ..api_utils import (
    APIError,
    external_error,
    get_int,
    get_str,
    ok,
    pubmed_service,
    rate_limited,
    require_external,
)
from ..extensions import db
from ..models import Association, AssociationPublication, Publication
from ..schemas import serializers as ser
from ..services.http_client import ExternalServiceError
from ..services.pubmed import pubmed_url
from ..validation.publications import apply_metadata

bp = Blueprint("literature", __name__)
PMID_RE = re.compile(r"^\d{1,9}$")


@bp.get("/publications/<pmid>")
@rate_limited("pubmed")
def publication_detail(pmid):
    if not PMID_RE.match(pmid) or int(pmid) == 0:
        raise APIError(400, "PMID must be a positive integer")
    pub = db.session.execute(select(Publication).filter_by(pmid=pmid)).scalars().first()
    refresh = get_str("refresh") == "true"
    external_note = None
    if pub is None or pub.metadata_status != "fetched" or refresh:
        if pub is None:
            require_external("PubMed")  # nothing stored locally to fall back to
        if current_app.config["EXTERNAL_LOOKUPS_ENABLED"]:
            try:
                meta = pubmed_service().fetch([pmid]).get(pmid)
            except ExternalServiceError as exc:
                if pub is None:
                    raise external_error(exc)
                # Serve the stored record; metadata_status explains what is missing.
                external_note = f"PubMed unavailable: {exc.message}. Showing locally stored record."
            else:
                if meta is None:
                    if pub is None:
                        raise APIError(404, f"PMID {pmid} was not found in PubMed")
                    pub.metadata_status = "not_found"
                else:
                    if pub is None:
                        pub = Publication(pmid=pmid, publication_url=pubmed_url(pmid))
                        db.session.add(pub)
                    apply_metadata(pub, meta)
                db.session.commit()
        else:
            external_note = "External lookups are disabled; showing locally stored record."
    links = db.session.execute(
        select(AssociationPublication).where(AssociationPublication.publication_id == pub.id)
    ).scalars().all()
    data = ser.publication(pub)
    data["associations"] = [{
        **ser.association_summary(l.association), "cited_by_sources": l.source_databases.split("; "),
    } for l in links]
    return ok(data, external_note=external_note)


@bp.get("/literature/search")
@rate_limited("pubmed")
def literature_search():
    q = get_str("q", max_length=300)
    if not q or len(q) < 2:
        raise APIError(400, "Query parameter 'q' (at least 2 characters) is required")
    retmax = get_int("limit", 20, 1, 50)
    start = get_int("offset", 0, 0, 9999)
    require_external("PubMed")
    try:
        result = pubmed_service().search(q, retmax=retmax, retstart=start)
    except ExternalServiceError as exc:
        raise external_error(exc)
    stored = {
        p.pmid: p.id for p in db.session.execute(
            select(Publication).where(Publication.pmid.in_([r["pmid"] for r in result["results"]]))).scalars()
    }
    linked = set(db.session.execute(
        select(AssociationPublication.publication_id).where(AssociationPublication.publication_id.in_(stored.values()))
    ).scalars()) if stored else set()
    for r in result["results"]:
        r["linked_to_associations"] = stored.get(r["pmid"]) in linked
    return ok(result["results"], total=result["count"], offset=start, query=q,
              notes="PubMed search results are bibliographic hits only. A hit mentioning an ncRNA and a disease "
                    "is not evidence of an association.")
