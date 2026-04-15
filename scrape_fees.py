"""
Scrape early bird deadlines and fee tiers from chesstour.com flyer pages.

Strategy:
  1. Attempt to discover tournament flyer links from chessevents.com.
  2. Brute-force common tournament code/year combos on chesstour.com.
  3. Parse the messy old-school HTML for fee tiers, deadlines, and prize fund.

Output: output/tournament_fees.csv
"""

import csv
import os
import re
import sys
import time
import logging
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper_utils import polite_session, respectful_get, DEFAULT_TIMEOUT

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
CSV_PATH = os.path.join(OUTPUT_DIR, "tournament_fees.csv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Common CCA tournament codes and the year suffixes to try
TOURNAMENT_CODES = [
    "wo",    # World Open
    "chio",  # Chicago Open
    "nao",   # North American Open
    "lib",   # Liberty Bell Open
    "ncc",   # National Chess Congress
    "aco",   # Atlantic City Open
    "scc",   # Southern California Chess
    "pho",   # Philadelphia Open
    "uso",   # US Open
    "eo",    # Eastern Open
    "ao",    # Atlantic Open
    "lvo",   # Las Vegas Open
    "cco",   # Cherry Blossom Classic / Continental Chess Open
    "dc",    # DC area events
]
YEAR_SUFFIXES = ["22", "23", "24", "25", "26"]

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

_session = polite_session()


def fetch(url, timeout=DEFAULT_TIMEOUT):
    """GET a URL with rate limiting; return (response, True) or (None, False)."""
    try:
        resp = respectful_get(_session, url, timeout=timeout)
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


# ---------------------------------------------------------------------------
# Step 3 — parse a chesstour.com flyer page
# ---------------------------------------------------------------------------

# Money amounts: $NNN or $N,NNN
_MONEY = r'\$[\d,]+'
# Date-like strings: month/day, month-day, "March 21", "3/21/25", etc.
_DATE_LOOSE = (
    r'(?:\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{2,4})?)'
)

# Regex for a fee tier line: "$207 by 3/21" or "$250 onsite/at door/after"
_FEE_TIER_RE = re.compile(
    rf'({_MONEY})\s*'
    rf'(?:if\s+(?:rec[\x27\u2019]?d?|postmarked|received)[\s,]*(?:by\s+)?|by|before|until|through|thru|b4)\s*'
    rf'({_DATE_LOOSE})',
    re.IGNORECASE,
)

_ONSITE_RE = re.compile(
    rf'({_MONEY})\s*(?:on\s*-?\s*site|at\s+(?:the\s+)?door|after|at\s+site|walk[\s-]*in)',
    re.IGNORECASE,
)

_PRIZE_RE = re.compile(
    rf'(?:prize\s+fund|prizes?|guaranteed|based\s+on)[:\s]*({_MONEY})',
    re.IGNORECASE,
)

_TITLE_GUESSES = [
    re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<h[12][^>]*>(.*?)</h[12]>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<font[^>]*size=["\']?[5-7]["\']?[^>]*>(.*?)</font>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<b>((?:20\d{2}\s+)?\w[\w\s]{5,40}(?:Open|Congress|Classic|Championship)s?)</b>', re.IGNORECASE),
]


def _clean(text):
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_fee(s):
    """Convert '$1,234' -> 1234 as int, or return the raw string."""
    s = s.strip().lstrip('$').replace(',', '')
    try:
        return int(s)
    except ValueError:
        return s


def _normalise_date(raw, year_hint=None):
    """Best-effort parse of a messy date string into YYYY-MM-DD.

    year_hint is the tournament year (from URL or page).  If the raw date
    has no year component we attach year_hint.
    """
    raw = raw.strip().rstrip('.')
    # Try common formats
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%m/%d", "%m-%d",
        "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
        "%B %d", "%b %d", "%b. %d",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            # If year came from format and is reasonable, keep it
            if '%Y' in fmt or '%y' in fmt:
                return dt.strftime("%Y-%m-%d")
            # Otherwise attach year_hint
            if year_hint:
                dt = dt.replace(year=int(year_hint))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: return as-is
    return raw


def _guess_year_from_url(url):
    """Extract a 2-digit year suffix from a chesstour.com filename."""
    m = re.search(r'(\d{2})\.htm', url)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy < 50 else 1900 + yy
    return None


def _guess_title(html, url):
    """Try several heuristics to extract the tournament name."""
    for pat in _TITLE_GUESSES:
        m = pat.search(html)
        if m:
            title = _clean(m.group(1))
            # Skip generic/junk titles
            if title and len(title) > 4 and 'chesstour' not in title.lower():
                return title
    # Fallback: derive from filename
    fname = url.rsplit('/', 1)[-1].replace('.htm', '')
    return fname


def parse_flyer(html, url):
    """Extract fee/deadline data from a chesstour.com flyer page.

    Returns a dict with the parsed fields, or None if nothing useful found.
    """
    year = _guess_year_from_url(url)
    title = _guess_title(html, url)

    # Work with the visible text (tags stripped) for regex matching,
    # but keep original for structured tag searches
    text = _clean(html)

    # --- Fee tiers (date-bound) ---
    tiers = []
    for m in _FEE_TIER_RE.finditer(text):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        tiers.append((fee, deadline))

    # Also scan raw HTML in case tags break up the visible text
    for m in _FEE_TIER_RE.finditer(html):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        if (fee, deadline) not in tiers:
            tiers.append((fee, deadline))

    # Sort tiers by fee amount (cheapest first = early bird)
    tiers.sort(key=lambda t: t[0] if isinstance(t[0], int) else 0)

    # --- Onsite fee ---
    onsite_fee = None
    for m in _ONSITE_RE.finditer(text):
        onsite_fee = _parse_fee(m.group(1))
        break
    if onsite_fee is None:
        for m in _ONSITE_RE.finditer(html):
            onsite_fee = _parse_fee(m.group(1))
            break

    # --- Prize fund ---
    prize_fund = None
    for m in _PRIZE_RE.finditer(text):
        prize_fund = _parse_fee(m.group(1))
        break
    if prize_fund is None:
        for m in _PRIZE_RE.finditer(html):
            prize_fund = _parse_fee(m.group(1))
            break

    # If we found nothing at all, skip this page
    if not tiers and onsite_fee is None:
        log.debug("No fee data found on %s", url)
        return None

    early_bird_fee = tiers[0][0] if len(tiers) >= 1 else ""
    early_bird_deadline = tiers[0][1] if len(tiers) >= 1 else ""
    regular_fee = tiers[1][0] if len(tiers) >= 2 else ""
    regular_deadline = tiers[1][1] if len(tiers) >= 2 else ""
    if onsite_fee is None and len(tiers) >= 3:
        onsite_fee = tiers[-1][0]

    return {
        "tournament_name": title,
        "year": year or "",
        "early_bird_fee": early_bird_fee,
        "early_bird_deadline": early_bird_deadline,
        "regular_fee": regular_fee,
        "regular_deadline": regular_deadline,
        "onsite_fee": onsite_fee or "",
        "prize_fund": prize_fund or "",
        "url": url,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "tournament_name",
    "year",
    "early_bird_fee",
    "early_bird_deadline",
    "regular_fee",
    "regular_deadline",
    "onsite_fee",
    "prize_fund",
    "url",
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collect candidate URLs from both discovery methods
    candidates = generate_candidate_urls()
    log.info("Generated %d brute-force candidate URLs", len(candidates))

    discovered = discover_from_chessevents()
    candidates |= discovered
    log.info("Total candidate URLs: %d", len(candidates))

    # Probe which URLs are actually live
    log.info("Probing candidates (this may take a few minutes) …")
    live_urls = probe_urls(candidates)
    log.info("Found %d live flyer pages", len(live_urls))

    if not live_urls:
        log.warning("No live chesstour.com pages found. CSV not written.")
        sys.exit(0)

    # Parse each live page
    results = []
    for url in sorted(live_urls):
        resp, ok = fetch(url)
        if not ok:
            continue
        # chesstour.com pages are often latin-1 encoded
        resp.encoding = resp.apparent_encoding or "latin-1"
        record = parse_flyer(resp.text, url)
        if record:
            results.append(record)
            log.info("  PARSED  %s  →  %s", url, record["tournament_name"])

    # Write CSV
    if results:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(results)
        log.info("Wrote %d rows to %s", len(results), CSV_PATH)
    else:
        log.warning("Parsed 0 records — CSV not written.")


if __name__ == "__main__":
    main()
