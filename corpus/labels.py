"""Whether an edition's final count can be graded against.

FINAL: the export was taken after the event ended, or the nightly scrape
followed registration to its close: it ran on or after the last day, and in
the WATCH_DAYS before that day it never missed more than CARRY_DAYS in a row,
counting the days before its first scrape in that window.
PROVISIONAL: finished, but neither source saw registration close.
OPEN: not finished.
"""
import pandas as pd

from corpus.coverage import CARRY_DAYS

FINAL, PROVISIONAL, OPEN = 'final', 'provisional', 'open'
WATCH_DAYS = 14


def edition_key(name):
    """An edition's name with commas and repeated spaces dropped: the export writes
    "2026 World Open  top 6 sections" where the scrape writes "2026 World Open, top 6
    sections"."""
    return ' '.join(str(name).replace(',', ' ').split())


def scrape_dates(scrape):
    """{edition key: sorted days the scrape counted it}."""
    if scrape is None or scrape.empty:
        return {}
    days = pd.to_datetime(scrape['date']).dt.normalize()
    return {key: sorted(set(d)) for key, d in days.groupby(scrape['tournament_name'].map(edition_key))}


def watched_to_close(days, end):
    """The scrape ran on or after `end`, with no gap over CARRY_DAYS in the WATCH_DAYS before it."""
    if not days or days[-1] < end:
        return False
    since = end - pd.Timedelta(days=WATCH_DAYS)
    before = [d for d in days if d < since]
    chain = before[-1:] + [d for d in days if since <= d <= end]
    chain += [d for d in days if d > end][:1]
    if not chain or (chain[0] - since).days > CARRY_DAYS:
        return False
    return all((b - a).days <= CARRY_DAYS + 1 for a, b in zip(chain, chain[1:]))


def final_labels(events, today, snapshot, days_by_name):
    """FINAL, PROVISIONAL or OPEN for each event (columns end, tournament_name)."""
    def label(end, name):
        if not end < today:
            return OPEN
        if end < snapshot or watched_to_close(days_by_name.get(name, []), end):
            return FINAL
        return PROVISIONAL
    return pd.Series([label(e, edition_key(n)) for e, n in zip(events['end'], events['tournament_name'])],
                     index=events.index, dtype=object)
