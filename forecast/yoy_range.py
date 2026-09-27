"""The range is no wider than last year's final alone would make it.

An edition's final lands within a known spread of the edition before it.
yoy_arms measures that spread on finished editions: the two log arms from
the median year-over-year change down to its 10th percentile and up to its
90th. A forecast that knows the family's past finals, and the count on top,
should say no less than they do alone, so cap_range holds each side of the
range to the arm. It only narrows, and only for an event with MIN_HISTORY
past finals: with fewer the point itself is unsure and the cap cost
coverage. On the walk-forward it lowered the interval score by 0.126 +/-
0.013 at T-28 and beyond and by 0.018 +/- 0.003 inside two weeks, in every
season (#185).
"""
import math
from dataclasses import replace

import numpy as np

# Editions smaller than this move too much in proportion to measure the spread.
MIN_FINAL = 30
# Two finals more than this many seasons apart are not consecutive editions.
MAX_GAP_YEARS = 2
# Fewer pairs than this measure no spread.
MIN_PAIRS = 30
# The cap applies to an event with at least this many past finals.
MIN_HISTORY = 2


def yoy_arms(finished):
    """(below, above): the log arms of the year-over-year change, or None.

    finished: settled in-person editions, one row each, with family,
    tournament_year and final_count.
    """
    rows = finished.dropna(subset=['final_count', 'tournament_year'])
    rows = rows[rows['final_count'] >= MIN_FINAL].sort_values(['family', 'tournament_year'])
    before = rows.groupby('family')[['final_count', 'tournament_year']].shift(1)
    gap = rows['tournament_year'] - before['tournament_year']
    pairs = gap.between(1, MAX_GAP_YEARS)
    if pairs.sum() < MIN_PAIRS:
        return None
    change = np.log(rows.loc[pairs, 'final_count'] / before.loc[pairs, 'final_count'])
    low, mid, high = np.percentile(change, [10, 50, 90])
    return float(mid - low), float(high - mid)


def cap_range(forecast, obs, history, arms, min_history=MIN_HISTORY):
    """The forecast with each side of its range held to the year-over-year arm.

    min_history: the past finals an event needs for the cap; a point moved
    toward the last final (forecast.known_final) needs only that one.
    """
    if arms is None or len(history or ()) < min_history or forecast.point <= 0:
        return forecast
    below, above = arms
    low = max(forecast.low, forecast.point * math.exp(-below))
    high = min(forecast.high, forecast.point * math.exp(above))
    if low == forecast.low and high == forecast.high:
        return forecast
    low = min(max(round(low), obs.count), forecast.point)
    return replace(forecast, low=low, high=max(round(high), forecast.point))
