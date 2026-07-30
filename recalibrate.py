"""
Post-season recalibration: compare predictions vs actuals and track accuracy.

After a tournament completes, run this to:
  - Compare prediction (from update_log.csv) vs actual final count
  - Log results to output/prediction_accuracy_log.csv
  - Compute rolling accuracy metrics (MAPE, coverage)
  - Suggest CI shrinkage adjustments if coverage drifts

Usage:
  python recalibrate.py                          # process all completed tournaments
  python recalibrate.py --family "Chicago Open"  # single family
"""

import pandas as pd
import os
import sys
import argparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
UPDATE_LOG = os.path.join(OUTPUT_DIR, "update_log.csv")
ACCURACY_LOG = os.path.join(OUTPUT_DIR, "prediction_accuracy_log.csv")

sys.path.insert(0, PROJECT_DIR)
from pipeline_utils import is_event_complete


def load_actuals():
    """Load tournament summary to get actual final counts for completed events.

    Excludes 2026 events whose end_date is today or later — their
    summary.final_count is a moving mid-event scrape (01_data_prep raises it
    via raise-only merge), not a real final. Scoring against that value would
    write false APE rows into prediction_accuracy_log.csv.
    """
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    completed = summary[
        (summary['tournament_year'] == 2026) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ][['family', 'final_count']].copy()

    meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    if os.path.exists(meta_path):
        meta = pd.read_csv(meta_path)
        meta_2026 = meta[meta['year'] == 2026][['family', 'end_date']].copy()
        meta_2026['end_date'] = pd.to_datetime(meta_2026['end_date'], errors='coerce')
        completed = completed.merge(meta_2026, on='family', how='left')
        today = pd.Timestamp.now().normalize()
        completed = completed[completed['end_date'].apply(
            lambda d: is_event_complete(d, today)
        )].drop(columns=['end_date'])

    completed.rename(columns={'final_count': 'actual'}, inplace=True)
    return completed


def load_predictions():
    """Load the update log with historical predictions."""
    if not os.path.exists(UPDATE_LOG):
        print(f"No update log found at {UPDATE_LOG}")
        print("Run auto_update.py at least once first.")
        sys.exit(1)
    log = pd.read_csv(UPDATE_LOG)
    log['run_timestamp'] = pd.to_datetime(log['run_timestamp'])
    return log


def load_existing_accuracy():
    """Load existing accuracy log if it exists."""
    if os.path.exists(ACCURACY_LOG):
        return pd.read_csv(ACCURACY_LOG)
    return pd.DataFrame(columns=[
        'date', 'family', 'predicted', 'actual', 'APE', 'T_at_prediction'
    ])


def compute_accuracy(predictions, actuals, family_filter=None):
    """Compare last prediction per family against actual results."""
    if family_filter:
        predictions = predictions[predictions['family'] == family_filter]

    # For each family, take the last prediction made while status was 'live'
    live_preds = predictions[predictions['status'] == 'live'].copy()
    if live_preds.empty:
        print("No live predictions found in update log.")
        return pd.DataFrame()

    # Last prediction per family (closest to event)
    last_preds = live_preds.sort_values('run_timestamp').groupby('family').last().reset_index()

    # Merge with actuals
    merged = last_preds.merge(actuals, on='family', how='inner')
    if merged.empty:
        print("No completed tournaments found with matching predictions.")
        return pd.DataFrame()

    # Compute APE
    merged['APE'] = (abs(merged['point_estimate'] - merged['actual']) / merged['actual'] * 100).round(2)

    results = merged[['run_timestamp', 'family', 'point_estimate', 'actual',
                       'APE', 'days_remaining', 'ci_lower', 'ci_upper']].copy()
    results.rename(columns={
        'run_timestamp': 'date',
        'point_estimate': 'predicted',
        'days_remaining': 'T_at_prediction'
    }, inplace=True)

    # Check if prediction was within CI
    results['covered'] = (results['actual'] >= merged['ci_lower']) & \
                         (results['actual'] <= merged['ci_upper'])

    return results


def rolling_metrics(accuracy_log, window=10):
    """Compute rolling accuracy metrics over the last N completed tournaments."""
    if len(accuracy_log) == 0:
        return None

    recent = accuracy_log.tail(window)
    mape = recent['APE'].mean()
    median_ape = recent['APE'].median()
    coverage = recent['covered'].mean() * 100 if 'covered' in recent.columns else None

    return {
        'n_tournaments': len(recent),
        'MAPE': round(mape, 2),
        'median_APE': round(median_ape, 2),
        'coverage_pct': round(coverage, 1) if coverage is not None else None,
    }


