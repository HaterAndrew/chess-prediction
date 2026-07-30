"""Blind-test harness (04c 1918-2037, verbatim; dev tool)."""

import numpy as np
import pandas as pd

from model.constants import CHOP_POINTS
from model.core import N5v4_Final

def run_blind_test(summary, daily):
    """
    Blind test: hold out 2024 and 2025 editions.
    Validate N5v4 after cleanup of retired exploratory models.
    Uses raw T throughout for consistency.
    """
    print("=" * 70)
    print("BLIND VALIDATION")
    print("=" * 70)

    all_results = []

    for test_year in [2024, 2025]:
        s = summary[
            (summary['has_timestamps']) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False))
        ]
        train = s[s['tournament_year'] < test_year]
        test = s[s['tournament_year'] == test_year]
        train_d = daily[daily['tid'].isin(train['tid'])]
        test_d = daily[daily['tid'].isin(test['tid'])]

        models = [('N5v4_Final', N5v4_Final())]

        for name, model in models:
            try:
                model.fit(train, train_d)
            except Exception as e:
                print(f"  {name}: fit failed - {e}")
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
                        'model': name,
                        'test_year': test_year,
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

    results = pd.DataFrame(all_results)

    # Report
    print("\nOverall:")
    overall = results.groupby('model').agg(
        n=('APE', 'size'),
        Median_APE=('APE', 'median'),
        MAPE=('APE', 'mean'),
        Within_10pct=('APE', lambda x: (x <= 10).mean() * 100),
        Within_20pct=('APE', lambda x: (x <= 20).mean() * 100),
        Coverage_80=('covered', lambda x: x.mean() * 100),
        Mean_CI_Width=('ci_width', 'mean'),
    ).round(1).sort_values('Median_APE')
    print(overall.to_string())

    print("\n80% CI Coverage by Lead Time:")
    cov = results.groupby(['model', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
    cov = cov[sorted(cov.columns, reverse=True)]
    print(cov.to_string())

    print("\nMean CI Width by Lead Time:")
    wid = results.groupby(['model', 'T_chop'])['ci_width'].mean().unstack(fill_value=np.nan).round(0)
    wid = wid[sorted(wid.columns, reverse=True)]
    print(wid.to_string())

    print("\nMAPE by Lead Time:")
    mape = results.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
    mape = mape[sorted(mape.columns, reverse=True)]
    print(mape.to_string())

    # Chicago Open specifics
    chi = results[results['family'] == 'Chicago Open']
    if len(chi) > 0:
        print("\nChicago Open Detail:")
        for _, r in chi.sort_values(['T_chop', 'model'], ascending=[False, True]).iterrows():
            print(f"  {r['model']:<20} {int(r['test_year'])}  T-{r['T_chop']:<3}  "
                  f"cnt={r['current_count']:>4}  pred={r['predicted']:>5}  "
                  f"actual={r['actual']:>5}  APE={r['APE']:>5}%  "
                  f"CI=[{r['lower']}, {r['upper']}]  w={r['ci_width']:>5}  "
                  f"{'OK' if r['covered'] else 'MISS'}")

    return results

