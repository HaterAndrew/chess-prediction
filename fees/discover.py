"""Flyer URL discovery: chessevents.com links + blind code/year probes
(scrape_fees, verbatim; session is created lazily so importing never
opens network state).
"""
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper_utils import polite_session, respectful_get, DEFAULT_TIMEOUT

# Blind-probe code list lives in fees/codes.py (see the discrepancy notes
# there); legacy name kept for the discovery loop and tests.
from fees.codes import FLYER_PROBE_CODES as TOURNAMENT_CODES  # noqa: F401

log = logging.getLogger(__name__)

YEAR_SUFFIXES = ["22", "23", "24", "25", "26"]

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

_session = None


def get_session():
    """Create the polite session on first use (P7: no session at import)."""
    global _session
    if _session is None:
        _session = polite_session()
    return _session


def fetch(url, timeout=DEFAULT_TIMEOUT):
    """GET a URL with rate limiting; return (response, True) or (None, False)."""
    try:
        resp = respectful_get(get_session(), url, timeout=timeout)
        if resp.status_code == 200:
            return resp, True
        log.debug("HTTP %s for %s", resp.status_code, url)
        return None, False
    except requests.RequestException as exc:
        log.debug("Request error for %s: %s", url, exc)
        return None, False


# ---------------------------------------------------------------------------
# Step 1 — discover flyer URLs from chessevents.com
# ---------------------------------------------------------------------------

def discover_from_chessevents():
    """Scrape chessevents.com schedule/tournament pages for chesstour.com links."""
    discovered = set()
    seed_urls = [
        "https://www.chessevents.com/tournaments",
        "https://www.chessevents.com/schedule",
        "https://www.chessevents.com/",
    ]
    for url in seed_urls:
        log.info("Checking %s for chesstour.com links …", url)
        resp, ok = fetch(url)
        if not ok:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            full = urljoin(url, href)
            if "chesstour.com" in full and full.endswith(".htm"):
                discovered.add(full)
    log.info("Discovered %d chesstour.com links from chessevents.com", len(discovered))
    return discovered


# ---------------------------------------------------------------------------
# Step 2 — brute-force common code+year URLs
# ---------------------------------------------------------------------------

def generate_candidate_urls():
    """Build a set of candidate chesstour.com flyer URLs."""
    urls = set()
    for code in TOURNAMENT_CODES:
        for yy in YEAR_SUFFIXES:
            urls.add(f"https://www.chesstour.com/{code}{yy}.htm")
    return urls


def probe_urls(urls):
    """Return the subset of URLs that respond with HTTP 200."""
    live = set()
    for url in sorted(urls):
        resp, ok = fetch(url)
        if ok:
            live.add(url)
            log.info("  LIVE  %s", url)
        else:
            log.debug("  MISS  %s", url)
    return live
