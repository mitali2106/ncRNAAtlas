"""Shared Flask extension instances."""
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Deterministic constraint names keep Alembic migrations portable between
# SQLite and PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    """Enforce foreign keys (off by default in SQLite) and enable WAL."""
    module = type(dbapi_connection).__module__
    if not module.startswith("sqlite3"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:  # in-memory databases do not support WAL
        pass
    cursor.close()
