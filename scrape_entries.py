"""
Daily scraper for CCA tournament entry counts from chessaction.com.

Scrapes all 2026 tournaments from the CCA index page, extracting:
  - Entry counts from "Entry List [NNN]" pattern (gross registrations)
  - Withdrawal counts from entry list HTML ("N Active [+M Withdrawn]")
  - Active counts (gross minus withdrawals)
  - Event dates (start/end) directly from CCA listings
  - State/location

The index page provides gross counts in a single load. A lightweight second
pass hits each tournament's entry list HTML page via requests to capture
withdrawal data. Tournaments without entry list pages get withdrawal_count=0.

World Open: only 3 sub-events are tracked (Under 13, top 6 sections,
lower sections). All others (G/7, G/10, Blitz, Action, etc.) are dropped.

Tournament dates are synced to output/tournament_metadata.csv so the
predictor always reflects the official CCA schedule.
"""

import os
import re
import sys
import time
import csv
import logging
from datetime import date, datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

from scraper_utils import rate_limit

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Selenium exceptions worth retrying on
RETRY_EXCEPTIONS = (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    ValueError,  # raised when regex matches 0 tournaments
)

# ---------------------------------------------------------------------------
# Retry / circuit-breaker settings
# ---------------------------------------------------------------------------
MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 2          # seconds; delays: 2, 4, 8, 16, 32
CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive full-pipeline failures before exit

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
CSV_PATH = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
META_PATH = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
TODAY = date.today().isoformat()

# World Open sub-events to KEEP as separate rows
WO_KEEP_PATTERNS = re.compile(r'under\s*13|top\s+6\s+sections|lower\s+sections', re.IGNORECASE)

# CCA name -> canonical family name: single source of truth in tournament_aliases.py
from tournament_aliases import CCA_CANONICALIZE as CCA_FAMILY_ALIASES

def to_family(name):
    """Strip year prefix from CCA tournament name and apply canonical aliases."""
    family = re.sub(r'^\d{4}\s+', '', name).strip()
    return CCA_FAMILY_ALIASES.get(family, family)


# ── CCA entry list URL codes ─────────────────────────────────────────────
# Maps lowercase family name fragments to the short code used in CCA's
# entry list URLs: /advlists/CCA/CCA_{CODE}{YY}/CCA_{CODE}{YY}_alp_n.html
ENTRY_LIST_CODES = {
    "atlantic city open": "ACO",
    "atlantic open": "AO",
    "world open": "WO",
    "chicago open blitz": "COB",
    "chicago open": "CHI",
    "chicago class": "CC",
    "liberty bell open": "LBO",
    "george washington open": "GWO",
    "golden state open": "GSO",
    "pacific coast open": "PCO",
    "pittsburgh open": "PIT",
    "cleveland open": "CLEV",
    "bradley open": "BRAD",
    "dc international": "DCI",
    "dc open": "DCO",
    "hartford open": "HO",
    "new york state championship": "NYSC",
    "new york state open": "NYSO",
    "southern open": "SO",
    "central california open": "CCO",
    "national chess congress": "NCC",
    "north american open": "NAO",
    "eastern open": "EO",
    "los angeles open": "LAO",
    "mid-america open": "MAO",
    "mid america open": "MAO",
    "new york open": "NYO",
    "kings island open": "KIO",
    "eastern chess congress": "ECC",
    "western class": "WC",
    "national open": "NO",
    "las vegas open": "LVO",
    "southwest class": "SWC",
    "boston chess congress": "BCC",
}

# Withdrawal pattern from CCA entry list HTML pages
_WD_PATTERN = re.compile(
    r'(\d+)\s+Active\s+Players?\s*\[\s*\+?\s*(\d+)\s+Withdrawn\s*\]',
    re.IGNORECASE,
)
_ACTIVE_ONLY_PATTERN = re.compile(
    r'(\d+)\s+Active\s+Players?',
    re.IGNORECASE,
)

ENTRY_LIST_URL_TEMPLATE = (
    'https://www.chessaction.com/tournaments/advlists/CCA/'
    'CCA_{code}{yy}/CCA_{code}{yy}_alp_n.html'
)


