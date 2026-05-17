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

# Regex for a fee tier line. CCA flyers vary wildly in spacing/markup:
#   "$207 by 3/19"
#   "$118 online at chessaction.com by 6/2"
#   "$148 if rec'd by 1/2"
# We allow up to 40 chars of letters / commas / periods / dots between the
# money and the deadline keyword, but no other dollar signs or digits in
# that gap (so we don't accidentally span two prize lines).
_FEE_TIER_RE = re.compile(
    rf'({_MONEY})'
    rf'(?:[A-Za-z\s,.\'"]{{0,40}})?\s*'
    rf'(?:if\s+(?:rec[\x27\u2019]?d?|postmarked|received)[\s,]*(?:by\s+)?|by|before|until|through|thru|b4)\s*'
    rf'({_DATE_LOOSE})',
    re.IGNORECASE,
)

# Fallback for the "$158 1/3-1/15" middle-tier pattern CCA uses when there's
# no "by" keyword \u2014 a bare date range right after the dollar amount. We
# capture the END of the range as the tier's deadline ($158 applies through
# 1/15, then prices step up). Requires the range form to limit false hits
# from prize lists like "$1000-600-400".
_FEE_TIER_RANGE_RE = re.compile(
    rf'({_MONEY})\s+'
    r'\d{1,2}/\d{1,2}\s*[\-\u2013to ]+\s*'
    r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)',
    re.IGNORECASE,
)

_ONSITE_RE = re.compile(
    rf'({_MONEY})'
    rf'(?:[A-Za-z\s,.\'"]{{0,30}})?\s*'
    rf'(?:on\s*-?\s*site|at\s+(?:the\s+)?door|after|at\s+site|walk[\s-]*in)',
    re.IGNORECASE,
)

_PRIZE_RE = re.compile(
    rf'(?:prize\s+fund|prizes?|guaranteed|based\s+on)[:\s]*({_MONEY})',
    re.IGNORECASE,
)

# Phrasing that signals an actual early-bird marketing structure (not just
# advance vs onsite). Combined with the 14-day gap rule below, this lets us
# distinguish Chicago Open ("early bird ends 3/19", T-63) from Cleveland
# ("online by 6/2", T-3 — just an advance/onsite step).
_EARLY_BIRD_PHRASE_RE = re.compile(
    r'\b(early[\s\-]?bird|early\s+registration|early\s+entry|advance\s+registration\s+discount)\b',
    re.IGNORECASE,
)

# Event date heuristic. Tolerates CCA's multi-schedule headers, e.g.
# "May 21-25, 22-25, 23-25, or 24-25, 2026" or "July 17-19 or 18-19, 2026"
# or the simple "May 5, 2026". We capture month + FIRST day, then accept
# up to 80 chars of glue (digits, dashes, commas, "or", whitespace) before
# the 4-digit year. The non-greedy gap stops at the first plausible year.
_EVENT_DATE_RE = re.compile(
    r'(?P<month>'
    r'January|February|March|April|May|June|July|August|September|October|November|December'
    r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec'
    r')\.?'
    r'\s+(?P<day>\d{1,2})'
    r'(?:[\s\-–,]|\d|or)*?'
    r'(?P<year>20\d{2})',
    re.IGNORECASE,
)

# An early bird is only real when the deadline is at least this many days
# before the event. Mirrors EARLY_BIRD_MIN_GAP_DAYS in 04d_website_data_v2.py
# and the JS gate in docs/app.js. 14 days = "well before the event."
EARLY_BIRD_MIN_GAP_DAYS = 14

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


def _guess_event_start(html, year_hint):
    """Pull the event start date out of a CCA flyer.

    CCA flyers consistently lead with a header like 'May 21-25, 2026' or
    'July 17-19 or 18-19, 2026'. We take the FIRST date hit on the page.
    Returns YYYY-MM-DD or None.
    """
    text = _clean(html)
    m = _EVENT_DATE_RE.search(text)
    if not m:
        return None
    raw = f"{m.group('month').strip('.')} {m.group('day')} {m.group('year')}"
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _days_gap(deadline_iso, event_iso):
    """Days between deadline and event_start. None if either is unparseable."""
    try:
        d = datetime.strptime(deadline_iso, "%Y-%m-%d")
        e = datetime.strptime(event_iso, "%Y-%m-%d")
        return (e - d).days
    except (TypeError, ValueError):
        return None


