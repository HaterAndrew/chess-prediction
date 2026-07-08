"""
Structure monitor for CCA website — detects changes that would break scrapers.

Usage:
    python structure_monitor.py check    # verify against baseline, exit 0/1
    python structure_monitor.py update   # regenerate baseline from live site
"""

import json
import logging
import os
import re
import sys
from bs4 import BeautifulSoup
from scraper_utils import polite_session, rate_limit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(PROJECT_DIR, "structure_baseline.json")
# H6: check the endpoint the scraper actually reads. The old
# /CCA/index.php?vendor=... page 302-redirects to a listless homepage now (it
# broke the 2026-06-03 run); scrape_entries.py switched to POSTing this AJAX
# tourlist endpoint directly, so that is the markup whose drift breaks the
# scraper. It is server-rendered HTML — a requests POST returns the same bytes
# scrape_entries parses, so the drift alarm no longer needs headless Chrome.
CCA_INDEX_URL = "https://www.chessaction.com/ajaxFrontGetTourListNew.php"
CCA_VENDOR_ID = 3

# ── Expected page structure the scraper relies on ────────────────────────
CCA_BASELINE = {
    "url": CCA_INDEX_URL,
    "selectors": [
        {"css": "a[href*='tournaments/index.php?view=']",
         "min_count": 3, "description": "Tournament detail links"},
        {"css": "div.text-muted.small",
         "min_count": 3, "description": "Date/state metadata divs"},
        {"css": "a[href*='tid=']",
         "min_count": 3, "description": "Links with tid= parameter"},
    ],
    "regex_patterns": [
        {"pattern": r'<a href="tournaments/index\.php\?view=[^"]+tid=[^"]+">[^<]+</a>',
         "min_count": 3, "description": "Tournament anchor tags with tid param"},
        {"pattern": r'Entry List \[\d+\]',
         "min_count": 1, "description": "Entry List [NNN] count pattern"},
        {"pattern": r'[A-Z][a-z]{2} \d{1,2}, \d{4}\s*-\s*[A-Z][a-z]{2} \d{1,2}, \d{4}',
         "min_count": 1, "description": "Date range (Mon DD, YYYY - Mon DD, YYYY)"},
        {"pattern": r'State:\s*\w',
         "min_count": 1, "description": "State field in listing"},
    ],
}


def _fetch_page(url):
    """Fetch the CCA tourlist HTML through the same polite requests POST the
    real scraper uses.

    H6: this used headless Chrome on the theory the listing is AJAX-rendered. It
    is — but scrape_entries.py gets the same content by POSTing the AJAX endpoint
    directly (vendor_search + length=-1) and parsing the server-rendered HTML with
    requests. Mirroring that POST here checks exactly the bytes the scraper parses
    and lets the drift alarm run in the daily CI job without a Chrome binary.
    """
    session = polite_session()
    rate_limit(min_delay=1.0, max_delay=2.0)
    log.info("Fetching %s", url)
    resp = session.post(url, data={"vendor_search": CCA_VENDOR_ID, "length": "-1"},
                        timeout=30)
    resp.raise_for_status()
    return resp.text


def check_structure(url, baseline):
    """Check live page against baseline. Returns list of deviation strings."""
    html = _fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")
    deviations = []

    for sel in baseline.get("selectors", []):
        count = len(soup.select(sel["css"]))
        if count < sel["min_count"]:
            msg = f"SELECTOR '{sel['css']}': found {count}, expected >= {sel['min_count']} — {sel['description']}"
            deviations.append(msg)
            log.warning(msg)
        else:
            log.info("OK  %-45s count=%d", sel["css"], count)

    for pat in baseline.get("regex_patterns", []):
        count = len(re.findall(pat["pattern"], html, re.DOTALL))
        if count < pat["min_count"]:
            msg = f"REGEX '{pat['description']}': found {count}, expected >= {pat['min_count']}"
            deviations.append(msg)
            log.warning(msg)
        else:
            log.info("OK  %-45s count=%d", pat["description"], count)

    return deviations


def generate_baseline(url):
    """Scrape current page, return fresh baseline dict with actual counts."""
    html = _fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")
    bl = {"url": url, "selectors": [], "regex_patterns": []}

    for sel in CCA_BASELINE["selectors"]:
        count = len(soup.select(sel["css"]))
        bl["selectors"].append({"css": sel["css"], "min_count": max(1, count),
                                "actual_count": count, "description": sel["description"]})
    for pat in CCA_BASELINE["regex_patterns"]:
        count = len(re.findall(pat["pattern"], html, re.DOTALL))
        bl["regex_patterns"].append({"pattern": pat["pattern"], "min_count": max(1, count),
                                     "actual_count": count, "description": pat["description"]})
    return bl


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "update"):
        print("Usage: python structure_monitor.py {check|update}")
        sys.exit(2)

    if sys.argv[1] == "update":
        log.info("Generating fresh baseline from live site...")
        baseline = generate_baseline(CCA_INDEX_URL)
        with open(BASELINE_PATH, "w") as f:
            json.dump(baseline, f, indent=2)
        log.info("Baseline saved to %s", BASELINE_PATH)
        for s in baseline["selectors"] + baseline["regex_patterns"]:
            log.info("  %-45s count=%d", s.get("css", s.get("description")), s["actual_count"])

    elif sys.argv[1] == "check":
        if os.path.exists(BASELINE_PATH):
            log.info("Using saved baseline: %s", BASELINE_PATH)
            with open(BASELINE_PATH) as f:
                baseline = json.load(f)
        else:
            log.info("No saved baseline — using hardcoded CCA_BASELINE")
            baseline = CCA_BASELINE

        deviations = check_structure(baseline.get("url", CCA_INDEX_URL), baseline)
        if deviations:
            log.error("STRUCTURE CHANGED — %d deviation(s):", len(deviations))
            for d in deviations:
                log.error("  - %s", d)
            sys.exit(1)
        else:
            log.info("All structure checks passed.")
            sys.exit(0)


if __name__ == "__main__":
    main()
