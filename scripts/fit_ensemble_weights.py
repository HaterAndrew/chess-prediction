#!/usr/bin/env python3
"""Fit the ensemble blend weights instead of guessing them (audit v3 T9).

predict_nowcast blends the ratio model with the pooled regression using four
hand-picked weights — 0.80 / 0.55 / 0.30 / 0.15 by lead-time bucket. They were
chosen because the shape looked right: trust the ratio model at short lead
times, lean on the regression at long ones. The shape probably is right. The
particular numbers had never been checked against held-out data, so there was no
way to know whether 0.55 beat 0.45, or whether the ratio model deserved any
weight at all at T > 28.

WHY THE NESTING MATTERS

The obvious version of this script picks the weights that score best on
2023-2025 and reports how well they score on 2023-2025. That number is
meaningless — it is the training error of a four-parameter fit, and it will
always look like an improvement. Audit finding T3 caught the same mistake in the
recalibration cohort, where every "held-out" record turned out to be in-sample.

So selection and reporting are kept apart. For each held-out year Y, the weights
are chosen using only folds strictly before Y, then scored once on Y, which had
no influence on the choice. The honest question this answers is not "can four
free parameters fit the past" (yes, always) but "would weights fitted on the
past have beaten the hand-picked ones on a year nobody had seen".

WHY ONE SWEEP FITS ALL FOUR BUCKETS

A bucket's weight only affects predictions at lead times inside that bucket, so
setting every bucket to the same candidate value and reading each bucket's own T
points measures all four independently in a single pass. That turns 4 x |grid|
evaluations into |grid|. The property is asserted at startup rather than
assumed — see check_bucket_independence().

Each fold's model is fit once and reused across the grid, since the weights
affect prediction only, not fitting. Recalibration IS refit per candidate,
because the recal factors are estimated from predictions and would otherwise
carry the default weights' bias into every candidate.

RESULT (run 2026-07-25, folds 2023-2025, grid 0.0-1.0 step 0.1)

Pooled MAE against candidate weight, with the hand-picked value marked:

     bucket   pooled-optimal   hand-picked   MAE at optimal / hand-picked
     T<=3          0.70           0.80            7.80 / 7.98
     T<=7          0.50           0.55            8.60 / ~8.60
     T<=28         0.30           0.30           12.28 / 12.28
     T>28          0.10           0.15           14.28 / ~14.5

Every hand-picked weight lands on the pooled optimum or one grid step from it,
and each curve is flat near its minimum — T<=3 moves by 0.18 MAE points across
0.6 to 0.9.

Nested evaluation, which is the number that actually counts:

     held-out 2024 (fitted on 2023)        +0.62 / +0.56 / +0.26 at T-14/7/3
     held-out 2025 (fitted on 2023-2024)   +0.00 / -0.05 / -0.64

     mean held-out MAE change from fitting: +0.13 points

Fitting made things slightly worse. The 2024 row shows why: with a single inner
fold the search picked 0.5/0.4/0.2/0.1, undershooting every bucket, and lost
0.2-0.6 MAE points on the held-out year. Given two inner folds it recovered to
0.7/0.5/0.3/0.1 and drew level. Four free parameters on this much data fit the
noise before they improve on a sensible prior.

So the weights do not move. That is the finding, not a failure to find one: the
hand-picked values are now known to sit at the optimum of a flat curve rather
than merely being untested, and re-running this script is how a future change to
them gets justified.

Usage:
    python scripts/fit_ensemble_weights.py
    python scripts/fit_ensemble_weights.py --grid 0.0 0.25 0.5 0.75 1.0
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
FOLD_YEARS = (2023, 2024, 2025)

# Which lead-time bucket each evaluated T point belongs to, given the bucket
# bounds in N5v4_Final.ENSEMBLE_WEIGHTS. Derived, not hardcoded, so a change to
# the bounds cannot silently desynchronise this script from the model.
def bucket_of(T, table):
    for i, (bound, _) in enumerate(table):
        if bound is None or T <= bound:
            return i
    return len(table) - 1


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
    if len(meta):
        daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)
    return summary, daily, enrichment


def build_fold(year, summary, daily, enrichment):
    """Fit one fold's model and assemble its test set. Done once per fold."""
    train = summary[summary['tournament_year'] < year].copy()
    model = m04c.N5v4_Final()
    model.fit(train, daily, enrichment, verbose_standings_join=False,
              fold_year=year)

    recal = train[
        (train['has_timestamps'])
        & (~train['is_online'].fillna(False))
        & (~train['is_covid'].fillna(False))
        & (train['final_count'] >= 50)
        & (train['tournament_year'].isin([year - 2, year - 1]))
    ].copy()

    test_df = summary[
        (summary['tournament_year'] == year)
        & (summary['has_timestamps'])
        & (~summary['is_online'].fillna(False))
        & (~summary['is_covid'].fillna(False))
        & (summary['final_count'] >= m04e.MIN_FINAL_COUNT)
    ]
    tests = [{
        'family': r['family'], 'tid': r['tid'],
        'tournament_name': r.get('tournament_name', r['family']),
        'final_count': int(r['final_count']),
        'event_start': str(r.get('last_reg', ''))[:10] or f"{year}-06-01",
    } for _, r in test_df.iterrows()]

    return {'model': model, 'recal': recal, 'tests': tests,
            'hist_lookup': m04e._hist_lookup(train)}


