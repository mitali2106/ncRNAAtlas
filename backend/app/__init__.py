"""ncRNAAtlas Flask application factory."""
import logging

from flask import Flask
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .api_utils import APIError, error_response
from .extensions import db, migrate


def create_app(config_object=None):
    from config import get_config

    app = Flask(__name__)
    app.config.from_object(config_object or get_config())
    for key in ("UPLOAD_DIR", "REPORT_DIR"):
        app.config[key].mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    from . import models  # noqa: F401  (register tables)

    migrate.init_app(app, db, directory=str(_migrations_dir()), render_as_batch=True)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
         allow_headers=["Content-Type", "X-Admin-Token"])

    from .routes import register_blueprints

    register_blueprints(app)
    _register_error_handlers(app)
    return app


def _migrations_dir():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "migrations"


def _register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(exc):
        return error_response(exc.status, exc.message, exc.code, exc.details)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(exc):
        mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return error_response(413, f"Uploaded file exceeds the {mb} MB limit", "payload_too_large")

    @app.errorhandler(HTTPException)
    def handle_http(exc):
        return error_response(exc.code, exc.description, exc.name.lower().replace(" ", "_"))

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        app.logger.exception("Unhandled error")
        db.session.rollback()
        return error_response(500, "An internal error occurred", "internal_error")
