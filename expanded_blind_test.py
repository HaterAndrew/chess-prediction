"""
Expanded blind test: expanding-window validation across all available years.

Tests 2022-2025, each time training on all prior years. Measures N5v4_Final
model only (no modifications). Reports per-year and per-T metrics, plus
early vs recent year comparison.
"""

import pandas as pd
import numpy as np
import os
import sys
import warnings

warnings.filterwarnings('ignore')

# Import from the final model module without modifying it
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
mod = import_module("04c_final_model")

N5v4_Final = mod.N5v4_Final
CHOP_POINTS = mod.CHOP_POINTS
OUTPUT_DIR = mod.OUTPUT_DIR


def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    return summary, daily


def run_expanded_blind_test():
    summary, daily = load_data()

    # Filter to valid tournaments (same criteria as the model)
    s = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    # Exclude 2026 in-progress tournaments
    s = s[s['tournament_year'] < 2026]

    test_years = [2022, 2023, 2024, 2025]
    all_results = []

    for test_year in test_years:
        train = s[s['tournament_year'] < test_year]
        test = s[s['tournament_year'] == test_year]

        n_train = len(train)
        n_test = len(test)

        print(f"\n{'='*70}")
        print(f"TEST YEAR: {test_year}  |  Train: {n_train} tournaments (pre-{test_year})  |  Test: {n_test} tournaments")
        print(f"{'='*70}")

        if n_train == 0:
            print(f"  ** SKIPPED: No valid training data before {test_year} **")
            print(f"     (All pre-{test_year} timestamped data is online or covid-flagged)")
            continue

        if n_test == 0:
            print(f"  ** SKIPPED: No test data for {test_year} **")
            continue

        train_d = daily[daily['tid'].isin(train['tid'])]
        test_d = daily[daily['tid'].isin(test['tid'])]

        model = N5v4_Final()
        try:
            model.fit(train, train_d)
        except Exception as e:
            print(f"  Model fit failed: {e}")
            continue

        for _, row in test.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            year = int(row['tournament_year'])

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

                try:
                    pred, lo, hi = model.predict_nowcast(
                        current, T_chop, family, year=year)
                    if pred is None:
                        continue
                except Exception:
                    continue

                ape = abs(pred - actual) / max(actual, 1) * 100
                covered = (lo <= actual <= hi)
                ci_width = hi - lo

                all_results.append({
                    'test_year': year,
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

    if not all_results:
        print("\nNo results generated.")
        return

    results = pd.DataFrame(all_results)

    # Save to CSV
    out_path = os.path.join(OUTPUT_DIR, "expanded_blind_test.csv")
    results.to_csv(out_path, index=False)
    print(f"\nResults saved to {out_path}")

    # -------------------------------------------------------------------------
    # PER-YEAR METRICS
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PER-YEAR METRICS")
    print("=" * 70)

    yearly = results.groupby('test_year').agg(
        n=('APE', 'size'),
        Median_APE=('APE', 'median'),
        MAPE=('APE', 'mean'),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
        Within_10pct=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20pct=('APE', lambda x: (x <= 20).mean() * 100),
    ).round(1)
    print(yearly.to_string())

    # -------------------------------------------------------------------------
    # PER-T METRICS (across all years)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PER-T METRICS (all years combined)")
    print("=" * 70)

    per_t = results.groupby('T_chop').agg(
        n=('APE', 'size'),
        Median_APE=('APE', 'median'),
        MAPE=('APE', 'mean'),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
        Within_10pct=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20pct=('APE', lambda x: (x <= 20).mean() * 100),
    ).round(1)
    per_t = per_t.sort_index(ascending=False)
    print(per_t.to_string())

    # -------------------------------------------------------------------------
    # PER-T PER-YEAR BREAKDOWN
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("MAPE BY LEAD TIME AND YEAR")
    print("=" * 70)

    mape_pivot = results.groupby(['test_year', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
    mape_pivot = mape_pivot[sorted(mape_pivot.columns, reverse=True)]
    print(mape_pivot.to_string())

    print("\nCOVERAGE BY LEAD TIME AND YEAR")
    cov_pivot = results.groupby(['test_year', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
    cov_pivot = cov_pivot[sorted(cov_pivot.columns, reverse=True)]
    print(cov_pivot.to_string())

    # -------------------------------------------------------------------------
    # EARLY (2022-2023) vs RECENT (2024-2025) COMPARISON
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("EARLY YEARS (2023) vs RECENT YEARS (2024-2025) COMPARISON")
    print("=" * 70)
    # Note: 2022 has no training data, so early = 2023 only

    available_years = results['test_year'].unique()
    early_years = [y for y in [2022, 2023] if y in available_years]
    recent_years = [y for y in [2024, 2025] if y in available_years]

    early = results[results['test_year'].isin(early_years)]
    recent = results[results['test_year'].isin(recent_years)]

    def summarize(df, label):
        if len(df) == 0:
            print(f"  {label}: No data")
            return
        print(f"\n  {label} (n={len(df)}, years={sorted(df['test_year'].unique())}):")
        print(f"    Median APE:     {df['APE'].median():.1f}%")
        print(f"    MAPE:           {df['APE'].mean():.1f}%")
        print(f"    Coverage (80%): {df['covered'].mean()*100:.1f}%")
        print(f"    Mean CI Width:  {df['ci_width'].mean():.0f}")
        print(f"    Within 10%:     {(df['APE'] <= 10).mean()*100:.1f}%")
        print(f"    Within 20%:     {(df['APE'] <= 20).mean()*100:.1f}%")

    summarize(early, "EARLY")
    summarize(recent, "RECENT")

    # Per-T comparison
    print(f"\n  {'T':<6} {'Early MAPE':>12} {'Recent MAPE':>12} {'Early Cov':>12} {'Recent Cov':>12}")
    print(f"  {'-'*54}")
    for T in sorted(CHOP_POINTS, reverse=True):
        e_t = early[early['T_chop'] == T]
        r_t = recent[recent['T_chop'] == T]
        e_mape = f"{e_t['APE'].mean():.1f}%" if len(e_t) > 0 else "N/A"
        r_mape = f"{r_t['APE'].mean():.1f}%" if len(r_t) > 0 else "N/A"
        e_cov = f"{e_t['covered'].mean()*100:.0f}%" if len(e_t) > 0 else "N/A"
        r_cov = f"{r_t['covered'].mean()*100:.0f}%" if len(r_t) > 0 else "N/A"
        print(f"  T-{T:<4} {e_mape:>12} {r_mape:>12} {e_cov:>12} {r_cov:>12}")

    # Overall summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY (all tested years)")
    print("=" * 70)
    print(f"  Total predictions: {len(results)}")
    print(f"  Years tested:      {sorted(results['test_year'].unique())}")
    print(f"  Median APE:        {results['APE'].median():.1f}%")
    print(f"  MAPE:              {results['APE'].mean():.1f}%")
    print(f"  Coverage (80%):    {results['covered'].mean()*100:.1f}%")
    print(f"  Mean CI Width:     {results['ci_width'].mean():.0f}")
    print(f"  Within 10%:        {(results['APE'] <= 10).mean()*100:.1f}%")
    print(f"  Within 20%:        {(results['APE'] <= 20).mean()*100:.1f}%")


if __name__ == "__main__":
    run_expanded_blind_test()