def _derive_entry_list_code(tournament_name):
    """Derive the CCA entry list URL code from a tournament name.

    Checks longer patterns first to avoid substring false positives
    (e.g., 'chicago open blitz' must match before 'chicago open').
    """
    name_lower = re.sub(r'^\d{4}\s+', '', tournament_name).strip().lower()
    # Sort patterns longest-first so more specific matches win
    for pattern in sorted(ENTRY_LIST_CODES, key=len, reverse=True):
        if pattern in name_lower:
            return ENTRY_LIST_CODES[pattern]
    # Fallback: initials of significant words
    words = re.findall(r'[a-z]+', name_lower)
    skip = {'the', 'of', 'and', 'in', 'at', 'for', 'a', 'an'}
    return ''.join(w[0].upper() for w in words if w not in skip) or None


def _create_session():
    """Create a requests session with retry logic for entry list fetches."""
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/131.0.0.0',
        'Accept': 'text/html,*/*',
    })
    return session


def scrape_withdrawals(tournaments, year=2026):
    """
    Hit each tournament's CCA entry list page to get withdrawal counts.

    Adds 'withdrawal_count' and 'active_count' keys to each tournament dict.
    Uses plain requests (no Selenium) — each page is a small static HTML fetch.
    Tournaments without an entry list page get withdrawal_count=0.

    World Open sub-events (Blitz, Action, G/xx) share the same entry list
    page as the main World Open, so we only scrape the main WO page once
    and skip sub-events (they'll be consolidated separately).
    """
    yy = str(year)[-2:]
    session = _create_session()
    print(f"\n── Scraping withdrawal counts from entry list pages ──")

    # Track codes already fetched to avoid hitting the same page twice
    # (World Open sub-events all map to WO)
    fetched_cache = {}  # code -> (active, withdrawn)

    for t in tournaments:
        code = _derive_entry_list_code(t['name'])
        t['withdrawal_count'] = 0
        t['active_count'] = t['entry_count']

        if not code or t['entry_count'] == 0:
            continue

        # Skip World Open sub-events we don't track. Keep only Under 13,
        # top 6 sections, and lower sections. Skip everything else.
        name_lower = t['name'].lower()
        if 'world open' in name_lower:
            is_kept = WO_KEEP_PATTERNS.search(t['name'])
            if not is_kept:
                continue

        # Use cache if we already fetched this code.
        # Exception: World Open sub-events share entry list code "WO" but the
        # page shows aggregate totals across ALL sections. Applying that total
        # to individual sub-events (Under 13, top 6, lower) overwrites their
        # per-section entry_count. Skip cache for WO sub-events and keep the
        # index page's per-section count as-is.
        if code in fetched_cache:
            if 'world open' in name_lower:
                continue  # keep per-section entry_count from index page
            active, withdrawn = fetched_cache[code]
            t['withdrawal_count'] = withdrawn
            t['active_count'] = active
            continue

        url = ENTRY_LIST_URL_TEMPLATE.format(code=code, yy=yy)
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code != 200 or len(resp.text) < 1000:
                fetched_cache[code] = (t['entry_count'], 0)
                continue

            wd_match = _WD_PATTERN.search(resp.text)
            if wd_match:
                active = int(wd_match.group(1))
                withdrawn = int(wd_match.group(2))
                t['withdrawal_count'] = withdrawn
                t['active_count'] = active
                # Entry list is authoritative: override index page gross count
                t['entry_count'] = active + withdrawn
                fetched_cache[code] = (active, withdrawn)
                print(f"  {t['name']:<40s}  {active} active + {withdrawn} withdrawn")
            else:
                active_match = _ACTIVE_ONLY_PATTERN.search(resp.text)
                if active_match:
                    active = int(active_match.group(1))
                    t['active_count'] = active
                    fetched_cache[code] = (active, 0)
                else:
                    fetched_cache[code] = (t['entry_count'], 0)

            time.sleep(0.3)  # rate limit
        except requests.RequestException:
            fetched_cache[code] = (t['entry_count'], 0)
            continue

    # ── Invariant validation ──
    # Ensure active_count <= entry_count and active + withdrawn == entry
    repaired = 0
    for t in tournaments:
        ec, ac, wd = t['entry_count'], t['active_count'], t['withdrawal_count']
        if ac > ec:
            # Withdrawal scraper returned aggregate totals for a shared page;
            # revert to index-page gross count as the per-event truth.
            t['active_count'] = ec
            t['withdrawal_count'] = 0
            repaired += 1
        elif ec > 0 and ac + wd != ec:
            # Recompute withdrawal as the difference
            t['withdrawal_count'] = ec - ac
            repaired += 1
    if repaired:
        print(f"  Repaired {repaired} count invariant violations (active + wd != gross)")

    total_wd = sum(t['withdrawal_count'] for t in tournaments)
    print(f"  Total withdrawals found: {total_wd}")
    return tournaments


