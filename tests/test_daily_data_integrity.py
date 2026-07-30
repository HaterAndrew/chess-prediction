"""
Regression tests for the 2026-07-25 daily_data corruption incident (v3 N1).

Incident: a missing scrape day (Jul 22, 04e timeout) exposed a misplaced stale
archive point that reanchor_daily_to_event_start had mis-shifted (it substituted
a family-median offset for a legitimately negative offset on a not-yet-concluded
event). The A4 3x-jump backstop in 04d then rescaled the whole earlier curve by
4.6x and the monotone cleaner dropped the true tail, so Bradley Open shipped
daily_data ending at 625 while its real count was 197.

These tests pin the three seams: reanchor negative-offset handling (04c),
the A4 backstop (must warn, never rescale) and monotone cleaner (04d), and the
full three-way interaction over frozen incident fixtures.
"""
import os
import sys
from datetime import timedelta
from importlib import import_module

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "incident_2026_07_25")

m04c = import_module("04c_final_model")
from pipeline_utils import build_chart_series


def test_reanchor_accepts_negative_offset_for_in_progress_event():
    """A not-yet-concluded event whose last_reg predates event_start has a
    negative offset; shifting by the TRUE offset is arithmetically correct.
    The old code substituted a family-median (+2) offset, sliding the archive
    curve toward T=0. Assert the true shift is applied, not the substitution."""
    future_start = m04c.TODAY + timedelta(days=16)   # event 16 days out
    last_reg = m04c.TODAY - timedelta(days=2)         # export is stale
    true_offset = (last_reg - future_start).days       # == -18 (negative)

    summary = pd.DataFrame([{
        'tid': 900, 'family': 'Synthetic Open', 'tournament_year': 2026.0,
        'last_reg': last_reg.strftime('%Y-%m-%d'), 'final_count': 100,
        'has_timestamps': True, 'is_online': False, 'is_covid': False,
        'tournament_name': '2026 Synthetic Open',
    }])
    # Two archive rows in last_reg-anchored T (days before last_reg).
    daily = pd.DataFrame([
        {'tid': 900, 'T': 20, 'daily_regs': 40, 'cum_regs': 40, 'cum_pct': 0.4},
        {'tid': 900, 'T': 10, 'daily_regs': 60, 'cum_regs': 100, 'cum_pct': 1.0},
    ])
    meta = pd.DataFrame([{
        'family': 'Synthetic Open', 'year': 2026,
        'start_date': future_start.strftime('%Y-%m-%d'),
        'end_date': (future_start + timedelta(days=2)).strftime('%Y-%m-%d'),
    }])

    out = m04c.reanchor_daily_to_event_start(summary, daily, meta)
    # new_T = old_T - true_offset ; true_offset is negative so T grows.
    assert set(out['T']) == {20 - true_offset, 10 - true_offset}, (
        f"expected true-offset shift (offset={true_offset}); got T={sorted(out['T'])}"
    )
    # The substitution path would have shifted by +2 (T=18, T=8) — reject that.
    assert 18 not in set(out['T']) and 8 not in set(out['T'])


def test_a4_backstop_never_rescales_observed_history():
    """A >3x jump between adjacent chart points must be WARNED, never used to
    rescale earlier observed points. Pre-fix, the earlier points were multiplied
    by the jump ratio."""
    # day_from_start ascending; a benign low archive tail then a real jump.
    daily = pd.DataFrame([
        {'tid': 1, 'T': 40, 'daily_regs': 0, 'cum_regs': 100, 'cum_pct': 0.5},
        {'tid': 1, 'T': 30, 'daily_regs': 0, 'cum_regs': 135, 'cum_pct': 0.7},
        {'tid': 1, 'T': 20, 'daily_regs': 0, 'cum_regs': 41, 'cum_pct': 0.2},
        {'tid': 1, 'T': 10, 'daily_regs': 0, 'cum_regs': 190, 'cum_pct': 1.0},
    ])
    series = build_chart_series(1, daily, current_count=197, is_live=True)
    counts = [c for _, c in series]
    # 100 and 135 must survive untouched (pre-fix they became ~464, ~626).
    assert 100 in counts and 135 in counts, f"observed history was rescaled: {counts}"
    assert max(counts) <= 197, f"no chart point may exceed current_count: {counts}"


