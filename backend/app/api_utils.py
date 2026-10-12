"""Shared helpers for the REST API: errors, validation, pagination, auth, rate limiting."""
import hmac
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, jsonify, request

from .services.http_client import ExternalServiceError
from .services.kegg import KEGGService
from .services.pubmed import PubMedService
from .services.rnacentral import RNAcentralService

MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 25
MAX_QUERY_LENGTH = 100


class APIError(Exception):
    def __init__(self, status, message, code=None, details=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code or {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
                             409: "conflict", 413: "payload_too_large", 429: "rate_limited",
                             503: "external_unavailable"}.get(status, "error")
        self.details = details


def error_response(status, message, code, details=None):
    body = {"error": {"status": status, "code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def ok(data, **meta):
    body = {"data": data}
    body.update(meta)
    return jsonify(body)


# ------------------------------------------------------------------ params
def get_int(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise APIError(400, f"Parameter '{name}' must be an integer")
    if minimum is not None and value < minimum:
        raise APIError(400, f"Parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise APIError(400, f"Parameter '{name}' must be <= {maximum}")
    return value


def get_str(name, default=None, max_length=MAX_QUERY_LENGTH):
    raw = request.args.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    if len(raw) > max_length:
        raise APIError(400, f"Parameter '{name}' exceeds {max_length} characters")
    return raw


def get_choice(name, choices, default=None):
    value = get_str(name, default)
    if value is not None and value not in choices:
        raise APIError(400, f"Parameter '{name}' must be one of: {', '.join(sorted(choices))}")
    return value


def get_bool(name, default=False):
    raw = request.args.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def pagination_params():
    return get_int("page", 1, minimum=1, maximum=100000), get_int("per_page", DEFAULT_PER_PAGE, 1, MAX_PER_PAGE)


def paginate(query, page, per_page):
    """Paginate a SQLAlchemy select; returns (items, pagination_meta)."""
    from .extensions import db

    result = db.paginate(query, page=page, per_page=per_page, error_out=False, count=True)
    meta = {"page": page, "per_page": per_page, "total": result.total, "pages": result.pages}
    return result.items, meta


# -------------------------------------------------------------------- auth
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = current_app.config.get("ADMIN_TOKEN")
        if not token:
            raise APIError(403, "Administrative endpoints are disabled: set ADMIN_TOKEN in the server environment",
                           code="admin_disabled")
        supplied = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            raise APIError(401, "A valid X-Admin-Token header is required")
        return fn(*args, **kwargs)

    return wrapper


# -------------------------------------------------------------- rate limit
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def rate_limited(group):
    """Sliding-window per-client limit for expensive / externally dependent endpoints."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            limit = current_app.config["EXTERNAL_RATE_LIMIT_PER_MINUTE"]
            key = (group, request.remote_addr or "unknown")
            now = time.monotonic()
            with _hits_lock:
                window = _hits[key]
                while window and now - window[0] > 60:
                    window.popleft()
                if len(window) >= limit:
                    raise APIError(429, f"Rate limit exceeded ({limit} requests/minute for {group})")
                window.append(now)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


# --------------------------------------------------------------- services
def _service(name, factory):
    ext = current_app.extensions.setdefault("ncrnaatlas_services", {})
    if name not in ext:
        ext[name] = factory()
    return ext[name]


def require_external(service):
    if not current_app.config["EXTERNAL_LOOKUPS_ENABLED"]:
        raise APIError(503, f"{service} lookups are disabled on this server", code="external_disabled")


def pubmed_service():
    cfg = current_app.config
    return _service("pubmed", lambda: PubMedService(cfg["NCBI_API_KEY"], cfg["NCBI_EMAIL"], cfg["NCBI_TOOL"],
                                                    timeout=cfg["EXTERNAL_TIMEOUT"]))


def kegg_service():
    return _service("kegg", lambda: KEGGService(timeout=current_app.config["EXTERNAL_TIMEOUT"]))


def rnacentral_service():
    return _service("rnacentral", lambda: RNAcentralService(timeout=current_app.config["EXTERNAL_TIMEOUT"]))


def external_error(exc: ExternalServiceError):
    return APIError(503, f"{exc.service} is currently unavailable ({exc.message}). Locally stored data is unaffected.",
                    code="external_unavailable", details={"service": exc.service})
