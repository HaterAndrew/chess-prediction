"""Tests for the online-window engine grader (audit v3 T7).

The failures worth catching here are the ones that would produce a plausible but
wrong grade rather than an error: scoring a fold that has no training data,
scoring an event that never takes the window path in production, or letting a
nine-observation day set the published letter.
"""
from importlib import import_module

import pandas as pd
import pytest



import window_grading as wg
from ratio_model import ratio_observation_count

m04c = import_module("04c_final_model")

_GRADE_ORDER = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D', 'F']


def _grade(mae, cov):
    for g, max_mae, min_cov in [('A+', 5, 85), ('A', 8, 75), ('A-', 10, 72),
                                ('B', 14, 65), ('C', 20, 50), ('F', 999, 0)]:
        if mae <= max_mae and cov >= min_cov:
            return g
    return 'F'


# ── count_at_window_day ──────────────────────────────────────────────────

def test_count_at_window_day_reads_the_right_day():
    daily = pd.DataFrame({'T': [2, 1, 0, -1, -2], 'cum_regs': [10, 20, 30, 40, 50]})
    assert wg.count_at_window_day(daily, 0) == 30   # T=0, event start
    assert wg.count_at_window_day(daily, 1) == 40   # T=-1
    assert wg.count_at_window_day(daily, 2) == 50   # T=-2


def test_count_at_window_day_steps_back_over_a_missing_day():
    """Days with no registrations have no row; use the last known count."""
    daily = pd.DataFrame({'T': [0, -2], 'cum_regs': [30, 50]})
    # Day 1 has no row. The count as of end of day 1 is still day 0's 30 —
    # taking day 2's 50 would credit the engine with entries it could not
    # have seen yet.
    assert wg.count_at_window_day(daily, 1) == 30


def test_count_at_window_day_carries_the_last_count_forward():
    """Past the end of the curve, the last known count stands.

    For a completed event the timestamped curve is complete, so no rows after
    T=1 means no registrations after T=1 — not missing data. Carrying forward
    is also the conservative direction: if a curve IS truncated, the count comes
    in too low, the prediction with it, and the error grows. It cannot flatter
    the grade. Badly truncated curves are excluded upstream by the frozen-curve
    gate anyway.
    """
    daily = pd.DataFrame({'T': [2, 1], 'cum_regs': [10, 20]})
    assert wg.count_at_window_day(daily, 5) == 20


def test_count_at_window_day_returns_none_with_no_usable_rows():
    daily = pd.DataFrame({'T': [], 'cum_regs': []})
    assert wg.count_at_window_day(daily, 0) is None


# ── eligible_events ──────────────────────────────────────────────────────

def _summary_row(**kw):
    base = {'tid': 't1', 'family': 'Test Open', 'tournament_year': 2025,
            'final_count': 200, 'has_timestamps': True, 'is_online': False,
            'is_covid': False, 'last_reg': '2025-06-05'}
    base.update(kw)
    return base


def _meta_row(start, end, family='Test Open', year=2025):
    return {'family': family, 'year': year,
            'start_date': pd.Timestamp(start), 'end_date': pd.Timestamp(end)}


def test_event_without_a_window_is_not_graded():
    """A single-day-schedule event never takes the window path in production."""
    summary = pd.DataFrame([_summary_row()])
    # end - 1 == start, so window_len == 0.
    meta = pd.DataFrame([_meta_row('2025-06-01', '2025-06-02')])
    assert len(wg.eligible_events(summary, meta)) == 0


def test_event_with_a_window_is_graded():
    summary = pd.DataFrame([_summary_row()])
    meta = pd.DataFrame([_meta_row('2025-06-01', '2025-06-05')])
    got = wg.eligible_events(summary, meta)
    assert len(got) == 1
    assert int(got.iloc[0]['window_len']) == 3


def test_small_and_online_events_are_excluded():
    summary = pd.DataFrame([
        _summary_row(tid='small', final_count=10),
        _summary_row(tid='online', is_online=True),
        _summary_row(tid='covid', is_covid=True),
        _summary_row(tid='keep'),
    ])
    meta = pd.DataFrame([_meta_row('2025-06-01', '2025-06-05')])
    got = wg.eligible_events(summary, meta)
    assert set(got['tid']) == {'keep'}


# ── grading ──────────────────────────────────────────────────────────────

def test_grade_takes_the_worst_qualifying_day():
    by_day = {
        '0': {'n': 150, 'mae_pct': 6.0, 'ci_coverage': 95.0},   # A
        '1': {'n': 100, 'mae_pct': 9.5, 'ci_coverage': 73.0},   # A-
    }
    grade, detail = wg.grade_from_by_day(by_day, _grade, _GRADE_ORDER)
    assert grade == 'A-'
    assert 'day 1' in detail