def test_monotone_cleaner_preserves_true_tail_after_missing_scrape_day():
    """The three-way interaction: a misplaced low archive point (missing-day
    exposed) must not cause the monotone cleaner to drop the real tail."""
    daily = pd.DataFrame([
        {'tid': 2, 'T': 40, 'daily_regs': 0, 'cum_regs': 108, 'cum_pct': 0.5},
        {'tid': 2, 'T': 30, 'daily_regs': 0, 'cum_regs': 135, 'cum_pct': 0.7},
        {'tid': 2, 'T': 20, 'daily_regs': 0, 'cum_regs': 41, 'cum_pct': 0.2},
        {'tid': 2, 'T': 10, 'daily_regs': 0, 'cum_regs': 190, 'cum_pct': 0.96},
        {'tid': 2, 'T': 5, 'daily_regs': 0, 'cum_regs': 197, 'cum_pct': 1.0},
    ])
    series = build_chart_series(2, daily, current_count=197, is_live=True)
    assert series[-1][1] == 197, f"true tail dropped: {series}"


def test_04e_gets_a_higher_step_timeout():
    """v3 O-series: the uniform 300s subprocess cap caused the 2026-07-22 miss
    (04e's leave-one-out cost grows with each completed 2026 event). 04e must get
    a larger cap; unlisted steps keep the default."""
    auto_update = import_module("auto_update")
    assert auto_update._step_timeout(
        [sys.executable, "04e_performance_data.py"]) > auto_update.DEFAULT_STEP_TIMEOUT
    assert auto_update._step_timeout(
        [sys.executable, "01_data_prep.py"]) == auto_update.DEFAULT_STEP_TIMEOUT


def test_incident_fixture_regression():
    """Full replay over the frozen Bradley/Pacific fixtures: rebuilt curves must
    be sane — last point == current count, monotone non-decreasing, no point
    above the current count."""
    summary = pd.read_csv(os.path.join(FIXTURES, "tournament_summary.csv"))
    summary['tournament_year'] = pd.to_numeric(
        summary['tournament_year'], errors='coerce').fillna(0).astype(int)
    daily = pd.read_csv(os.path.join(FIXTURES, "daily_registration_counts.csv"))
    meta = pd.read_csv(os.path.join(FIXTURES, "tournament_metadata.csv"))
    meta['start_date'] = pd.to_datetime(meta['start_date'])
    scrape = pd.read_csv(os.path.join(FIXTURES, "daily_scrape.csv"))
    scrape['date'] = pd.to_datetime(scrape['date'])

    daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)

    # Insert the latest scrape row per tid at its event-start-based T, mirroring
    # 04d's merge (event_start - scrape_date), so archive + scrape share T=0.
    for _, s in scrape.iterrows():
        fam = s['tournament_name'].replace('2026 ', '', 1)
        trow = summary[(summary['family'] == fam)
                       & (summary['tournament_year'] == 2026)]
        mrow = meta[(meta['family'] == fam) & (meta['year'] == 2026)]
        if len(trow) == 0 or len(mrow) == 0:
            continue
        tid = trow.iloc[0]['tid']
        event_start = pd.to_datetime(mrow.iloc[0]['start_date'])
        T = max((event_start - pd.to_datetime(s['date'])).days, 0)
        cnt = int(s['active_count']) if s['active_count'] > 0 else int(s['entry_count'])
        existing = daily[(daily['tid'] == tid) & (daily['T'] == T)]
        if len(existing) == 0 and cnt > 0:
            daily = pd.concat([daily, pd.DataFrame([{
                'tid': tid, 'T': T, 'daily_regs': 0, 'cum_regs': cnt, 'cum_pct': 1.0,
            }])], ignore_index=True)
        elif len(existing) > 0 and cnt > existing.iloc[0]['cum_regs']:
            daily.loc[(daily['tid'] == tid) & (daily['T'] == T), 'cum_regs'] = cnt

    # Expected net tail per tid: the latest scrape's active_count (the value
    # actually inserted into the curve). final_count is gross; the two differ by
    # withdrawals (Pacific Coast: gross 199, net 197).
    latest = scrape.sort_values('date').groupby('tournament_name').last()
    for _, trow in summary[summary['tournament_year'] == 2026].iterrows():
        tid = trow['tid']
        gross = int(trow['final_count'])
        net = int(latest.loc[trow['tournament_name'], 'active_count'])
        series = build_chart_series(tid, daily, current_count=gross, is_live=True)
        counts = [c for _, c in series]
        assert counts == sorted(counts), f"tid {tid} not monotone: {counts}"
        assert max(counts) <= gross, f"tid {tid} point exceeds gross {gross}: {max(counts)}"
        assert series[-1][1] == net, f"tid {tid} tail {series[-1][1]} != net {net}"


