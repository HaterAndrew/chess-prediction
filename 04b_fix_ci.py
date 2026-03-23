"""
Phase 4B: Fix CI calibration properly.

Problem: With only 3-5 historical data points per family per T,
percentile-based CIs from family data alone can't achieve 80% coverage.

Solution: Hybrid CI — use family-specific median for the point estimate,
but compute CI width from the global distribution of prediction errors
(across all families). This pools information from ~200 tournaments
instead of ~4.
"""

import pandas as pd
import numpy as np
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


class N5v3_CalibratedRatio:
    """
    Historical ratio model with properly calibrated CIs.

    Point estimate: family-specific median ratio (same as original N5).
    CI: computed from the global distribution of (actual/predicted) errors
    at each lead time T, calibrated to achieve actual 80% coverage.
    """
    name = "N5v3_CalibratedCI"

    def __init__(self):
        self.error_quantiles = {}  # T -> (low_mult, high_mult) for 80% CI

    def fit(self, summary, daily):
        """Build ratios AND calibrate CI from training data."""
        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ]

        # Step 1: Build family-specific ratios (same as original N5)
        self.ratios = {}
        self.global_ratios = {}

        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']

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
                self.ratios[family].setdefault(T, []).append(ratio)
                self.global_ratios.setdefault(T, []).append(ratio)

        self.ratios['__global__'] = self.global_ratios

        # Step 2: Calibrate CIs using leave-one-out cross-validation
        # For each tournament, predict using all OTHER tournaments' ratios,
        # then collect the error (actual / predicted) across all tournaments.
        error_ratios = {}  # T -> list of (actual / predicted) values

        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']

            tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(tid_daily) < 5:
                continue

            for T in CHOP_POINTS:
                regs = tid_daily[tid_daily['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                # LOO: get ratios for this family EXCLUDING this tournament
                fam_ratios = self.ratios.get(family, {}).get(T, [])
                this_ratio = actual / count_at_T

                loo_ratios = [r for r in fam_ratios if abs(r - this_ratio) > 0.001]
                if not loo_ratios:
                    # Use global ratios as fallback
                    loo_ratios = [r for r in self.global_ratios.get(T, []) if abs(r - this_ratio) > 0.001]
                if not loo_ratios:
                    continue

                predicted = count_at_T * np.median(loo_ratios)
                if predicted > 0:
                    error_ratio = actual / predicted  # >1 = underpredicted, <1 = overpredicted
                    error_ratios.setdefault(T, []).append(error_ratio)

        # Step 3: Compute 80% CI multipliers from error distribution
        for T in CHOP_POINTS:
            errors = error_ratios.get(T, [])
            if len(errors) >= 10:
                self.error_quantiles[T] = (
                    np.percentile(errors, 10),  # low multiplier (10th percentile)
                    np.percentile(errors, 90),  # high multiplier (90th percentile)
                )
            else:
                # Not enough data, use wide default
                self.error_quantiles[T] = (0.6, 1.5)

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        ratio_list = fam_ratios[closest_T]

        if not ratio_list:
            return None, None, None

        median_ratio = np.median(ratio_list)
        point = current_count * median_ratio

        # CI from calibrated error quantiles
        eq = self.error_quantiles.get(closest_T, (0.6, 1.5))
        low = point * eq[0]
        high = point * eq[1]

        return (round(max(point, current_count)),
                round(max(low, current_count)),
                round(max(high, point)))


def run_blind_test(summary, daily):
    """Blind test: N5_Original vs N5v3_CalibratedCI vs others."""
    print("="*70)
    print("BLIND TEST: N5v3 Calibrated CI vs All Models")
    print("="*70)

    all_results = []

    for test_year in [2024, 2025]:
        print(f"\n── Test Year: {test_year} ──")

        s = summary[
            (summary['has_timestamps']) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False))
        ]
        train = s[s['tournament_year'] < test_year]
        test = s[s['tournament_year'] == test_year]
        train_d = daily[daily['tid'].isin(train['tid'])]
        test_d = daily[daily['tid'].isin(test['tid'])]

        models = [
            m03.N5_HistoricalRatio(),
            m03.N1_TemplateCurve(),
            m03.N3_XGBoostNowcast(),
            N5v3_CalibratedRatio(),
        ]

        for model in models:
            try:
                model.fit(train, train_d)
            except Exception as e:
                print(f"  {model.name}: fit failed - {e}")
                continue

            for _, row in test.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']
                year = row['tournament_year']

                td = test_d[test_d['tid'] == tid].sort_values('T', ascending=False)
                if len(td) < 5:
                    continue

                for T_chop in CHOP_POINTS:
                    regs = td[td['T'] >= T_chop]
                    if len(regs) == 0:
                        continue
                    current = int(regs['cum_regs'].max())
                    if current == 0:
                        continue

                    r7 = td[(td['T'] >= T_chop) & (td['T'] < T_chop + 7)]
                    r3 = td[(td['T'] >= T_chop) & (td['T'] < T_chop + 3)]
                    rate_7d = r7['daily_regs'].mean() if len(r7) > 0 else 0
                    rate_3d = r3['daily_regs'].mean() if len(r3) > 0 else 0

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
                        'model': model.name,
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

    return pd.DataFrame(all_results)


