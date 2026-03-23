"""
Blind backtest of predict_with_lognormal_ci from 04d_website_data_v2.py.
Test years: 2024, 2025. Train on all data before the test year.
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Imports from 04d ──
# We can't cleanly import from 04d because it runs top-level code,
# so we copy the two functions directly.

from scipy.stats import lognorm

CHOP_POINTS = [120, 90, 60, 42, 28, 14, 7, 3, 1, 0]
TEST_T = [90, 60, 42, 28, 14, 7, 3, 1]

def build_ratio_model(train_summary, train_daily):
    """Build historical ratio model with lognormal CIs."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False))
    ]
    ratios = {}
    global_ratios = {}
    for _, row in valid.iterrows():
        tid = row['tid']
        family = row['family']
        actual = row['final_count']
        tid_daily = train_daily[train_daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) < 5:
            continue
        if family not in ratios:
            ratios[family] = {}
        for T in CHOP_POINTS:
            regs = tid_daily[tid_daily['T'] >= T]
            if len(regs) == 0:
                continue
            count_at_T = int(regs['cum_regs'].max())
            if count_at_T == 0:
                continue
            ratio = actual / count_at_T
            ratios[family].setdefault(T, []).append(ratio)
            global_ratios.setdefault(T, []).append(ratio)
    ratios['__global__'] = global_ratios
    return ratios


def predict_with_lognormal_ci(current_count, days_remaining, family, ratios, ci_level=0.80):
    """Predict using median ratio with lognormal CI."""
    fam_ratios = ratios.get(family, ratios.get('__global__', {}))
    if not fam_ratios:
        fam_ratios = ratios.get('__global__', {})
    available_T = sorted(fam_ratios.keys())
    if not available_T:
        return current_count, current_count, current_count
    closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
    ratio_list = fam_ratios[closest_T]
    if not ratio_list or len(ratio_list) < 2:
        if ratio_list:
            r = ratio_list[0]
            return round(current_count * r), round(current_count * r * 0.7), round(current_count * r * 1.3)
        return current_count, current_count, current_count
    q1, q3 = np.percentile(ratio_list, [25, 75])
    iqr = q3 - q1
    filtered = [r for r in ratio_list if q1 - 3*iqr <= r <= q3 + 3*iqr]
    if len(filtered) < 2:
        filtered = ratio_list
    log_ratios = np.log(filtered)
    mu = np.mean(log_ratios)
    sigma = max(np.std(log_ratios, ddof=1), 0.05)
    # For families with few ratio observations, use global sigma as floor
    n_ratios = len(filtered)
    if n_ratios < 4:
        global_ratios_at_T = ratios.get('__global__', {}).get(closest_T, [])
        if len(global_ratios_at_T) >= 5:
            global_sigma = max(np.std(np.log(global_ratios_at_T), ddof=1), 0.1)
        else:
            global_sigma = 0.3
        sigma = max(sigma, global_sigma * 0.5)
    median_ratio = np.exp(mu)
    alpha = (1 - ci_level) / 2
    lo_ratio = lognorm.ppf(alpha, s=sigma, scale=np.exp(mu))
    hi_ratio = lognorm.ppf(1 - alpha, s=sigma, scale=np.exp(mu))
    point = round(current_count * median_ratio)
    lo = round(current_count * lo_ratio)
    hi = round(current_count * hi_ratio)
    return max(point, current_count), max(lo, current_count), max(hi, point)


# ── Load data ──
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
summary = pd.read_csv(os.path.join(DATA_DIR, "tournament_summary.csv"))
daily = pd.read_csv(os.path.join(DATA_DIR, "daily_registration_counts.csv"))

# ── Run blind test ──
results = []

