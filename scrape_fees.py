"""
Scrape early bird deadlines and fee tiers from chesstour.com flyer pages.

Strategy:
  1. Attempt to discover tournament flyer links from chessevents.com.
  2. Brute-force common tournament code/year combos on chesstour.com.
  3. Parse the messy old-school HTML for fee tiers, deadlines, and prize fund.

Output: output/tournament_fees.csv
"""

import csv
import logging
import os
import sys

from fees.discover import (  # noqa: F401
    TOURNAMENT_CODES,
    YEAR_SUFFIXES,
    discover_from_chessevents,
    fetch,
    generate_candidate_urls,
    probe_urls,
)
from fees.parse import parse_flyer  # noqa: F401
from fees.patterns import EARLY_BIRD_MIN_GAP_DAYS  # noqa: F401
from shared.paths import OUTPUT_DIR

CSV_PATH = os.path.join(OUTPUT_DIR, "tournament_fees.csv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


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

    # Bridge the scraped flyer fees into the family-keyed tournament_metadata.csv
    # the prediction path reads. Without this, fees sit unused in
    # tournament_fees.csv (the gap the data-health scan surfaced — seven
    # near-events showed null fees that were already scraped here). Lazy import
    # avoids a scrape_fees <-> validate_fees import cycle; non-fatal.
    try:
        from merge_fees import merge_fees
        merge_fees()
    except Exception as e:
        log.warning("fee->metadata merge failed: %s", e)
        # v5 Cat F: the log.warning format ("WARNING " padded, no colon) is
        # invisible to auto_update._harvest_warnings, so a failed merge never
        # reached audit_warnings.json. Print the harvestable form too.
        print(f"WARNING: fee->metadata merge failed: {e}")


if __name__ == "__main__":
    main()