def test_a_tiny_day_cannot_set_the_grade():
    """Day 2 has 9 observations in the real data; one event swings it."""
    by_day = {
        '0': {'n': 150, 'mae_pct': 6.0, 'ci_coverage': 95.0},
        '2': {'n': 9, 'mae_pct': 90.0, 'ci_coverage': 0.0},   # would be F
    }
    grade, _ = wg.grade_from_by_day(by_day, _grade, _GRADE_ORDER)
    assert grade == 'A'


def test_grade_is_na_when_no_day_has_enough_data():
    by_day = {'0': {'n': 3, 'mae_pct': 1.0, 'ci_coverage': 100.0}}
    grade, detail = wg.grade_from_by_day(by_day, _grade, _GRADE_ORDER)
    assert grade == 'N/A'
    assert 'enough observations' in detail


# ── the empty-fold guard ─────────────────────────────────────────────────

def test_ratio_observation_count_detects_an_empty_model():
    """An empty ratio model makes the engine predict current_count with a
    zero-width CI, which scores as confidently wrong rather than as absent.
    The 2022 fold hits this, and grading it produced 0.0% coverage over 68
    predictions."""
    assert ratio_observation_count({}) == 0
    assert ratio_observation_count({'__global__': {}}) == 0
    assert ratio_observation_count({'Test': {0: [1.1, 1.2]}}) == 2


def test_training_population_is_separable_from_the_scored_population():
    """04d trains its ratio model on a wider frame than the grade scores.

    Production filters only online/COVID when building ratios; the evaluation
    frame also drops blitz families and World Open sub-events. Training on the
    evaluation frame grades a model that is never deployed — when this was wired
    that way it moved the window grade by a full letter. The signature has to
    keep the two frames distinct.
    """
    import inspect
    params = inspect.signature(wg.grade_window_engine).parameters
    assert 'train_summary' in params
    assert params['train_summary'].default is None, \
        "must default to `summary` so the distinction is opt-in, not silent"


def test_scoring_an_unanchored_event_raises():
    """An event missing from train_summary would be read at the wrong offset.

    reanchor only shifts T for tids in the frame it is handed. Grading an event
    it never saw yields a plausible wrong number rather than a failure, so the
    grader refuses instead.
    """
    summary = pd.DataFrame([_summary_row(tid='scored_only')])
    meta = pd.DataFrame([_meta_row('2025-06-01', '2025-06-05')])
    daily = pd.DataFrame({'tid': ['scored_only'], 'T': [1],
                          'daily_regs': [5], 'cum_regs': [5]})
    train = pd.DataFrame([_summary_row(tid='something_else')])

    with pytest.raises(ValueError) as exc:
        wg.grade_window_engine(summary, daily, meta, [2025],
                               lambda _t: {}, train_summary=train,
                               verbose=False)
    assert 'reanchored' in str(exc.value)


# ── the reanchor flag this grader depends on ─────────────────────────────

def _reanchor_frames():
    summary = pd.DataFrame([{
        'tid': 't1', 'family': 'Test Open', 'tournament_year': 2025,
        'final_count': 100, 'has_timestamps': True, 'is_online': False,
        'is_covid': False, 'last_reg': '2025-06-04', 'roster_pending': False,
    }])
    daily = pd.DataFrame({
        'tid': ['t1'] * 5,
        'T': [5, 4, 3, 2, 1],           # last_reg-anchored
        'daily_regs': [10, 20, 30, 25, 15],
        'cum_regs': [10, 30, 60, 85, 100],
    })
    meta = pd.DataFrame([{
        'family': 'Test Open', 'year': 2025,
        'start_date': pd.Timestamp('2025-06-01'),
        'end_date': pd.Timestamp('2025-06-04'),
    }])
    return summary, daily, meta


def test_reanchor_drops_post_start_rows_by_default():
    summary, daily, meta = _reanchor_frames()
    out = m04c.reanchor_daily_to_event_start(summary, daily.copy(), meta)
    assert (out['T'] >= 0).all()


def test_reanchor_keeps_post_start_rows_when_asked():
    summary, daily, meta = _reanchor_frames()
    out = m04c.reanchor_daily_to_event_start(summary, daily.copy(), meta,
                                             keep_post_start=True)
    assert (out['T'] < 0).any(), "window rows must survive for the grader"
    # And the cumulative count still runs monotonically through the window,
    # since the grader reads current_count off it.
    ordered = out.sort_values('T', ascending=False)
    assert list(ordered['cum_regs']) == sorted(ordered['cum_regs'])


@pytest.mark.parametrize("keep", [True, False])
def test_reanchor_never_changes_the_pre_start_rows(keep):
    """Whatever the flag does to the window, the training region is identical."""
    summary, daily, meta = _reanchor_frames()
    out = m04c.reanchor_daily_to_event_start(summary, daily.copy(), meta,
                                             keep_post_start=keep)
    pre = out[out['T'] >= 0].sort_values('T')
    assert list(pre['T']) == [0, 1, 2]