def score(fold, daily, table):
    """Per-T MAE and coverage for one candidate weight table on one fold."""
    model = fold['model']
    model.ensemble_weights = table
    if len(fold['recal']) >= 5:
        # Refit: recal factors are estimated from predictions, so leaving the
        # default-weight factors in place would contaminate every candidate.
        model.recalibrate(fold['recal'], daily)
        model.ensemble_weights = table
    results = m04e.evaluate_tournaments(model, fold['tests'], daily,
                                        hist_lookup=fold['hist_lookup'])
    per_T = {}
    for r in results:
        for T, p in r['predictions'].items():
            per_T.setdefault(T, {'err': [], 'hit': []})
            per_T[T]['err'].append(p['abs_error_pct'])
            per_T[T]['hit'].append(p['in_ci'])
    return {T: {'mae': float(np.mean(v['err'])),
                'cov': float(np.mean(v['hit'])) * 100,
                'n': len(v['err'])}
            for T, v in per_T.items()}


def check_bucket_independence(fold, daily, table):
    """Confirm a bucket's weight cannot move predictions in another bucket.

    The single-pass sweep is only valid under this property. Assert it rather
    than trusting the code to have stayed decoupled.
    """
    base = score(fold, daily, table)
    probe_idx = 2
    probed = tuple((b, 0.99 if i == probe_idx else w)
                   for i, (b, w) in enumerate(table))
    got = score(fold, daily, probed)
    for T in sorted(set(base) & set(got)):
        same = abs(base[T]['mae'] - got[T]['mae']) < 1e-9
        in_probed = bucket_of(T, table) == probe_idx
        if in_probed and same and base[T]['n']:
            return False, f"T-{T} is in the probed bucket but did not move"
        if not in_probed and not same:
            return False, f"T-{T} moved despite being outside the probed bucket"
    return True, "buckets are independent"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grid', nargs='*', type=float,
                    default=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    default_table = m04c.N5v4_Final.ENSEMBLE_WEIGHTS
    bounds = [b for b, _ in default_table]
    n_buckets = len(default_table)

    summary, daily, enrichment = load_inputs()

    print("Fitting folds ...")
    folds = {y: build_fold(y, summary, daily, enrichment) for y in FOLD_YEARS}

    ok, msg = check_bucket_independence(folds[FOLD_YEARS[-1]], daily, default_table)
    if not ok:
        print(f"ABORT: {msg}")
        print("The single-pass sweep assumes bucket independence and it no "
              "longer holds. Fit the buckets separately before trusting any "
              "result from this script.")
        return 1
    print(f"  control check: {msg}")

    # grid value -> fold -> {T: metrics}
    print(f"\nSweeping {len(args.grid)} weights x {len(FOLD_YEARS)} folds ...")
    sweep = {}
    for w in args.grid:
        flat = tuple((b, w) for b in bounds)
        sweep[w] = {y: score(folds[y], daily, flat) for y in FOLD_YEARS}
    baseline = {y: score(folds[y], daily, default_table) for y in FOLD_YEARS}

    def bucket_mae(metrics_by_T, bucket):
        """Sample-weighted MAE over the T points inside one bucket."""
        num = den = 0.0
        for T, m in metrics_by_T.items():
            if bucket_of(T, default_table) == bucket:
                num += m['mae'] * m['n']
                den += m['n']
        return (num / den) if den else None

    print("\nPer-bucket MAE by candidate weight (pooled over all folds, "
          "for orientation only — selection uses inner folds alone):")
    for bkt in range(n_buckets):
        lo = "T<=%s" % bounds[bkt] if bounds[bkt] is not None else "T>%s" % bounds[bkt - 1]
        cells = []
        for w in args.grid:
            vals = [bucket_mae(sweep[w][y], bkt) for y in FOLD_YEARS]
            vals = [v for v in vals if v is not None]
            cells.append(f"{w:.1f}:{np.mean(vals):5.2f}" if vals else f"{w:.1f}:  --")
        print(f"  {lo:>8}  " + "  ".join(cells))
        print(f"  {'':>8}  hand-picked {default_table[bkt][1]:.2f}")

    print("\nNested evaluation — weights chosen on earlier folds only:")
    rows = []
    for outer in FOLD_YEARS[1:]:
        inner = [y for y in FOLD_YEARS if y < outer]
        chosen = []
        for bkt in range(n_buckets):
            best_w, best_mae = None, None
            for w in args.grid:
                vals = [bucket_mae(sweep[w][y], bkt) for y in inner]
                vals = [v for v in vals if v is not None]
                if not vals:
                    continue
                mae = float(np.mean(vals))
                if best_mae is None or mae < best_mae:
                    best_w, best_mae = w, mae
            chosen.append(best_w if best_w is not None else default_table[bkt][1])
        chosen_table = tuple((b, w) for b, w in zip(bounds, chosen))

        held = score(folds[outer], daily, chosen_table)
        base = baseline[outer]
        print(f"\n  held-out {outer} (weights fitted on {inner})")
        print(f"    fitted weights: {[round(w, 2) for w in chosen]}")
        print(f"    hand-picked:    {[w for _, w in default_table]}")
        for T in (14, 7, 3):
            if T in held and T in base:
                d = held[T]['mae'] - base[T]['mae']
                verdict = ("fitted better" if d < -0.1 else
                           "hand-picked better" if d > 0.1 else "no difference")
                print(f"    T-{T:<3} hand {base[T]['mae']:5.2f}%  "
                      f"fitted {held[T]['mae']:5.2f}%  ({d:+.2f})  {verdict}")
                rows.append({'held_out': outer, 'T': T,
                             'hand_mae': round(base[T]['mae'], 2),
                             'fitted_mae': round(held[T]['mae'], 2),
                             'delta': round(d, 2), 'n': base[T]['n'],
                             'fitted_weights': [round(w, 2) for w in chosen]})

    if rows:
        agg = float(np.mean([r['delta'] for r in rows]))
        print(f"\nMean held-out MAE change from fitting: {agg:+.2f} points")
        print("  (negative favours the fitted weights)")
        if agg > -0.1:
            print("  The hand-picked weights hold up. Fitting four more "
                  "parameters on this much data does not beat them out of "
                  "sample, so they stay as they are.")

    if args.json:
        with open(args.json, 'w') as fh:
            json.dump({'grid': args.grid, 'nested': rows}, fh, indent=2)
        print(f"\nWrote {args.json}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
