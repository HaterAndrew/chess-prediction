"""Weekly standings scrape: a row for each ended edition the file lacks.

For each edition of the current or previous season that has ended and has
no row in output/historical_standings.csv, find its chessevents.com event,
read its main sections' USCF IDs, and count it with standings.count_rule,
the rule the cca-site import built the file with. New rows carry source
"chessevents". History older than the previous season comes from
scripts/import_ccasite_standings.py.

An edition CCA has not published yet is asked for again next week. A page
that fails to load or parse is a WARNING, and that edition stays due.

Output: output/historical_standings.csv
  Columns: tournament_name, year, total_players, num_sections, sections, source
  (sections is a JSON string of {section name: rows} for the counted sections)
"""
import os
import time
from datetime import date

import requests

from registry.keys import standings_edition_key
from scraper_utils import polite_session
from scrapers.chessevents_standings import StandingsUnreadable, read_edition, read_events
from shared.paths import OUTPUT_DIR
from shared.season import CURRENT_SEASON
from standings.due import editions_due
from standings.families import Folder, folder_spellings, legacy_standings_name
from standings.importer import build_rows
from standings.output_files import (STANDINGS_CSV, ended_editions, read_standings,
                                    spelling_years, write_standings)
from standings.world_open import LOWER, SLUG as WORLD_OPEN, TOP6
from tournament_aliases import canonicalize_family

SOURCE = "chessevents"

# Wall-clock budget (seconds). Exit cleanly before the CI step timeout so any
# rows already counted are still written. Overridable for local runs.
TIME_BUDGET_SEC = int(os.environ.get("SCRAPE_TIME_BUDGET_SEC", 50 * 60))


def _slug_of(family, spellings):
    """The chessevents event a family spelling belongs to, or None."""
    if canonicalize_family(family) in {canonicalize_family(TOP6), canonicalize_family(LOWER)}:
        return WORLD_OPEN
    slugs = sorted(slug for slug, owned in spellings.items() if family in owned)
    return slugs[0] if len(slugs) == 1 else None


def _editions_to_read(due, spellings):
    """{(slug, year): edition keys}, and the due families with no event."""
    wanted, unmatched = {}, []
    for key, family in sorted(due.items()):
        slug = _slug_of(family, spellings)
        if slug is None:
            unmatched.append(f"{family} {key[1]}")
        else:
            wanted.setdefault((slug, key[1]), set()).add(key)
    return wanted, unmatched


def _count(session, slug, year, keys, folders, spellings, years):
    """The new rows for one chessevents edition, or [] when not yet readable."""
    try:
        edition = read_edition(session, slug, year)
    except (StandingsUnreadable, requests.RequestException) as exc:
        print(f"WARNING: standings for {slug} {year} not read: {exc}")
        return []
    if edition is None:
        print(f"  {slug} {year}: standings not published yet")
        return []
    report = build_rows([edition], folders, spellings, years)
    for note in report.notes:
        print(f"WARNING: standings {note}")
    rows = [r for r in report.rows if standings_edition_key(r["tournament_name"], r["year"]) in keys]
    for row in rows:
        row["source"] = SOURCE
        print(f"  {row['tournament_name']} {row['year']}: {row['total_players']} players "
              f"in {row['num_sections']} sections")
    return rows


def scrape_all(output_dir=OUTPUT_DIR, today=None):
    start = time.monotonic()
    path = os.path.join(output_dir, STANDINGS_CSV)
    rows = read_standings(path)
    have = {standings_edition_key(r["tournament_name"], int(r["year"])) for r in rows}
    due = editions_due(ended_editions(output_dir), have, today or date.today(),
                       first_year=CURRENT_SEASON - 1)
    if not due:
        print("Every ended edition has a standings row.")
        return
    session = polite_session()
    events = read_events(session)
    folders = [Folder(slug, (name, legacy_standings_name(slug))) for slug, name in events.items()]
    years = spelling_years(output_dir)
    spellings = folder_spellings(folders, years, canonicalize_family)
    wanted, unmatched = _editions_to_read(due, spellings)
    if unmatched:
        print(f"{len(unmatched)} ended edition(s) have no chessevents event: {'; '.join(unmatched)}")
    added = []
    for (slug, year), keys in sorted(wanted.items()):
        if time.monotonic() - start >= TIME_BUDGET_SEC:
            print(f"[BUDGET] {TIME_BUDGET_SEC}s budget spent; the rest stay due")
            break
        added += _count(session, slug, year, keys, folders, spellings, years)
    if added:
        write_standings(path, rows + added)
    print(f"{len(added)} standings row(s) added; {len(due) - len(added)} edition(s) still due.")


if __name__ == "__main__":
    scrape_all()
