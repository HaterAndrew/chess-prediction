#!/usr/bin/env python3
"""Measure what each predict_nowcast stage is actually worth (audit v3 T8).

predict_nowcast is a ~400-line pipeline of roughly thirteen stages — late-surge
damping, size-matched ratio caps, growth trend, withdrawal correction, feature
adjustments, recalibration — stacked over the ratio model. Every one of them was
added because it seemed right; none had a number attached. A stage that does
nothing is dead weight, and a stage that actively hurts is worse, but without
per-stage measurement there was no way to tell which was which.

This runs the standard expanding-window backtest once with everything on, then
once per stage with that stage disabled, and reports the change in MAE and CI
coverage at the horizons the published grade uses (T-14/7/3).

Reading the output: a stage that EARNS its place shows worse numbers when it is
removed (positive MAE delta). A stage whose removal changes nothing is inert. A
stage whose removal IMPROVES the metrics is costing accuracy.

This is a diagnostic, not part of the pipeline. It refits the model per fold per
configuration, so it is slow — expect several minutes.

Usage:
    python scripts/ablate_stages.py                  # all stages
    python scripts/ablate_stages.py --stages trend withdrawal
    python scripts/ablate_stages.py --year 2025      # single fold
"""
import argparse
import json
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

m04c = import_module("04c_final_model")
m04e = import_module("04e_performance_data")

OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
HORIZONS = (14, 7, 3)


def load_inputs():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    meta = pd.read_csv(meta_path) if os.path.exists(meta_path) else pd.DataFrame()
    if len(meta):
        meta['start_date'] = pd.to_datetime(meta['start_date'], errors='coerce')
    hist_path = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
    hist = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
    enrichment = m04c.build_enrichment_lookup(hist) if len(hist) else {}
    daily = m04c.reanchor_daily_to_event_start(summary, daily, meta) if len(meta) else daily
    return summary, daily, meta, enrichment


def run_fold(year, summary, daily, meta, enrichment, stage_flags):
    """One expanding-window fold under a given stage configuration."""
    train = summary[summary['tournament_year'] < year].copy()
    model = m04c.N5v4_Final()
    model.fit(train, daily, enrichment, verbose_standings_join=False, fold_year=year)
    if stage_flags:
        model.set_stage_flags(**stage_flags)

    recal = train[
        (train['has_timestamps'])
        & (~train['is_online'].fillna(False))
        & (~train['is_covid'].fillna(False))
        & (train['final_count'] >= 50)
        & (train['tournament_year'].isin([year - 2, year - 1]))
    ].copy()
    if len(recal) >= 5:
        model.recalibrate(recal, daily)
        if stage_flags:
            model.set_stage_flags(**stage_flags)

    test_df = summary[
        (summary['tournament_year'] == year)
        & (summary['has_timestamps'])
        & (~summary['is_online'].fillna(False))
        & (~summary['is_covid'].fillna(False))
        & (summary['final_count'] >= m04e.MIN_FINAL_COUNT)
    ]
    tests = []
    for _, row in test_df.iterrows():
        tests.append({
            'family': row['family'], 'tid': row['tid'],
            'tournament_name': row.get('tournament_name', row['family']),
            'final_count': int(row['final_count']),
            'event_start': str(row.get('last_reg', ''))[:10] or f"{year}-06-01",
        })
    return m04e.evaluate_tournaments(model, tests, daily,
                                     hist_lookup=m04e._hist_lookup(train))


def metrics(results):
    """MAE% and CI coverage at each published horizon."""
    out = {}
    for T in HORIZONS:
        errs, hits = [], []
        for r in results:
            p = r['predictions'].get(T)
            if p:
                errs.append(p['abs_error_pct'])
                hits.append(p['in_ci'])
        if errs:
            out[T] = {'mae': round(float(np.mean(errs)), 2),
                      'cov': round(float(np.mean(hits)) * 100, 1),
                      'n': len(errs)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stages', nargs='*', default=None,
                    help="stages to ablate (default: all)")
    ap.add_argument('--year', type=int, default=None,
                    help="single fold year (default: 2023-2025)")
    ap.add_argument('--json', default=None, help="write raw results here")
    args = ap.parse_args()

    years = [args.year] if args.year else [2023, 2024, 2025]
    stages = args.stages if args.stages else list(m04c.N5v4_Final.ABLATABLE_STAGES)

    summary, daily, meta, enrichment = load_inputs()

    print(f"Ablation over folds {years}, stages {stages}")
    print("Baseline (all stages on) ...")
    base_results = []
    for y in years:
        base_results.extend(run_fold(y, summary, daily, meta, enrichment, None))
    base = metrics(base_results)
    for T in HORIZONS:
        if T in base:
            print(f"  T-{T:<3} MAE {base[T]['mae']:>6.2f}%  cov {base[T]['cov']:>5.1f}%  (n={base[T]['n']})")

    rows = []
    for stage in stages:
        print(f"\nWithout '{stage}' ...")
        res = []
        for y in years:
            res.extend(run_fold(y, summary, daily, meta, enrichment, {stage: False}))
        m = metrics(res)
        for T in HORIZONS:
            if T in base and T in m:
                d_mae = m[T]['mae'] - base[T]['mae']
                d_cov = m[T]['cov'] - base[T]['cov']
                # Positive d_mae => removing the stage made error worse => the
                # stage was earning its place at this horizon.
                verdict = "helps" if d_mae > 0.25 else ("HURTS" if d_mae < -0.25 else "inert")
                print(f"  T-{T:<3} MAE {m[T]['mae']:>6.2f}% ({d_mae:+.2f})  "
                      f"cov {m[T]['cov']:>5.1f}% ({d_cov:+.1f})   {verdict}")
                rows.append({'stage': stage, 'T': T, 'mae': m[T]['mae'],
                             'mae_delta': round(d_mae, 2), 'cov': m[T]['cov'],
                             'cov_delta': round(d_cov, 1), 'verdict': verdict})

    print("\nSummary — stages whose removal did not measurably hurt:")
    inert = sorted({r['stage'] for r in rows
                    if all(x['verdict'] != 'helps' for x in rows if x['stage'] == r['stage'])})
    print(f"  {inert if inert else '(none — every stage helps at some horizon)'}")

    if args.json:
        with open(args.json, 'w') as fh:
            json.dump({'baseline': base, 'ablations': rows}, fh, indent=2)
        print(f"\nWrote {args.json}")


if __name__ == '__main__':
    main()
