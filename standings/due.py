"""Which editions the weekly scrape owes a standings row.

An edition is due once it has ended and the standings file has no row for
its edition key. Only the current and previous seasons are looked for:
older editions came from the cca-site import, and an edition chessevents
never published would otherwise be asked for every week. Side-event
families are never due.
"""
from registry.keys import summary_edition_key
from shared.side_events import SIDE_EVENT_RE


def editions_due(editions, have, today, first_year):
    """editions: (family, year, end date) per metadata row; have: edition
    keys the file already holds. Returns {edition key: family spelling}."""
    due = {}
    for family, year, end in editions:
        if year < first_year or end >= today or SIDE_EVENT_RE.search(family):
            continue
        key = summary_edition_key(family, year)
        if key not in have:
            due.setdefault(key, family)
    return due
