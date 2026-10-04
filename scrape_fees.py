"""
Scrape early bird deadlines and fee tiers from chesstour.com flyer pages.

Strategy:
  1. Attempt to discover tournament flyer links from chessevents.com.
  2. Brute-force common tournament code/year combos on chesstour.com.
  3. Parse the messy old-school HTML for fee tiers, deadlines, and prize fund.

Output: output/tournament_fees.csv
"""

import logging
import os
import sys
from datetime import date

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
from fees.store import read_fees, upsert, write_fees
from registry.keys import flyer_code
from shared.paths import OUTPUT_DIR

CSV_PATH = os.path.join(OUTPUT_DIR, "tournament_fees.csv")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_live(live):
    """(parsed rows, URLs of live pages that did not parse)."""
    parsed, unparsed = [], []
    for url, resp in sorted(live.items()):
        # chesstour.com pages are often latin-1 encoded
        resp.encoding = resp.apparent_encoding or "latin-1"
        record = parse_flyer(resp.text, url)
        if record:
            parsed.append(record)
            log.info("  PARSED  %s  →  %s", url, record["tournament_name"])
        else:
            unparsed.append(url)
    return parsed, unparsed


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    existing = read_fees(CSV_PATH)

    # Every flyer already on file is probed again, with the mapped codes for
    # this season and next and whatever chessevents.com links to.
    candidates = generate_candidate_urls(row["url"] for row in existing)
    candidates |= discover_from_chessevents()
    log.info("Total candidate URLs: %d", len(candidates))

    log.info("Probing candidates (this may take a few minutes) …")
    live = probe_urls(candidates)
    log.info("Found %d live flyer pages", len(live))
    if not live:
        log.warning("No live chesstour.com pages found. CSV not written.")
        sys.exit(0)

    parsed, unparsed = _parse_live(live)
    # chessevents.com also links help pages (Byes.htm, taxes.htm); only
    # <code><yy>.htm pages are flyers.
    unparsed = [url for url in unparsed if flyer_code(url)]
    if unparsed:
        print(f"{len(unparsed)} live flyer(s) did not parse: {', '.join(unparsed)}")
    if not parsed:
        log.warning("Parsed 0 records — CSV not written.")
    else:
        rows = upsert(existing, parsed, date.today().isoformat())
        write_fees(CSV_PATH, rows)
        log.info("Wrote %d rows (%d parsed this run) to %s", len(rows), len(parsed), CSV_PATH)

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
