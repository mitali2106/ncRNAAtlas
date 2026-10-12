"""High-level import orchestration shared by the CLI scripts and the admin API."""
import json
import logging
import threading
from functools import lru_cache
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import ExternalCache, ImportJob, utcnow
from ..normalization.resolver import EntityResolver
from ..services.hgnc import HGNCIndex
from ..services.mesh import MeSHService
from ..validation.quality import generate_quality_report, save_report
from .adapters import get_adapter
from .pipeline import ImportPipeline

log = logging.getLogger(__name__)


def hgnc_path():
    cfg = current_app.config
    candidates = [cfg.get("HGNC_PATH"), cfg["RAW_DIR"] / "hgnc_complete_set.txt", cfg["SAMPLE_DIR"] / "hgnc_subset.tsv"]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return None


@lru_cache(maxsize=4)
def _load_hgnc(path_str, mtime):
    return HGNCIndex.from_file(path_str)


def load_hgnc():
    path = hgnc_path()
    if path is None:
        log.warning("No HGNC reference file found; ncRNA/gene names will remain unresolved")
        return None
    return _load_hgnc(str(path), path.stat().st_mtime)


def load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_cache(namespace):
    return {row.cache_key: row.value for row in ExternalCache.query.filter_by(namespace=namespace)}


def store_cache(namespace, key, value):
    row = ExternalCache.query.filter_by(namespace=namespace, cache_key=key).first()
    if row is None:
        db.session.add(ExternalCache(namespace=namespace, cache_key=key, value=value, fetched_at=utcnow()))
    else:
        row.value, row.fetched_at = value, utcnow()


def build_resolver(live=None, retry_mesh_misses=False):
    cfg = current_app.config
    live = cfg["EXTERNAL_LOOKUPS_ENABLED"] if live is None else live
    mesh_cache = load_json(cfg["SAMPLE_DIR"] / "mesh_cache.json")
    mesh_cache.update(load_cache("mesh"))
    return EntityResolver(
        hgnc_index=load_hgnc(),
        mesh_cache=mesh_cache,
        mesh_service=MeSHService(timeout=cfg["EXTERNAL_TIMEOUT"]) if live else None,
        on_mesh_lookup=lambda k, v: store_cache("mesh", k, v),
        retry_mesh_misses=retry_mesh_misses,
    )


def publication_cache():
    return load_json(current_app.config["SAMPLE_DIR"] / "pubmed_cache.json")


def run_import(adapter_key, path, *, dataset_label="real", source_version=None, source_database=None,
               dry_run=False, overrides=None, skip_unresolved=False, human_only=False, live_lookups=None,
               limit=None, job=None):
    """Run one import and record an :class:`ImportJob` plus a quality report."""
    adapter = get_adapter(adapter_key, source_version=source_version, source_database=source_database)
    resolver = build_resolver(live_lookups)
    if not dry_run and job is None:
        job = ImportJob(source_database=adapter.source_database, job_type=adapter.kind,
                        dataset_label=dataset_label, source_file=Path(path).name, source_version=source_version,
                        status="running", started_at=utcnow())
        db.session.add(job)
        db.session.commit()
    elif job is not None:
        job.status, job.started_at = "running", utcnow()
        db.session.commit()
    job_id = job.id if job is not None else None

    def progress(res):
        # Commits in batches of 500 records (SQLite permits a single writer, so
        # progress cannot be written through a second connection). Imports are
        # idempotent, so a failed job can simply be re-run.
        if job_id is None:
            return
        j = db.session.get(ImportJob, job_id)
        j.records_processed, j.records_inserted = res.raw_records, res.inserted
        j.records_updated, j.records_skipped = res.updated, res.skipped
        db.session.commit()

    pipeline = ImportPipeline(
        resolver, is_synthetic=dataset_label == "synthetic", overrides=overrides,
        skip_unresolved=skip_unresolved, human_only=human_only,
        publication_cache=publication_cache(), import_job=job,
    )
    result = pipeline.run(adapter, path, dry_run=dry_run, progress=None if dry_run else progress, limit=limit)
    summary = result.to_dict()
    if dry_run:
        return result, None

    job = db.session.get(ImportJob, job_id)
    job.completed_at = utcnow()
    job.records_processed, job.records_inserted = result.raw_records, result.inserted
    job.records_updated, job.records_skipped = result.updated, result.skipped
    if result.errors:
        job.status = "failed"
        job.error_summary = "; ".join(result.errors)[:4000]
    else:
        job.status = "completed_with_errors" if resolver.mesh_errors else "completed"
        if resolver.mesh_errors:
            job.error_summary = f"{resolver.mesh_errors} MeSH lookups failed (diseases left unresolved)"
    job.summary = {k: v for k, v in summary.items() if k not in ("preview", "warnings", "unresolved")}
    db.session.commit()
    report = generate_quality_report(summary)
    report["import_job_id"] = job.id
    path_out = save_report(report, current_app.config["REPORT_DIR"], f"import_job_{job.id}")
    job.report_path = str(path_out)
    db.session.commit()
    return result, job


def run_import_in_background(app, job_id, adapter_key, path, **kwargs):
    """Run an import in a worker thread so the admin UI can poll job progress."""

    def work():
        with app.app_context():
            job = db.session.get(ImportJob, job_id)
            try:
                run_import(adapter_key, path, job=job, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("Background import failed")
                db.session.rollback()
                job = db.session.get(ImportJob, job_id)
                job.status, job.error_summary, job.completed_at = "failed", str(exc)[:4000], utcnow()
                db.session.commit()
            finally:
                db.session.remove()

    thread = threading.Thread(target=work, name=f"import-job-{job_id}", daemon=True)
    thread.start()
    return thread