def init_driver():
    """Set up headless Chrome with polite identification and timeouts."""
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument(
        '--user-agent=CCA-Entry-Predictor/1.0 '
        '(chess tournament prediction tool; contact: github.com/HaterAndrew)'
    )
    # Only set binary_location if the local path exists; on GitHub Actions
    # the browser-actions/setup-chrome action puts chrome on PATH instead.
    local_chrome = '/usr/bin/google-chrome'
    if os.path.exists(local_chrome):
        opts.binary_location = local_chrome
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    return driver


def scrape_index(driver, max_retries=3, backoff=15):
    """
    Load CCA index page and extract all 2026 tournaments with their
    name, URL, dates, state, and entry count in a single pass.
    Retries up to max_retries times with backoff between attempts.
    """
    url = 'https://chessaction.com/CCA/index.php?vendor=Continental%20Chess%20Association'

    # Extract: link, name, start date, end date, state, entry count
    pattern = (
        r'<a href="(tournaments/index\.php\?view=[^"]+tid=[^"]+)">([^<]+)</a>'
        r'.*?<div class="text-muted small">'
        r'([A-Z][a-z]{2} \d{1,2}, \d{4})\s*-\s*([A-Z][a-z]{2} \d{1,2}, \d{4})'
        r'\s*(?:&nbsp;\s*)*State:\s*([^<]+?)\s*</div>'
        r'.*?Entry List \[(\d+)\]'
    )

    for attempt in range(1, max_retries + 1):
        try:
            rate_limit(min_delay=1.0, max_delay=2.0)
            print(f"Loading CCA index (attempt {attempt}/{max_retries}): {url}")
            driver.get(url)
            print("Waiting 10s for AJAX content...")
            time.sleep(10)

            page_source = driver.page_source
            matches = re.findall(pattern, page_source, re.DOTALL)

            if not matches:
                raise ValueError("Regex matched 0 tournaments — page may not have loaded")

            tournaments = []
            for rel_url, name, start_date, end_date, state, count in matches:
                if '2026' not in name and '2026' not in rel_url:
                    continue
                full_url = f'https://chessaction.com/{rel_url}'.replace('&amp;', '&')
                start_iso = datetime.strptime(start_date.strip(), '%b %d, %Y').strftime('%Y-%m-%d')
                end_iso = datetime.strptime(end_date.strip(), '%b %d, %Y').strftime('%Y-%m-%d')
                tournaments.append({
                    'name': name.strip(),
                    'url': full_url,
                    'start_date': start_iso,
                    'end_date': end_iso,
                    'state': state.strip(),
                    'entry_count': int(count),
                })

            print(f"Found {len(tournaments)} tournaments for 2026")
            return tournaments

        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                print(f"  Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                raise


def consolidate_world_open(tournaments):
    """
    Keep only 3 World Open sub-events (Under 13, top 6 sections, lower sections)
    as separate rows. Drop all other WO variants entirely.
    """
    result = []
    for t in tournaments:
        is_wo = 'world open' in t['name'].lower()
        if is_wo:
            # Only keep the 3 tracked sub-events
            if WO_KEEP_PATTERNS.search(t['name']):
                result.append(t)
            # else: drop silently (G/7, G/10, Blitz, Action, Women, etc.)
        else:
            result.append(t)
    return result


def load_existing_csv():
    """Load existing daily_scrape.csv, return list of dicts.

    Backfills active_count and withdrawal_count for older rows that
    predate those columns.
    """
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, 'r', newline='') as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if 'active_count' not in r or not r.get('active_count'):
            r['active_count'] = r.get('entry_count', '0')
        if 'withdrawal_count' not in r or not r.get('withdrawal_count'):
            r['withdrawal_count'] = '0'
    return rows


