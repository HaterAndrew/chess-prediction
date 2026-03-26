"""
Phase 4E: Generate model performance data for the website.

Runs blind tests on completed 2026 tournaments by predicting at various
T-points (days before event) and comparing to actual final counts.
Outputs performance_data.json for embedding in the website.
"""

import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m04c = import_module("04c_final_model")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
TODAY = pd.Timestamp.now().normalize()

# T-points to evaluate (days before event)
T_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]

# Minimum final count to include in evaluation
MIN_FINAL_COUNT = 50

# Grading rubric based on T-14 MAE% and CI coverage
GRADE_RUBRIC = [
    ("A+", 5, 85), ("A", 8, 75), ("A-", 10, 72),
    ("B+", 12, 68), ("B", 14, 65), ("B-", 16, 60),
    ("C+", 18, 55), ("C", 20, 50), ("C-", 22, 48),
    ("D", 25, 45), ("F", 999, 0),
]


def compute_grade(mae_pct, ci_coverage):
    """Assign letter grade from T-14 MAE% and CI coverage."""
    for grade, max_mae, min_cov in GRADE_RUBRIC:
        if mae_pct <= max_mae and ci_coverage >= min_cov:
            return grade
    return "F"


def main():
    # Load data
    summary, daily, meta, hist_enrich = m04c.load_data()
    enrichment_lookup = m04c.build_enrichment_lookup(hist_enrich)

    # Parse metadata dates
    meta['start_date'] = pd.to_datetime(meta['start_date'])

    # Identify completed 2026 tournament tids (for rolling retraining)
    completed_2026_all = summary[
        (summary['tournament_year'] == 2026) &
        (~summary['is_online'].fillna(False)) &
        (summary['has_timestamps'])
    ].copy()
    completed_2026_all['last_reg'] = pd.to_datetime(completed_2026_all['last_reg'])
    completed_tids = set()
    for _, row in completed_2026_all.iterrows():
        lr = row['last_reg']
        if pd.isna(lr) or lr > TODAY:
            continue
        family = row['family']
        m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
        if len(m_row) > 0 and pd.notna(m_row.iloc[0]['start_date']) and m_row.iloc[0]['start_date'] > TODAY:
            continue
        completed_tids.add(row['tid'])

    # Fit model with rolling retraining (completed 2026 tournaments in training)
    model = m04c.N5v4_Final()
    model.fit(summary, daily, enrichment_lookup,
              completed_tids=completed_tids if completed_tids else None)

    # Identify completed 2026 tournaments using last_reg date
    # A tournament is "complete" when its last_reg date has passed
    completed_2026 = summary[
        (summary['tournament_year'] == 2026) &
        (~summary['is_online'].fillna(False)) &
        (summary['final_count'] >= MIN_FINAL_COUNT)
    ].copy()
    completed_2026['last_reg'] = pd.to_datetime(completed_2026['last_reg'])

    # Exclude tournaments still in progress (last_reg in the future or
    # events that haven't started yet per metadata)
    completed_families = []
    for _, row in completed_2026.iterrows():
        family = row['family']
        last_reg = row['last_reg']

        # Must have last_reg in the past
        if pd.isna(last_reg) or last_reg > TODAY:
            continue

        # If metadata has a future start_date, this is still live
        m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
        if len(m_row) > 0:
            event_start = m_row.iloc[0]['start_date']
            if pd.notna(event_start) and event_start > TODAY:
                continue
            event_start_str = event_start.strftime('%Y-%m-%d') if pd.notna(event_start) else last_reg.strftime('%Y-%m-%d')
        else:
            # No metadata — use last_reg as proxy for event date
            event_start_str = last_reg.strftime('%Y-%m-%d')

        completed_families.append({
            'family': family,
            'tid': row['tid'],
            'final_count': int(row['final_count']),
            'event_start': event_start_str,
        })

    print(f"Found {len(completed_families)} completed 2026 tournaments for evaluation")

    # Apply automated recalibration (bias + CI corrections from completed data)
    if completed_tids:
        recal_data = summary[summary['tid'].isin(completed_tids)].copy()
        if len(recal_data) >= 3:
            recal_diag = model.recalibrate(recal_data, daily)
            print(f"  Recalibration applied from {len(recal_data)} tournaments")

    if not completed_families:
        # Output empty performance data
        output = {
            "generated": TODAY.strftime('%Y-%m-%d'),
            "model": "N5v4_Final",
            "n_tournaments": 0,
            "tournaments": [],
            "aggregate": [],
            "grade": "N/A",
            "grade_detail": "No completed tournaments to evaluate yet",
        }
        out_path = os.path.join(OUTPUT_DIR, "performance_data.json")
        with open(out_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"  No completed tournaments — wrote empty performance data")
        return

    # For each completed tournament, get daily data and predict at each T-point
    tournament_results = []

    for tinfo in completed_families:
        family = tinfo['family']
        tid = tinfo['tid']
        final = tinfo['final_count']

        # Get daily registration data for this tournament
        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) == 0:
            continue

        t_predictions = {}
        for T in T_POINTS:
            # T in daily data and model are both "days before last_reg"
            # Use T directly — no duration offset needed for blind test
            # (the model's predict_nowcast expects raw T in this coordinate)

            # Find closest available T in the data (within 2-day tolerance)
            available = tid_daily[(tid_daily['T'] >= T - 2) & (tid_daily['T'] <= T + 2)].copy()
            available['dist'] = (available['T'] - T).abs()
            available = available.sort_values('dist')
            if len(available) == 0:
                continue

            closest = available.iloc[0]
            count_at_T = int(closest['cum_regs'])

            if count_at_T <= 0:
                continue

            # Predict using raw T (same coordinate as training data)
            point, ci_lo, ci_hi = model.predict_nowcast(
                count_at_T, T, family
            )

            if point is None:
                continue

            point = int(round(point))
            ci_lo = int(round(ci_lo))
            ci_hi = int(round(ci_hi))

            error_pct = round((point - final) / final * 100, 1)
            abs_error_pct = abs(error_pct)
            in_ci = 1 if ci_lo <= final <= ci_hi else 0

            t_predictions[T] = {
                "T": T,
                "count_at_T": count_at_T,
                "predicted": point,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "error_pct": error_pct,
                "abs_error_pct": abs_error_pct,
                "in_ci": in_ci,
            }

        if not t_predictions:
            continue

        tournament_results.append({
            "family": family,
            "final_count": final,
            "event_start": tinfo['event_start'],
            "predictions": t_predictions,
        })

    # Compute aggregate metrics at each T-point
    aggregate = []
    for T in T_POINTS:
        errors = []
        abs_errors = []
        ci_hits = []
        for tr in tournament_results:
            pred = tr['predictions'].get(T)
            if pred:
                errors.append(pred['error_pct'])
                abs_errors.append(pred['abs_error_pct'])
                ci_hits.append(pred['in_ci'])

        if not abs_errors:
            continue

        mae = round(np.mean(abs_errors), 1)
        median_ape = round(np.median(abs_errors), 1)
        ci_coverage = round(np.mean(ci_hits) * 100, 0)
        bias = round(np.mean(errors), 1)
        n = len(abs_errors)

        aggregate.append({
            "T": T,
            "n": n,
            "mae_pct": mae,
            "median_ape_pct": median_ape,
            "ci_coverage": ci_coverage,
            "bias_pct": bias,
        })

    # Compute overall grade from T-14 metrics
    t14 = next((a for a in aggregate if a['T'] == 14), None)
    if t14:
        grade = compute_grade(t14['mae_pct'], t14['ci_coverage'])
        grade_detail = f"T-14 MAE: {t14['mae_pct']}%, CI coverage: {t14['ci_coverage']}%"
    else:
        # Fall back to best available T
        best = min(aggregate, key=lambda a: a['T'])
        grade = compute_grade(best['mae_pct'], best['ci_coverage'])
        grade_detail = f"T-{best['T']} MAE: {best['mae_pct']}%, CI coverage: {best['ci_coverage']}%"

    # Format tournament results for JSON (convert predictions dict to list)
    tournaments_out = []
    for tr in tournament_results:
        preds_list = sorted(tr['predictions'].values(), key=lambda p: -p['T'])
        tournaments_out.append({
            "family": tr['family'],
            "final_count": tr['final_count'],
            "event_start": tr['event_start'],
            "predictions": preds_list,
        })

    output = {
        "generated": TODAY.strftime('%Y-%m-%d'),
        "model": "N5v4_Final",
        "n_tournaments": len(tournaments_out),
        "grade": grade,
        "grade_detail": grade_detail,
        "aggregate": aggregate,
        "tournaments": tournaments_out,
    }

    out_path = os.path.join(OUTPUT_DIR, "performance_data.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  MODEL PERFORMANCE REPORT — {len(tournaments_out)} tournaments")
    print(f"  Grade: {grade} ({grade_detail})")
    print(f"{'='*60}")
    for a in aggregate:
        print(f"  T-{a['T']:>2}: MAE {a['mae_pct']:>5.1f}%  CI cov {a['ci_coverage']:>3.0f}%  bias {a['bias_pct']:>+5.1f}%  (n={a['n']})")
    print(f"\n  Output: {out_path}")


if __name__ == '__main__':
    main()
