"""When the walk-forward backtest refits, and which fit serves each forecast.

The production model refits every night. Refitting per forecast date would
cost a fit per (event, horizon); refitting on the first of each month and
serving every forecast dated that month from it keeps the backtest within
a month of production's freshness at a fraction of the cost.
"""
from bisect import bisect_right

import pandas as pd

# The first season the walk-forward grades: the last four as they roll.
FIRST_SEASON = 2023


def monthly_cutoffs(first_season, through):
    """The first of every month from January of first_season through `through`."""
    return list(pd.date_range(pd.Timestamp(int(first_season), 1, 1),
                              pd.Timestamp(through).normalize(), freq='MS'))


def cutoff_for(d, cutoffs):
    """The latest cutoff on or before d, or None when d precedes them all."""
    i = bisect_right(cutoffs, pd.Timestamp(d)) - 1
    return cutoffs[i] if i >= 0 else None


def forecast_points(events, horizons, cutoffs, through):
    """(tid, T, forecast date, cutoff) for every event and horizon.

    events: rows with tid and start. A forecast is dated start - T; one dated
    after `through` or before the first cutoff is not made.
    """
    through = pd.Timestamp(through).normalize()
    points = []
    for tid, start in zip(events['tid'], events['start']):
        for T in horizons:
            d = start - pd.Timedelta(days=int(T))
            cutoff = cutoff_for(d, cutoffs)
            if cutoff is None or d > through:
                continue
            points.append((tid, int(T), d, cutoff))
    return points
