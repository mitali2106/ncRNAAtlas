"""Health, statistics, sources, vocabularies and import-job endpoints."""
from flask import Blueprint, current_app
from sqlalchemy import select, text

from ..api_utils import APIError, get_choice, ok, paginate, pagination_params
from ..extensions import db
from ..models import ImportJob
from ..models.constants import (
    ASSOCIATION_TYPES,
    EVIDENCE_LEVELS,
    GENE_RELATIONSHIPS,
    IMPORT_STATUSES,
    NCRNA_TYPES,
    REVIEW_OUTCOMES,
    VALIDATION_STATUSES,
)
from ..schemas.serializers import import_job
from ..services.sources import sources_with_status
from ..services.statistics import compute_statistics

bp = Blueprint("meta", __name__)


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    dialect = db.engine.dialect.name
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": {"connected": db_ok, "dialect": dialect},
        "external_lookups_enabled": current_app.config["EXTERNAL_LOOKUPS_ENABLED"],
        "admin_enabled": bool(current_app.config["ADMIN_TOKEN"]),
    }
    return ok(body), 200 if db_ok else 503


@bp.get("/statistics")
def statistics():
    return ok(compute_statistics())


@bp.get("/sources")
def sources():
    return ok(sources_with_status())


@bp.get("/vocabularies")
def vocabularies():
    return ok({
        "ncrna_types": list(NCRNA_TYPES),
        "evidence_levels": EVIDENCE_LEVELS,
        "validation_statuses": VALIDATION_STATUSES,
        "association_types": ASSOCIATION_TYPES,
        "gene_relationships": GENE_RELATIONSHIPS,
        "review_outcomes": REVIEW_OUTCOMES,
    })


@bp.get("/import-jobs")
def import_jobs():
    page, per_page = pagination_params()
    status = get_choice("status", IMPORT_STATUSES)
    stmt = select(ImportJob)
    if status:
        stmt = stmt.where(ImportJob.status == status)
    items, meta = paginate(stmt.order_by(ImportJob.id.desc()), page, per_page)
    return ok([import_job(j) for j in items], pagination=meta)


@bp.get("/import-jobs/<int:job_id>")
def import_job_detail(job_id):
    job = db.session.get(ImportJob, job_id)
    if job is None:
        raise APIError(404, f"Import job {job_id} not found")
    return ok(import_job(job))
