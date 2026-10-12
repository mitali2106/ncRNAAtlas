"""Shared HTTP client for external resources: timeouts, rate limiting, retries."""
import logging
import threading
import time

import requests

log = logging.getLogger(__name__)

USER_AGENT = "ncRNAAtlas/1.0 (academic bioinformatics database)"


class ExternalServiceError(Exception):
    """Raised when an external resource is unavailable or returns an error."""

    def __init__(self, service, message, status_code=None):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message
        self.status_code = status_code


class ExternalLookupsDisabled(ExternalServiceError):
    def __init__(self, service):
        super().__init__(service, "external lookups are disabled by configuration")


class RateLimitedClient:
    """Thread-safe client enforcing a minimum interval between requests."""

    def __init__(self, service, min_interval=0.34, timeout=15.0, retries=2):
        self.service = service
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self._lock = threading.Lock()
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _wait_turn(self):
        with self._lock:
            delay = self.min_interval - (time.monotonic() - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()

    def get(self, url, params=None, accept_404=False):
        last_error = None
        for attempt in range(self.retries + 1):
            self._wait_turn()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = ExternalServiceError(self.service, f"request failed: {exc.__class__.__name__}")
                log.warning("%s request error (attempt %s): %s", self.service, attempt + 1, exc.__class__.__name__)
            else:
                if resp.status_code == 404 and accept_404:
                    return resp
                if resp.status_code < 400:
                    return resp
                last_error = ExternalServiceError(
                    self.service, f"HTTP {resp.status_code}", status_code=resp.status_code
                )
                if resp.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self.retries:
                time.sleep(min(2.0 * (attempt + 1), 6.0))
        raise last_error
