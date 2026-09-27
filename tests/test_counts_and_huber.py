"""One reading of an event's count at each chop point, one Huber fit, and a
calibration search that builds each interval once: all three must reproduce
the loops they replaced exactly."""
import numpy as np
import pandas as pd
import pytest

from model import robust_reg
from model.core import N5v4_Final, _coverage
from model.counts import MIN_CURVE_ROWS, counts_by_event, curve_count_at
from model.stats import lognormal_ci


def _curve(tid, points):
    return pd.DataFrame({"tid": tid, "T": [p[0] for p in points], "cum_regs": [p[1] for p in points]})


def test_count_at_T_is_the_largest_count_at_least_T_days_out():
    td = _curve(1, [(100, 5), (60, 30), (30, 80), (7, 150), (0, 200)])
    assert curve_count_at(td, 60) == 30
    assert curve_count_at(td, 45) == 30, "between rows the earlier (larger T) row holds"
    assert curve_count_at(td, 0) == 200
    assert curve_count_at(td, 120) is None, "no row that early"


def test_counts_skip_short_curves_zero_counts_and_missing_chop_points():
    daily = pd.concat([
        _curve(1, [(100, 0), (60, 30), (30, 80), (7, 150), (0, 200)]),
        _curve(2, [(10, 5), (5, 9)]),                        # too few rows
        _curve(3, [(9, 0), (8, 0), (7, 0), (6, 0), (5, 0)]),  # qualifies, nothing usable
    ])
    out = counts_by_event(daily, [1, 2, 3, 4], [120, 90, 60, 7])
    assert out == {1: {60: 30, 7: 150}, 3: {}}
    assert MIN_CURVE_ROWS == 5
    assert list(out[1]) == [60, 7], "chop-point order kept"


def _reference_counts(daily, tids, chop_points):
    """The loop every caller used to run."""
    out = {}
    for tid in tids:
        td = daily[daily["tid"] == tid].sort_values("T", ascending=False)
        if len(td) < 5:
            continue
        got = {}
        for T in chop_points:
            regs = td[td["T"] >= T]
            if len(regs) == 0:
                continue
            c = int(regs["cum_regs"].max())
            if c == 0:
                continue
            got[T] = c
        out[tid] = got
    return out


def test_counts_match_the_old_loop_on_random_curves():
    rng = np.random.default_rng(7)
    frames = []
    for tid in range(40):
        n = int(rng.integers(2, 30))
        T = np.sort(rng.choice(np.arange(0, 150), size=n, replace=False))[::-1]
        frames.append(_curve(tid, list(zip(T, np.cumsum(rng.integers(0, 6, size=n))))))
    daily = pd.concat(frames)
    chops = [120, 90, 60, 42, 28, 14, 7, 3, 1]
    assert counts_by_event(daily, range(45), chops) == _reference_counts(daily, range(45), chops)


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")
def test_huber_counts_fits_that_stop_at_the_cap(monkeypatch):
    robust_reg.reset_unconverged()
    pts = [(c, t, 3 * c + t) for c in range(5, 25) for t in (7, 28)]
    coeffs = robust_reg.fit_huber(pts, label="fam")
    assert coeffs.shape == (3,)
    assert robust_reg.unconverged() == []
    monkeypatch.setattr(robust_reg, "MAX_ITER", 1)
    robust_reg.fit_huber(pts, label="capped")
    assert robust_reg.unconverged() == ["capped"]
    robust_reg.reset_unconverged()
    assert robust_reg.unconverged() == []


def _old_coverage(loo_data, scale, g_sigma):
    """The search step as it was: the interval rebuilt on every call."""
    covered = 0
    for count_at_T, actual, loo in loo_data:
        med, lo_r, hi_r = lognormal_ci(loo, level=0.80, global_sigma=g_sigma, count_stats=False)
        if scale != 1.0:
            log_med, log_lo, log_hi = np.log(med), np.log(lo_r), np.log(hi_r)
            hw = (log_hi - log_lo) / 2 * scale
            lo_r, hi_r = np.exp(log_med - hw), np.exp(log_med + hw)
        if count_at_T * lo_r <= actual <= count_at_T * hi_r:
            covered += 1
    return covered / len(loo_data)


@pytest.mark.parametrize("scale", [0.4, 0.73, 1.0, 1.2, 1.9])
def test_hoisted_coverage_equals_the_rebuilt_one(scale):
    rng = np.random.default_rng(3)
    loo_data, records = [], []
    for _ in range(60):
        loo = list(np.exp(rng.normal(1.2, 0.3, size=int(rng.integers(2, 12)))))
        count = int(rng.integers(5, 200))
        actual = count * float(np.exp(rng.normal(1.2, 0.4)))
        loo_data.append((count, actual, loo))
        records.append((count, actual, *lognormal_ci(loo, level=0.80, global_sigma=0.3, count_stats=False)))
    assert _coverage(records, scale) == _old_coverage(loo_data, scale, 0.3)


def test_calibration_records_leave_the_event_out():
    m = N5v4_Final()
    m.global_log_sigma = {28: 0.3}
    m.ratios = {"A": {28: [(2.0, 2024, 1), (2.2, 2025, 2), (1.8, 2023, 3)]}}
    m.global_ratios = {28: []}
    cal = pd.DataFrame({"tid": [1, 9], "family": ["A", "A"], "final_count": [100, 90]})
    records = m._loo_interval_records(cal, {1: {28: 50}, 9: {}}, 28)
    assert len(records) == 1
    count, actual, med, lo_r, hi_r = records[0]
    assert (count, actual) == (50, 100)
    assert (med, lo_r, hi_r) == lognormal_ci([2.2, 1.8], level=0.80, global_sigma=0.3, count_stats=False)
