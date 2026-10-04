"""Sync scraped CCA dates into tournament_metadata.csv.

Extracted from scrapers/entries.py on 2026-09-17, when the sync became
edition-aware. A metadata row is one edition, (family, year). The old sync
keyed on the family alone under a literal year, so the 2027 Atlantic City Open
either could not get a row or would have overwritten the 2026 edition's dates.

`plan_sync` is pure (rows in, rows out); `sync_metadata` is the CSV adapter.
"""
import csv
import os

from shared.paths import OUTPUT_DIR
from tournament_aliases import cca_family

META_PATH = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")


def _edition_key(family, year):
    """(spelling, 'YYYY'). Year is a string because that is how the metadata
    CSV holds it. The spelling ignores commas, spacing and case, so CCA's
    "World Open, top 6 sections" card updates the "World Open top 6
    sections" row instead of adding a second row for the same edition
    (found 2026-10-04).

    It keeps an "(in <place>)" suffix and does not fold lineage renames
    (canonicalize_family maps "Philadelphia Open" to "DC Open"). sitebuild
    looks a metadata row's scrape counts up by the row's own spelling, so
    folding a respelled card onto an older row would leave that row reading
    the old name's frozen count. A respelled card gets its own row instead,
    and the edition registry fails the run on the second row for one edition.
    """
    spelling = ' '.join(family.replace(',', ' ').split()).casefold()
    return spelling, str(year)


def _index_scraped(tournaments):
    """Scraped cards by edition key, and the keys two cards claimed with
    different dates. Neither card of such a pair is applied: picking one
    would drop the other's dates without a trace."""
    scraped, clashes = {}, set()
    for t in tournaments:
        key = _edition_key(cca_family(t['name']), t['year'])
        prior = scraped.setdefault(key, t)
        if (prior['start_date'], prior['end_date']) != (t['start_date'], t['end_date']):
            clashes.add(key)
    return {k: t for k, t in scraped.items() if k not in clashes}, sorted(clashes)


def _new_row(t, fieldnames):
    row = {fn: '' for fn in fieldnames}
    row['family'], row['year'] = cca_family(t['name']), str(t['year'])
    row['start_date'], row['end_date'] = t['start_date'], t['end_date']
    if 'venue_state' in fieldnames:
        row['venue_state'] = t.get('state', '')
    return row


def plan_sync(meta_rows, tournaments, fieldnames):
    """Apply scraped dates to metadata rows, matching on the edition key.

    Returns (rows, changes). `rows` is `meta_rows` with dates updated in place
    plus a new row per scraped edition that had none, under the scraper's
    spelling; fee and venue columns on existing rows are left alone.
    `changes` is a list of human-readable lines, empty when nothing differed.
    """
    scraped, clashes = _index_scraped(tournaments)
    changes = [f"WARNING: two scraped cards name {k[0]!r} {k[1]} with different dates; "
               f"neither applied" for k in clashes]
    seen = set()

    for row in meta_rows:
        key = _edition_key(row['family'], row['year'])
        seen.add(key)
        t = scraped.get(key)
        if t is None:
            continue
        old = (row.get('start_date', ''), row.get('end_date', ''))
        new = (t['start_date'], t['end_date'])
        if old == new:
            continue
        changes.append(f"UPDATED {row['family']} {key[1]}: {old[0]}..{old[1]} -> {new[0]}..{new[1]}")
        row['start_date'], row['end_date'] = new

    for key, t in scraped.items():
        if key in seen:
            continue
        row = _new_row(t, fieldnames)
        meta_rows.append(row)
        changes.append(f"ADDED {row['family']} {key[1]}: {t['start_date']}..{t['end_date']}")

    return meta_rows, changes


def sync_metadata(tournaments, meta_path=None):
    """Update tournament_metadata.csv with dates scraped from chessaction.com.

    Updates the row of each scraped edition and adds a row for an edition that
    appears on chessaction but is not in the CSV yet. Preserves fee and venue
    info already in the CSV.
    """
    meta_path = meta_path or META_PATH
    if not os.path.exists(meta_path):
        print("  No metadata CSV found — skipping metadata sync.")
        return

    with open(meta_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        meta_rows = list(reader)

    meta_rows, changes = plan_sync(meta_rows, tournaments, fieldnames)
    if not changes:
        print("  All scraped editions match the metadata dates — no changes needed.")
        return

    for line in changes:
        print(f"  {line}")
    with open(meta_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(meta_rows)
    print(f"  Synced metadata: {len(changes)} change(s) written to {meta_path}")