for test_year in [2024, 2025]:
    # Train on everything before test year
    train_sum = summary[summary['tournament_year'] < test_year]
    train_daily_ids = set(train_sum['tid'].values)
    train_day = daily[daily['tid'].isin(train_daily_ids)]
    ratios = build_ratio_model(train_sum, train_day)

    # Test tournaments: in-person, non-COVID, with timestamps
    test_sum = summary[
        (summary['tournament_year'] == test_year) &
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ]

    for _, row in test_sum.iterrows():
        tid = row['tid']
        family = row['family']
        actual = row['final_count']
        if actual < 10:  # skip tiny events
            continue

        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) < 5:
            continue

        for T in TEST_T:
            regs = tid_daily[tid_daily['T'] >= T]
            if len(regs) == 0:
                continue
            count_at_T = int(regs['cum_regs'].max())
            if count_at_T == 0:
                continue

            point, ci_lo, ci_hi = predict_with_lognormal_ci(count_at_T, T, family, ratios)
            ape = abs(point - actual) / actual * 100
            covered = ci_lo <= actual <= ci_hi

            results.append({
                'year': test_year,
                'family': family,
                'tid': tid,
                'T': T,
                'actual': actual,
                'count_at_T': count_at_T,
                'point': point,
                'ci_lo': ci_lo,
                'ci_hi': ci_hi,
                'ape': ape,
                'covered': covered,
            })

df = pd.DataFrame(results)

# ── Report ──
print("=" * 70)
print("BLIND BACKTEST: predict_with_lognormal_ci  |  Test years: 2024-2025")
print("=" * 70)

print(f"\nTotal test cases: {len(df)}")
print(f"Tournaments tested: {df['tid'].nunique()}")
print(f"Families tested: {df['family'].nunique()}")

print(f"\n--- Overall ---")
print(f"  MAPE:          {df['ape'].mean():.1f}%")
print(f"  Median APE:    {df['ape'].median():.1f}%")
print(f"  80% CI cover:  {df['covered'].mean()*100:.1f}%")

print(f"\n--- MAPE by T (days before event) ---")
by_t = df.groupby('T').agg(
    mape=('ape', 'mean'),
    median_ape=('ape', 'median'),
    coverage=('covered', 'mean'),
    n=('ape', 'count')
).sort_index(ascending=False)
print(f"  {'T':>4s}  {'MAPE':>7s}  {'MedAPE':>7s}  {'Cover':>7s}  {'N':>5s}")
for T, r in by_t.iterrows():
    print(f"  {T:>4d}  {r['mape']:>6.1f}%  {r['median_ape']:>6.1f}%  {r['coverage']*100:>5.1f}%  {int(r['n']):>5d}")

print(f"\n--- Coverage by T ---")
print(f"  (Target: 80% for all T values)")

print(f"\n--- MAPE by year ---")
by_year = df.groupby('year').agg(mape=('ape', 'mean'), coverage=('covered', 'mean'), n=('ape', 'count'))
for yr, r in by_year.iterrows():
    print(f"  {yr}: MAPE={r['mape']:.1f}%, Coverage={r['coverage']*100:.1f}%, N={int(r['n'])}")

# Chicago Open stats
chi = df[df['family'].str.contains('Chicago Open', case=False, na=False)]
if len(chi) > 0:
    print(f"\n--- Chicago Open ---")
    print(f"  Cases: {len(chi)}")
    print(f"  MAPE: {chi['ape'].mean():.1f}%")
    print(f"  Coverage: {chi['covered'].mean()*100:.1f}%")
    print(f"  Detail:")
    print(f"  {'Year':>4s}  {'T':>4s}  {'Ct@T':>5s}  {'Pred':>5s}  {'Actual':>6s}  {'APE':>6s}  {'CI':>15s}  {'Hit':>4s}")
    for _, r in chi.sort_values(['year', 'T'], ascending=[True, False]).iterrows():
        ci_str = f"[{int(r['ci_lo'])}, {int(r['ci_hi'])}]"
        hit = "Y" if r['covered'] else "N"
        print(f"  {int(r['year']):>4d}  {int(r['T']):>4d}  {int(r['count_at_T']):>5d}  {int(r['point']):>5d}  {int(r['actual']):>6d}  {r['ape']:>5.1f}%  {ci_str:>15s}  {hit:>4s}")
else:
    print(f"\n--- Chicago Open: no test data found ---")

# Worst predictions
print(f"\n--- Top 10 worst predictions (by APE) ---")
worst = df.nlargest(10, 'ape')
print(f"  {'Family':30s}  {'Yr':>4s}  {'T':>4s}  {'Ct@T':>5s}  {'Pred':>5s}  {'Actual':>6s}  {'APE':>6s}")
for _, r in worst.iterrows():
    print(f"  {r['family']:30s}  {int(r['year']):>4d}  {int(r['T']):>4d}  {int(r['count_at_T']):>5d}  {int(r['point']):>5d}  {int(r['actual']):>6d}  {r['ape']:>5.1f}%")

print("\n" + "=" * 70)
