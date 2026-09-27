"""N5v4_Final.recalibrate as a mixin (04c 1518-1869): per-horizon bias and width factors.

The residuals come from model.recal_residuals, the arithmetic from
model.recal_factors; this module fits each horizon and reports what it did.
"""

import warnings

import numpy as np
import pandas as pd

from model.constants import (RECAL_IN_SAMPLE_WIDENING, RECAL_MIN_OOS_RECORDS,
                             RECAL_REGIME_MIN_N)
from model.recal_factors import (bias_factor_of, bias_fit, ci_scale, cohort_has_year,
                                 recent_half_bias, stationarity_of)
from model.recal_residuals import residuals_at

class RecalibrationMixin:
    def recalibrate(self, completed_tournaments, daily, T_points=None,
                    target_coverage=0.80, ci_min_scale=0.5, ci_max_scale=3.0,
                    loo=True, regime_year=None, pickup_gains=None):
        """Automated recalibration from completed tournament results.

        Computes per-T bias correction and CI width adjustment factors
        by comparing model predictions to actual final counts.

        AUDIT.md C1: ci_adj derived from log-residual quantile rather than
        a 5-bucket step function, so empirical coverage actually converges
        to target_coverage=80% rather than landing in a "close enough" band.

        AUDIT.md C2: stationarity diagnostic — fits bias on the older half
        of completed tournaments and evaluates on the newer half. Logs both
        if they materially diverge so the user knows the per-T bias factors
        are time-dependent.

        v5 Cat L: with loo=True (the default) every residual is computed with
        the tournament's own ratio excluded from the ratio lists
        (predict_nowcast(_exclude_tid=...)), so fit-cohort records are honest
        pseudo-out-of-sample and the whole cohort is usable. Residual leakage
        through the pooled regression, family anchors and _calibrate's scale
        remains (diffuse, robust-estimator channels) — bounded optimism,
        measured by tests/test_recal_honesty.py. loo=False preserves the
        pre-v5 behavior: prefer genuinely held-out records, fall back to the
        in-sample cohort with the declared RECAL_IN_SAMPLE_WIDENING penalty.

        completed_tournaments: DataFrame with completed tournaments
            (must have tid, family, final_count columns)
        daily: daily registration counts DataFrame
        T_points: list of T values to calibrate at (default: CHOP_POINTS)
        target_coverage: desired empirical CI coverage (default 0.80)
        ci_min_scale, ci_max_scale: clamp range for ci_adj. Ceiling raised
            1.8 -> 3.0 in v5: honest LOO residuals need more headroom (T=7
            already pinned 1.799 on optimistic in-sample residuals), and the
            end-to-end multiplier implied by _calibrate's raw scales runs to
            ~3.0. Pinning either clamp is surfaced in diagnostics.
        regime_year: the year this model will PREDICT. When the cohort's most
            recent tournament_year equals it (i.e. current-year completed
            events are in the cohort) and that subset has
            >= RECAL_REGIME_MIN_N records, the bias correction is fitted on
            that regime subset — a pooled multi-year mean dilutes a
            current-regime shift toward zero. When the cohort predates the
            target year (04e's historical folds), the regime path stays OFF:
            fitting bias on year-1 and assuming carryover measurably
            overcorrected the 2024 fold. None disables the regime path.

        pickup_gains: {(tid, T): what the event's last edition took after T}
            (forecast.cohort_pickup). Inside two weeks the width residuals
            are then centred on the pickup blend the site publishes (#191);
            None centres them on the model's point, as before.

        Sets self._recal_bias, self._recal_ci, self._recal_n dicts.
        Returns dict with calibration diagnostics.
        """
        warnings.filterwarnings("ignore")  # scoped here from the old module-level call (P2b):
        # numeric/sklearn noise fires inside this method; importing the
        # model package no longer poisons every importer process-wide.
        if T_points is None:
            T_points = [90, 60, 42, 28, 14, 7, 3, 1]

        # Filter to meaningful tournaments (skip tiny sub-events)
        completed_tournaments = completed_tournaments[
            completed_tournaments['final_count'] >= 50
        ]

        self._recal_bias = {}
        self._recal_ci = {}
        self._recal_n = {}
        diagnostics = {}

        # AUDIT.md C2 — order tournaments chronologically for stationarity check
        if 'last_reg' in completed_tournaments.columns:
            completed_sorted = completed_tournaments.copy()
            completed_sorted['_lr'] = pd.to_datetime(
                completed_sorted['last_reg'], errors='coerce')
            completed_sorted = completed_sorted.sort_values('_lr', na_position='last')
        else:
            completed_sorted = completed_tournaments

        for T in T_points:
            records = residuals_at(self, completed_sorted, daily, T, loo, pickup_gains)
            if len(records) < 3:
                continue
            diag = self._recalibrate_at(T, records, loo, regime_year, target_coverage,
                                        ci_min_scale, ci_max_scale)
            diagnostics[T] = diag

        return diagnostics

    def _recalibrate_at(self, T, records, loo, regime_year, target_coverage,
                        ci_min_scale, ci_max_scale):
        """Fit and set the bias and width factors at one horizon; return its diagnostics."""
        # v3 T3 → v5 Cat L (audit/AUDIT_2026-07-30.md): the v3 oos-preference
        # was dead code — every production caller hands recalibrate() a
        # strict subset of the fit frame, so len(oos) was always 0, the
        # cohort was always in-sample, and both corrections were ~null
        # (measured bias ~0 against a real 2026 bias of +7..+11%). Under
        # loo=True the residual loop already excluded each tournament's own
        # ratio, so every record is honest and the whole cohort is usable.
        # The loo=False branch keeps the old logic.
        oos = [r for r in records if not r.in_sample]
        cohort_is_in_sample = False
        if not loo and len(oos) >= RECAL_MIN_OOS_RECORDS:
            records = oos
        elif not loo and len(oos) < len(records):
            # Not enough held-out events to calibrate on. Keep the in-sample
            # cohort but say so, and widen below rather than publish an
            # interval whose width was measured on training data.
            cohort_is_in_sample = True

        # ── Bias correction ─────────────────────────────────────────
        mean_bias, bias_cohort = bias_fit(records, regime_year, RECAL_REGIME_MIN_N)
        bias_factor = bias_factor_of(mean_bias)

        # Stationarity probe: split records chronologically (older half vs
        # newer half). Diagnostic always; the auto-refit fires only on the
        # pooled path — the regime path already fits on the newest cohort,
        # and pruning records here would thin the pooled width quantile.
        #
        # AUDIT.md C2 auto-action — when bias is non-stationary across halves
        # by more than 5pp, refit bias_factor on just the recent half.
        # Old-cohort behavior (pre-2024 conditions) shouldn't drag current
        # predictions backward. The records are also pruned so the CI scale
        # below is computed from the same recent cohort. v5 Cat L: the refit
        # is the same carryover bet the regime gate polices, so it fires only
        # when the cohort CONTAINS the target year (then the recent half
        # includes current-regime records — the small-current-n complement to
        # the regime path). With honest LOO residuals, refitting a
        # pre-target-year cohort on its recent half applied 2023's real -12%
        # to the 2024 fold and overshot it to +17.9% at T=28.
        stationarity = stationarity_of(records)
        recent_recalibrated = False
        if (stationarity and bias_cohort == 'pooled'
                and cohort_has_year(records, regime_year)
                and abs(stationarity['delta_pct']) > 5.0):
            records, mean_bias = recent_half_bias(records)
            bias_factor = bias_factor_of(mean_bias)
            stationarity['action'] = 'refit-on-recent-half'
            recent_recalibrated = True

        # ── CI scale (continuous derivation, AUDIT.md C1) ───────────
        ci_adj = ci_scale(records, bias_factor, target_coverage, T)
        # v3 T3: residuals measured on tournaments the model was fitted on
        # understate real error, so the scale derived from them would publish
        # intervals narrower than the model has earned. Widen by a fixed,
        # declared penalty rather than pretending the number is honest.
        # (loo=False path only — under LOO the residuals are honest and the
        # penalty would double-count.)
        if cohort_is_in_sample:
            ci_adj *= RECAL_IN_SAMPLE_WIDENING
        pre_clamp = ci_adj
        ci_adj = max(ci_min_scale, min(ci_max_scale, ci_adj))

        self._recal_bias[T] = bias_factor
        self._recal_ci[T] = ci_adj
        self._recal_n[T] = len(records)
        diag = {
            'n': len(records),
            'mean_bias': round(mean_bias * 100, 1),
            'coverage_before': round(float(np.mean([r.ci_hit for r in records])) * 100, 0),
            'bias_factor': round(bias_factor, 3),
            'ci_adj': round(ci_adj, 3),
            'target_coverage': int(target_coverage * 100),
            # v3 T3: make the provenance of this scale inspectable.
            'cohort': cohort_label(records, oos, loo, cohort_is_in_sample),
            # v5 Cat L: which subset the bias (location) correction was
            # fitted on — 'regime-<year>' or 'pooled'.
            'bias_cohort': bias_cohort,
            'n_out_of_sample': len(oos),
        }
        report_clamp(diag, T, pre_clamp, ci_min_scale, ci_max_scale)
        if cohort_is_in_sample:
            print(f"  WARNING: T={T} recalibration ran on an in-sample cohort "
                  f"({len(oos)} held-out record(s), need {RECAL_MIN_OOS_RECORDS}); "
                  f"CI scale widened x{RECAL_IN_SAMPLE_WIDENING} to offset "
                  f"training-set optimism.")
        if stationarity:
            diag['stationarity'] = stationarity
            report_stationarity(T, stationarity, recent_recalibrated, bias_cohort, diag,
                                len(records))
        return diag


