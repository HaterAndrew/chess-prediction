"""output/tournament_fees.csv, one row per flyer URL.

Until 2026-10-04 every weekly run rewrote the file from the flyers it found
that week, and chessevents.com stops listing an event once it is over, so a
flyer fell out of the file while its page stayed up: 27 rows of 2026 events
were gone by October. A run now updates the rows it parsed and keeps the
rest; last_seen is the date a run last parsed that flyer.
"""
import csv
import os

COLUMNS = [
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
    "last_seen",
]


def upsert(existing, parsed, seen_on):
    """existing rows updated by this run's parses (dicts keyed like COLUMNS),
    sorted by URL. Rows this run did not parse keep their values and date."""
    by_url = {row["url"]: row for row in existing}
    for row in parsed:
        by_url[row["url"]] = dict(row, last_seen=seen_on)
    return [by_url[url] for url in sorted(by_url)]


def read_fees(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_fees(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)   # csv's \r\n, as committed
        writer.writeheader()
        writer.writerows(rows)