def parse_flyer(html, url):
    """Extract fee/deadline data from a chesstour.com flyer page.

    Returns a dict with the parsed fields, or None if nothing useful found.

    Guardrails (in order of application):
      1. early_bird_fee / early_bird_deadline are populated ONLY when the
         cheapest tier's deadline lands ≥EARLY_BIRD_MIN_GAP_DAYS before
         event_start. CCA's advance/onsite step (T-3 days) is NOT an early
         bird and gets demoted to the regular slot.
      2. If event_start can't be determined, EB fields stay blank — fail
         loud rather than guess.
      3. The cheapest tier must be strictly less than the next tier
         (no flat "early bird = regular" placeholders).
    """
    year = _guess_year_from_url(url)
    title = _guess_title(html, url)

    # Work with the visible text (tags stripped) for regex matching,
    # but keep original for structured tag searches
    text = _clean(html)
    event_start = _guess_event_start(html, year)

    has_eb_phrase = bool(_EARLY_BIRD_PHRASE_RE.search(text))

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

    # Catch the keyword-less "$158 1/3-1/15" middle-tier pattern. We deduplicate
    # against tiers we already have.
    for m in _FEE_TIER_RANGE_RE.finditer(text):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        if (fee, deadline) not in tiers:
            tiers.append((fee, deadline))

    # Collapse per-deadline to the HIGHEST fee at that deadline. CCA pages
    # usually list "Top 5 sections $X by Y, all $Z at site" and then a
    # lower section ("Under 1200: $X-20 by Y"). Without this step, the
    # sub-section's $X-20 sorts as "cheapest" and pollutes the early-bird
    # detection. Top-section pricing is what we want to publish.
    by_deadline = {}
    for fee, deadline in tiers:
        if not isinstance(fee, int):
            continue
        if deadline not in by_deadline or fee > by_deadline[deadline]:
            by_deadline[deadline] = fee
    tiers = [(fee, dl) for dl, fee in by_deadline.items()]

    # Sort tiers by fee amount (cheapest first)
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

    # ── Apply early-bird guardrails ────────────────────────────────────
    # An "early bird" is a price hike WELL BEFORE the event during the
    # advance-registration window — not the 3-day-out advance/onsite step
    # that nearly every CCA event has.
    early_bird_fee = ""
    early_bird_deadline = ""
    regular_fee = ""
    regular_deadline = ""
    eb_demoted_reason = None

    if len(tiers) >= 2 and isinstance(tiers[0][0], int) and isinstance(tiers[1][0], int):
        cheapest_fee, cheapest_deadline = tiers[0]
        second_fee, second_deadline = tiers[1]
        gap = _days_gap(cheapest_deadline, event_start) if event_start else None

        if cheapest_fee >= second_fee:
            eb_demoted_reason = f"cheapest tier ${cheapest_fee} not less than next tier ${second_fee}"
        elif event_start is None:
            eb_demoted_reason = "could not parse event_start from flyer"
        elif gap is None:
            eb_demoted_reason = f"could not compute gap (deadline={cheapest_deadline}, event={event_start})"
        elif gap < EARLY_BIRD_MIN_GAP_DAYS:
            eb_demoted_reason = (
                f"deadline {cheapest_deadline} is T-{gap} (< T-{EARLY_BIRD_MIN_GAP_DAYS}) "
                f"vs event {event_start} — advance/onsite step, not early bird"
            )

        if eb_demoted_reason is None:
            early_bird_fee = cheapest_fee
            early_bird_deadline = cheapest_deadline
            regular_fee = second_fee
            regular_deadline = second_deadline
            if not has_eb_phrase:
                log.info(
                    "  EB-NOTE  %s — accepted on gap (T-%d) but flyer lacks explicit "
                    "'early bird' phrasing; double-check the source if values look off",
                    url, gap,
                )
        else:
            log.info("  EB-DEMOTE  %s — %s", url, eb_demoted_reason)
            regular_fee = cheapest_fee
            regular_deadline = cheapest_deadline
            # Promote the second tier toward onsite if we don't have one yet
            if onsite_fee is None:
                onsite_fee = second_fee
    elif len(tiers) == 1 and isinstance(tiers[0][0], int):
        # Single date-bound tier = advance fee, no early bird possible.
        # Treat as the same "advance/onsite step" we filter elsewhere so the
        # validator can flag it consistently.
        regular_fee, regular_deadline = tiers[0]
        gap = _days_gap(regular_deadline, event_start) if event_start else None
        if event_start is None:
            eb_demoted_reason = "could not parse event_start from flyer"
        elif gap is None:
            eb_demoted_reason = f"could not compute gap (deadline={regular_deadline}, event={event_start})"
        else:
            eb_demoted_reason = (
                f"only one date-bound tier (${regular_fee} by {regular_deadline}, T-{gap}) — "
                f"advance/onsite step, not early bird"
            )
        log.info("  EB-DEMOTE  %s — %s", url, eb_demoted_reason)

    if onsite_fee is None and len(tiers) >= 3:
        onsite_fee = tiers[-1][0]

    return {
        "tournament_name": title,
        "year": year or "",
        "event_start": event_start or "",
        "early_bird_fee": early_bird_fee,
        "early_bird_deadline": early_bird_deadline,
        "regular_fee": regular_fee,
        "regular_deadline": regular_deadline,
        "onsite_fee": onsite_fee or "",
        "prize_fund": prize_fund or "",
        "has_eb_phrasing": has_eb_phrase,
        "eb_demoted_reason": eb_demoted_reason or "",
        "url": url,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "tournament_name",
    "year",
    "event_start",
    "early_bird_fee",
    "early_bird_deadline",
    "regular_fee",
    "regular_deadline",
    "onsite_fee",
    "prize_fund",
    "has_eb_phrasing",
    "eb_demoted_reason",
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
