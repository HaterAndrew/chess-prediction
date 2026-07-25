"""Shared helpers used across the daily pipeline scripts.

Single source of truth for predicates that the perf eval, website model
fitting, recalibration, and walk-in multiplier scripts must all agree on.
"""
import pandas as pd


def is_event_complete(end_date, today=None):
    """A tournament is 'complete' iff its event end_date is strictly in the past.

    Mid-event days (today == end_date) count as in-progress: late entries and
    walk-ins can still arrive on the last day, so summary.final_count is not
    yet authoritative.

    Returns False for NaT / None / unparseable end_dates (unknown = not safe
    to treat as complete).
    """
    if end_date is None:
        return False
    end = pd.to_datetime(end_date, errors='coerce')
    if pd.isna(end):
        return False
    if today is None:
        today = pd.Timestamp.now().normalize()
    return end < today


def build_chart_series(tid, daily, current_count, is_live=False):
    """Build one tournament's [day_from_start, cumulative] chart series.

    Extracted from 04d_website_data_v2 so it can be regression-tested in
    isolation (see tests/test_daily_data_integrity.py). Given the reanchored
    `daily` frame, dedupe to the highest count at each T, convert T (days
    before event start) to day_from_start (0 = earliest scrape), and drop any
    non-increasing points (a cumulative count can only rise).

    v3 N1 (audit/AUDIT_2026-07-25.md): the old A4 "3x-jump backstop" here
    rescaled *every earlier point* by the jump ratio when it saw a >3x step.
    A missing scrape day exposed a benign gap and that rescale multiplied real
    observed history by 4.6x (Bradley Open shipped 625 vs a true 197). The
    backstop is now WARN-ONLY: it flags the anomaly (harvested into
    audit_warnings.json) but never mutates the observed counts.
    """
    tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(tid_daily) == 0:
        return [[0, int(current_count)]]

    max_T = tid_daily['T'].max()
    by_T = {}
    for _, d in tid_daily.iterrows():
        T = int(d['T'])
        count = int(d['cum_regs'])
        if T not in by_T or count > by_T[T]:
            by_T[T] = count
    daily_data = [[int(max_T - T), by_T[T]] for T in sorted(by_T.keys(), reverse=True)]
    daily_data.sort(key=lambda x: x[0])

    # A4 anomaly detector — WARN-ONLY (v3 N1). A >3x jump between adjacent points
    # signals a misplaced archive/scrape point upstream; surface it, do not rescale.
    for i in range(1, len(daily_data)):
        if daily_data[i][1] > daily_data[i - 1][1] * 3 and daily_data[i][1] > 50:
            print(f"WARNING: A4 3x-jump detected for tid={tid}: point {i} "
                  f"({daily_data[i][1]}) > 3x prior ({daily_data[i - 1][1]}); "
                  f"left unmodified (warn-only, see audit/AUDIT_2026-07-25.md).")
            break

    # Monotone cleaner: keep only non-decreasing points (cumulative can't fall).
    peak = 0
    cleaned = []
    for pt in daily_data:
        if pt[1] >= peak:
            peak = pt[1]
            cleaned.append(pt)
    daily_data = cleaned

    # Post-build invariant (v3 N1): no chart point on a live card may exceed the
    # scraped total — net cumulative registrations cannot outnumber the current
    # count. A violation means the series is misanchored upstream.
    if is_live and daily_data:
        max_pt = max(pt[1] for pt in daily_data)
        if max_pt > current_count:
            print(f"WARNING: daily_data max ({max_pt}) exceeds current_count "
                  f"({current_count}) for tid={tid}; chart series is misanchored.")
    return daily_data