# ---------------------------------------------------------------------------
# v3 N2: the plausibility clamp must never display a final estimate below the
# entry count already observed. A prediction of "fewer entries than we have
# already counted" is impossible for a cumulative registration total, and it is
# what the >3x clamp produced whenever a real surge outran the historical range
# (verifier: fires whenever current_count > hist_max * 1.5).
# ---------------------------------------------------------------------------


def test_plausibility_clamp_never_returns_below_current_count():
    """A genuine surge: history tops out at 100 but 400 entries are already in.
    The old clamp rewrote point to hist_max*1.5 == 150, i.e. BELOW the 400
    already counted. The floor must hold the real observed value."""
    from pipeline_utils import apply_plausibility_clamp

    current_count = 400
    point, ci_lo, ci_hi = apply_plausibility_clamp(
        point=500, ci_lo=450, ci_hi=560,
        current_count=current_count, hist_counts=[80, 95, 100],
        days_remaining=10)

    assert point >= current_count, (
        f"clamp produced point={point} below current_count={current_count}")
    assert ci_hi >= point, f"ci_hi={ci_hi} below point={point}"
    assert ci_lo <= point, f"ci_lo={ci_lo} above point={point}"


def test_plausibility_clamp_still_damps_implausible_high_estimate():
    """The clamp must keep doing its job when current_count is NOT the reason
    the estimate is high: history ~100, only 20 entries in, model says 900."""
    from pipeline_utils import apply_plausibility_clamp

    point, _lo, _hi = apply_plausibility_clamp(
        point=900, ci_lo=800, ci_hi=1000,
        current_count=20, hist_counts=[80, 95, 100],
        days_remaining=10)

    assert point < 900, "implausibly high estimate was not damped"
    assert point >= 20


def test_plausibility_clamp_low_end_respects_current_count():
    """The 'extremely low' re-centre on the historical median must also not
    land below what has already been counted."""
    from pipeline_utils import apply_plausibility_clamp

    point, _lo, _hi = apply_plausibility_clamp(
        point=5, ci_lo=1, ci_hi=20,
        current_count=140, hist_counts=[100, 120, 130],
        days_remaining=90)

    assert point >= 140, f"low-end clamp produced point={point} below 140 counted"


def test_plausibility_clamp_noop_without_enough_history():
    """Fewer than 3 historical editions: no clamp fires, and a point already
    above current_count is returned untouched."""
    from pipeline_utils import apply_plausibility_clamp

    result = apply_plausibility_clamp(
        point=250, ci_lo=200, ci_hi=300,
        current_count=40, hist_counts=[100],
        days_remaining=30)

    assert result == (250, 200, 300)
