"""
Shared scraping utilities — polite headers, rate limiting, and request wrapper.

All scrapers in this project should use these helpers to ensure:
  - Honest User-Agent identification
  - Minimum delay between requests (with random jitter)
  - Consistent timeout defaults (separate connect/read)
  - Per-host circuit breaker (fast-fail on dead hosts)
  - Request timing logs
"""

import functools
import logging
import random
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Polite session factory
# ---------------------------------------------------------------------------

# (connect, read) — a dead host should fail the TCP handshake fast; reads stay generous
DEFAULT_TIMEOUT = (5, 30)

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


def rate_limit(min_delay=3.0, max_delay=5.0):
    """
    Sleep enough to ensure at least *min_delay* seconds since the last
    request, adding random jitter up to *max_delay*.

    Defaults raised from 1-2s to 3-5s after observing origin rate-limits
    on chessevents.com trip within ~15 requests from GitHub-hosted runners.
    """
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    target = random.uniform(min_delay, max_delay)
    if elapsed < target:
        time.sleep(target - elapsed)
    _last_request_time = time.monotonic()


# ---------------------------------------------------------------------------
# Per-host circuit breaker
# ---------------------------------------------------------------------------

# After this many consecutive connect failures on a host, mark it dead and
# fast-fail all further requests to it. Any successful response resets the count.
DEAD_HOST_THRESHOLD = 5

_host_failures = {}   # host -> consecutive connect-failure count
_dead_hosts = set()   # hosts we've given up on for the rest of the run


def _host_of(url):
    return urlparse(url).netloc.lower()


def is_host_dead(url):
    return _host_of(url) in _dead_hosts


def mark_host_failure(url):
    host = _host_of(url)
    n = _host_failures.get(host, 0) + 1
    _host_failures[host] = n
    if n >= DEAD_HOST_THRESHOLD and host not in _dead_hosts:
        _dead_hosts.add(host)
        log.warning("circuit-breaker: %s marked dead after %d connect failures", host, n)
        print(f"  [CIRCUIT] {host} marked dead after {n} connect failures — skipping remaining URLs on this host", flush=True)


def mark_host_success(url):
    host = _host_of(url)
    if _host_failures.get(host):
        _host_failures[host] = 0


# ---------------------------------------------------------------------------
# Respectful GET wrapper
# ---------------------------------------------------------------------------

class DeadHostError(requests.ConnectionError):
    """Raised when a request targets a host the circuit breaker has opened."""


def respectful_get(session, url, min_delay=3.0, max_delay=5.0,
                   timeout=DEFAULT_TIMEOUT, **kwargs):
    """
    GET *url* through *session* with rate limiting, timing log, and a
    per-host circuit breaker.

    Returns the Response object (caller should check status_code).
    Raises DeadHostError (a ConnectionError subclass) if the host has
    been marked dead; otherwise raises like session.get().
    """
    if is_host_dead(url):
        raise DeadHostError(f"host {_host_of(url)} marked dead by circuit breaker")

    rate_limit(min_delay=min_delay, max_delay=max_delay)

    kwargs.setdefault("timeout", timeout)
    t0 = time.monotonic()
    try:
        resp = session.get(url, **kwargs)
    except (requests.ConnectTimeout, requests.ConnectionError):
        mark_host_failure(url)
        raise
    elapsed_ms = (time.monotonic() - t0) * 1000

    mark_host_success(url)
    log.debug(
        "GET %s -> %s (%.0f ms)", url, resp.status_code, elapsed_ms
    )
    return resp
