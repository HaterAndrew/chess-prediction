"""Flyer URL discovery: chessevents.com links + blind code/year probes
(scrape_fees, verbatim; session is created lazily so importing never
opens network state).
"""
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper_utils import polite_session, respectful_get, DEFAULT_TIMEOUT
from shared.season import CURRENT_SEASON

# Blind-probe code list lives in fees/codes.py (see the discrepancy notes
# there); legacy name kept for the discovery loop and tests.
from fees.codes import FLYER_PROBE_CODES as TOURNAMENT_CODES  # noqa: F401
from fees.codes import FAMILY_TO_CODE

log = logging.getLogger(__name__)

# 2022 through next season: CCA posts next season's flyers while this season
# is still running (the 2027 January-March events were open in September 2026).
YEAR_SUFFIXES = [f"{y % 100:02d}" for y in range(2022, CURRENT_SEASON + 2)]
CHESSTOUR = "https://www.chesstour.com/"

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
                discovered.add(flyer_url(full))
    log.info("Discovered %d chesstour.com links from chessevents.com", len(discovered))
    return discovered


# ---------------------------------------------------------------------------
# Step 2 — brute-force common code+year URLs
# ---------------------------------------------------------------------------

def flyer_url(url):
    """One spelling per flyer: https://www.chesstour.com/<page>. The rows of
    tournament_fees.csv are keyed by it."""
    return CHESSTOUR + url.rsplit("/", 1)[-1]


def generate_candidate_urls(known_urls=()):
    """Candidate flyer URLs: the probe codes for every year, every mapped
    family's code for this season and next, and every flyer already on file.
    chessevents.com stops listing an event once it is over, so probing only
    what it lists left flyers such as the 2026 Boston, Golden State and
    Mid-America ones unscraped while their pages were up."""
    urls = {f"{CHESSTOUR}{code}{yy}.htm" for code in TOURNAMENT_CODES for yy in YEAR_SUFFIXES}
    seasons = [f"{y % 100:02d}" for y in (CURRENT_SEASON, CURRENT_SEASON + 1)]
    urls |= {f"{CHESSTOUR}{code}{yy}.htm" for code in set(FAMILY_TO_CODE.values()) for yy in seasons}
    return urls | {flyer_url(u) for u in known_urls}


def probe_urls(urls):
    """{url: response} for the URLs that answer HTTP 200. The response is
    parsed as it is, rather than fetched a second time."""
    live = {}
    for url in sorted(urls):
        resp, ok = fetch(url)
        if ok:
            live[url] = resp
            log.info("  LIVE  %s", url)
        else:
            log.debug("  MISS  %s", url)
    return live
