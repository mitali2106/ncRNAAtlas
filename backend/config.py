"""Environment-based configuration for the ncRNAAtlas backend.

All secrets and deployment-specific values are read from environment
variables (optionally loaded from a ``.env`` file at the project root).
Nothing sensitive is hard-coded here.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")


def _bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_sqlite_uri():
    return "sqlite:///" + (PROJECT_ROOT / "data" / "ncrnaatlas.db").as_posix()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-not-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _default_sqlite_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    ]

    # Admin endpoints are disabled entirely when no token is configured.
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

    # External services
    EXTERNAL_LOOKUPS_ENABLED = _bool("EXTERNAL_LOOKUPS_ENABLED", True)
    EXTERNAL_TIMEOUT = float(os.getenv("EXTERNAL_TIMEOUT", "15"))
    NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
    NCBI_EMAIL = os.getenv("NCBI_EMAIL", "")
    NCBI_TOOL = os.getenv("NCBI_TOOL", "ncRNAAtlas")

    # Rate limit for expensive / externally dependent endpoints (per client IP).
    EXTERNAL_RATE_LIMIT_PER_MINUTE = int(os.getenv("EXTERNAL_RATE_LIMIT_PER_MINUTE", "30"))

    # Uploads
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
    UPLOAD_DIR = DATA_DIR / "processed" / "uploads"
    REPORT_DIR = DATA_DIR / "reports"
    SAMPLE_DIR = DATA_DIR / "sample"
    RAW_DIR = DATA_DIR / "raw"

    # Optional path to the full HGNC complete set (falls back to the sample subset).
    HGNC_PATH = os.getenv("HGNC_PATH", "")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    EXTERNAL_LOOKUPS_ENABLED = False
    ADMIN_TOKEN = "test-admin-token"
    EXTERNAL_RATE_LIMIT_PER_MINUTE = 1000


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name=None):
    name = name or os.getenv("FLASK_ENV_NAME") or os.getenv("APP_ENV", "development")
    return CONFIGS.get(name, DevelopmentConfig)
