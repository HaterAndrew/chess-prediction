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


def _edition_key(tournament):
    """(family, 'YYYY') for a scraped tournament dict. Year is a string because
    that is how the metadata CSV holds it."""
    return cca_family(tournament['name']), str(tournament['year'])


def plan_sync(meta_rows, tournaments, fieldnames):
    """Apply scraped dates to metadata rows, matching on the edition.

    Returns (rows, changes). `rows` is `meta_rows` with dates updated in place
    plus a new row per scraped edition that had none; fee and venue columns on
    existing rows are left alone. `changes` is a list of human-readable lines,
    empty when nothing differed.
    """
    scraped = {_edition_key(t): t for t in tournaments}
    changes = []
    seen = set()

    for row in meta_rows:
        key = (row['family'], str(row['year']))
        seen.add(key)
        t = scraped.get(key)
        if t is None:
            continue
        old = (row.get('start_date', ''), row.get('end_date', ''))
        new = (t['start_date'], t['end_date'])
        if old == new:
            continue
        changes.append(f"UPDATED {key[0]} {key[1]}: {old[0]}..{old[1]} -> {new[0]}..{new[1]}")
        row['start_date'], row['end_date'] = new

    for key, t in scraped.items():
        if key in seen:
            continue
        new_row = {fn: '' for fn in fieldnames}
        new_row['family'], new_row['year'] = key
        new_row['start_date'] = t['start_date']
        new_row['end_date'] = t['end_date']
        if 'venue_state' in fieldnames:
            new_row['venue_state'] = t.get('state', '')
        meta_rows.append(new_row)
        changes.append(f"ADDED {key[0]} {key[1]}: {t['start_date']}..{t['end_date']}")

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
