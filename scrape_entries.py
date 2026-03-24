"""
Daily scraper for CCA tournament entry counts from chessaction.com.

Scrapes all 2026 tournaments from the CCA index page, extracting:
  - Entry counts from "Entry List [NNN]" pattern
  - Event dates (start/end) directly from CCA listings
  - State/location

All data is extracted from the index page in a single load — no need to
visit individual tournament pages.

World Open sub-events (excluding Blitz/Action/G variants) are consolidated
into a single "World Open" row by summing their counts.

Tournament dates are synced to output/tournament_metadata.csv so the
predictor always reflects the official CCA schedule.
"""

import os
import re
import sys
import time
import csv
from datetime import date, datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
CSV_PATH = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
META_PATH = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
TODAY = date.today().isoformat()

# Patterns to exclude from World Open consolidation
WO_EXCLUDE_PATTERNS = re.compile(r'blitz|action|g\s*\d|g/\d|g\s+50', re.IGNORECASE)

# CCA name -> canonical family name (for cases where CCA renamed a tournament)
CCA_FAMILY_ALIASES = {
    'Atlantic City Open': 'Atlantic Open',
}

def to_family(name):
    """Strip year prefix from CCA tournament name and apply canonical aliases."""
    family = re.sub(r'^\d{4}\s+', '', name).strip()
    return CCA_FAMILY_ALIASES.get(family, family)


def init_driver():
    """Set up headless Chrome."""
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    # Only set binary_location if the local path exists; on GitHub Actions
    # the browser-actions/setup-chrome action puts chrome on PATH instead.
    local_chrome = '/usr/bin/google-chrome'
    if os.path.exists(local_chrome):
        opts.binary_location = local_chrome
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


def scrape_index(driver):
    """
    Load CCA index page and extract all 2026 tournaments with their
    name, URL, dates, state, and entry count in a single pass.
    """
    url = 'https://chessaction.com/CCA/index.php?vendor=Continental%20Chess%20Association'
    print(f"Loading CCA index: {url}")
    driver.get(url)
    print("Waiting 10s for AJAX content...")
    time.sleep(10)

    page_source = driver.page_source

    # Extract: link, name, start date, end date, state, entry count
    pattern = (
        r'<a href="(tournaments/index\.php\?view=[^"]+tid=[^"]+)">([^<]+)</a>'
        r'.*?<div class="text-muted small">'
        r'([A-Z][a-z]{2} \d{1,2}, \d{4})\s*-\s*([A-Z][a-z]{2} \d{1,2}, \d{4})'
        r'\s*(?:&nbsp;\s*)*State:\s*([^<]+?)\s*</div>'
        r'.*?Entry List \[(\d+)\]'
    )
    matches = re.findall(pattern, page_source, re.DOTALL)

    tournaments = []
    for rel_url, name, start_date, end_date, state, count in matches:
        if '2026' not in name and '2026' not in rel_url:
            continue
        full_url = f'https://chessaction.com/{rel_url}'.replace('&amp;', '&')
        # Parse dates to ISO format
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


def consolidate_world_open(tournaments):
    """
    Sum all 'World Open' variant entries (excluding Blitz/Action/G variants)
    into a single 'World Open' row. Non-World-Open rows pass through unchanged.
    """
    wo_total = 0
    wo_entry = None
    other = []

    for t in tournaments:
        is_wo = 'world open' in t['name'].lower()
        is_excluded = WO_EXCLUDE_PATTERNS.search(t['name']) if is_wo else False

        if is_wo and not is_excluded:
            wo_total += t['entry_count']
            # Use the broadest date range (top sections) as the World Open dates
            if wo_entry is None or 'top' in t['name'].lower():
                wo_entry = dict(t)
        else:
            other.append(t)

    if wo_total > 0 and wo_entry:
        wo_entry['name'] = '2026 World Open'
        wo_entry['entry_count'] = wo_total
        other.append(wo_entry)

    return other


def load_existing_csv():
    """Load existing daily_scrape.csv, return list of dicts."""
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, 'r', newline='') as f:
        return list(csv.DictReader(f))


def save_csv(rows):
    """Write rows back to daily_scrape.csv."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'tournament_name', 'entry_count', 'url'])
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

    today_data = {r['tournament_name']: int(r['entry_count'])
                  for r in all_rows if r['date'] == TODAY}
    yesterday_data = {r['tournament_name']: int(r['entry_count'])
                      for r in all_rows if r['date'] == yesterday}

    print(f"\n{'='*70}")
    print(f"  DAILY SCRAPE SUMMARY — {TODAY}")
    print(f"{'='*70}")
    print(f"  {'Tournament':<40s} {'Count':>6s} {'Delta':>8s}")
    print(f"  {'-'*40} {'-'*6} {'-'*8}")

    for name in sorted(today_data.keys()):
        count = today_data[name]
        if name in yesterday_data:
            delta = count - yesterday_data[name]
            delta_str = f"+{delta}" if delta >= 0 else str(delta)
        else:
            delta_str = "new"
        print(f"  {name:<40s} {count:>6d} {delta_str:>8s}")

    for name in sorted(yesterday_data.keys()):
        if name not in today_data:
            print(f"  {name:<40s} {'GONE':>6s} {'':>8s}")

    print(f"{'='*70}")
    print(f"  Total tournaments scraped: {len(today_data)}")
    print()


def main():
    driver = None
    try:
        driver = init_driver()
        print(f"Scraping CCA tournaments for {TODAY}...")

        # Step 1: Extract all data from index page (single page load)
        tournaments = scrape_index(driver)
        if not tournaments:
            print("WARNING: No 2026 tournaments found on CCA index page.")
            print("Site may be down or page structure changed.")
            sys.exit(1)

        for t in tournaments:
            print(f"  {t['name']:<45s} {t['start_date']} - {t['end_date']}  [{t['entry_count']}]")

        # Step 2: Consolidate World Open sub-events
        consolidated = consolidate_world_open(tournaments)
        print(f"\nConsolidated to {len(consolidated)} rows (World Open sub-events combined)")

        # Step 3: Update daily_scrape.csv (idempotent)
        all_rows = update_csv(consolidated)
        print(f"Saved to {CSV_PATH}")

        # Step 4: Sync dates to tournament_metadata.csv
        print(f"\n── Metadata sync ──")
        sync_metadata(consolidated)

        # Step 5: Print comparison
        print_comparison(all_rows)

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()


if __name__ == '__main__':
    main()