def report(results):
    """Print results."""
    print("\n" + "="*70)
    print("FINAL LEADERBOARD")
    print("="*70)

    overall = results.groupby('model').agg(
        n=('APE', 'size'),
        MAPE=('APE', 'mean'),
        Median_APE=('APE', 'median'),
        Within_10=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20=('APE', lambda x: (x <= 20).mean() * 100),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
    ).round(1).sort_values('MAPE')

    print("\nOverall:")
    print(overall.to_string())

    # MAPE by T
    print("\nMAPE by Lead Time:")
    pivot = results.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
    pivot = pivot[sorted(pivot.columns, reverse=True)]
    print(pivot.to_string())

    # Coverage by T
    print("\n80% CI Coverage by Lead Time:")
    cov = results.groupby(['model', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
    cov = cov[sorted(cov.columns, reverse=True)]
    print(cov.to_string())

    # Chicago Open
    chi = results[results['family'] == 'Chicago Open']
    if len(chi) > 0:
        print("\nChicago Open:")
        chi_summary = chi.groupby('model').agg(
            MAPE=('APE', 'mean'),
            Coverage=('covered', lambda x: x.mean() * 100),
        ).round(1).sort_values('MAPE')
        print(chi_summary.to_string())

        # T-28 detail
        t28 = chi[chi['T_chop'] == 28]
        if len(t28) > 0:
            print("\nChicago Open at T-28:")
            for _, r in t28.iterrows():
                print(f"  {r['model']:<25} {r['test_year']}  pred={r['predicted']:>5}  actual={r['actual']:>5}  "
                      f"APE={r['APE']:>5}%  CI=[{r['lower']}, {r['upper']}]  {'✓' if r['covered'] else '✗'}")

    # Convergence
    print("\nConvergence Test:")
    for model in pivot.index:
        mapes = pivot.loc[model].dropna()
        if len(mapes) < 3:
            continue
        diffs = mapes.diff().dropna()
        increases = (diffs > 0).sum()
        print(f"  {model}: {'PASS' if increases <= 1 else f'WARN ({increases} increases)'}")

    return overall


def plot_final(results):
    fig, axes = plt.subplots(1, 3, figsize=(20, 6))

    # MAPE convergence
    ax = axes[0]
    for model in sorted(results['model'].unique()):
        m = results[results['model'] == model]
        mape = m.groupby('T_chop')['APE'].mean()
        ax.plot(mape.index, mape.values, 'o-', label=model, linewidth=2)
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('MAPE (%)')
    ax.set_title('MAPE Convergence')
    ax.legend(fontsize=8)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)

    # Coverage
    ax = axes[1]
    for model in sorted(results['model'].unique()):
        m = results[results['model'] == model]
        cov = m.groupby('T_chop')['covered'].mean() * 100
        ax.plot(cov.index, cov.values, 'o-', label=model, linewidth=2)
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.5, label='Target 80%')
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('Coverage (%)')
    ax.set_title('80% CI Coverage')
    ax.legend(fontsize=8)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)

    # Scatter: accuracy vs calibration
    ax = axes[2]
    for model in sorted(results['model'].unique()):
        m = results[results['model'] == model]
        mape = m['APE'].mean()
        cov = m['covered'].mean() * 100
        ax.scatter(mape, cov, s=120, zorder=5)
        ax.annotate(model, (mape, cov), fontsize=8, ha='left', va='bottom')
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.3)
    ax.set_xlabel('MAPE (%)')
    ax.set_ylabel('Coverage (%)')
    ax.set_title('Accuracy vs Calibration Tradeoff')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "final_comparison.png"), dpi=150)
    print(f"\nSaved final comparison to output/final_comparison.png")


if __name__ == "__main__":
    print("Loading data...")
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))

    # Show calibrated error quantiles
    print("\nFitting N5v3 on all data to show calibration parameters...")
    full_model = N5v3_CalibratedRatio()
    s_valid = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ]
    full_model.fit(s_valid, daily)

    print("\nCalibrated error quantiles (actual/predicted):")
    print(f"  {'T':<6} {'10th%':<8} {'90th%':<8} {'CI width factor'}")
    print(f"  {'-'*30}")
    for T in CHOP_POINTS:
        eq = full_model.error_quantiles.get(T, (0.6, 1.5))
        print(f"  T-{T:<4} {eq[0]:.3f}   {eq[1]:.3f}   {eq[1]-eq[0]:.3f}")

    # Run blind test
    results = run_blind_test(summary, daily)
    results.to_csv(os.path.join(OUTPUT_DIR, "final_blind_test.csv"), index=False)

    # Report
    overall = report(results)
    plot_final(results)

    # Final prediction
    print("\n" + "="*70)
    print("2026 CHICAGO OPEN — FINAL PREDICTION")
    print("="*70)

    pred, lo, hi = full_model.predict_nowcast(179, 63, 'Chicago Open', year=2026)
    print(f"\n  Current registrations:  179")
    print(f"  Days to event:          ~63 (event May 21-25)")
    print(f"  Early bird deadline:    March 19 (3 days ago)")
    print(f"\n  Point estimate:  {pred}")
    print(f"  80% CI:          [{lo}, {hi}]")
    print(f"  Historical:      860-960 (2022-2025)")

    print(f"\n  Lead time projections:")
    for T in [90, 60, 42, 28, 14, 7, 3, 1]:
        p, l, h = full_model.predict_nowcast(179, T, 'Chicago Open', year=2026)
        if p:
            marker = " <--" if abs(T - 63) <= 5 else ""
            print(f"    T-{T:<4}  {p:>5}  [{l}, {h}]{marker}")

    print(f"\n{'='*70}")
    print("DONE")
    print(f"{'='*70}")
