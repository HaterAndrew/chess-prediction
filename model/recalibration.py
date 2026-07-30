"""N5v4_Final.recalibrate, verbatim as a mixin (04c 1518-1869)."""

import warnings

import numpy as np
import pandas as pd

from model.constants import (RECAL_IN_SAMPLE_WIDENING, RECAL_MIN_OOS_RECORDS,
                             RECAL_REGIME_MIN_N)

class RecalibrationMixin:
    def recalibrate(self, completed_tournaments, daily, T_points=None,
                    target_coverage=0.80, ci_min_scale=0.5, ci_max_scale=3.0,
                    loo=True, regime_year=None):
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
            # Records: (residual_pct, log_actual, log_point, log_halfwidth,
            #           ci_hit, last_reg, in_sample, tournament_year)
            records = []

            for _, row in completed_sorted.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']
                lr = row.get('_lr', pd.NaT) if '_lr' in row else pd.NaT

                td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
                if len(td) == 0:
                    continue

                # Find count at this T (within 2-day tolerance)
                available = td[(td['T'] >= T - 2) & (td['T'] <= T + 2)].copy()
                if len(available) == 0:
                    continue
                available['dist'] = (available['T'] - T).abs()
                closest = available.sort_values('dist').iloc[0]
                count_at_T = int(closest['cum_regs'])
                if count_at_T <= 0:
                    continue

                # Predict WITHOUT recalibration (use raw model). Under loo,
                # also without the tournament's own ratio (v5 Cat L).
                old_bias = self._recal_bias
                old_ci = self._recal_ci
                self._recal_bias = {}
                self._recal_ci = {}
                point, lo, hi = self.predict_nowcast(
                    count_at_T, T, family, _track_tier=False,
                    _exclude_tid=tid if loo else None)
                # v5 Cat L width geometry: the LOO interval is systematically
                # WIDER than the interval production will publish — dropping a
                # ratio from a 3-5 entry family list triggers the small-n EB
                # sigma floor. Normalizing honest residuals by LOO widths
                # understated the needed scale (measured: fold ci_adj fell to
                # the 0.5 floor and fold coverage collapsed to ~41%). So: LOO
                # point for the residual NUMERATOR (honest location error),
                # full-list width for the DENOMINATOR (application geometry).
                if loo:
                    point_full, lo_full, hi_full = self.predict_nowcast(
                        count_at_T, T, family, _track_tier=False)
                    if (point_full is not None and point_full > 0
                            and lo_full > 0 and hi_full > 0):
                        lo_w, hi_w = lo_full, hi_full
                    else:
                        lo_w, hi_w = lo, hi
                else:
                    lo_w, hi_w = lo, hi
                self._recal_bias = old_bias
                self._recal_ci = old_ci

                if point is None or point <= 0 or lo <= 0 or hi <= 0:
                    continue

                err_pct = (point - actual) / actual
                # Half-width in log space (the lognormal CI's natural unit)
                log_halfw = (np.log(max(hi_w, 1)) - np.log(max(lo_w, 1))) / 2.0
                if log_halfw <= 0:
                    continue
                log_actual = np.log(max(actual, 1))
                log_point = np.log(max(point, 1))
                # coverage_before describes the interval production would
                # publish (pre-recal), so it uses the application-width bounds.
                ci_hit = 1 if lo_w <= actual <= hi_w else 0
                in_sample = tid in getattr(self, '_fit_tids', set())
                year = row.get('tournament_year')
                year = int(year) if pd.notna(year) else None
                records.append((err_pct, log_actual, log_point, log_halfw, ci_hit,
                                lr, in_sample, year))

            if len(records) < 3:
                continue

            # v3 T3 → v5 Cat L (audit/AUDIT_2026-07-30.md): the v3 oos-preference
            # was dead code — every production caller hands recalibrate() a
            # strict subset of the fit frame, so len(oos) was always 0, the
            # cohort was always in-sample, and both corrections were ~null
            # (measured bias ~0 against a real 2026 bias of +7..+11%). Under
            # loo=True the residual loop above already excluded each
            # tournament's own ratio, so every record is honest and the whole
            # cohort is usable. The loo=False branch keeps the old logic.
            oos = [r for r in records if not r[6]]
            cohort_is_in_sample = False
            if loo:
                pass  # all records are pseudo-out-of-sample by construction
            elif len(oos) >= RECAL_MIN_OOS_RECORDS:
                records = oos
            elif len(oos) < len(records):
                # Not enough held-out events to calibrate on. Keep the in-sample
                # cohort but say so, and widen below rather than publish an
                # interval whose width was measured on training data.
                cohort_is_in_sample = True

            # ── Bias correction ─────────────────────────────────────────
            err_arr = np.array([r[0] for r in records])

            def _trimmed_mean(errs):
                """IQR-trimmed mean (>2x IQR dropped), falling back to the
                raw mean below 3 survivors — same rule the pooled path has
                always used."""
                errs = np.asarray(errs, dtype=float)
                q1, q3 = np.percentile(errs, [25, 75])
                iqr = q3 - q1
                m = (errs >= q1 - 2 * iqr) & (errs <= q3 + 2 * iqr)
                kept = errs[m]
                return float(np.mean(kept if len(kept) >= 3 else errs))

            # v5 Cat L: bias is a REGIME (location) property. Production recal
            # exists to correct predictions for the current year, and a pooled
            # multi-year mean dilutes a current-regime shift toward 0 (measured
            # 2026-07-30: 2026-only bias +14.2% at T=3 / +4..5% at mid-T while
            # the pooled mean read ~0). Fires ONLY when the cohort actually
            # CONTAINS the target year (regime_year) with enough records —
            # fitting bias on year-1 and assuming carryover measurably
            # overcorrected the 2024 backtest fold. Implements what the 04d
            # call site has always claimed ("Recent data is weighted more
            # heavily"). The CI width quantile below stays pooled: scale is
            # stable across years, and n~24 is too thin for an 80th percentile.
            bias_cohort = 'pooled'
            years = [r[7] for r in records if r[7] is not None]
            if regime_year is not None and years and max(years) == regime_year:
                regime_errs = [r[0] for r in records if r[7] == regime_year]
                if len(regime_errs) >= RECAL_REGIME_MIN_N:
                    mean_bias = _trimmed_mean(regime_errs)
                    bias_cohort = f'regime-{regime_year}'
            if bias_cohort == 'pooled':
                mean_bias = _trimmed_mean(err_arr)
            bias_factor = 1.0 / (1.0 + mean_bias)
            bias_factor = max(0.80, min(1.20, bias_factor))

            # Stationarity probe: split records chronologically (older half vs
            # newer half). Diagnostic always; the auto-refit fires only on the
            # pooled path — the regime path already fits on the newest cohort,
            # and pruning records here would thin the pooled width quantile.
            stationarity = None
            recent_recalibrated = False
            if len(records) >= 6:
                mid = len(records) // 2
                old_half = err_arr[:mid]
                new_half = err_arr[mid:]
                stationarity = {
                    'old_bias_pct': round(float(np.mean(old_half)) * 100, 1),
                    'new_bias_pct': round(float(np.mean(new_half)) * 100, 1),
                    'delta_pct': round((float(np.mean(new_half)) - float(np.mean(old_half))) * 100, 1),
                }
                # AUDIT.md C2 auto-action — when bias is non-stationary across
                # halves by more than 5pp, refit bias_factor on just the recent
                # half. Old-cohort behavior (pre-2024 conditions) shouldn't drag
                # current predictions backward. The records list is also pruned
                # so the CI scale below is computed from the same recent cohort.
                # v5 Cat L: the refit is the same carryover bet the regime gate
                # polices, so it fires only when the cohort CONTAINS the target
                # year (then the recent half includes current-regime records —
                # the small-current-n complement to the regime path). With
                # honest LOO residuals, refitting a pre-target-year cohort on
                # its recent half applied 2023's real -12% to the 2024 fold
                # and overshot it to +17.9% at T=28.
                cohort_has_target = (regime_year is not None and years
                                     and max(years) == regime_year)
                if (bias_cohort == 'pooled' and cohort_has_target
                        and abs(stationarity['delta_pct']) > 5.0):
                    new_records = records[mid:]
                    new_trimmed = new_half
                    nq1, nq3 = np.percentile(new_trimmed, [25, 75])
                    niqr = nq3 - nq1
                    nmask = (new_trimmed >= nq1 - 2 * niqr) & (new_trimmed <= nq3 + 2 * niqr)
                    refit = new_trimmed[nmask] if nmask.sum() >= 3 else new_trimmed
                    mean_bias = float(np.mean(refit))
                    bias_factor = 1.0 / (1.0 + mean_bias)
                    bias_factor = max(0.80, min(1.20, bias_factor))
                    records = new_records
                    err_arr = new_half
                    stationarity['action'] = 'refit-on-recent-half'
                    recent_recalibrated = True

            # ── CI scale (continuous derivation, AUDIT.md C1) ───────────
            # Empirical 80th percentile of normalized residual tells us the scale
            # needed to make the 80% CI actually cover 80% of cases. Compute it
            # around the same bias-corrected center used when the scale is later
            # applied in predict_nowcast().
            log_bias_factor = np.log(max(bias_factor, 1e-9))
            norm_residuals = np.array([
                abs(r[1] - (r[2] + log_bias_factor)) / r[3]
                for r in records
            ])
            empirical_q = float(np.percentile(norm_residuals, target_coverage * 100))
            # The empirical_q is already in units of half-width, so it is the
            # scale to apply around the bias-corrected center.
            ci_adj = empirical_q
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

            current_coverage = float(np.mean([r[4] for r in records]))

            # v5 Cat L cohort provenance: 'held-out' only when every record is
            # genuinely outside _fit_tids; 'loo' when fit-cohort records were
            # predicted with their own ratio excluded (honest, but not a claim
            # of true holdout); 'in-sample' only on the loo=False fallback.
            if len(oos) == len(records):
                cohort_label = 'held-out'
            elif loo:
                cohort_label = 'loo'
            else:
                cohort_label = 'in-sample' if cohort_is_in_sample else 'held-out'

            self._recal_bias[T] = bias_factor
            self._recal_ci[T] = ci_adj
            self._recal_n[T] = len(records)
            diag = {
                'n': len(records),
                'mean_bias': round(mean_bias * 100, 1),
                'coverage_before': round(current_coverage * 100, 0),
                'bias_factor': round(bias_factor, 3),
                'ci_adj': round(ci_adj, 3),
                'target_coverage': int(target_coverage * 100),
                # v3 T3: make the provenance of this scale inspectable.
                'cohort': cohort_label,
                # v5 Cat L: which subset the bias (location) correction was
                # fitted on — 'regime-<year>' or 'pooled'.
                'bias_cohort': bias_cohort,
                'n_out_of_sample': len(oos),
            }
            # v5 Cat L: surface clamp pinning. Ceiling pin = the published CI
            # is NARROWER than the residuals earned — a real warning. Floor
            # pin = the floor holds the CI wider than residuals asked for —
            # conservative, so a NOTICE (kept out of the harvested warning
            # channel; 04e's LOO folds pin the floor routinely at long T).
            if pre_clamp > ci_max_scale:
                diag['ci_adj_clamped'] = 'high'
                print(f"  WARNING: T={T} ci_adj pinned at ceiling "
                      f"{ci_max_scale} (residuals wanted {pre_clamp:.3f}) — "
                      f"published CI narrower than measured error.")
            elif pre_clamp < ci_min_scale:
                diag['ci_adj_clamped'] = 'low'
                print(f"  NOTICE: T={T} ci_adj pinned at floor "
                      f"{ci_min_scale} (residuals wanted {pre_clamp:.3f}).")
            if cohort_is_in_sample:
                print(f"  WARNING: T={T} recalibration ran on an in-sample cohort "
                      f"({len(oos)} held-out record(s), need {RECAL_MIN_OOS_RECORDS}); "
                      f"CI scale widened x{RECAL_IN_SAMPLE_WIDENING} to offset "
                      f"training-set optimism.")
            if stationarity:
                diag['stationarity'] = stationarity
                # Loud notice when bias materially differs across halves,
                # naming which correction is in force (v5 Cat L: the old else
                # branch always claimed "n<6", which was wrong whenever the
                # refit was declined by the regime/carryover gate instead).
                if abs(stationarity['delta_pct']) > 5.0:
                    probe = (f"T={T} bias non-stationary "
                             f"(old: {stationarity['old_bias_pct']}%, "
                             f"new: {stationarity['new_bias_pct']}%, "
                             f"Δ={stationarity['delta_pct']}pp)")
                    if recent_recalibrated:
                        print(f"  NOTICE: {probe} — auto-refit on recent half "
                              f"(n={len(records)}, "
                              f"bias_factor={diag['bias_factor']}).")
                    elif bias_cohort.startswith('regime-'):
                        print(f"  NOTICE: {probe} — {bias_cohort} bias "
                              f"correction already in force.")
                    else:
                        print(f"  NOTICE: {probe} — pooled bias kept; cohort "
                              f"predates the target year, so no carryover "
                              f"refit (v5 Cat L).")
            diagnostics[T] = diag

        return diagnostics