def suggest_shrinkage(coverage_pct):
    """Suggest CI shrinkage factor adjustment based on coverage drift."""
    if coverage_pct is None:
        return None

    if coverage_pct < 75:
        # Under-covering: CIs too narrow, widen them.
        # (v5 chore: the 0.05 sigma floor lives in ratio_model.py — the
        # window engine — not 04c; 04c's empirical-Bayes floor is inside
        # lognormal_ci. The old text pointed at a floor 04c doesn't have.)
        return (
            f"Coverage {coverage_pct:.1f}% is BELOW 75% target floor. "
            f"CIs are too narrow — consider raising the sigma floor in "
            f"ratio_model.py (0.05) for window-path predictions, or easing "
            f"the empirical-Bayes shrinkage in 04c_final_model.lognormal_ci."
        )
    elif coverage_pct > 90:
        # Over-covering: CIs too wide, tighten them
        return (
            f"Coverage {coverage_pct:.1f}% is ABOVE 90% target ceiling. "
            f"CIs are too wide — consider decreasing sigma floor or increasing shrinkage "
            f"to tighten intervals without sacrificing calibration."
        )
    else:
        return f"Coverage {coverage_pct:.1f}% is within target range [75%, 90%]. No adjustment needed."


def main():
    parser = argparse.ArgumentParser(description="Post-season prediction recalibration")
    parser.add_argument('--family', type=str, default=None,
                        help='Recalibrate for a specific family only')
    args = parser.parse_args()

    actuals = load_actuals()
    predictions = load_predictions()
    existing = load_existing_accuracy()

    results = compute_accuracy(predictions, actuals, family_filter=args.family)

    if results.empty:
        print("\nNo new results to log.")
        return

    # Append new results (avoid duplicates by family+date)
    if not existing.empty:
        existing['date'] = pd.to_datetime(existing['date'])
        results['date'] = pd.to_datetime(results['date'])
        # Only add families not already in the log for this date
        existing_keys = set(zip(
            existing['date'].dt.date.astype(str),
            existing['family']
        ))
        new_rows = results[
            ~results.apply(
                lambda r: (str(r['date'].date()), r['family']) in existing_keys, axis=1
            )
        ]
    else:
        new_rows = results

    if new_rows.empty:
        print("All results already logged. No new entries.")
    else:
        combined = pd.concat([existing, new_rows], ignore_index=True)
        # Save with selected columns
        save_cols = ['date', 'family', 'predicted', 'actual', 'APE', 'T_at_prediction']
        combined[save_cols].to_csv(ACCURACY_LOG, index=False)
        print(f"Logged {len(new_rows)} new results to {ACCURACY_LOG}")

    # ── Summary Report ────────────────────────────────────────────────
    # Reload full log for metrics
    full_log = pd.read_csv(ACCURACY_LOG)
    if 'covered' not in full_log.columns and os.path.exists(UPDATE_LOG):
        # Reconstruct coverage from update log if not stored
        preds = load_predictions()
        live = preds[preds['status'] == 'live']
        last = live.sort_values('run_timestamp').groupby('family').last().reset_index()
        ci_map = {r['family']: (r['ci_lower'], r['ci_upper']) for _, r in last.iterrows()}
        full_log['covered'] = full_log.apply(
            lambda r: (
                r['actual'] >= ci_map.get(r['family'], (0, 0))[0] and
                r['actual'] <= ci_map.get(r['family'], (0, 0))[1]
            ) if r['family'] in ci_map else None,
            axis=1
        )

    metrics = rolling_metrics(full_log)

    print(f"\n{'='*60}")
    print("RECALIBRATION REPORT")
    print(f"{'='*60}")

    if metrics:
        print(f"  Tournaments evaluated:  {metrics['n_tournaments']}")
        print(f"  MAPE:                   {metrics['MAPE']}%")
        print(f"  Median APE:             {metrics['median_APE']}%")
        if metrics['coverage_pct'] is not None:
            print(f"  80% CI coverage:        {metrics['coverage_pct']}%")
            suggestion = suggest_shrinkage(metrics['coverage_pct'])
            print(f"\n  {suggestion}")
    else:
        print("  Insufficient data for metrics.")

    # Per-family breakdown
    if len(full_log) > 0:
        print("\n  Per-Family Results:")
        print(f"  {'Family':<35} {'Predicted':>10} {'Actual':>10} {'APE':>8}")
        print(f"  {'-'*65}")
        for _, r in full_log.iterrows():
            print(f"  {r['family']:<35} {int(r['predicted']):>10} {int(r['actual']):>10} {r['APE']:>7.1f}%")


if __name__ == "__main__":
    main()
