"""N5v4_Final.fit, verbatim as a mixin (04c 664-995)."""

import os
import re

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor

from model.constants import CHOP_POINTS, OUTPUT_DIR
from model.stats import report_trim_stats, reset_trim_stats, trim_outliers

class FitMixin:
    def fit(self, summary, daily, enrichment_lookup=None, completed_tids=None,
            verbose_standings_join=True, all_summary_families=None,
            fold_year=None, exclude_family_years=None):
        """Build ratios from completed, non-online, non-covid tournaments.

        fold_year: when set (backtests), every auxiliary source is restricted to
            strictly earlier years. v3 T5 (audit/AUDIT_2026-07-25.md): the
            standings and enrichment joins had no fold filter, so an
            expanding-window fold predicting year Y could still read standings
            and withdrawal rates from year Y and later — 35 standings rows sit at
            year >= 2025, and one family's size anchor came entirely from its
            2026 row. Leave it None in production, where using all completed
            history is correct.
        exclude_family_years: optional {(family, year)} withheld from the
            standings and enrichment joins. The 2026 leave-one-out fold trains on
            every OTHER completed 2026 event, so a blanket fold_year cut would be
            wrong there; it withholds just the target's own row instead.

        completed_tids: optional set of 2026 tournament tids that have completed.
            If provided, these are included in training (rolling retraining).
            All other 2026 tournaments are excluded.
        verbose_standings_join: when False, suppress the orphan-list warning. Set
            False on backtest folds (04e) so the user-facing pipeline run doesn't
            emit the same warning N times for N expanding-window cohorts.
        all_summary_families: optional set of every family in the unfiltered summary.
            Used as the cross-check basis for validate_standings_join so pre-timestamp
            families (which are filtered out of the training subset but supplemented
            from standings later) don't show up as false orphans. If omitted, the
            current `summary` arg's families are used (less accurate when caller
            already filtered upstream — e.g., 04d passes train_ts).
        """
        self.enrichment = enrichment_lookup or {}

        # AUDIT.md C7 — reset trim counters at start of every fit so reports
        # reflect this fit only, not accumulated across calls.
        reset_trim_stats()

        # Auto-populate BLITZ_FAMILIES from data: any family matching the pattern
        _blitz_pat = re.compile(r'Blitz|Rapid|Bullet|Bughouse|Armageddon|Action|G/\d+|G \d+', re.IGNORECASE)
        for fam in summary['family'].unique():
            if _blitz_pat.search(fam):
                self.BLITZ_FAMILIES.add(fam)

        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ].copy()

        # Exclude in-progress 2026 tournaments, but keep completed ones
        if completed_tids:
            valid = valid[
                (valid['tournament_year'] < 2026) |
                (valid['tid'].isin(completed_tids))
            ]
        else:
            valid = valid[valid['tournament_year'] < 2026]

        # v3 T3 → v5 Cat L: remember exactly which tournaments contributed
        # ratios. recalibrate() needs it to tell a genuinely held-out residual
        # from a fit-cohort one. Populated INSIDE the loop below so a tid that
        # passed the frame filter but contributed zero ratios (len(td) < 5, or
        # no usable count at any T) doesn't count as in-sample — before v5 it
        # was captured from the frame up front and would have masked genuine
        # holdouts in n_out_of_sample.
        self._fit_tids = set()

        self.ratios = {}
        self.global_ratios = {}
        self.global_log_sigma = {}  # T -> sigma of log(ratios) across all families
        # Track family mean final counts for size-matched fallback
        self.family_mean_final = {}

        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            year = row['tournament_year']

            td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(td) < 5:
                continue

            if family not in self.ratios:
                self.ratios[family] = {}

            for T in CHOP_POINTS:
                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                ratio = actual / count_at_T
                self.ratios[family].setdefault(T, []).append((ratio, year, tid))
                self.global_ratios.setdefault(T, []).append((ratio, year, tid))
                self._fit_tids.add(tid)

        self.ratios['__global__'] = self.global_ratios

        # Compute mean final count per family for size-matched fallback
        fam_finals = valid.groupby('family')['final_count'].mean()
        self.family_mean_final = fam_finals.to_dict()

        # Most recent year's final count per family (better anchor than mean)
        recent = valid.sort_values('tournament_year').groupby('family')['final_count'].last()
        self.family_recent_final = recent.to_dict()

        # Compute per-family growth trend (YoY slope normalized by mean)
        # Used to adjust predictions for growing/declining tournaments
        self.family_trend = {}
        for fam, grp in valid.groupby('family'):
            grp_sorted = grp.sort_values('tournament_year')
            if len(grp_sorted) >= 3:
                counts = grp_sorted['final_count'].values
                years = grp_sorted['tournament_year'].values
                # Simple linear regression: count ~ year
                if len(set(years)) >= 3:
                    slope = np.polyfit(years, counts, 1)[0]
                    mean_count = np.mean(counts)
                    if mean_count > 0:
                        # Normalize slope as fraction of mean (e.g., -0.05 = 5% decline/year)
                        self.family_trend[fam] = np.clip(slope / mean_count, -0.15, 0.15)

        # Supplement with standings data — normalize names to match training families.
        # Single source of truth for the name map: tournament_aliases.STANDINGS_NAME_MAP.
        # AUDIT.md A2: previously the inline map had 19 entries while 37 unique
        # standings names existed in production — the rest dropped silently.
        standings_path = os.path.join(OUTPUT_DIR, "historical_standings.csv")
        if os.path.exists(standings_path):
            from tournament_aliases import STANDINGS_NAME_MAP, validate_standings_join
            standings = pd.read_csv(standings_path)
            standings = standings[standings['total_players'] > 10]
            # v3 T5: a backtest fold must not see standings from its own target
            # year or later. Production (fold_year=None) keeps everything.
            if fold_year is not None and 'year' in standings.columns:
                before = len(standings)
                standings = standings[standings['year'] < fold_year]
                if verbose_standings_join and before != len(standings):
                    print(f"  Standings restricted to year < {fold_year}: "
                          f"{before} -> {len(standings)} rows")
            if exclude_family_years and 'year' in standings.columns:
                standings = standings[~standings.apply(
                    lambda r: (r['tournament_name'], int(r['year'])) in exclude_family_years,
                    axis=1)]
            standings['tournament_name'] = standings['tournament_name'].replace(
                STANDINGS_NAME_MAP)
            # Surface unmapped names so silent drops become visible.
            # Cross-check against the full summary families, not just the
            # training subset (which excludes pre-timestamp / online / covid
            # tournaments). Names that are in summary but absent from the
            # training subset are not data gaps — they're picked up by the
            # supplementation loop below. Only true orphans (in standings,
            # absent from summary entirely) get flagged.
            # Backtest folds (04e) pass verbose_standings_join=False because
            # each fold's training cohort produces its own list and firing
            # N copies just buries the real signal.
            check_against = (all_summary_families
                             if all_summary_families is not None
                             else set(summary['family'].dropna().unique()))
            validate_standings_join(
                standings['tournament_name'].unique(),
                check_against,
                verbose=verbose_standings_join,
            )
            for fam, grp in standings.groupby('tournament_name'):
                if fam not in self.family_mean_final:
                    self.family_mean_final[fam] = grp['total_players'].mean()

        # Track number of training editions per family (for CI widening)
        self.family_n_editions = valid.groupby('family').size().to_dict()

        # Compute per-family withdrawal rates from enrichment data
        self.family_withdrawal_rates = {}
        if self.enrichment:
            from collections import defaultdict
            wd_data = defaultdict(list)
            for (fam, yr), info in self.enrichment.items():
                # v3 T5: same fold restriction as the standings join above.
                if exclude_family_years and (fam, yr) in exclude_family_years:
                    continue
                if fold_year is not None:
                    try:
                        if int(yr) >= int(fold_year):
                            continue
                    except (TypeError, ValueError):
                        continue
                total = info.get('total_entries', 0)
                wd = info.get('withdrawal_count', 0)
                if total > 0 and wd > 0 and isinstance(wd, (int, float)):
                    wd_data[fam].append(wd / total)
            for fam, rates in wd_data.items():
                if rates:
                    self.family_withdrawal_rates[fam] = np.median(rates)

        # Compute global log-sigma per T for empirical Bayes shrinkage
        for T in CHOP_POINTS:
            g_rats = self.global_ratios.get(T, [])
            if g_rats:
                vals = [r[0] for r in g_rats]
                if len(vals) >= 5:
                    self.global_log_sigma[T] = np.std(np.log(vals), ddof=1)

        # LOO calibration — expanding window.
        # With completed 2026 data in training, calibrate on pre-2025 data
        # (2025 + completed 2026 serve as validation). Without 2026 data,
        # calibrate on pre-2024 (original behavior).
        cal_year = 2025 if completed_tids else 2024
        self._calibrate(valid, daily, cal_max_year=cal_year)

        # T-dependent CI shrinkage: less shrinkage at long T (more uncertainty),
        # more shrinkage at short T (ratios converge toward 1.0)
        for T in self.ci_scale:
            # v3 T6 (audit/AUDIT_2026-07-25.md): this table used to dip — 0.42 in
            # the 10<=T<28 band but 0.40 in 7<=T<10 — so shrinkage briefly went
            # DOWN as the event got closer, against the stated rationale (ratios
            # converge toward 1.0 near the event, so shrinkage should rise
            # monotonically). The About-page table at index.html already rendered
            # it as a clean 0.33 -> 0.75 ramp, hiding the dip from readers.
            # Straightened to 0.42 so the sequence is monotone and matches what
            # the page claims.
            if T >= 60:
                shrink = 0.33
            elif T >= 28:
                shrink = 0.36
            elif T >= 10:
                shrink = 0.42
            elif T >= 7:
                shrink = 0.42
            elif T >= 5:
                shrink = 0.50
            else:
                shrink = 0.75
            self.ci_scale[T] *= shrink

        # AUDIT.md C7 — count each family/T ratio list once. Calibration and
        # prediction calls can touch the same list repeatedly, so they opt out
        # of trim accounting and this pass owns the per-fit audit totals.
        reset_trim_stats()
        for fam, fam_rats in self.ratios.items():
            if fam == '__global__':
                continue
            for T, rats in fam_rats.items():
                if isinstance(T, (int, float)):
                    trim_outliers([r[0] for r in rats], label=fam)

        # Build pooled per-family regression: final ~ count_at_T + T + intercept
        # Pooling across all T values gives more data points and lets the model
        # learn how lead time affects the count-to-final relationship
        reg_data = {}  # family -> [(count_at_T, T, final_count), ...]
        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(td) < 5:
                continue
            for T in CHOP_POINTS:
                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue
                reg_data.setdefault(family, []).append(
                    (count_at_T, T, actual))

        self.reg_params = {}
        self._reg_data = reg_data  # save for size-matched regression fallback
        for fam, pts in reg_data.items():
            if len(pts) < 6:
                continue
            X = np.array([[p[0], p[1]] for p in pts], dtype=float)
            y = np.array([p[2] for p in pts], dtype=float)
            try:
                hub = HuberRegressor(epsilon=1.35, max_iter=200)
                hub.fit(X, y)
                coeffs = np.array([hub.coef_[0], hub.coef_[1], hub.intercept_])
                self.reg_params[fam] = coeffs
            except Exception:
                try:
                    X_aug = np.column_stack([X, np.ones(len(X))])
                    coeffs, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
                    self.reg_params[fam] = coeffs
                except Exception:
                    continue

        # Build separate global regressions for large (mean>300) vs small
        # tournaments — different growth dynamics at different scales
        large_pts = []
        small_pts = []
        for fam, pts in reg_data.items():
            mean_final = self.family_mean_final.get(fam, 0)
            if mean_final > 300:
                large_pts.extend(pts)
            else:
                small_pts.extend(pts)
        self._large_reg = None
        self._small_reg = None
        for pts_list, attr in [(large_pts, '_large_reg'), (small_pts, '_small_reg')]:
            if len(pts_list) >= 10:
                X = np.array([[p[0], p[1]] for p in pts_list], dtype=float)
                y = np.array([p[2] for p in pts_list], dtype=float)
                try:
                    hub = HuberRegressor(epsilon=1.35, max_iter=200)
                    hub.fit(X, y)
                    setattr(self, attr, np.array([hub.coef_[0], hub.coef_[1], hub.intercept_]))
                except Exception as e:
                    # H5: don't swallow — a failed backstop fit leaves this leg
                    # unset, which quietly changes predictions. Make it visible.
                    print(f"WARNING: backstop Huber fit failed for {attr} "
                          f"(n={len(pts_list)}): {e}; leaving {attr} unset")

        # AUDIT.md C7 — surface IQR outlier trim activity at end of fit so
        # silent point dropping is visible. Threshold of 5% pct_trimmed flagged
        # as a warning since IQR 3.0x should normally trim very little.
        ts = report_trim_stats(top_n=5)
        if ts['total_in'] > 0:
            print(f"  IQR outlier trim: {ts['total_in'] - ts['total_out']}/{ts['total_in']} "
                  f"points trimmed ({ts['pct_trimmed']}%)")
            if ts['top_offenders']:
                print("  Top families by trim rate:")
                for label, dropped, n_in, pct in ts['top_offenders']:
                    print(f"    {label:<45} {dropped:>3}/{n_in:<3}  ({pct:>4.1f}%)")
            # Warn only when materially elevated. Healthy production runs sit
            # around 5-6% because ratios have heavy tails by nature; 8% means
            # something noisy entered training.
            if ts['pct_trimmed'] > 8.0:
                print(f"  WARNING: {ts['pct_trimmed']}% of points trimmed (>8% threshold). "
                      f"IQR factor 3.0 may be dropping legitimate variation; check top offenders.")

