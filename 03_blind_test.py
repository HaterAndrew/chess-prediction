"""
Phase 3B: Blind Testing Gauntlet
Every model tested under simulated real-world conditions.
No peeking at test data during training.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import warnings

warnings.filterwarnings('ignore')

# Import model classes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m03 = import_module("03_models")
MODE_A_MODELS = m03.MODE_A_MODELS
MODE_B_MODELS = m03.MODE_B_MODELS

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]


def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    return summary, daily


# ═══════════════════════════════════════════════════════════════════════════
# TEST SUITE 1: Mode A — Blind Total Count Prediction
# ═══════════════════════════════════════════════════════════════════════════

def run_mode_a_tests(summary, daily):
    """
    For each test year, train on all prior years, predict test year tournaments.
    The model never sees the test year data.
    """
    print("\n" + "="*70)
    print("TEST SUITE 1: MODE A — BLIND TOTAL COUNT PREDICTION")
    print("="*70)

    # Filter to in-person tournaments
    s = summary[~summary['is_online'].fillna(False)].copy()

    test_years = [2023, 2024, 2025]
    all_results = []

    for test_year in test_years:
        print(f"\n── Test Year: {test_year} ──")

        # Training data: everything before test_year (exclude COVID for clean training)
        train = s[
            (s['tournament_year'] < test_year) &
            (~s['is_covid'].fillna(False))
        ].copy()
        test = s[
            (s['tournament_year'] == test_year) &
            (~s['is_covid'].fillna(False))
        ].copy()

        train_daily = daily[daily['tid'].isin(train['tid'])].copy()

        if len(test) == 0:
            continue

        print(f"  Train: {len(train)} tournaments ({int(train['tournament_year'].min())}-{int(train['tournament_year'].max())})")
        print(f"  Test:  {len(test)} tournaments")

        for ModelClass in MODE_A_MODELS:
            model = ModelClass()
            try:
                model.fit(train, train_daily)
            except Exception as e:
                print(f"  {model.name}: fit failed - {e}")
                continue

            for _, row in test.iterrows():
                family = row['family']
                actual = row['final_count']
                month_val = pd.to_datetime(row.get('last_reg', None), errors='coerce')
                month = month_val.month if pd.notna(month_val) else 6

                try:
                    pred, lower, upper = model.predict_count(family, test_year, month)
                    if pred is None:
                        continue
                except Exception:
                    continue

                ape = abs(pred - actual) / max(actual, 1) * 100
                covered = (lower <= actual <= upper) if (lower is not None and upper is not None) else False
                ci_width = (upper - lower) if (lower is not None and upper is not None) else 0

                all_results.append({
                    'model': model.name,
                    'test_year': test_year,
                    'tid': row['tid'],
                    'family': family,
                    'actual': actual,
                    'predicted': pred,
                    'lower': lower,
                    'upper': upper,
                    'APE': round(ape, 1),
                    'covered': covered,
                    'ci_width': ci_width,
                })

    results_df = pd.DataFrame(all_results)
    return results_df


# ═══════════════════════════════════════════════════════════════════════════
# TEST SUITE 2: Mode B — Blind Nowcast
# ═══════════════════════════════════════════════════════════════════════════

def run_mode_b_tests(summary, daily):
    """
    For each timestamped tournament, chop registrations at various points
    and predict final count. Train only on prior tournaments.
    """
    print("\n" + "="*70)
    print("TEST SUITE 2: MODE B — BLIND NOWCAST")
    print("="*70)

    s = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    test_years = [2024, 2025]
    all_results = []

    for test_year in test_years:
        print(f"\n── Test Year: {test_year} ──")

        train = s[s['tournament_year'] < test_year].copy()
        test = s[s['tournament_year'] == test_year].copy()

        train_daily = daily[daily['tid'].isin(train['tid'])].copy()
        test_daily = daily[daily['tid'].isin(test['tid'])].copy()

        if len(test) == 0 or len(train) == 0:
            continue

        print(f"  Train: {len(train)} tournaments")
        print(f"  Test:  {len(test)} tournaments")

        for ModelClass in MODE_B_MODELS:
            model = ModelClass()
            try:
                model.fit(train, train_daily)
            except Exception as e:
                print(f"  {model.name}: fit failed - {e}")
                continue

            for _, row in test.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']
                year = row['tournament_year']

                tid_daily = test_daily[test_daily['tid'] == tid].sort_values('T', ascending=False)
                if len(tid_daily) < 5:
                    continue

                for T_chop in CHOP_POINTS:
                    # Get registrations up to chop point
                    regs = tid_daily[tid_daily['T'] >= T_chop]
                    if len(regs) == 0:
                        continue
                    current_count = int(regs['cum_regs'].max())
                    if current_count == 0:
                        continue

                    # Compute features available at chop time
                    recent_7d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 7)]
                    recent_3d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 3)]
                    rate_7d = recent_7d['daily_regs'].mean() if len(recent_7d) > 0 else 0
                    rate_3d = recent_3d['daily_regs'].mean() if len(recent_3d) > 0 else 0

                    eb = tid_daily[(tid_daily['T'] >= 55) & (tid_daily['T'] <= 75)]
                    bl = tid_daily[(tid_daily['T'] >= 76) & (tid_daily['T'] <= 90)]
                    spike = 0
                    if len(eb) > 0 and len(bl) > 0:
                        bl_rate = max(bl['daily_regs'].median(), 1)
                        if eb['daily_regs'].max() / bl_rate >= 5:
                            spike = 1

                    try:
                        pred, lower, upper = model.predict_nowcast(
                            current_count, T_chop, family,
                            rate_7d=rate_7d, rate_3d=rate_3d,
                            spike_detected=spike, year=year
                        )
                        if pred is None:
                            continue
                    except Exception:
                        continue

                    ape = abs(pred - actual) / max(actual, 1) * 100
                    covered = (lower <= actual <= upper) if (lower is not None and upper is not None) else False
                    ci_width = (upper - lower) if (lower is not None and upper is not None) else 0

                    all_results.append({
                        'model': model.name,
                        'test_year': test_year,
                        'tid': tid,
                        'family': family,
                        'T_chop': T_chop,
                        'current_count': current_count,
                        'actual': actual,
                        'predicted': pred,
                        'lower': lower,
                        'upper': upper,
                        'APE': round(ape, 1),
                        'covered': covered,
                        'ci_width': ci_width,
                    })

    results_df = pd.DataFrame(all_results)
    return results_df


# ═══════════════════════════════════════════════════════════════════════════
# TEST SUITE 3: Chicago Open Deep Dive (Leave-One-Out)
# ═══════════════════════════════════════════════════════════════════════════

def run_chicago_open_tests(summary, daily):
    """Leave-one-out test for each Chicago Open edition."""
    print("\n" + "="*70)
    print("TEST SUITE 3: CHICAGO OPEN LEAVE-ONE-OUT")
    print("="*70)

    s = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    chicago = s[s['family'] == 'Chicago Open'].copy()
    all_others = s[s['family'] != 'Chicago Open'].copy()
    all_results = []

    print(f"  Chicago Open editions: {len(chicago)}")
    print(f"  Other tournaments for training: {len(all_others)}")

    for leave_out_idx, leave_out_row in chicago.iterrows():
        leave_out_tid = leave_out_row['tid']
        leave_out_year = leave_out_row['tournament_year']
        actual = leave_out_row['final_count']

        # Train on everything EXCEPT this edition (and anything from same/later year)
        train_chicago = chicago[chicago['tournament_year'] < leave_out_year]
        train = pd.concat([all_others[all_others['tournament_year'] < leave_out_year], train_chicago])
        train_daily = daily[daily['tid'].isin(train['tid'])].copy()

        test_daily = daily[daily['tid'] == leave_out_tid].sort_values('T', ascending=False)
        if len(test_daily) < 5:
            continue

        print(f"\n  Leave out: {leave_out_row['tournament_name']} (actual={actual})")

        for ModelClass in MODE_B_MODELS:
            model = ModelClass()
            try:
                model.fit(train, train_daily)
            except Exception:
                continue

            for T_chop in CHOP_POINTS:
                regs = test_daily[test_daily['T'] >= T_chop]
                if len(regs) == 0:
                    continue
                current_count = int(regs['cum_regs'].max())
                if current_count == 0:
                    continue

                recent_7d = test_daily[(test_daily['T'] >= T_chop) & (test_daily['T'] < T_chop + 7)]
                recent_3d = test_daily[(test_daily['T'] >= T_chop) & (test_daily['T'] < T_chop + 3)]
                rate_7d = recent_7d['daily_regs'].mean() if len(recent_7d) > 0 else 0
                rate_3d = recent_3d['daily_regs'].mean() if len(recent_3d) > 0 else 0

                try:
                    pred, lower, upper = model.predict_nowcast(
                        current_count, T_chop, 'Chicago Open',
                        rate_7d=rate_7d, rate_3d=rate_3d, year=leave_out_year
                    )
                    if pred is None:
                        continue
                except Exception:
                    continue

                ape = abs(pred - actual) / actual * 100
                covered = (lower <= actual <= upper) if (lower and upper) else False

                all_results.append({
                    'model': model.name,
                    'tournament_name': leave_out_row['tournament_name'],
                    'year': leave_out_year,
                    'T_chop': T_chop,
                    'current_count': current_count,
                    'actual': actual,
                    'predicted': pred,
                    'lower': lower,
                    'upper': upper,
                    'APE': round(ape, 1),
                    'covered': covered,
                })

    return pd.DataFrame(all_results)


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════

def report_mode_a(results_df):
    """Print Mode A leaderboard."""
    if len(results_df) == 0:
        print("No Mode A results.")
        return

    print("\n" + "="*70)
    print("MODE A LEADERBOARD — Total Count Prediction")
    print("="*70)

    leaderboard = results_df.groupby('model').agg(
        n=('APE', 'size'),
        Median_APE=('APE', 'median'),
        MAPE=('APE', 'mean'),
        SMAPE=('APE', lambda x: round((2 * x / (100 + x / 50)).mean(), 1)),
        Max_APE=('APE', 'max'),
        Within_10=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20=('APE', lambda x: (x <= 20).mean() * 100),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
    ).round(1).sort_values('Median_APE')

    print(leaderboard.to_string())
    return leaderboard


def report_mode_b(results_df):
    """Print Mode B leaderboard with convergence analysis."""
    if len(results_df) == 0:
        print("No Mode B results.")
        return

    print("\n" + "="*70)
    print("MODE B LEADERBOARD — Nowcast by Lead Time")
    print("="*70)

    # Overall — sort by Median APE (robust, symmetric, outlier-resistant)
    overall = results_df.groupby('model').agg(
        n=('APE', 'size'),
        Median_APE=('APE', 'median'),
        MAPE=('APE', 'mean'),
        Within_10=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20=('APE', lambda x: (x <= 20).mean() * 100),
        Coverage_80=('covered', lambda x: x.mean() * 100),
    ).round(1).sort_values('Median_APE')

    print("\nOverall Performance:")
    print(overall.to_string())

    # By lead time
    print("\nMAPE by Lead Time:")
    pivot = results_df.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
    pivot = pivot[sorted(pivot.columns, reverse=True)]
    print(pivot.to_string())

    # Coverage by lead time
    print("\n80% CI Coverage by Lead Time:")
    cov_pivot = results_df.groupby(['model', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
    cov_pivot = cov_pivot[sorted(cov_pivot.columns, reverse=True)]
    print(cov_pivot.to_string())

    # Convergence test: does error monotonically decrease?
    print("\nConvergence Test (does error decrease as T→0?):")
    for model in pivot.index:
        mapes = pivot.loc[model].dropna()
        if len(mapes) < 3:
            continue
        # Check if mostly decreasing
        diffs = mapes.diff().dropna()
        n_increases = (diffs > 0).sum()
        status = "PASS" if n_increases <= 1 else f"WARN ({n_increases} increases)"
        print(f"  {model}: {status}")

    return overall, pivot


def report_chicago(results_df):
    """Print Chicago Open deep dive."""
    if len(results_df) == 0:
        print("No Chicago Open results.")
        return

    print("\n" + "="*70)
    print("CHICAGO OPEN DEEP DIVE")
    print("="*70)

    # Per-edition results
    for year in sorted(results_df['year'].unique()):
        year_results = results_df[results_df['year'] == year]
        actual = year_results['actual'].iloc[0]
        print(f"\n  {year_results['tournament_name'].iloc[0]} (actual: {actual})")
        pivot = year_results.pivot_table(
            index='model', columns='T_chop', values='predicted', aggfunc='first'
        )
        pivot = pivot[sorted(pivot.columns, reverse=True)]
        print(pivot.round(0).to_string())

    # MAPE by model across all Chicago Opens
    print("\nChicago Open MAPE by Model:")
    chi_mape = results_df.groupby('model')['APE'].mean().round(1).sort_values()
    print(chi_mape.to_string())


def plot_results(mode_b_results, chicago_results):
    """Generate comparison plots."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))

    # 1. Mode B MAPE convergence
    ax = axes[0, 0]
    for model in mode_b_results['model'].unique():
        m_data = mode_b_results[mode_b_results['model'] == model]
        mape_by_T = m_data.groupby('T_chop')['APE'].mean()
        ax.plot(mape_by_T.index, mape_by_T.values, 'o-', label=model, linewidth=2)
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('MAPE (%)')
    ax.set_title('Mode B: MAPE Convergence by Lead Time')
    ax.legend(fontsize=8)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)

    # 2. Mode B predicted vs actual scatter
    ax = axes[0, 1]
    t28 = mode_b_results[mode_b_results['T_chop'] == 28]
    for model in t28['model'].unique():
        m_data = t28[t28['model'] == model]
        ax.scatter(m_data['actual'], m_data['predicted'], alpha=0.5, s=20, label=model)
    max_val = max(t28['actual'].max(), t28['predicted'].max()) * 1.1
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, label='Perfect')
    ax.set_xlabel('Actual')
    ax.set_ylabel('Predicted')
    ax.set_title('Mode B at T-28: Predicted vs Actual')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 3. Chicago Open convergence
    ax = axes[1, 0]
    if len(chicago_results) > 0:
        for model in chicago_results['model'].unique():
            m_data = chicago_results[chicago_results['model'] == model]
            mape_by_T = m_data.groupby('T_chop')['APE'].mean()
            ax.plot(mape_by_T.index, mape_by_T.values, 'o-', label=model, linewidth=2)
        ax.set_xlabel('Days Before Event (T)')
        ax.set_ylabel('MAPE (%)')
        ax.set_title('Chicago Open: MAPE Convergence')
        ax.legend(fontsize=8)
        ax.invert_xaxis()
        ax.grid(True, alpha=0.3)

    # 4. CI Calibration
    ax = axes[1, 1]
    for model in mode_b_results['model'].unique():
        m_data = mode_b_results[mode_b_results['model'] == model]
        coverage_by_T = m_data.groupby('T_chop')['covered'].mean()
        ax.plot(coverage_by_T.index, coverage_by_T.values * 100, 'o-', label=model, linewidth=2)
    ax.axhline(y=80, color='red', linestyle='--', alpha=0.5, label='Target 80%')
    ax.set_xlabel('Days Before Event (T)')
    ax.set_ylabel('Coverage (%)')
    ax.set_title('80% CI Calibration by Lead Time')
    ax.legend(fontsize=8)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "model_comparison.png"), dpi=150)
    print(f"\nSaved comparison plots to output/model_comparison.png")


