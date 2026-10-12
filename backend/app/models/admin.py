"""Import auditing and external-metadata cache tables."""
from sqlalchemy import UniqueConstraint

from ..extensions import db
from .entities import utcnow


class ImportJob(db.Model):
    __tablename__ = "import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    source_database = db.Column(db.String(64), nullable=False, index=True)
    job_type = db.Column(db.String(32), nullable=False, default="associations")
    dataset_label = db.Column(db.String(32), nullable=False, default="real")  # real | sample | synthetic
    source_file = db.Column(db.String(512), nullable=True)
    source_version = db.Column(db.String(64), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="pending")
    records_processed = db.Column(db.Integer, nullable=False, default=0)
    records_inserted = db.Column(db.Integer, nullable=False, default=0)
    records_updated = db.Column(db.Integer, nullable=False, default=0)
    records_skipped = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.Text, nullable=True)
    report_path = db.Column(db.String(512), nullable=True)
    summary = db.Column(db.JSON, nullable=True)


class ExternalCache(db.Model):
    """Cache of external metadata lookups (MeSH, KEGG, RNAcentral ...)."""

    __tablename__ = "external_cache"
    __table_args__ = (UniqueConstraint("namespace", "cache_key"),)

    id = db.Column(db.Integer, primary_key=True)
    namespace = db.Column(db.String(32), nullable=False)
    cache_key = db.Column(db.String(255), nullable=False)
    value = db.Column(db.JSON, nullable=True)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
