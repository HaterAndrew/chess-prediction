"""
Shared scraping utilities — polite headers, rate limiting, and request wrapper.

All scrapers in this project should use these helpers to ensure:
  - Honest User-Agent identification
  - Minimum delay between requests (with random jitter)
  - Consistent timeout defaults
  - Request timing logs
"""

import functools
import logging
import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Polite session factory
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30  # seconds

_HEADERS = {
    "User-Agent": (
        "CCA-Entry-Predictor/1.0 "
        "(chess tournament prediction tool; contact: github.com/HaterAndrew)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def polite_session(retries=3, backoff_factor=1.0,
                   status_forcelist=(500, 502, 503, 504)):
    """Return a requests.Session with polite headers and retry logic."""
    session = requests.Session()
    session.headers.update(_HEADERS)

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

# Module-level timestamp of last request (shared across all callers)
_last_request_time = 0.0


def rate_limit(min_delay=1.0, max_delay=2.0):
    """
    Sleep enough to ensure at least *min_delay* seconds since the last
    request, adding random jitter up to *max_delay*.
    """
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    target = random.uniform(min_delay, max_delay)
    if elapsed < target:
        time.sleep(target - elapsed)
    _last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Respectful GET wrapper
# ---------------------------------------------------------------------------

def respectful_get(session, url, min_delay=1.0, max_delay=2.0,
                   timeout=DEFAULT_TIMEOUT, **kwargs):
    """
    GET *url* through *session* with rate limiting and timing log.

    Returns the Response object (caller should check status_code).
    Raises on connection/timeout errors just like session.get().
    """
    rate_limit(min_delay=min_delay, max_delay=max_delay)

    kwargs.setdefault("timeout", timeout)
    t0 = time.monotonic()
    resp = session.get(url, **kwargs)
    elapsed_ms = (time.monotonic() - t0) * 1000

    log.debug(
        "GET %s -> %s (%.0f ms)", url, resp.status_code, elapsed_ms
    )
    return resp
