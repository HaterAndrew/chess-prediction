"""Rows the integrity checks deliberately do not resolve to an edition.

Every exemption is an explicit list or a named rule, and every run reports
how many rows each one covered, so a check can never pass by skipping rows
silently. A new row that needs exempting is added here with its reason.
"""
from fees.codes import UNMAPPED_CODES
from shared.side_events import SIDE_EVENT_RE

# tournament_summary.csv tids 10-75: the oldest export rows, named "42nd
# annual Continental Open" and the like, with no tournament_year.
LEGACY_TID_RANGE = range(10, 76)

# Modern summary rows with no year that are not editions of any family.
NON_EDITION_TIDS = {
    1604: "Manhattan Blitz, a side event",
    3832: "a 2025 wait list, not an event",
    4023: "World Open Junior Octos, a side event",
    4024: "Philadelphia Octos, a side event",
}

# historical_tournaments.csv rows whose name year contradicts their own
# start_date; each has 0 entries and duplicates the real edition's row.
MISDATED_HISTORICAL_ROWS = {
    ("2018 New York State Championship", 2017),
    ("2017 Boston Chess Congress", 2016),
    ("2016 Bradley Open", 2015),
}


def summary_exemption(row):
    """The rule that exempts a summary row from resolution, or None."""
    if row["tid"] in NON_EDITION_TIDS:
        return "non-edition tid"
    if row["tid"] in LEGACY_TID_RANGE:
        return "legacy tid 10-75"
    return None


def fee_exemption(code):
    """Blitz side-event flyers share the parent's code plus "b" and carry no
    advance fee schedule (fees/codes.UNMAPPED_CODES)."""
    return "side-event flyer" if code in UNMAPPED_CODES else None


def historical_exemption(row):
    if (row["tournament_name"], row["year"]) in MISDATED_HISTORICAL_ROWS:
        return "name year contradicts start_date"
    if SIDE_EVENT_RE.search(str(row["tournament_name"])):
        return "side event"
    return None
