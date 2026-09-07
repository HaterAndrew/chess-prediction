"""Fit N5v4_Final.ANCHOR_WEIGHTS against held-out folds.

Why this exists
---------------
The 2026-09-07 review published two naive baselines beside the model for the
first time. One of them, "this family's most recent final count", beat the full
ensemble on MAE at every horizon past two weeks:

    T-90   baseline 10.5%   model 14.4%
    T-60   baseline 11.5%   model 15.5%
    T-42   baseline 12.2%   model 13.4%
    T-28   baseline 12.2%   model 15.0%
    T-14   baseline 12.2%   model 10.3%   <- model wins from here inward

Both legs of the ensemble read the registration curve, which carries little
information three months out, and the ratio leg amplifies what noise it has.
Last year's size does carry information, and the model already computed it.

So the anchor gets a weight. This script chooses it the same way
fit_ensemble_weights.py chooses the ratio/regression split: one weight per
lead-time bucket, swept over a grid, selected on inner folds only and reported
on a year the selection never saw. Anything chosen by looking at the graded
years would be fitting the number that gets published.

Protocol
--------
Mostly as fit_ensemble_weights.py, with one deliberate difference.

  * Fold models are built once and reused across candidates, so the sweep costs
    one fit per fold rather than one per candidate.
  * Recalibration is refit for every candidate. Recal factors are estimated
    from predictions, so carrying the default-weight factors across candidates
    would contaminate all of them.
  * Selection is nested: weights for held-out year Y come from the folds before
    Y alone.

The difference: this sweep is JOINT over the buckets, not one bucket at a time.
fit_ensemble_weights.py may sweep buckets independently because a bucket's
weight cannot move a prediction at a lead time outside it. That property does
not hold here, and the control check caught it on the first run:

    ABORT: T-14 moved despite being outside the probed bucket

The path is recalibration. Bias and CI factors are estimated from the model's
own predictions across all horizons, so raising the anchor weight at T>28
changes the cohort those factors are fitted on, which changes what gets applied
at T-14. Real coupling, not a bug. A per-bucket sweep would have selected each
weight against a moving target, so the buckets are searched together and the
objective is total sample-weighted MAE across every horizon. The held-out table
splits long from short so a long-lead gain bought with a short-lead loss cannot
hide inside the total.

The first bucket is pinned at zero rather than searched. The model beats the
naive forecast from T-14 inward and there is no reason to spend held-out
evidence re-establishing that.

Result, 2026-09-07
------------------
Nested selection landed on 0.6 / 0.8 in both outer folds:

    held-out 2024   T-90 -0.65   T-60 -1.29   T-42 -3.14   T-28 -3.60
    held-out 2025   T-90 -0.16   T-60 +0.01   T-42 +0.36   T-28 +0.38
    mean held-out MAE change  T>=28  -1.01 points   T<28  +0.00 points

So the anchor earns its place, but not evenly: 2024 is where the gain lives and
2025 is fractionally worse at T-42 and T-28. One year of the two. Worth having
at a mean of -1.01, worth revisiting when 2026 closes and there is a third
outer fold to judge it on.

T<28 is unchanged to the digit at every one of the 25 candidate pairs, which is
the pin doing its job. Note that this is stronger than the earlier ABORT
implied: the coupling exists at a probe weight of 0.99 but does not show at any
weight in the 0.0-0.8 range actually swept. The joint search stays anyway,
because "the coupling is small in the region we looked at" is not a property
worth assuming on the next run.

The shipped constants come from the pooled table rather than the nested pick.
That table is flat across 0.4-0.6 x 0.6 (T>=28 MAE 14.13 against 15.23 with no
anchor), and the shipped 0.4 / 0.6 is the more conservative of the two tied
minima. The nested run's job is to say whether the procedure generalises, which
it does; the constant is then refit on everything available, the same way
fit_ensemble_weights.py reports its own.

Usage:
    python scripts/fit_anchor_weights.py
    python scripts/fit_anchor_weights.py --grid 0.0 0.25 0.5 0.75
"""
import argparse
import json
import os
import sys
from importlib import import_module
from itertools import product

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

m04c = import_module("04c_final_model")
m04e = import_module("04e_performance_data")

from scripts.fit_ensemble_weights import (  # noqa: E402
    FOLD_YEARS, build_fold, load_inputs,
)


def score(fold, daily, table):
    """Per-T MAE and coverage for one candidate anchor table on one fold."""
    model = fold['model']
    model.anchor_weights = table
    if len(fold['recal']) >= 5:
        model.recalibrate(fold['recal'], daily)
        model.anchor_weights = table
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


