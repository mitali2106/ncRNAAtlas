"""Literature-review workflow for ncRNA–disease associations.

1. ``triage_association`` gathers the association's publications, fetches
   missing PubMed metadata (if allowed) and records *hints* — whether the
   title/abstract mentions the ncRNA and the disease. Hints are stored as an
   ``automated_triage`` review and never change the validation status, because
   keyword co-occurrence is not proof of an association.
2. A curator records one ``curator`` review per publication with an explicit
   outcome (see ``REVIEW_OUTCOMES``).
3. ``derive_validation_status`` turns curator reviews into the association's
   validation status. ``curator_confirmed`` requires at least one review
   reporting direct experimental support and none reporting non-support.
"""
import re

from ..extensions import db
from ..models import Alias, Association, LiteratureReview, utcnow
from ..models.constants import REVIEW_OUTCOMES
from .publications import enrich_publications


class ReviewError(ValueError):
    pass


def derive_validation_status(reviews):
    outcomes = [r.outcome for r in reviews if r.review_type == "curator" and r.outcome]
    if not outcomes:
        queued = any(r.review_type == "automated_triage" for r in reviews)
        return "under_review" if queued else "not_reviewed"
    s = set(outcomes)
    direct = "supports_direct_experimental" in s
    negative = "does_not_support" in s
    if "conflicting" in s or (direct and negative):
        return "conflicting"
    if direct:
        return "curator_confirmed"
    if s == {"does_not_support"}:
        return "curator_rejected"
    return "insufficient_evidence"


def record_review(association, outcome, pmid=None, evidence_type=None, notes=None, reviewer=None):
    if outcome not in REVIEW_OUTCOMES:
        raise ReviewError(f"outcome must be one of: {', '.join(REVIEW_OUTCOMES)}")
    if not reviewer:
        raise ReviewError("reviewer is required for curator reviews")
    cited = {link.publication.pmid for link in association.publication_links}
    if pmid and pmid not in cited:
        raise ReviewError(f"PMID {pmid} is not linked to this association")
    review = LiteratureReview(
        association=association, pmid=pmid, review_type="curator", outcome=outcome,
        evidence_type=evidence_type, notes=notes, reviewer=reviewer, reviewed_at=utcnow(),
    )
    db.session.add(review)
    db.session.flush()
    association.validation_status = derive_validation_status(association.reviews)
    association.last_verified_at = utcnow()
    return review


def _name_variants(association):
    ncrna = association.ncrna
    names = {ncrna.canonical_name}
    names |= {
        a.alias for a in Alias.query.filter_by(entity_type="ncrna", entity_id=ncrna.id)
        if a.alias_type != "identifier"
    }
    variants = set()
    for n in names:
        variants.add(n.lower())
        m = re.match(r"^[a-z]{3}-(mir|let)-(.+)$", n.lower())
        if m:  # hsa-mir-21 -> "mir-21", "microrna-21", "mir21"
            stem = m.group(2).rsplit("-", 1)[0] if re.search(r"[a-z]-\d+$", m.group(2)) else m.group(2)
            for core in {m.group(2), stem}:
                variants |= {f"{m.group(1)}-{core}", f"{m.group(1)}{core}", f"microrna-{core}", f"microrna {core}"}
    return {v for v in variants if len(v) >= 3}


def _disease_variants(association):
    d = association.disease
    names = {d.canonical_name}
    names |= {
        a.alias for a in Alias.query.filter_by(entity_type="disease", entity_id=d.id)
        if a.alias_type != "identifier"
    }
    out = set()
    for n in names:
        n = n.lower()
        out.add(n)
        if ", " in n:  # MeSH inverted headings: "carcinoma, hepatocellular" -> "hepatocellular carcinoma"
            head, tail = n.split(", ", 1)
            out.add(f"{tail} {head}")
    return out


def _mentions(text, variants):
    text = (text or "").lower()
    return sorted(v for v in variants if re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", text))


def triage_association(association, pubmed_service=None):
    """Create automated triage hints for each linked publication."""
    pubs = [link.publication for link in association.publication_links]
    if pubmed_service is not None:
        enrich_publications(pubs, pubmed_service)
    ncrna_v, disease_v = _name_variants(association), _disease_variants(association)
    created = []
    for pub in pubs:
        text = " ".join(filter(None, [pub.publication_title, pub.abstract]))
        flags = {
            "metadata_available": pub.metadata_status == "fetched",
            "has_abstract": bool(pub.abstract),
            "ncrna_mentions": _mentions(text, ncrna_v),
            "disease_mentions": _mentions(text, disease_v),
        }
        flags["needs_manual_assessment"] = not (flags["ncrna_mentions"] and flags["disease_mentions"])
        flags["disclaimer"] = "Keyword mentions are triage hints only, not evidence of an association."
        LiteratureReview.query.filter_by(
            association_id=association.id, pmid=pub.pmid, review_type="automated_triage"
        ).delete()
        review = LiteratureReview(association=association, pmid=pub.pmid, review_type="automated_triage",
                                  flags=flags, reviewer="automated", reviewed_at=utcnow())
        db.session.add(review)
        created.append(review)
    db.session.flush()
    association.validation_status = derive_validation_status(association.reviews)
    return created


def review_queue(limit=50):
    """Associations awaiting curator review, most-cited first."""
    return (
        Association.query.filter(Association.validation_status.in_(["not_reviewed", "under_review"]))
        .order_by(Association.id)
        .limit(limit)
        .all()
    )
