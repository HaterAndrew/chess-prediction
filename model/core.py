"""N5v4_Final: class shell + calibration + size-matched fallbacks.

fit/predict_nowcast/recalibrate bodies live in fitting/nowcast/
recalibration as mixins — moved verbatim, self untouched, so the
decomposition diff is relocation only (04c 579-663 + 996-1141).
"""

import numpy as np
from sklearn.linear_model import HuberRegressor

from model.constants import CHOP_POINTS
from model.fitting import FitMixin
from model.nowcast import NowcastMixin
from model.recalibration import RecalibrationMixin
from model.stats import lognormal_ci

class N5v4_Final(FitMixin, NowcastMixin, RecalibrationMixin):
    """
    Historical ratio model with:
    - Exclusion of in-progress tournaments from ratio computation
    - Lognormal parametric CIs
    - LOO-calibrated CI width scaling with ensemble shrinkage
    - Ensemble: blends ratio prediction with per-family pooled
      regression using final ~ count_at_T + T + intercept
      (T-dependent weights: ratio 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28)
    - Ratio cap: at T>=60, falls back to regression-only if ratio
      prediction diverges >50% from regression
    - CI widening for low-history families (0 or 1 prior editions)
    """
    name = "N5v4_Final"

    # Weight given to the ratio model when blending it with the pooled
    # regression, by lead-time bucket: (bucket upper bound in days, weight).
    # None means "everything above the previous bound". The ratio model is more
    # accurate at short T, where the ratio converges toward 1:1, so it carries
    # most of the weight there and cedes to the regression at long T.
    #
    # v3 T9 (audit/AUDIT_2026-07-25.md): these four numbers were hand-picked and
    # never fitted. scripts/fit_ensemble_weights.py searches them against
    # held-out folds and they survived it — each one sits on the pooled optimum
    # or one grid step away, on a curve that is flat nearby, and weights fitted
    # by nested CV were 0.13 MAE points WORSE out of sample than these. Do not
    # change them without re-running that script; the full result is in its
    # docstring.
    ENSEMBLE_WEIGHTS = ((3, 0.80), (7, 0.55), (28, 0.30), (None, 0.15))

    # (v3 T6: CI_ENSEMBLE_SHRINK = 0.32 used to sit here with zero readers — the
    # actual shrinkage is the T-dependent table in fit(). Removed rather than
    # left to imply a knob that does nothing.)
    # CI widening multipliers for families with few training editions.
    # 0-edition families use size-matched fallback which is inherently noisy;
    # 1-edition families have a single ratio data point per T.
    # These factors were calibrated on 2024-2025 holdout to bring coverage
    # from ~40% up to ~80% for these subgroups. Increased from 5.0/3.0 to
    # compensate for tighter ensemble shrinkage (0.32 vs 0.42).
    CI_WIDEN_0_EDITIONS = 2.5
    CI_WIDEN_1_EDITION = 1.5

    def __init__(self):
        self.ratios = {}
        self.ci_scale = {}
        self.reg_params = {}  # family -> [slope_count, slope_T, intercept]
        self.family_n_editions = {}  # family -> count of training editions

    def _ensemble_weight(self, days_remaining):
        """Ratio-model weight for this lead time.

        Reads the instance attribute when one is set so the weight-fitting
        script can try candidate tables without touching the class default.
        """
        table = getattr(self, 'ensemble_weights', None) or self.ENSEMBLE_WEIGHTS
        for bound, weight in table:
            if bound is None or days_remaining <= bound:
                return weight
        return table[-1][1]

    # Stages of predict_nowcast that can be switched off individually, for the
    # ablation harness (v3 T8, audit/AUDIT_2026-07-25.md). predict_nowcast is a
    # ~400-line, 13-stage pipeline whose stages had never been measured
    # separately: each one's marginal contribution was assumed, not shown. Every
    # stage defaults to ON, so production behaviour is unchanged unless a caller
    # explicitly ablates something.
    ABLATABLE_STAGES = ('late_surge', 'ratio_caps', 'trend', 'withdrawal',
                        'features', 'recal')

    def set_stage_flags(self, **flags):
        """Enable/disable individual prediction stages. Unknown names raise, so
        a typo in an ablation run fails loudly instead of silently measuring
        nothing."""
        unknown = set(flags) - set(self.ABLATABLE_STAGES)
        if unknown:
            raise ValueError(f"unknown stage(s): {sorted(unknown)}; "
                             f"valid: {list(self.ABLATABLE_STAGES)}")
        self._stage_flags = dict(getattr(self, '_stage_flags', {}) or {})
        self._stage_flags.update(flags)
        return self

    def _stage_on(self, name):
        flags = getattr(self, '_stage_flags', None)
        return True if not flags else flags.get(name, True)


    def _calibrate(self, valid, daily, cal_max_year=None):
        """LOO calibration to find CI scale factors per T via binary search.

        cal_max_year: if set, only use tournaments with year < cal_max_year
        for calibration (expanding-window approach to avoid leakage).
        """
        cal_valid = valid
        if cal_max_year is not None:
            cal_valid = valid[valid['tournament_year'] < cal_max_year]

        for T in CHOP_POINTS:
            # Collect all LOO error ratios for this T
            loo_data = []
            for _, row in cal_valid.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']

                td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
                if len(td) < 5:
                    continue

                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                # LOO: get family ratios excluding this tournament
                fam_rats = self.ratios.get(family, {}).get(T, [])
                loo = [r[0] for r in fam_rats if r[2] != tid]
                if len(loo) < 2:
                    loo = [r[0] for r in self.global_ratios.get(T, []) if r[2] != tid]
                if len(loo) < 2:
                    continue

                loo_data.append((count_at_T, actual, loo))

            if len(loo_data) < 10:
                self.ci_scale[T] = 1.0
                continue

            # Binary search for scale factor that gives ~80% coverage
            g_sigma = self.global_log_sigma.get(T)

            def get_coverage(scale):
                covered = 0
                for count_at_T, actual, loo in loo_data:
                    med, lo_r, hi_r = lognormal_ci(
                        loo, level=0.80, global_sigma=g_sigma,
                        count_stats=False,
                    )
                    if scale != 1.0:
                        log_med = np.log(med)
                        log_lo = np.log(lo_r)
                        log_hi = np.log(hi_r)
                        hw = (log_hi - log_lo) / 2 * scale
                        lo_r = np.exp(log_med - hw)
                        hi_r = np.exp(log_med + hw)
                    lo = count_at_T * lo_r
                    hi = count_at_T * hi_r
                    if lo <= actual <= hi:
                        covered += 1
                return covered / len(loo_data)

            lo_s, hi_s = 0.4, 2.0
            for _ in range(20):
                mid_s = (lo_s + hi_s) / 2
                cov = get_coverage(mid_s)
                if cov < 0.80:
                    lo_s = mid_s
                else:
                    hi_s = mid_s

            self.ci_scale[T] = round(hi_s, 3)

    def _get_size_matched_regression(self, current_count):
        """Build a Huber regression from size-matched families' training data.

        Returns coefficients [slope_count, slope_T, intercept] or None.
        """
        est_final = current_count * 2
        matched_pts = []
        for fam, mean_final in self.family_mean_final.items():
            if est_final > 0 and 0.5 <= mean_final / est_final <= 2.0:
                matched_pts.extend(self._reg_data.get(fam, []))
        if len(matched_pts) < 10:
            est_final = current_count * 2
            if est_final > 300 and self._large_reg is not None:
                return self._large_reg
            elif self._small_reg is not None:
                return self._small_reg
            return None
        X = np.array([[p[0], p[1]] for p in matched_pts], dtype=float)
        y = np.array([p[2] for p in matched_pts], dtype=float)
        try:
            hub = HuberRegressor(epsilon=1.35, max_iter=200)
            hub.fit(X, y)
            return np.array([hub.coef_[0], hub.coef_[1], hub.intercept_])
        except Exception:
            return None

    def _get_size_matched_ratios(self, current_count):
        """Build ratios from families with similar historical size (within 2x).

        For new families with no history, this is much better than global
        because a 1500-person tournament has very different growth ratios
        than a 50-person tournament.
        """
        # Estimate final count from current_count — use global median ratio at
        # a generic T to get a rough size estimate, or just use current_count
        est_final = current_count * 2  # rough estimate for size matching
        size_matched = {}
        for fam, mean_final in self.family_mean_final.items():
            # Within 2x of estimated final size
            if est_final > 0 and 0.5 <= mean_final / est_final <= 2.0:
                fam_rats = self.ratios.get(fam, {})
                for T, rats in fam_rats.items():
                    if isinstance(T, (int, float)):
                        size_matched.setdefault(T, []).extend(rats)
        # Need enough data — fall back to global if too few matches
        has_enough = any(len(v) >= 3 for v in size_matched.values())
        if has_enough:
            return size_matched
        return self.ratios.get('__global__', {})

    # Families with late-surge registration patterns (scholastic/HS events)
    # where standard ratio extrapolation over-predicts
    LATE_SURGE_FAMILIES = {
        'New York State High School Championship',
        'New York State Scholastic Championships Grades K-8',
        'New York State Scholastic Championships',
    }

    # Blitz/action events: massive day-of registration (100-300% growth at T<=1)
    # Standard ratio models vastly underpredict these.
    # Auto-populated from data during fit(); seeded with known families.
    BLITZ_FAMILIES = {
        'World Open Blitz Championship',
        'North American Blitz Championship',
        'Chicago Open Blitz',
        'Blitz at Foxwoods',
        'World Open Action',
    }

