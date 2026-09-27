"""Any edition's entry count so many days before its start, read as its curve allows.

The walk-forward reads an event's count on each forecast date, and both it and
the live cards read the family's last edition at the same horizon for the
pickup forecast (forecast.pickup). An export curve is exact through the
export's snapshot; a scraped curve is a set of observations (corpus.coverage).
"""
from dataclasses import dataclass

import pandas as pd

from corpus.calendar import event_calendar
from corpus.coverage import count_as_of
from shared.curves import has_curve


def snapshot_date(summary):
    """When the registration export was taken: the latest registration it holds."""
    col = 'snapshot_last_reg' if 'snapshot_last_reg' in summary.columns else 'last_reg'
    return pd.to_datetime(summary[col], errors='coerce').max().normalize()


@dataclass(frozen=True)
class EditionCounts:
    """Every edition's curve, the horizon through which its export is exact, and
    which curves the scrape alone built (observations, never exact)."""
    by_tid: dict
    bounds: dict
    scraped: frozenset
    empty: pd.DataFrame

    def count(self, tid, T):
        """The edition's count T days out, read as count_as_of reads its kind of curve."""
        return count_as_of(self.by_tid.get(tid, self.empty), T, exact=tid not in self.scraped,
                           exact_until_T=self.bounds.get(tid))


def edition_counts(corpus):
    """Curves by edition; one still running at the export snapshot is exact only up to it."""
    snapshot = snapshot_date(corpus.summary)
    cal = event_calendar(corpus.summary, corpus.meta)
    bounds = {tid: int((start - snapshot).days)
              for tid, start, end in zip(cal['tid'], cal['start'], cal['end'])
              if pd.notna(start) and not end < snapshot}
    return edition_counts_from(corpus.summary, corpus.daily, bounds)


def edition_counts_from(summary, daily, bounds=None):
    """Curves by edition from a summary and its daily counts.

    bounds: the horizon through which each running edition's export is exact;
    None for finished editions, which are exact throughout.
    """
    s = summary
    scraped = frozenset(s.loc[has_curve(s) & ~s['has_timestamps'].fillna(False).astype(bool), 'tid'])
    return EditionCounts(dict(tuple(daily.groupby('tid'))), bounds or {}, scraped,
                         daily.iloc[0:0])
