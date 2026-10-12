"""Protected administrative endpoints: uploads, imports, QC reports, curator reviews.

All routes require the ``X-Admin-Token`` header. No route deletes data.
"""
import json
import re
import uuid
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from werkzeug.utils import secure_filename

from ..api_utils import APIError, get_choice, get_int, ok, pubmed_service, require_admin
from ..extensions import db
from ..ingestion.adapters import ADAPTERS
from ..ingestion.runner import run_import, run_import_in_background
from ..models import Association, ImportJob, utcnow
from ..schemas import serializers as ser
from ..validation.literature_review import ReviewError, record_review, review_queue, triage_association
from ..validation.quality import generate_quality_report, report_to_csv

bp = Blueprint("admin", __name__)
ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


def _upload_paths(upload_id):
    if not UPLOAD_ID.match(upload_id or ""):
        raise APIError(400, "Invalid upload id")
    meta_path = current_app.config["UPLOAD_DIR"] / f"{upload_id}.json"
    if not meta_path.exists():
        raise APIError(404, "Upload not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return meta_path, meta, current_app.config["UPLOAD_DIR"] / meta["stored_file"]


@bp.post("/admin/verify")
@require_admin
def verify():
    return ok({"authenticated": True})


@bp.get("/admin/adapters")
@require_admin
def adapters():
    return ok([a.describe() for a in ADAPTERS.values()])


@bp.post("/admin/uploads")
@require_admin
def upload():
    file = request.files.get("file")
    adapter_key = request.form.get("adapter", "generic_associations")
    if adapter_key not in ADAPTERS:
        raise APIError(400, f"Unknown adapter. Available: {', '.join(ADAPTERS)}")
    if file is None or not file.filename:
        raise APIError(400, "A file is required (multipart field 'file')")
    name = secure_filename(file.filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    head = file.stream.read(4096)
    file.stream.seek(0)
    if b"\x00" in head:
        raise APIError(400, "File appears to be binary; upload a UTF-8 CSV/TSV text file")
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        if exc.start < len(head) - 4:  # tolerate a multi-byte char cut at the 4 KB boundary
            raise APIError(400, "File is not valid UTF-8 text")
    upload_id = uuid.uuid4().hex
    stored = f"{upload_id}{ext}"
    path = current_app.config["UPLOAD_DIR"] / stored
    file.save(path)

    source_version = (request.form.get("source_version") or "").strip()[:64] or None
    source_database = (request.form.get("source_database") or "").strip()[:64] or None
    result, _ = run_import(adapter_key, path, dry_run=True, live_lookups=False, source_version=source_version,
                           source_database=source_database)
    preview = result.to_dict()
    meta = {
        "upload_id": upload_id, "original_filename": name, "stored_file": stored, "adapter": adapter_key,
        "source_version": source_version, "source_database": source_database,
        "uploaded_at": utcnow().isoformat(), "valid": not result.errors and result.valid_records > 0,
        "preview": preview, "job_id": None,
        "notes": "Preview resolves names with locally cached references only. Diseases may additionally be "
                 "resolved against MeSH at import time if external lookups are enabled.",
    }
    (current_app.config["UPLOAD_DIR"] / f"{upload_id}.json").write_text(json.dumps(meta, default=str),
                                                                        encoding="utf-8")
    return ok(meta), 201


@bp.get("/admin/uploads/<upload_id>")
@require_admin
def upload_detail(upload_id):
    _, meta, _ = _upload_paths(upload_id)
    return ok(meta)


@bp.post("/admin/uploads/<upload_id>/commit")
@require_admin
def commit_upload(upload_id):
    meta_path, meta, path = _upload_paths(upload_id)
    if meta.get("job_id"):
        raise APIError(409, f"Upload already imported as job {meta['job_id']}")
    if not meta.get("valid"):
        raise APIError(400, "Upload failed validation and cannot be imported")
    body = request.get_json(silent=True) or {}
    overrides = body.get("overrides") or {}
    if not isinstance(overrides, dict) or not all(
        k in ("ncrna", "disease", "gene") and isinstance(v, dict) and all(isinstance(x, str) for x in v.values())
        for k, v in overrides.items()
    ):
        raise APIError(400, "overrides must look like {'ncrna': {raw: canonical}, 'disease': {...}, 'gene': {...}}")
    dataset_label = body.get("dataset_label", "real")
    if dataset_label not in ("real", "sample", "synthetic"):
        raise APIError(400, "dataset_label must be real, sample or synthetic")
    adapter_cls = ADAPTERS[meta["adapter"]]
    job = ImportJob(source_database=meta.get("source_database") or adapter_cls.source_database,
                    job_type=adapter_cls.kind, dataset_label=dataset_label, source_file=meta["original_filename"],
                    source_version=meta.get("source_version"), status="pending")
    db.session.add(job)
    db.session.commit()
    meta["job_id"] = job.id
    meta_path.write_text(json.dumps(meta, default=str), encoding="utf-8")
    kwargs = dict(dataset_label=dataset_label, overrides=overrides,
                  skip_unresolved=bool(body.get("skip_unresolved")), human_only=bool(body.get("human_only")),
                  source_version=meta.get("source_version"), source_database=meta.get("source_database"))
    if body.get("synchronous") or current_app.config.get("TESTING"):
        run_import(meta["adapter"], path, job=job, **kwargs)
        db.session.refresh(job)
        return ok(ser.import_job(job)), 201
    run_import_in_background(current_app._get_current_object(), job.id, meta["adapter"], path, **kwargs)
    return ok(ser.import_job(job)), 202


@bp.get("/admin/import-jobs/<int:job_id>/report")
@require_admin
def job_report(job_id):
    job = db.session.get(ImportJob, job_id)
    if job is None:
        raise APIError(404, f"Import job {job_id} not found")
    if not job.report_path or not Path(job.report_path).exists():
        raise APIError(404, "No quality report is available for this job")
    fmt = get_choice("format", {"json", "csv"}, "json")
    path = Path(job.report_path)
    if fmt == "csv":
        path = path.with_suffix(".csv")
    return send_file(path, as_attachment=True, download_name=f"ncrnaatlas_import_{job_id}_quality.{fmt}")


@bp.get("/admin/quality-report")
@require_admin
def quality_report():
    report = generate_quality_report()
    if get_choice("format", {"json", "csv"}, "json") == "csv":
        return current_app.response_class(
            report_to_csv(report), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=ncrnaatlas_quality_report.csv"})
    return ok(report)


@bp.get("/admin/review-queue")
@require_admin
def queue():
    limit = get_int("limit", 50, 1, 200)
    return ok([ser.association_summary(a) for a in review_queue(limit)])


@bp.post("/admin/associations/<int:association_id>/triage")
@require_admin
def triage(association_id):
    a = db.session.get(Association, association_id)
    if a is None:
        raise APIError(404, f"Association {association_id} not found")
    body = request.get_json(silent=True) or {}
    service = pubmed_service() if body.get("fetch_metadata") and current_app.config["EXTERNAL_LOOKUPS_ENABLED"] else None
    reviews = triage_association(a, service)
    db.session.commit()
    return ok({"validation_status": a.validation_status, "triage": [ser.review(r) for r in reviews]})


@bp.post("/admin/associations/<int:association_id>/reviews")
@require_admin
def add_review(association_id):
    a = db.session.get(Association, association_id)
    if a is None:
        raise APIError(404, f"Association {association_id} not found")
    body = request.get_json(silent=True) or {}
    try:
        r = record_review(a, outcome=body.get("outcome"), pmid=(body.get("pmid") or None),
                          evidence_type=(body.get("evidence_type") or "")[:128] or None,
                          notes=(body.get("notes") or "")[:5000] or None,
                          reviewer=(body.get("reviewer") or "")[:128].strip() or None)
    except ReviewError as exc:
        db.session.rollback()
        raise APIError(400, str(exc))
    db.session.commit()
    return ok({"review": ser.review(r), "validation_status": a.validation_status}), 201
