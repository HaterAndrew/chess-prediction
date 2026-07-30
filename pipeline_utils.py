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


# How often each clamp branch fired since import. The whole v3 audit theme is
# heuristics silently overriding real values, so the clamp keeps a tally the
# callers can print rather than mutating predictions invisibly. Reset with
# reset_clamp_stats() when measuring a single run.
_CLAMP_STATS = {'calls': 0, 'blend-low': 0, 'recentre-low': 0,
                'damp-high': 0, 'floor-current-count': 0}


def reset_clamp_stats():
    for k in _CLAMP_STATS:
        _CLAMP_STATS[k] = 0


def clamp_stats():
    return dict(_CLAMP_STATS)


def apply_plausibility_clamp(point, ci_lo, ci_hi, current_count, hist_counts,
                             days_remaining):
    """Damp an estimate that sits far outside the family's historical range.

    Extracted from 04d_website_data_v2 so the clamp is testable in isolation
    and so eval and display can share one code path.

    Returns the (point, ci_lo, ci_hi) triple to publish. The clamp blends
    toward the historical median when the model lands implausibly high or low,
    carrying the interval with the point by scaling both arms proportionally.

    v3 N2 (audit/AUDIT_2026-07-25.md): the clamp used to be able to publish a
    final estimate BELOW the entry count already scraped. With history topping
    out at 100 and 400 entries already in, `point > hist_max*3` rewrote the
    estimate to `hist_max*1.5` == 150 -- i.e. the site predicted a final of 150
    for an event that had already taken 400 entries. A cumulative registration
    total cannot fall, so `current_count` is a hard floor on any published
    estimate. The clamp now applies that floor and warns when it binds, because
    a binding floor means the family's history no longer describes this event
    (a genuine surge) and the ratio model needs re-fitting, not silent damping.
    """
    hist_counts = [c for c in hist_counts if c is not None]

    def _reanchor(old_point, new_point, lo, hi):
        """Move the interval with the point, preserving each arm's PROPORTION.

        v3 T2/N3: this used to recentre symmetrically (point +/- width/2). The
        underlying interval is lognormal — its upper arm is legitimately longer
        than its lower — so symmetrising it threw away the skew the model had
        fitted. Scaling both arms by the same factor the point moved keeps the
        relative uncertainty intact.

        No measured effect on the current published grade: the clamp fires zero
        times across the 133 graded 2026 predictions (04e prints the tally). This
        is a correctness fix for when it does fire, not a scoring change.
        """
        if old_point and old_point > 0 and new_point > 0:
            scale = float(new_point) / float(old_point)
            return int(round(lo * scale)), int(round(hi * scale))
        width = hi - lo
        return int(new_point - width / 2), int(new_point + width / 2)

    _CLAMP_STATS['calls'] += 1

    if len(hist_counts) >= 3:
        hist_min = min(hist_counts)
        hist_max = max(hist_counts)
        hist_med = int(pd.Series(hist_counts).median())
        if days_remaining > 60 and point < hist_med * 0.7:
            # Far out + low: blend model with historical median (50/50)
            new_point = int(0.5 * point + 0.5 * hist_med)
            ci_lo, ci_hi = _reanchor(point, new_point, ci_lo, ci_hi)
            point = new_point
            _CLAMP_STATS['blend-low'] += 1
        elif point < hist_min * 0.3:
            # Extremely low -- re-centre on historical median
            new_point = hist_med
            ci_lo, ci_hi = _reanchor(point, new_point, ci_lo, ci_hi)
            point = new_point
            _CLAMP_STATS['recentre-low'] += 1
        elif point > hist_max * 3.0:
            new_point = int(hist_max * 1.5)
            ci_lo, ci_hi = _reanchor(point, new_point, ci_lo, ci_hi)
            point = new_point
            _CLAMP_STATS['damp-high'] += 1

    # v3 N2 floor: never publish a final below what has already been counted.
    if current_count is not None and point < current_count:
        _CLAMP_STATS['floor-current-count'] += 1
        print(f"WARNING: plausibility clamp produced point={point} below "
              f"current_count={current_count}; flooring to the observed count. "
              f"History (n={len(hist_counts)}, max="
              f"{max(hist_counts) if hist_counts else 'n/a'}) no longer "
              f"describes this event -- treat as a genuine surge.")
        point = int(current_count)

    # Keep the interval consistent with the (possibly floored) point.
    ci_lo = min(ci_lo, point)
    ci_hi = max(ci_hi, point)
    return int(point), int(ci_lo), int(ci_hi)


