"""Publication metadata enrichment (PubMed), shared by scripts, API and review workflow."""
import logging

from ..models import Publication, utcnow
from ..services.http_client import ExternalServiceError

log = logging.getLogger(__name__)

METADATA_FIELDS = ("publication_title", "abstract", "journal", "publication_year", "authors", "doi")


def apply_metadata(pub, meta):
    for key in METADATA_FIELDS:
        value = meta.get(key)
        if value is not None:
            if key == "publication_year":
                value = int(value)
            setattr(pub, key, value)
    pub.metadata_status = "fetched"
    pub.fetched_at = utcnow()


def enrich_publications(publications, pubmed_service, only_pending=True):
    """Fetch PubMed metadata for publications. Returns ``(fetched, not_found, error)``."""
    targets = [p for p in publications if not only_pending or p.metadata_status != "fetched"]
    if not targets:
        return 0, 0, None
    try:
        found = pubmed_service.fetch([p.pmid for p in targets])
    except ExternalServiceError as exc:
        log.warning("PubMed enrichment failed: %s", exc.message)
        for p in targets:
            if p.metadata_status == "pending":
                p.metadata_status = "error"
        return 0, 0, exc.message
    fetched = not_found = 0
    for p in targets:
        if p.pmid in found:
            apply_metadata(p, found[p.pmid])
            fetched += 1
        else:
            p.metadata_status = "not_found"
            not_found += 1
    return fetched, not_found, None


def pending_publications(limit=None):
    q = Publication.query.filter(Publication.metadata_status.in_(["pending", "error"])).order_by(Publication.id)
    return q.limit(limit).all() if limit else q.all()
