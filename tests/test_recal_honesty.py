"""v5 Cat L (audit/AUDIT_2026-07-30.md): recalibration honesty.

The v3 T3 held-out-cohort preference in recalibrate() was dead code: every
production caller (04d, 04e's folds, the fit scripts) hands recalibrate a
strict subset of the fit frame, so len(oos) was always 0, the cohort was
always in-sample, and — because the residual loop had no LOO exclusion —
measured bias read ~0 against a real 2026 out-of-sample bias of +7..+14%.
Both corrections it produced were ~null while 2026 CI coverage sat 20+ points
under nominal, every T<=28 miss one-sided low.

Contract after the fix:
  * recalibrate(loo=True) excludes each tournament's own ratio from the ratio
    lists when predicting it (predict_nowcast _exclude_tid), so fit-cohort
    residuals are honest pseudo-out-of-sample and a planted bias IS detected;
  * with loo=False (the pre-v5 behavior) the same planted bias is partially
    reproduced from the tournament's own ratio and detection shrinks — the
    bug this module documents;
  * production-shaped calls (recal frame ⊂ fit frame) never report an
    'in-sample' cohort and never apply the RECAL_IN_SAMPLE_WIDENING penalty;
  * ci_adj clamp pinning is surfaced in diagnostics, not silently absorbed.
"""
import os
import sys
from importlib import import_module
from types import MethodType

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

m04c = import_module("04c_final_model")  # noqa: E402


def _planted_bias_frames(n_families=12, plant=1.15):
    """Synthetic corpus with a planted regime shift.

    Each family has 2023/2024 editions filling exactly 2.0x from the T=3
    count, and a 2025 edition whose actual final undershoots that consensus
    by `plant` (final = 100 / plant). A model whose recalibration is honest
    must measure ~+(plant-1) bias on the 2025 cohort; one that leaks the
    tournament's own ratio into its residuals reads a fraction of it.
    """
    rows, daily_rows = [], []
    tid = 0
    for f in range(n_families):
        family = f"Synthetic Open {f}"
        for year, final in ((2023, 100), (2024, 100), (2025, round(100 / plant))):
            rows.append({
                "tid": tid, "tournament_name": f"{year} {family}",
                "family": family, "tournament_year": year,
                "final_count": final, "has_timestamps": True,
                "ts_count": final, "is_covid": False, "is_online": False,
                "last_reg": f"{year}-06-01",
            })
            # >=5 daily rows so fit's len(td)<5 skip keeps the tid; count at
            # T=3 is exactly 50 regardless of the final, so the family ratio
            # at T=3 is final/50 (2.0 for the 2023/24 editions).
            for T, cum in ((10, 20), (7, 30), (5, 40), (3, 50),
                           (1, round(final * 0.8)), (0, final)):
                daily_rows.append({"tid": tid, "T": T, "daily_regs": 0,
                                   "cum_regs": cum, "cum_pct": cum / final})
            tid += 1
    return pd.DataFrame(rows), pd.DataFrame(daily_rows)


def _fit_and_recal(loo, regime_year=2025):
    summary, daily = _planted_bias_frames()
    model = m04c.N5v4_Final()
    model.fit(summary, daily)
    # Production-shaped recal cohort: the most recent completed year only,
    # a strict subset of the fit frame (which holds year < 2026). The model
    # "predicts 2025", and the cohort contains 2025 events — regime path on.
    cohort = summary[summary["tournament_year"] == 2025]
    diag = model.recalibrate(cohort, daily, T_points=[3], loo=loo,
                             regime_year=regime_year)
    return model, diag


def test_planted_bias_detected_by_loo_recal():
    """A +15% planted regime bias must be measured and corrected under LOO."""
    model, diag = _fit_and_recal(loo=True)
    factor = model._recal_bias[3]
    assert 0.83 <= factor <= 0.93, f"planted bias not corrected: {factor}"
    assert diag[3]["cohort"] == "loo"
    assert diag[3]["bias_cohort"] == "regime-2025"