def cohort_label(records, oos, loo, cohort_is_in_sample):
    """v5 Cat L cohort provenance: 'held-out' only when every record is
    genuinely outside _fit_tids; 'loo' when fit-cohort records were predicted
    with their own ratio excluded (honest, but not a claim of true holdout);
    'in-sample' only on the loo=False fallback."""
    if len(oos) == len(records):
        return 'held-out'
    if loo:
        return 'loo'
    return 'in-sample' if cohort_is_in_sample else 'held-out'


def report_clamp(diag, T, pre_clamp, ci_min_scale, ci_max_scale):
    """v5 Cat L: surface clamp pinning. Ceiling pin = the published CI is
    NARROWER than the residuals earned — a real warning. Floor pin = the floor
    holds the CI wider than residuals asked for — conservative, so a NOTICE
    (kept out of the harvested warning channel; 04e's LOO folds pin the floor
    routinely at long T)."""
    if pre_clamp > ci_max_scale:
        diag['ci_adj_clamped'] = 'high'
        print(f"  WARNING: T={T} ci_adj pinned at ceiling "
              f"{ci_max_scale} (residuals wanted {pre_clamp:.3f}) — "
              f"published CI narrower than measured error.")
    elif pre_clamp < ci_min_scale:
        diag['ci_adj_clamped'] = 'low'
        print(f"  NOTICE: T={T} ci_adj pinned at floor "
              f"{ci_min_scale} (residuals wanted {pre_clamp:.3f}).")


def report_stationarity(T, stationarity, recent_recalibrated, bias_cohort, diag, n):
    """Loud notice when bias materially differs across halves, naming which
    correction is in force (v5 Cat L: the old else branch always claimed
    "n<6", which was wrong whenever the refit was declined by the
    regime/carryover gate instead)."""
    if abs(stationarity['delta_pct']) <= 5.0:
        return
    probe = (f"T={T} bias non-stationary "
             f"(old: {stationarity['old_bias_pct']}%, "
             f"new: {stationarity['new_bias_pct']}%, "
             f"Δ={stationarity['delta_pct']}pp)")
    if recent_recalibrated:
        print(f"  NOTICE: {probe} — auto-refit on recent half "
              f"(n={n}, bias_factor={diag['bias_factor']}).")
    elif bias_cohort.startswith('regime-'):
        print(f"  NOTICE: {probe} — {bias_cohort} bias "
              f"correction already in force.")
    else:
        print(f"  NOTICE: {probe} — pooled bias kept; cohort "
              f"predates the target year, so no carryover "
              f"refit (v5 Cat L).")