CSV_FIELDS = ['date', 'tournament_name', 'entry_count', 'active_count', 'withdrawal_count', 'url']


def save_csv(rows):
    """Write rows back to daily_scrape.csv."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def update_csv(tournaments):
    """
    Merge today's scraped data into the CSV. Idempotent: if today's row
    already exists for a tournament, update it rather than duplicating.
    """
    existing = load_existing_csv()

    # Index existing rows by (date, tournament_name)
    index = {(r['date'], r['tournament_name']): r for r in existing}

    # Upsert today's data
    for t in tournaments:
        key = (TODAY, t['name'])
        index[key] = {
            'date': TODAY,
            'tournament_name': t['name'],
            'entry_count': str(t['entry_count']),
            'active_count': str(t.get('active_count', t['entry_count'])),
            'withdrawal_count': str(t.get('withdrawal_count', 0)),
            'url': t['url'],
        }

    all_rows = sorted(index.values(), key=lambda r: (r['date'], r['tournament_name']))
    save_csv(all_rows)
    return all_rows


def sync_metadata(tournaments):
    """
    Update tournament_metadata.csv with dates scraped from chessaction.com.
    Updates existing 2026 rows AND adds new rows for tournaments that
    appear on chessaction but aren't in the CSV yet.
    Preserves fee and venue info already in the CSV.
    """
    if not os.path.exists(META_PATH):
        print("  No metadata CSV found — skipping metadata sync.")
        return

    with open(META_PATH, 'r', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        meta_rows = list(reader)

    # Build lookup of scraped dates by family name
    scraped = {}
    for t in tournaments:
        family = to_family(t['name'])
        scraped[family] = t

    # Track which scraped families already have a 2026 row
    existing_2026 = set()
    updated = 0
    for row in meta_rows:
        if row['year'] != '2026':
            continue
        family = row['family']
        existing_2026.add(family)
        if family not in scraped:
            continue

        t = scraped[family]
        old_start = row.get('start_date', '')
        old_end = row.get('end_date', '')

        if old_start != t['start_date'] or old_end != t['end_date']:
            print(f"  UPDATED {family}: {old_start}..{old_end} -> {t['start_date']}..{t['end_date']}")
            row['start_date'] = t['start_date']
            row['end_date'] = t['end_date']
            updated += 1

    # Add new rows for scraped tournaments missing from metadata
    added = 0
    for family, t in scraped.items():
        if family in existing_2026:
            continue
        new_row = {fn: '' for fn in fieldnames}
        new_row['family'] = family
        new_row['year'] = '2026'
        new_row['start_date'] = t['start_date']
        new_row['end_date'] = t['end_date']
        if 'venue_state' in fieldnames:
            new_row['venue_state'] = t.get('state', '')
        meta_rows.append(new_row)
        print(f"  ADDED {family}: {t['start_date']}..{t['end_date']}")
        added += 1

    if updated or added:
        with open(META_PATH, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(meta_rows)
        print(f"  Synced metadata: {updated} updated, {added} added to {META_PATH}")
    else:
        print("  All 2026 metadata dates match CCA — no changes needed.")


def print_comparison(all_rows):
    """Print today's counts vs yesterday's (if available)."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    today_rows = {r['tournament_name']: r for r in all_rows if r['date'] == TODAY}
    yesterday_data = {r['tournament_name']: int(r['entry_count'])
                      for r in all_rows if r['date'] == yesterday}

    print(f"\n{'='*82}")
    print(f"  DAILY SCRAPE SUMMARY — {TODAY}")
    print(f"{'='*82}")
    print(f"  {'Tournament':<36s} {'Gross':>6s} {'Active':>7s} {'WD':>4s} {'Delta':>8s}")
    print(f"  {'-'*36} {'-'*6} {'-'*7} {'-'*4} {'-'*8}")

    for name in sorted(today_rows.keys()):
        r = today_rows[name]
        gross = int(r['entry_count'])
        active = int(r.get('active_count', gross))
        wd = int(r.get('withdrawal_count', 0))
        if name in yesterday_data:
            delta = gross - yesterday_data[name]
            delta_str = f"+{delta}" if delta >= 0 else str(delta)
        else:
            delta_str = "new"
        wd_str = str(wd) if wd > 0 else ""
        print(f"  {name:<36s} {gross:>6d} {active:>7d} {wd_str:>4s} {delta_str:>8s}")

    for name in sorted(yesterday_data.keys()):
        if name not in today_rows:
            print(f"  {name:<36s} {'GONE':>6s} {'':>7s} {'':>4s} {'':>8s}")

    print(f"{'='*82}")
    print(f"  Total tournaments scraped: {len(today_rows)}")
    total_wd = sum(int(r.get('withdrawal_count', 0)) for r in today_rows.values())
    if total_wd > 0:
        print(f"  Total withdrawals across all tournaments: {total_wd}")
    print()


