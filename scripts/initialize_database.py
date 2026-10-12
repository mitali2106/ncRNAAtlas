"""Create (or upgrade) the ncRNAAtlas database schema via Alembic migrations.

Usage:
    python scripts/initialize_database.py            # apply migrations
    python scripts/initialize_database.py --sample   # ... then load the sample dataset
    python scripts/initialize_database.py --reset    # SQLite only: delete the DB file first (asks to confirm)

The database location comes from DATABASE_URL (see .env.example); by default a
SQLite file at data/ncrnaatlas.db is used.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from _bootstrap import PROJECT_ROOT, make_app


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="import the sample dataset after initialization")
    parser.add_argument("--reset", action="store_true", help="delete an existing SQLite database file first")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation with --reset")
    args = parser.parse_args()

    app = make_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if args.reset:
        if not uri.startswith("sqlite:///"):
            sys.exit("--reset is only supported for SQLite. Drop PostgreSQL databases with your own tooling.")
        db_path = Path(uri.replace("sqlite:///", "", 1))
        if db_path.exists():
            if not args.yes and input(f"Delete {db_path}? [y/N] ").strip().lower() != "y":
                sys.exit("Aborted.")
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(db_path) + suffix)
                if p.exists():
                    p.unlink()
            print(f"Deleted {db_path}")

    from flask_migrate import upgrade

    with app.app_context():
        upgrade(directory=str(PROJECT_ROOT / "backend" / "migrations"))
        from app.extensions import db
        from sqlalchemy import inspect

        tables = sorted(inspect(db.engine).get_table_names())
        print(f"Database ready ({db.engine.dialect.name}): {len(tables)} tables")

    if args.sample:
        subprocess.run([sys.executable, str(Path(__file__).with_name("import_data.py")), "sample"], check=True)


if __name__ == "__main__":
    main()