def test_regime_path_off_when_cohort_predates_target_year():
    """04e's historical folds recalibrate on years before the fold's test
    year. Fitting bias on year-1 and assuming carryover overcorrected the
    2024 fold — the regime path must stay off unless the cohort contains the
    target year."""
    _, diag = _fit_and_recal(loo=True, regime_year=2026)  # cohort max is 2025
    assert diag[3]["bias_cohort"] == "pooled"
    _, diag_none = _fit_and_recal(loo=True, regime_year=None)
    assert diag_none[3]["bias_cohort"] == "pooled"


def test_planted_bias_suppressed_without_loo():
    """The bug leg: with the tournament's own ratio left in the lists, the
    measured bias shrinks — detection is materially weaker than under LOO."""
    model_loo, _ = _fit_and_recal(loo=True)
    model_leaky, diag_leaky = _fit_and_recal(loo=False)
    assert diag_leaky[3]["cohort"] == "in-sample"
    assert model_leaky._recal_bias[3] >= model_loo._recal_bias[3] + 0.02, (
        "own-ratio leakage should suppress the measured bias "
        f"(loo={model_loo._recal_bias[3]:.3f}, "
        f"leaky={model_leaky._recal_bias[3]:.3f})"
    )


def test_production_shaped_recal_is_honest(capsys):
    """recal frame ⊂ fit frame (every production call site's shape) must
    never yield an 'in-sample' cohort or the in-sample widening WARNING."""
    model, diag = _fit_and_recal(loo=True)
    for T, d in diag.items():
        assert d["cohort"] in ("loo", "held-out"), (T, d["cohort"])
    out = capsys.readouterr().out
    assert "ran on an in-sample cohort" not in out


def test_ci_adj_ceiling_pinning_surfaced(capsys):
    """When residuals want more width than ci_max_scale allows, the clamp is
    reported in diagnostics and printed as a WARNING — the published interval
    is narrower than the measured error and must say so."""
    completed = pd.DataFrame({
        "tid": range(10),
        "family": ["Synthetic"] * 10,
        "final_count": [120] * 8 + [140] * 2,
        "last_reg": pd.date_range("2025-01-01", periods=10),
    })
    daily = pd.DataFrame({"tid": range(10), "T": [14] * 10, "cum_regs": [50] * 10})
    model = m04c.N5v4_Final()

    def fake_predict(self, current_count, days_remaining, family, **kwargs):
        # Absurdly narrow raw interval: normalized residuals blow past any
        # reasonable ceiling.
        return 100, 99, 101

    model.predict_nowcast = MethodType(fake_predict, model)
    diag = model.recalibrate(completed, daily, T_points=[14])

    assert diag[14].get("ci_adj_clamped") == "high"
    assert model._recal_ci[14] == pytest.approx(3.0)
    out = capsys.readouterr().out
    assert "pinned at ceiling" in out


def test_exclude_tid_filters_every_ratio_source():
    """_filter_ratios drops the excluded tid from family lists and never
    mutates the input dict."""
    fam = {3: [(2.0, 2023, 1), (2.1, 2024, 2)], 7: [(1.5, 2023, 1)]}
    out = m04c._filter_ratios(fam, 1)
    assert out[3] == [(2.1, 2024, 2)]
    assert out[7] == []
    # input untouched
    assert len(fam[3]) == 2 and len(fam[7]) == 1
    # None passthrough returns the same object (no copy cost on the hot path)
    assert m04c._filter_ratios(fam, None) is fam


def test_fit_tids_only_contains_ratio_contributors():
    """v5 Cat L provenance: a tid whose daily curve is too thin to contribute
    ratios (len(td) < 5) must not be labelled in-sample."""
    summary, daily = _planted_bias_frames(n_families=3)
    # Starve one tid's curve below the 5-row threshold
    starved = summary.iloc[0]["tid"]
    daily = daily[~((daily["tid"] == starved) & (daily["T"] > 1))]
    model = m04c.N5v4_Final()
    model.fit(summary, daily)
    assert starved not in model._fit_tids
    other = summary.iloc[1]["tid"]
    assert other in model._fit_tids