def run_scrape_pipeline():
    """
    Execute the full scrape-consolidate-save pipeline once.
    Returns normally on success; raises on any failure.
    """
    driver = None
    try:
        driver = init_driver()
        logger.info("Scraping CCA tournaments for %s ...", TODAY)

        # Step 1: Extract all data from index page (single page load)
        tournaments = scrape_index(driver)
        if not tournaments:
            raise ValueError("No 2026 tournaments found on CCA index page.")

        for t in tournaments:
            logger.info("  %s  %s - %s  [%d]",
                        t['name'].ljust(45), t['start_date'], t['end_date'], t['entry_count'])

        # Step 2: Scrape withdrawal counts from entry list pages
        scrape_withdrawals(tournaments)

        # Step 3: Filter World Open to only Under 13, top 6, lower sections
        consolidated = consolidate_world_open(tournaments)
        logger.info("Filtered to %d rows (kept 3 WO sub-events, dropped others)", len(consolidated))

        # Step 4: Update daily_scrape.csv (idempotent)
        all_rows = update_csv(consolidated)
        logger.info("Saved to %s", CSV_PATH)

        # Step 5: Sync dates to tournament_metadata.csv
        logger.info("── Metadata sync ──")
        sync_metadata(consolidated)

        # Step 6: Print comparison
        print_comparison(all_rows)

    finally:
        if driver:
            driver.quit()


def main():
    consecutive_failures = 0

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            logger.info("Pipeline attempt %d/%d", attempt, MAX_RETRY_ATTEMPTS)
            run_scrape_pipeline()
            logger.info("Pipeline succeeded on attempt %d", attempt)
            return  # success — exit

        except RETRY_EXCEPTIONS as exc:
            consecutive_failures += 1
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Attempt %d/%d failed (%s: %s). Retrying in %ds...",
                attempt, MAX_RETRY_ATTEMPTS, type(exc).__name__, exc, delay,
            )

            # Circuit breaker check
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                logger.critical(
                    "CIRCUIT BREAKER: %d consecutive pipeline failures. "
                    "Aborting to avoid repeated load on target site.",
                    consecutive_failures,
                )
                sys.exit(2)

            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(delay)

        except Exception as exc:
            # Non-retryable error — fail immediately
            logger.error("Non-retryable error: %s: %s", type(exc).__name__, exc)
            sys.exit(1)

    # Exhausted all retries
    logger.error(
        "All %d retry attempts exhausted. Scrape failed.", MAX_RETRY_ATTEMPTS
    )
    sys.exit(1)


if __name__ == '__main__':
    main()