def chart_series_start_date(tid, daily, event_start):
    """Calendar date of the `day_from_start == 0` point in build_chart_series.

    v3 P1 (audit/AUDIT_2026-07-25.md): the front end used to derive every chart
    date by counting array positions back from the generation date, which is
    only correct while the daily series has no gaps. A single missed scrape day
    shifted every label by one and mislabelled the resulting jump as one day's
    registrations (the visible "+125 entries yesterday" bar). Exporting the real
    anchor lets the client compute each point's date from its own
    `day_from_start` instead of its index, so gaps stop corrupting labels.

    build_chart_series maps T (days before event start) to
    day_from_start = max_T - T, so day 0 sits max_T days before event_start.

    Returns a 'YYYY-MM-DD' string, or None when the anchor cannot be derived
    (no rows for this tid, or no event_start) — the client falls back to its
    previous index-based behaviour in that case.
    """
    if event_start is None or pd.isna(event_start):
        return None
    rows = daily[daily['tid'] == tid]
    if len(rows) == 0:
        return None
    max_T = rows['T'].max()
    if pd.isna(max_T):
        return None
    start = pd.to_datetime(event_start, errors='coerce')
    if pd.isna(start):
        return None
    return (start - pd.Timedelta(days=int(max_T))).strftime('%Y-%m-%d')


# v4 X1 (audit/AUDIT_2026-07-26.md): pace-gate for interim metadata cards.
# 0e1c6a1 widened the pace window from 45 to 90 days, but at 46-90 days out a
# typical family curve sits at 1-2% cumulative, so the ratio scale-up
# (~1/pct) was pure noise that pinned the max(hist)*1.5 clamp ceiling while
# shipping labeled as live pace. The gate keeps the pre-0e1c6a1 behaviour
# untouched inside 45 days and grants the 46-90 day extension only when the
# family's expected cumulative share at that lead time clears this floor,
# i.e. only where the ratio actually carries signal.
PACE_MIN_CURVE_PCT = 0.05


def curve_pct_at(curve, days_before):
    """Expected cumulative registration share at a lead time.

    `curve` maps lead-time grid points (days before event start) to cumulative
    fractions, e.g. {90: 0.012, 42: 0.10, ...}. Linear interpolation between
    the bracketing grid points; outside the grid, the nearest endpoint.
    Returns 0.0 for an empty/unknown curve so callers fail conservative.
    """
    if not curve:
        return 0.0
    pts = sorted((int(k), float(v)) for k, v in curve.items())
    d = float(days_before)
    if d <= pts[0][0]:
        return pts[0][1]
    if d >= pts[-1][0]:
        return pts[-1][1]
    for (k0, v0), (k1, v1) in zip(pts, pts[1:]):
        if k0 <= d <= k1:
            if k1 == k0:
                return v1
            return v0 + (v1 - v0) * (d - k0) / (k1 - k0)
    return 0.0


def pace_gate_ok(current_count, days_to_start, curve):
    """Should an interim card extrapolate from live registration pace?

    Inside 45 days: yes with 10+ registrations (the long-standing gate).
    46-90 days: additionally requires curve_pct_at >= PACE_MIN_CURVE_PCT.
    Beyond 90 days, or under 10 registrations: no.
    """
    if current_count < 10:
        return False
    if days_to_start <= 45:
        return True
    if days_to_start > 90:
        return False
    return curve_pct_at(curve, days_to_start) >= PACE_MIN_CURVE_PCT


def roster_pending_model_ok(current_count, days_to_start, status, event_date,
                            curve):
    """Should a roster-pending summary row ride the main model card path?

    Roster-pending skeletons (reconcile_final_counts H2) carry no registration
    timestamps, but 04d injects their live scrape counts and a full daily curve
    before prediction, and the ratio model trains only on pre-2026 editions —
    so predict_nowcast needs nothing the missing export would provide
    (audit v5 Cat R). Admission requires:

      * status == 'live' with days_to_start > 0 — ended / reg-closed /
        post-start-window events keep their settled or in_progress cards from
        the metadata loop, exactly as before;
      * event_date present — the injected curve's T values are anchored to the
        metadata start_date, so without it there is no usable curve;
      * pace_gate_ok — the same threshold the interim metadata_pace path uses,
        so the model path and the fallback flip at the same point and no card
        can land on a worse estimate than the old interim one.
    """
    if status != 'live' or days_to_start <= 0:
        return False
    if event_date is None:
        return False
    return pace_gate_ok(current_count, days_to_start, curve)
