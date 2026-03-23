"""
Phase 4: All Three Improvements
1. Data enrichment — use real event start dates where available
2. Recency-weighted historical ratios
3. Calibrated confidence intervals

Then re-run the blind test gauntlet to measure improvement.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import os
import sys
import warnings

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m03 = import_module("03_models")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]
T_GRID = np.arange(0, 121)


# ═══════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 1: Enrich with real event dates
# ═══════════════════════════════════════════════════════════════════════════

def enrich_with_metadata(summary, daily):
    """
    Replace last_reg proxy with actual start dates where available.
    Recompute T (days before event) using real dates.
    """
    meta = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_metadata.csv"))
    meta['start_date'] = pd.to_datetime(meta['start_date'])
    meta['early_bird_deadline'] = pd.to_datetime(meta['early_bird_deadline'])

    # Match metadata to summary by family + year
    summary = summary.copy()
    summary['event_start'] = pd.NaT
    summary['early_bird_date'] = pd.NaT
    summary['eb_fee'] = np.nan
    summary['reg_fee'] = np.nan

    for _, m in meta.iterrows():
        mask = (summary['family'] == m['family']) & (summary['tournament_year'] == m['year'])
        summary.loc[mask, 'event_start'] = m['start_date']
        summary.loc[mask, 'early_bird_date'] = m['early_bird_deadline']
        summary.loc[mask, 'eb_fee'] = m['early_bird_fee']
        summary.loc[mask, 'reg_fee'] = m['regular_fee']

    # For tournaments without metadata, keep using last_reg as proxy
    no_meta = summary['event_start'].isna()
    summary.loc[no_meta, 'event_start'] = pd.to_datetime(summary.loc[no_meta, 'last_reg'], errors='coerce')

    enriched_count = (~no_meta).sum()
    print(f"  Enriched {enriched_count} tournaments with real event dates")

    # Recompute daily T values using real event dates
    daily_enriched = daily.copy()
    # We need to rebuild T for enriched tournaments
    # For now, we can adjust T by the offset between last_reg and event_start
    for _, row in summary[~no_meta].iterrows():
        tid = row['tid']
        last_reg = pd.to_datetime(row['last_reg'], errors='coerce')
        event_start = row['event_start']
        if pd.isna(last_reg) or pd.isna(event_start):
            continue
        # Offset: how many days between last_reg and event_start
        offset = (event_start - last_reg).days
        mask = daily_enriched['tid'] == tid
        daily_enriched.loc[mask, 'T'] = daily_enriched.loc[mask, 'T'] + offset

    return summary, daily_enriched


# ═══════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 2: Recency-Weighted Historical Ratios
# ═══════════════════════════════════════════════════════════════════════════

class N5_RecencyWeightedRatio:
    """
    Historical ratio model with exponential decay weighting.
    Recent years contribute more to the median ratio estimate.
    Also uses calibrated CIs (Improvement 3).
    """
    name = "N5v2_RecencyRatio"

    def __init__(self, half_life=2.0, ci_multiplier=1.0):
        self.half_life = half_life  # years — weight halves every N years
        self.ci_multiplier = ci_multiplier  # CI width adjustment for calibration

    def fit(self, summary, daily):
        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ]

        self.ratios = {}  # family -> {T -> [(ratio, year), ...]}
        self.global_ratios = {}

        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            year = row['tournament_year']

            tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(tid_daily) < 5:
                continue

            if family not in self.ratios:
                self.ratios[family] = {}

            for T in CHOP_POINTS:
                regs = tid_daily[tid_daily['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                ratio = actual / count_at_T
                self.ratios[family].setdefault(T, []).append((ratio, year))
                self.global_ratios.setdefault(T, []).append((ratio, year))

        self.ratios['__global__'] = self.global_ratios

    def _weighted_stats(self, ratio_year_pairs, ref_year=2026):
        """Compute weighted median and percentiles using exponential decay."""
        if not ratio_year_pairs:
            return None, None, None

        ratios = np.array([r for r, y in ratio_year_pairs])
        years = np.array([y for r, y in ratio_year_pairs])

        # Exponential decay weight: w = 2^(-(ref_year - year) / half_life)
        weights = np.power(2.0, -(ref_year - years) / self.half_life)
        weights = weights / weights.sum()

        # Weighted median via interpolation
        sorted_idx = np.argsort(ratios)
        sorted_ratios = ratios[sorted_idx]
        sorted_weights = weights[sorted_idx]
        cum_weights = np.cumsum(sorted_weights)

        # Weighted median
        median_idx = np.searchsorted(cum_weights, 0.5)
        median_idx = min(median_idx, len(sorted_ratios) - 1)
        w_median = sorted_ratios[median_idx]

        # Weighted percentiles for CI
        ci_low_target = 0.5 - 0.4 * self.ci_multiplier  # calibration adjustment
        ci_high_target = 0.5 + 0.4 * self.ci_multiplier

        low_idx = np.searchsorted(cum_weights, max(ci_low_target, 0.01))
        low_idx = min(low_idx, len(sorted_ratios) - 1)
        high_idx = np.searchsorted(cum_weights, min(ci_high_target, 0.99))
        high_idx = min(high_idx, len(sorted_ratios) - 1)

        w_low = sorted_ratios[low_idx]
        w_high = sorted_ratios[high_idx]

        return w_median, w_low, w_high

    def predict_nowcast(self, current_count, days_remaining, family, year=2026, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        # Find closest chop point
        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        pairs = fam_ratios[closest_T]

        if not pairs:
            return None, None, None

        w_median, w_low, w_high = self._weighted_stats(pairs, ref_year=year)
        if w_median is None:
            return None, None, None

        point = current_count * w_median
        low = current_count * w_low
        high = current_count * w_high

        return (round(max(point, current_count)),
                round(max(low, current_count)),
                round(max(high, point)))


# ═══════════════════════════════════════════════════════════════════════════
# IMPROVEMENT 3: CI Calibration via Cross-Validation
# ═══════════════════════════════════════════════════════════════════════════

def calibrate_ci(summary, daily):
    """
    Find the ci_multiplier that achieves ~80% coverage on cross-validated data.
    Test multipliers from 0.5 to 3.0, pick the one closest to 80% coverage.
    """
    print("\nCalibrating CI multiplier...")

    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False))
    ]

    # Use 2024 as calibration set, train on prior
    train = valid[valid['tournament_year'] < 2024]
    test = valid[valid['tournament_year'] == 2024]
    train_daily = daily[daily['tid'].isin(train['tid'])]
    test_daily = daily[daily['tid'].isin(test['tid'])]

    best_mult = 1.0
    best_diff = 999

    for mult in np.arange(0.5, 4.1, 0.1):
        model = N5_RecencyWeightedRatio(half_life=2.0, ci_multiplier=mult)
        model.fit(train, train_daily)

        covered_count = 0
        total_count = 0

        for _, row in test.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            year = row['tournament_year']

            tid_daily = test_daily[test_daily['tid'] == tid].sort_values('T', ascending=False)
            if len(tid_daily) < 5:
                continue

            for T_chop in CHOP_POINTS:
                regs = tid_daily[tid_daily['T'] >= T_chop]
                if len(regs) == 0:
                    continue
                current = int(regs['cum_regs'].max())
                if current == 0:
                    continue

                pred, lo, hi = model.predict_nowcast(current, T_chop, family, year=year)
                if pred is None:
                    continue

                total_count += 1
                if lo <= actual <= hi:
                    covered_count += 1

        if total_count > 0:
            coverage = covered_count / total_count
            diff = abs(coverage - 0.80)
            if diff < best_diff:
                best_diff = diff
                best_mult = mult

    print(f"  Best CI multiplier: {best_mult:.1f} (achieves ~{100*(0.80 - best_diff if best_diff < 0.80 else 0.80 + best_diff):.0f}% coverage on 2024 cal set)")
    return best_mult


def calibrate_half_life(summary, daily):
    """Find optimal half-life for recency weighting via cross-validation."""
    print("\nCalibrating half-life...")

    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False))
    ]

    train = valid[valid['tournament_year'] < 2024]
    test = valid[valid['tournament_year'] == 2024]
    train_daily = daily[daily['tid'].isin(train['tid'])]
    test_daily = daily[daily['tid'].isin(test['tid'])]

    best_hl = 2.0
    best_mape = 999

    for hl in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 999.0]:
        model = N5_RecencyWeightedRatio(half_life=hl, ci_multiplier=1.0)
        model.fit(train, train_daily)

        apes = []
        for _, row in test.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']

            tid_daily = test_daily[test_daily['tid'] == tid].sort_values('T', ascending=False)
            if len(tid_daily) < 5:
                continue

            for T_chop in [28, 14, 7]:  # Focus on actionable lead times
                regs = tid_daily[tid_daily['T'] >= T_chop]
                if len(regs) == 0:
                    continue
                current = int(regs['cum_regs'].max())
                if current == 0:
                    continue

                pred, _, _ = model.predict_nowcast(current, T_chop, family, year=2024)
                if pred is None:
                    continue
                apes.append(abs(pred - actual) / actual * 100)

        mape = np.mean(apes) if apes else 999
        label = f"hl={hl:<5}" if hl < 100 else "hl=∞ (uniform)"
        print(f"  {label}  MAPE={mape:.1f}%  (n={len(apes)})")

        if mape < best_mape:
            best_mape = mape
            best_hl = hl

    print(f"  Best half-life: {best_hl} years (MAPE={best_mape:.1f}%)")
    return best_hl


# ═══════════════════════════════════════════════════════════════════════════
# BLIND TEST: Compare original vs improved models
# ═══════════════════════════════════════════════════════════════════════════

def run_comparative_blind_test(summary, daily, summary_enriched, daily_enriched,
                                best_hl, best_ci_mult):
    """Run blind test comparing original N5 vs all improved variants."""
    print("\n" + "="*70)
    print("COMPARATIVE BLIND TEST: Original vs Improved")
    print("="*70)

    models = {
        'N5_Original': (m03.N5_HistoricalRatio(), summary, daily),
        'N5v2_Recency': (N5_RecencyWeightedRatio(half_life=best_hl), summary, daily),
        'N5v2_Enriched': (N5_RecencyWeightedRatio(half_life=best_hl), summary_enriched, daily_enriched),
        'N5v2_Calibrated': (N5_RecencyWeightedRatio(half_life=best_hl, ci_multiplier=best_ci_mult),
                           summary_enriched, daily_enriched),
    }

    # Also test original models for comparison
    original_models = {
        'N1_Template': (m03.N1_TemplateCurve(), summary, daily),
        'N3_XGB_Nowcast': (m03.N3_XGBoostNowcast(), summary, daily),
    }
    models.update(original_models)

    all_results = []

    for test_year in [2024, 2025]:
        print(f"\n── Test Year: {test_year} ──")

        for model_name, (model, s, d) in models.items():
            s_valid = s[
                (s['has_timestamps']) &
                (~s.get('is_online', pd.Series(False)).fillna(False)) &
                (~s.get('is_covid', pd.Series(False)).fillna(False))
            ]
            train = s_valid[s_valid['tournament_year'] < test_year]
            test = s_valid[s_valid['tournament_year'] == test_year]
            train_d = d[d['tid'].isin(train['tid'])]
            test_d = d[d['tid'].isin(test['tid'])]

            try:
                model.fit(train, train_d)
            except Exception as e:
                print(f"  {model_name}: fit failed - {e}")
                continue

            for _, row in test.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']
                year = row['tournament_year']

                tid_daily = test_d[test_d['tid'] == tid].sort_values('T', ascending=False)
                if len(tid_daily) < 5:
                    continue

                for T_chop in CHOP_POINTS:
                    regs = tid_daily[tid_daily['T'] >= T_chop]
                    if len(regs) == 0:
                        continue
                    current = int(regs['cum_regs'].max())
                    if current == 0:
                        continue

                    recent_7d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 7)]
                    recent_3d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 3)]
                    rate_7d = recent_7d['daily_regs'].mean() if len(recent_7d) > 0 else 0
                    rate_3d = recent_3d['daily_regs'].mean() if len(recent_3d) > 0 else 0

                    try:
                        pred, lo, hi = model.predict_nowcast(
                            current, T_chop, family,
                            rate_7d=rate_7d, rate_3d=rate_3d, year=year
                        )
                        if pred is None:
                            continue
                    except Exception:
                        continue

                    ape = abs(pred - actual) / max(actual, 1) * 100
                    covered = (lo <= actual <= hi) if (lo is not None and hi is not None) else False
                    ci_width = (hi - lo) if (lo is not None and hi is not None) else 0

                    all_results.append({
                        'model': model_name,
                        'test_year': test_year,
                        'tid': tid,
                        'family': family,
                        'T_chop': T_chop,
                        'current_count': current,
                        'actual': actual,
                        'predicted': pred,
                        'lower': lo,
                        'upper': hi,
                        'APE': round(ape, 1),
                        'covered': covered,
                        'ci_width': ci_width,
                    })

    results_df = pd.DataFrame(all_results)
    return results_df


def report_comparison(results_df):
    """Print comparison leaderboard."""
    print("\n" + "="*70)
    print("COMPARATIVE LEADERBOARD")
    print("="*70)

    # Overall
    overall = results_df.groupby('model').agg(
        n=('APE', 'size'),
        MAPE=('APE', 'mean'),
        Median_APE=('APE', 'median'),
        Within_10=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20=('APE', lambda x: (x <= 20).mean() * 100),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
    ).round(1).sort_values('MAPE')

    print("\nOverall Performance:")
    print(overall.to_string())

    # MAPE by lead time
    print("\nMAPE by Lead Time:")
    pivot = results_df.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
    pivot = pivot[sorted(pivot.columns, reverse=True)]
    print(pivot.to_string())

    # Coverage by lead time
    print("\n80% CI Coverage by Lead Time:")
    cov_pivot = results_df.groupby(['model', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
    cov_pivot = cov_pivot[sorted(cov_pivot.columns, reverse=True)]
    print(cov_pivot.to_string())

    # Chicago Open specific
    chi = results_df[results_df['family'] == 'Chicago Open']
    if len(chi) > 0:
        print("\nChicago Open Results:")
        chi_mape = chi.groupby('model').agg(
            MAPE=('APE', 'mean'),
            Coverage=('covered', 'mean'),
        ).round(1).sort_values('MAPE')
        print(chi_mape.to_string())

        # Detailed predictions
        print("\nChicago Open Predictions by Model at T-28:")
        t28_chi = chi[chi['T_chop'] == 28]
        for _, row in t28_chi.iterrows():
            print(f"  {row['model']:<25} pred={row['predicted']:>6}  actual={row['actual']:>5}  APE={row['APE']:>5}%  CI=[{row['lower']}, {row['upper']}]  covered={row['covered']}")

    return overall

    # Plot comparison
def plot_comparison(results_df):
    fig, axes = plt.subplots(1, 3, figsize=(20, 6))

    # 1. MAPE convergence
    ax = axes[0]
    for model in results_df['model'].unique():
        m = results_df[results_df['model'] == model]
        mape_by_T = m.groupby('T_chop')['APE'].mean()
        ax.plot(mape_by_T.index, mape_by_T.values, 'o-', label=model, linewidth=2)
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('MAPE (%)')
    ax.set_title('MAPE Convergence: All Models')
    ax.legend(fontsize=7)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)

    # 2. Coverage
    ax = axes[1]
    for model in results_df['model'].unique():
        m = results_df[results_df['model'] == model]
        cov = m.groupby('T_chop')['covered'].mean() * 100
        ax.plot(cov.index, cov.values, 'o-', label=model, linewidth=2)
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.5, label='Target 80%')
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('Coverage (%)')
    ax.set_title('80% CI Coverage: All Models')
    ax.legend(fontsize=7)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)

    # 3. MAPE vs Coverage scatter (overall per model)
    ax = axes[2]
    for model in results_df['model'].unique():
        m = results_df[results_df['model'] == model]
        mape = m['APE'].mean()
        cov = m['covered'].mean() * 100
        ax.scatter(mape, cov, s=100, zorder=5)
        ax.annotate(model, (mape, cov), fontsize=7, ha='left', va='bottom')
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.3)
    ax.set_xlabel('MAPE (%)')
    ax.set_ylabel('80% CI Coverage (%)')
    ax.set_title('Accuracy vs Calibration')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "improved_comparison.png"), dpi=150)
    print(f"\nSaved comparison plot to output/improved_comparison.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Loading data...")
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))

    # Improvement 1: Enrich with real event dates
    print("\n" + "="*70)
    print("IMPROVEMENT 1: DATA ENRICHMENT")
    print("="*70)
    summary_enriched, daily_enriched = enrich_with_metadata(summary, daily)

    # Improvement 2: Calibrate half-life for recency weighting
    print("\n" + "="*70)
    print("IMPROVEMENT 2: RECENCY WEIGHTING")
    print("="*70)
    best_hl = calibrate_half_life(summary_enriched, daily_enriched)

    # Improvement 3: Calibrate CI multiplier
    print("\n" + "="*70)
    print("IMPROVEMENT 3: CI CALIBRATION")
    print("="*70)
    best_ci_mult = calibrate_ci(summary_enriched, daily_enriched)

    # Run comparative blind test
    results = run_comparative_blind_test(
        summary, daily, summary_enriched, daily_enriched,
        best_hl, best_ci_mult
    )

    # Save and report
    results.to_csv(os.path.join(OUTPUT_DIR, "improved_blind_test.csv"), index=False)
    overall = report_comparison(results)
    plot_comparison(results)

    # Final 2026 Chicago Open prediction with best model
    print("\n" + "="*70)
    print("2026 CHICAGO OPEN NOWCAST — IMPROVED MODEL")
    print("="*70)

    # Train on all available data
    s_valid = summary_enriched[
        (summary_enriched['has_timestamps']) &
        (~summary_enriched['is_online'].fillna(False)) &
        (~summary_enriched['is_covid'].fillna(False))
    ]
    best_model = N5_RecencyWeightedRatio(half_life=best_hl, ci_multiplier=best_ci_mult)
    best_model.fit(s_valid, daily_enriched)

    current_count = 179  # Current registrations
    days_remaining = 63  # Approx days to event

    pred, lo, hi = best_model.predict_nowcast(current_count, days_remaining, 'Chicago Open', year=2026)

    print(f"\n  Model: N5v2 Recency-Weighted + Calibrated CI")
    print(f"  Half-life: {best_hl} years")
    print(f"  CI multiplier: {best_ci_mult}")
    print(f"\n  Current registrations:  {current_count}")
    print(f"  Days to event (est.):   ~{days_remaining}")
    print(f"  Early bird deadline:    March 19, 2026")
    print(f"  Event dates:            May 21-25, 2026")
    print(f"\n  Point estimate:  {pred}")
    print(f"  80% interval:    [{lo}, {hi}]")
    print(f"  Historical:      860-960 (2022-2025)")

    # Show at different lead times
    print(f"\n  Projections at different lead times:")
    print(f"  {'Lead Time':<12} {'Predicted':<12} {'80% CI':<20}")
    print(f"  {'-'*44}")
    for T in [90, 60, 42, 28, 14, 7, 3, 1]:
        p, l, h = best_model.predict_nowcast(current_count, T, 'Chicago Open', year=2026)
        if p is not None:
            marker = " <--" if abs(T - days_remaining) <= 5 else ""
            print(f"  T-{T:<9} {p:<12} [{l}, {h}]{marker}")

    print(f"\n{'='*70}")
    print(f"ALL IMPROVEMENTS COMPLETE")
    print(f"{'='*70}")
