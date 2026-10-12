"""Make the backend importable from the scripts directory and build an app context."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Windows consoles default to a legacy code page; biological names and arrows need UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def make_app():
    from app import create_app

    return create_app()
