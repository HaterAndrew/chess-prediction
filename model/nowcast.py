"""N5v4_Final.predict_nowcast, verbatim as a mixin (04c 1142-1517)."""

import warnings

import numpy as np

from feature_engineering import compute_adjustment_factor, compute_all_features

from model.ci_floors import _predict_nowcast_ci_tail
from model.constants import (ENSEMBLE_DIVERGENCE_THRESHOLD,
                             ENSEMBLE_DIVERGENCE_WIDENING, FAMILY_ALIASES,
                             MAX_WITHDRAWAL_CORRECTION, TODAY)
from model.stats import _filter_ratios, lognormal_ci

class NowcastMixin:
    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        """
        Predict final count given current registrations and days remaining.
        days_remaining = days until event_start (T=0 is first day of tournament).
        Training T is anchored to event_start after reanchor_daily_to_event_start().
        Prediction includes expected on-site registrations (baked into ratios).

        Side effect (AUDIT.md B1): records `self._last_tier` and, unless
        `_track_tier=False`, increments `self._tier_counts[tier]` so callers
        can surface fallback distribution.
        Tiers: 'family-direct', 'family-alias', 'size-matched', 'guard-no-data',
        'guard-event-started', 'guard-no-ratios'.

        `_exclude_tid` (v5 Cat L): drop that tournament's own ratio from every
        ratio list for this one call — recalibrate()'s per-record LOO seam.
        Must be popped (kwargs is re-read for feature adjustments below).
        """
        warnings.filterwarnings("ignore")  # scoped here from the old module-level call (P2b):
        # numeric/sklearn noise fires inside this method; importing the
        # model package no longer poisons every importer process-wide.
        track_tier = kwargs.pop('_track_tier', True)
        exclude_tid = kwargs.pop('_exclude_tid', None)

        # Initialize tier tracking lazily for user-facing predictions only.
        if track_tier and not hasattr(self, '_tier_counts'):
            from collections import defaultdict
            self._tier_counts = defaultdict(int)
            self._last_tier = None

        def record_tier(tier):
            self._last_tier = tier
            if track_tier:
                self._tier_counts[tier] += 1

        # AUDIT.md C8 — flag predictions for families with sparse history.
        # Default n_editions=0 for unknown families. Threshold of 4 picked from
        # the lognormal CI: <4 points means parametric CI is unreliable.
        n_editions = self.family_n_editions.get(family, 0) if hasattr(self, 'family_n_editions') else 0
        self._last_low_confidence = n_editions < 4

        # Guard: event already started or no data
        if days_remaining < 0:
            record_tier('guard-event-started')
            return current_count, current_count, current_count
        if current_count <= 0:
            record_tier('guard-no-data')
            return None, None, None

        # Late-surge families: dampen ratio extrapolation to avoid over-prediction
        # These events get bulk registrations in the last 1-3 days
        is_late_surge = family in self.LATE_SURGE_FAMILIES
        is_blitz = family in self.BLITZ_FAMILIES

        # Use family-specific ratios if available (>= 2 data points at some T)
        use_family = False
        used_alias = False
        fam_ratios = self.ratios.get(family, {})

        # Check family aliases: pool ratios from comparable families
        if not fam_ratios and family in FAMILY_ALIASES:
            fam_ratios = {}
            for alias_fam in FAMILY_ALIASES[family]:
                alias_rats = self.ratios.get(alias_fam, {})
                for T, rats in alias_rats.items():
                    if isinstance(T, (int, float)):
                        fam_ratios.setdefault(T, []).extend(rats)
            used_alias = bool(fam_ratios)

        # v5 Cat L: LOO exclusion happens BEFORE the >=2 usable-ratios scan,
        # so a family reduced below 2 ratios falls to size-matched exactly as
        # it would for a genuinely unseen event (mirrors _calibrate's fallback).
        fam_ratios = _filter_ratios(fam_ratios, exclude_tid)

        if fam_ratios:
            for T, rats in fam_ratios.items():
                if isinstance(T, (int, float)) and len(rats) >= 2:
                    use_family = True
                    break

        if use_family:
            record_tier('family-alias' if used_alias else 'family-direct')
        else:
            record_tier('size-matched')
            # Fall back to size-matched families instead of global
            fam_ratios = _filter_ratios(
                self._get_size_matched_ratios(current_count), exclude_tid)
            if not fam_ratios:
                record_tier('guard-no-ratios')
                return None, None, None

        available_T = sorted([k for k in fam_ratios.keys()
                             if isinstance(k, (int, float))])
        if not available_T:
            return None, None, None

        # Interpolate between two nearest chop points to avoid discontinuities
        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        T_below = max([t for t in available_T if t <= days_remaining], default=None)
        T_above = min([t for t in available_T if t >= days_remaining], default=None)

        if T_below is not None and T_above is not None and T_below != T_above:
            # Inverse-distance weighted blend of two nearest T buckets
            dist_total = T_above - T_below
            w_below = (T_above - days_remaining) / dist_total
            w_above = (days_remaining - T_below) / dist_total

            rats_below = [r[0] for r in fam_ratios[T_below]]
            rats_above = [r[0] for r in fam_ratios[T_above]]
            g_sigma_below = self.global_log_sigma.get(T_below)
            g_sigma_above = self.global_log_sigma.get(T_above)

            med_b, lo_b, hi_b = lognormal_ci(
                rats_below, level=0.80, global_sigma=g_sigma_below,
                label=family, count_stats=False)
            med_a, lo_a, hi_a = lognormal_ci(
                rats_above, level=0.80, global_sigma=g_sigma_above,
                label=family, count_stats=False)

            # Blend in log space for ratios
            med = np.exp(w_below * np.log(med_b) + w_above * np.log(med_a))
            lo_r = np.exp(w_below * np.log(lo_b) + w_above * np.log(lo_a))
            hi_r = np.exp(w_below * np.log(hi_b) + w_above * np.log(hi_a))

            # Blend calibration scales too
            scale_b = self.ci_scale.get(T_below, 1.0)
            scale_a = self.ci_scale.get(T_above, 1.0)
            scale = w_below * scale_b + w_above * scale_a
        else:
            ratio_list = [r[0] for r in fam_ratios[closest_T]]
            if not ratio_list:
                return None, None, None
            g_sigma = self.global_log_sigma.get(closest_T)
            med, lo_r, hi_r = lognormal_ci(
                ratio_list, level=0.80, global_sigma=g_sigma,
                label=family, count_stats=False)
            scale = self.ci_scale.get(closest_T, 1.0)

        # Apply calibration scaling (scale already set above for interpolated path)
        if scale != 1.0:
            log_med = np.log(med)
            log_lo = np.log(lo_r)
            log_hi = np.log(hi_r)
            half_w = (log_hi - log_lo) / 2
            half_w *= scale
            lo_r = np.exp(log_med - half_w)
            hi_r = np.exp(log_med + half_w)

        # For non-family fallback, cap ratios based on lead time
        # (size-matched ratios are better than global but still noisy)
        # Exempt blitz events — they have legitimately high short-T ratios
        if self._stage_on('ratio_caps') and not use_family and not is_blitz:
            if days_remaining <= 7:
                cap_med, cap_lo_r, cap_hi_r = 2.0, 1.5, 3.0
            elif days_remaining <= 28:
                cap_med, cap_lo_r, cap_hi_r = 5.0, 3.0, 8.0
            else:
                cap_med, cap_lo_r, cap_hi_r = 15.0, 10.0, 25.0
            # v3 N6: the cap used to bind silently, so a genuinely high-growth
            # family on the size-matched fallback was quietly held down with no
            # trace in the output. Count it — a family that keeps hitting the cap
            # is one whose own ratios should be fitted instead of borrowed.
            if med > cap_med:
                self._ratio_cap_hits = getattr(self, '_ratio_cap_hits', 0) + 1
                self._ratio_cap_families = getattr(self, '_ratio_cap_families', set())
                self._ratio_cap_families.add(family)
            med = min(med, cap_med)
            lo_r = min(lo_r, cap_lo_r)
            hi_r = min(hi_r, cap_hi_r)

        # Late-surge damping: these events get most registrations in last 1-3 days
        # Standard ratios over-extrapolate because early registration is very sparse
        # Use aggressive damping — these tournaments have ~1.1-1.4x ratio even at T=28
        if self._stage_on('late_surge') and is_late_surge and days_remaining > 3:
            # Target ratio: 1.1-1.5 depending on lead time (much lower than standard opens)
            max_ratio = 1.1 + 0.4 * min(days_remaining / 90, 1.0)  # 1.1 at T=3, 1.5 at T=90
            if med > max_ratio:
                med = max_ratio
            lo_r = min(lo_r, med)
            hi_r = min(hi_r, max_ratio * 1.5)

        # Count-based ratio adjustment: when current count is already a large
        # fraction of the expected final, shrink ratios toward 1.0
        # (high counts → tournament is close to final → lower remaining growth)
        fam_mean = self.family_mean_final.get(family, 0)
        if fam_mean > 0 and current_count > 0 and use_family:
            fill_pct = current_count / fam_mean  # e.g., 0.7 = 70% of expected final
            if fill_pct > 0.6:
                # Linearly shrink toward 1.0 as fill_pct goes from 0.6 to 1.0+
                shrink = min(1.0, (fill_pct - 0.6) * 2.0)  # 0 at 0.6, 0.8 at 1.0
                med = 1.0 + (med - 1.0) * (1 - shrink * 0.2)  # at most 20% reduction
                lo_r = 1.0 + (lo_r - 1.0) * (1 - shrink * 0.2)
                hi_r = 1.0 + (hi_r - 1.0) * (1 - shrink * 0.2)

        point = current_count * med
        low = current_count * lo_r
        high = current_count * hi_r

        # At long T with very low counts, anchor toward family historical size
        # Blend of recent final (60%) and mean (40%) — recent is a better
        # predictor (MAPE 13.8%) but mean is more stable
        anchor_thresh = 15 if days_remaining < 60 else 30
        if current_count < anchor_thresh and days_remaining >= 42 and use_family:
            fam_recent = self.family_recent_final.get(family, 0)
            fam_mean_val = self.family_mean_final.get(family, 0)
            if fam_recent > 0 and fam_mean_val > 0:
                fam_anchor = 0.6 * fam_recent + 0.4 * fam_mean_val
            else:
                fam_anchor = fam_recent or fam_mean_val
            if fam_anchor > 0:
                # Blend: more weight to anchor when count is very low
                anchor_w = max(0.2, min(0.6, 1.0 - current_count / anchor_thresh))
                point = anchor_w * fam_anchor + (1 - anchor_w) * point
                # Widen CI to reflect uncertainty of anchoring
                low = min(low, point * 0.5)
                high = max(high, point * 1.5)

        # Cap CI width relative to point estimate to prevent absurd CIs
        # at long lead times (where LOO leaves too few family data points)
        # Use tighter cap at shorter lead times where we have more certainty
        if days_remaining >= 60:
            cap_hi, cap_lo = 2.0, 0.45
        elif days_remaining >= 28:
            cap_hi, cap_lo = 1.8, 0.5
        elif days_remaining >= 7:
            cap_hi, cap_lo = 1.5, 0.6
        elif days_remaining >= 3:
            cap_hi, cap_lo = 1.40, 0.65
        else:
            cap_hi, cap_lo = 1.40, 0.65
        high = min(high, point * cap_hi)
        low = max(low, point * cap_lo)

        # Ensemble: blend ratio-based point estimate with pooled regression
        # Regression uses (count_at_T, T) -> final_count
        fam_reg = self.reg_params.get(family)
        # For aliased families, try alias regression params
        if fam_reg is None and family in FAMILY_ALIASES:
            for alias_fam in FAMILY_ALIASES[family]:
                fam_reg = self.reg_params.get(alias_fam)
                if fam_reg is not None:
                    break
        if fam_reg is None and not use_family and days_remaining >= 14:
            # Build size-matched regression only at long lead times for unknown
            # families. At short T (< 14), ratio-based prediction is more reliable
            # because ratios converge to ~1.0 and regression tends to over-predict.
            fam_reg = self._get_size_matched_regression(current_count)
        if fam_reg is not None:
            coeffs = fam_reg  # [slope_count, slope_T, intercept]
            reg_pred = coeffs[0] * current_count + coeffs[1] * days_remaining + coeffs[2]
            reg_pred = max(reg_pred, current_count)
            w = self._ensemble_weight(days_remaining)
            ratio_point = point
            point = w * point + (1 - w) * reg_pred
            # At long T the ratio model has high variance, so a large divergence
            # from the regression is a signal to lean on the regression.
            #
            # v3 N5 (audit/AUDIT_2026-07-25.md): this used to DISCARD the ratio
            # model outright (`point = reg_pred`) the moment divergence crossed
            # 50%. Two models disagreeing is evidence that neither is confident,
            # not evidence that one is right — and the hard swap put a
            # discontinuity in the output at exactly the 50% line. Shift the
            # blend toward the regression instead, and widen the interval to
            # reflect the disagreement rather than hiding it.
            if days_remaining >= 60:
                ratio_diff = abs(ratio_point - reg_pred) / max(reg_pred, 1)
                if ratio_diff > ENSEMBLE_DIVERGENCE_THRESHOLD:
                    # Fully weight regression at 2x the threshold, easing in from
                    # the threshold itself so there is no step in the output.
                    excess = ratio_diff - ENSEMBLE_DIVERGENCE_THRESHOLD
                    shift = min(1.0, excess / ENSEMBLE_DIVERGENCE_THRESHOLD)
                    point = point * (1 - shift) + reg_pred * shift
                    # Disagreement is real uncertainty: widen proportionally to it.
                    widen = 1.0 + min(ratio_diff, 1.0) * ENSEMBLE_DIVERGENCE_WIDENING
                    half_lo = (point - low) * widen
                    half_hi = (high - point) * widen
                    low, high = point - half_lo, point + half_hi

        # (YoY pacing tested: hurt MAPE in all configs. Ratio model already
        # captures count-level info; pacing adds noise from timing variability.)

        # Re-center CI on ensemble point estimate in log-space to preserve
        # lognormal asymmetry (right-skewed, appropriate for count data)
        if point > 0 and low > 0 and high > 0:
            log_half_w = (np.log(high) - np.log(low)) / 2
            low = np.exp(np.log(point) - log_half_w)
            high = np.exp(np.log(point) + log_half_w)
        else:
            ci_half_width = max((high - low) / 2, 1)
            low = point - ci_half_width
            high = point + ci_half_width

        # Guard against NaN from any upstream calculation. H16: collapsing to a
        # zero-width CI at current_count is a real degradation — surface it rather
        # than silently shipping a fake point-mass interval.
        if any(np.isnan(x) for x in (point, low, high)):
            print(f"WARNING: NaN in prediction interval (point={point}, low={low}, "
                  f"high={high}); collapsing to current_count={current_count}")
            # v3 N12: give this its own tier bucket. The collapse used to be
            # counted under whichever tier the prediction had reached, so a run
            # producing degraded point-mass intervals looked, in the tier tally,
            # exactly like a run of healthy predictions.
            record_tier('guard-nan')
            return current_count, current_count, current_count

        # Growth trend adjustment: shift prediction for growing/declining families
        # e.g., if a tournament grows ~5%/year, nudge prediction up for current year
        trend = self.family_trend.get(family, 0.0)
        if self._stage_on('trend') and trend != 0.0 and days_remaining >= 7:
            # Apply trend relative to most recent training year
            # Moderate: at most half the raw trend rate to avoid overfit
            adj = 1.0 + trend * 0.5
            point *= adj
            # Shift CI center but don't widen — trend is a location shift
            low *= adj
            high *= adj

        # Widen CIs for families with few training editions.
        # Size-matched fallback (0 editions) and single-edition families
        # have much higher prediction variance than well-observed families.
        n_editions = self.family_n_editions.get(family, 0)
        # For aliased families, sum editions across all alias sources
        if n_editions == 0 and family in FAMILY_ALIASES:
            n_editions = sum(self.family_n_editions.get(f, 0)
                            for f in FAMILY_ALIASES[family])
        # Sparse-history widening. This is multiplicative, so unlike the floors
        # below it must run exactly once (v3 N3 — the ratio floors and caps that
        # used to live here now sit in _apply_ci_floors, which is idempotent and
        # runs again after recalibration).
        if n_editions == 0:
            ci_half_width = (high - low) / 2 * self.CI_WIDEN_0_EDITIONS
            low = point - ci_half_width
            high = point + ci_half_width
        elif n_editions == 1:
            ci_half_width = (high - low) / 2 * self.CI_WIDEN_1_EDITION
            low = point - ci_half_width
            high = point + ci_half_width

        # Withdrawal rate correction: reduce prediction by expected withdrawal %.
        # v3 N4 (audit/AUDIT_2026-07-25.md): the comment said "cap at 15%" but
        # the condition `wd_rate < 0.15` DISABLED the correction above the
        # threshold instead of capping it. A family at 14.9% withdrawals got the
        # full correction; one at 15.1% — withdrawing more — got none at all, a
        # discontinuity that moved the estimate the wrong way exactly where the
        # correction matters most. Cap the rate, as intended.
        wd_rate = self.family_withdrawal_rates.get(family, 0.0)
        if self._stage_on('withdrawal') and wd_rate > 0:
            wd_rate = min(wd_rate, MAX_WITHDRAWAL_CORRECTION)
            point *= (1 - wd_rate)
            low *= (1 - wd_rate)
            high *= (1 - wd_rate)

        # Feature-engineered adjustments: day-of-week, holiday proximity,
        # early-bird deadline distance. These apply small multiplicative
        # corrections to the point estimate and CI bounds.
        eb_deadline = kwargs.get('early_bird_deadline')
        event_start = kwargs.get('event_start_date')
        if self._stage_on('features') and event_start and days_remaining > 0:
            try:
                features = compute_all_features(TODAY, event_start, eb_deadline)
                feat_adj = compute_adjustment_factor(features, days_remaining)
                if feat_adj != 1.0:
                    point *= feat_adj
                    low *= feat_adj
                    high *= feat_adj
            except (ValueError, TypeError) as e:
                # v3 N11: this used to be a bare `pass`. A broken feature
                # pipeline then degraded every prediction silently — the
                # day-of-week, holiday and early-bird adjustments would stop
                # applying with nothing anywhere to say so. Surface it; the
                # prediction still proceeds unadjusted.
                print(f"WARNING: feature adjustment failed for {family} "
                      f"(T-{days_remaining}): {type(e).__name__}: {e}; "
                      f"prediction continues without feature corrections.")

        return _predict_nowcast_ci_tail(
            self, point, low, high,
            days_remaining=days_remaining, current_count=current_count,
            n_editions=n_editions, is_blitz=is_blitz)

