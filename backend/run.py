"""Development server entry point: ``python run.py`` (or ``flask --app run run``)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=app.config.get("DEBUG", False))