# ═══════════════════════════════════════════════════════════════════════════
# WINNER SELECTION
# ═══════════════════════════════════════════════════════════════════════════

def select_winner(mode_a_results, mode_b_results):
    """Apply elimination criteria and select winning models."""
    print("\n" + "="*70)
    print("WINNER SELECTION")
    print("="*70)

    # Mode A
    if len(mode_a_results) > 0:
        a_scores = mode_a_results.groupby('model').agg(
            MAPE=('APE', 'mean'),
            Coverage=('covered', 'mean'),
        )
        best_mape = a_scores['MAPE'].min()
        survivors = a_scores[
            (a_scores['MAPE'] <= best_mape * 2) &
            (a_scores['Coverage'] >= 0.6)
        ]
        if len(survivors) == 0:
            survivors = a_scores[a_scores['MAPE'] <= best_mape * 2]

        winner_a = survivors['MAPE'].idxmin()
        print(f"\n  Mode A Winner: {winner_a} (MAPE: {survivors.loc[winner_a, 'MAPE']:.1f}%)")
        print(f"  Survivors: {list(survivors.index)}")

    # Mode B — select at T-28 (actionable sweet spot)
    if len(mode_b_results) > 0:
        t28 = mode_b_results[mode_b_results['T_chop'] == 28]
        if len(t28) > 0:
            b_scores = t28.groupby('model').agg(
                MAPE=('APE', 'mean'),
                Coverage=('covered', 'mean'),
            )
        else:
            b_scores = mode_b_results.groupby('model').agg(
                MAPE=('APE', 'mean'),
                Coverage=('covered', 'mean'),
            )

        best_mape = b_scores['MAPE'].min()

        # Convergence check
        failed_convergence = []
        for model in mode_b_results['model'].unique():
            m = mode_b_results[mode_b_results['model'] == model]
            mapes = m.groupby('T_chop')['APE'].mean().sort_index(ascending=False)
            if len(mapes) >= 3:
                diffs = mapes.diff().dropna()
                if (diffs > 0).sum() > 2:
                    failed_convergence.append(model)

        survivors = b_scores[
            (b_scores['MAPE'] <= best_mape * 2) &
            (~b_scores.index.isin(failed_convergence))
        ]
        if len(survivors) == 0:
            survivors = b_scores[b_scores['MAPE'] <= best_mape * 2]

        winner_b = survivors['MAPE'].idxmin()
        print(f"\n  Mode B Winner (at T-28): {winner_b} (MAPE: {survivors.loc[winner_b, 'MAPE']:.1f}%)")
        print(f"  Survivors: {list(survivors.index)}")
        if failed_convergence:
            print(f"  Failed convergence: {failed_convergence}")

    return winner_a if len(mode_a_results) > 0 else None, winner_b if len(mode_b_results) > 0 else None


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    summary, daily = load_data()

    # Run all test suites
    mode_a_results = run_mode_a_tests(summary, daily)
    mode_b_results = run_mode_b_tests(summary, daily)
    chicago_results = run_chicago_open_tests(summary, daily)

    # Save raw results
    mode_a_results.to_csv(os.path.join(OUTPUT_DIR, "blind_test_mode_a.csv"), index=False)
    mode_b_results.to_csv(os.path.join(OUTPUT_DIR, "blind_test_mode_b.csv"), index=False)
    chicago_results.to_csv(os.path.join(OUTPUT_DIR, "blind_test_chicago.csv"), index=False)

    # Report
    a_leaderboard = report_mode_a(mode_a_results)
    b_overall, b_pivot = report_mode_b(mode_b_results)
    report_chicago(chicago_results)

    # Plots
    plot_results(mode_b_results, chicago_results)

    # Winner selection
    winner_a, winner_b = select_winner(mode_a_results, mode_b_results)

    print(f"\n{'='*70}")
    print(f"BLIND TESTING GAUNTLET COMPLETE")
    print(f"{'='*70}")
    print(f"Mode A tests: {len(mode_a_results)}")
    print(f"Mode B tests: {len(mode_b_results)}")
    print(f"Chicago Open tests: {len(chicago_results)}")