def pooled_mae(metrics_by_T, only=None):
    """Sample-weighted MAE over the T points selected by `only`."""
    num = den = 0.0
    for T, m in metrics_by_T.items():
        if only is not None and not only(T):
            continue
        num += m['mae'] * m['n']
        den += m['n']
    return (num / den) if den else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--grid', nargs='*', type=float,
                    default=[0.0, 0.2, 0.4, 0.6, 0.8])
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    default_table = m04c.N5v4_Final.ANCHOR_WEIGHTS
    bounds = [b for b, _ in default_table]
    # Bucket 0 (T <= first bound) is pinned at zero; the rest are searched.
    free = list(range(1, len(bounds)))
    combos = [c for c in product(args.grid, repeat=len(free))]

    summary, daily, enrichment = load_inputs()

    print("Fitting folds ...")
    folds = {y: build_fold(y, summary, daily, enrichment) for y in FOLD_YEARS}

    def table_for(values):
        vals = dict(zip(free, values))
        return tuple((b, vals.get(i, 0.0)) for i, b in enumerate(bounds))

    print(f"\nJoint sweep: {len(combos)} weight pairs x {len(FOLD_YEARS)} folds "
          f"= {len(combos) * len(FOLD_YEARS)} evaluations ...")
    sweep = {}
    for n, c in enumerate(combos, 1):
        sweep[c] = {y: score(folds[y], daily, table_for(c)) for y in FOLD_YEARS}
        print(f"  [{n}/{len(combos)}] {[round(v, 2) for v in c]}", flush=True)
    baseline = {y: sweep[tuple(0.0 for _ in free)][y] for y in FOLD_YEARS}

    print("\nPooled MAE by weight pair (all folds, orientation only — "
          "selection uses inner folds alone):")
    print(f"    {'T<=28':>12} x {'T>28':<6}   all-T   T>=28   T<28")
    for c in combos:
        allT = np.mean([pooled_mae(sweep[c][y]) for y in FOLD_YEARS])
        lng = np.mean([pooled_mae(sweep[c][y], lambda T: T >= 28) for y in FOLD_YEARS])
        srt = np.mean([pooled_mae(sweep[c][y], lambda T: T < 28) for y in FOLD_YEARS])
        print(f"    {c[0]:12.2f} x {c[1]:<6.2f}  {allT:6.2f}  {lng:6.2f}  {srt:6.2f}")

    print("\nNested evaluation — weights chosen on earlier folds only:")
    rows = []
    for outer in FOLD_YEARS[1:]:
        inner = [y for y in FOLD_YEARS if y < outer]
        best_c, best_mae = None, None
        for c in combos:
            vals = [pooled_mae(sweep[c][y]) for y in inner]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mae = float(np.mean(vals))
            if best_mae is None or mae < best_mae:
                best_c, best_mae = c, mae
        chosen = table_for(best_c)

        held = sweep[best_c][outer]
        base = baseline[outer]
        print(f"\n  held-out {outer} (weights fitted on {inner})")
        print(f"    fitted anchor weights: {[round(w, 2) for _, w in chosen]}")
        for T in (90, 60, 42, 28, 14, 7, 3):
            if T in held and T in base:
                d = held[T]['mae'] - base[T]['mae']
                verdict = ("anchor better" if d < -0.1 else
                           "no anchor better" if d > 0.1 else "no difference")
                print(f"    T-{T:<3} none {base[T]['mae']:5.2f}%  "
                      f"anchored {held[T]['mae']:5.2f}%  ({d:+.2f})  "
                      f"cov {base[T]['cov']:.0f}->{held[T]['cov']:.0f}  {verdict}")
                rows.append({'held_out': outer, 'T': T,
                             'none_mae': round(base[T]['mae'], 2),
                             'anchored_mae': round(held[T]['mae'], 2),
                             'delta': round(d, 2), 'n': base[T]['n'],
                             'none_cov': round(base[T]['cov'], 0),
                             'anchored_cov': round(held[T]['cov'], 0),
                             'fitted_weights': [round(w, 2) for _, w in chosen]})

    if rows:
        long_rows = [r for r in rows if r['T'] >= 28]
        short_rows = [r for r in rows if r['T'] < 28]
        print(f"\nMean held-out MAE change, T>=28: "
              f"{np.mean([r['delta'] for r in long_rows]):+.2f} points")
        print(f"Mean held-out MAE change, T<28:  "
              f"{np.mean([r['delta'] for r in short_rows]):+.2f} points")
        print("  (negative favours the anchor)")

    if args.json:
        with open(args.json, 'w') as fh:
            json.dump({'grid': args.grid, 'nested': rows}, fh, indent=2)
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
