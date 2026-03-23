"""
Phase 2: Template Curves & Simple Nowcast
- Build median cumulative registration curves per family
- Create interpolators for nowcasting
- Validate on held-out 2025 data
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import os
import pickle

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# ── Load Phase 1 outputs ───────────────────────────────────────────────────
print("Loading Phase 1 outputs...")
summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))

# Filter to timestamped, in-person, non-COVID tournaments
valid_tids = summary[
    (summary['has_timestamps']) &
    (~summary['is_online'].fillna(False)) &
    (~summary['is_covid'].fillna(False))
]['tid'].values

daily_valid = daily[daily['tid'].isin(valid_tids)].copy()
print(f"  {len(valid_tids)} valid tournaments for curve building")

# ── Build Template Curves Per Family ────────────────────────────────────────
print("\nBuilding template curves per family...")

# Standard T grid for interpolation (days before event)
T_GRID = np.arange(0, 121)  # 0 to 120 days before event

# For each family, build a median curve from its editions
family_curves = {}
family_stats = {}

# Get family info for valid tournaments
tid_family = summary[summary['tid'].isin(valid_tids)][['tid', 'family', 'tournament_year', 'final_count']]

families_with_data = tid_family.groupby('family').filter(lambda x: len(x) >= 3)['family'].unique()
print(f"  {len(families_with_data)} families with 3+ timestamped editions")

for family in families_with_data:
    family_tids = tid_family[tid_family['family'] == family]

    curves_at_T = {}  # T -> list of cum_pct values across editions

    for _, row in family_tids.iterrows():
        tid = row['tid']
        edition_daily = daily_valid[daily_valid['tid'] == tid].sort_values('T')

        if len(edition_daily) < 5:
            continue

        # Interpolate this edition's curve onto the standard T grid
        # cum_pct is cumulative from earliest reg to event (T descending = time progressing)
        # We need cum_pct as function of T (days before event)
        # At high T (far from event), cum_pct is low; at T=0, cum_pct = 1.0
        t_vals = edition_daily['T'].values
        pct_vals = edition_daily['cum_pct'].values

        # Create interpolator (T -> cum_pct)
        # Extrapolate: before first registration = 0, at event = 1.0
        try:
            f = interp1d(t_vals, pct_vals, kind='linear', bounds_error=False,
                        fill_value=(1.0, 0.0))  # (below min T -> 1.0, above max T -> 0.0)

            for t in T_GRID:
                if t not in curves_at_T:
                    curves_at_T[t] = []
                curves_at_T[t].append(float(f(t)))
        except Exception:
            continue

    if not curves_at_T:
        continue

    # Compute median and std at each T
    median_curve = np.array([np.median(curves_at_T.get(t, [0])) for t in T_GRID])
    std_curve = np.array([np.std(curves_at_T.get(t, [0])) for t in T_GRID])
    n_editions = len(family_tids)

    family_curves[family] = {
        'T': T_GRID,
        'median_pct': median_curve,
        'std_pct': std_curve,
        'n_editions': n_editions,
    }

    family_stats[family] = {
        'n_editions': n_editions,
        'pct_at_T90': median_curve[90] if len(median_curve) > 90 else 0,
        'pct_at_T60': median_curve[60] if len(median_curve) > 60 else 0,
        'pct_at_T28': median_curve[28] if len(median_curve) > 28 else 0,
        'pct_at_T14': median_curve[14] if len(median_curve) > 14 else 0,
        'pct_at_T7': median_curve[7] if len(median_curve) > 7 else 0,
        'pct_at_T3': median_curve[3] if len(median_curve) > 3 else 0,
    }

print(f"  Built curves for {len(family_curves)} families")

# Also build a global "all families" curve as fallback
all_curves_at_T = {}
for _, row in tid_family.iterrows():
    tid = row['tid']
    edition_daily = daily_valid[daily_valid['tid'] == tid].sort_values('T')
    if len(edition_daily) < 5:
        continue
    t_vals = edition_daily['T'].values
    pct_vals = edition_daily['cum_pct'].values
    try:
        f = interp1d(t_vals, pct_vals, kind='linear', bounds_error=False,
                    fill_value=(1.0, 0.0))
        for t in T_GRID:
            if t not in all_curves_at_T:
                all_curves_at_T[t] = []
            all_curves_at_T[t].append(float(f(t)))
    except Exception:
        continue

global_median = np.array([np.median(all_curves_at_T.get(t, [0])) for t in T_GRID])
global_std = np.array([np.std(all_curves_at_T.get(t, [0])) for t in T_GRID])
family_curves['__global__'] = {
    'T': T_GRID,
    'median_pct': global_median,
    'std_pct': global_std,
    'n_editions': len(valid_tids),
}

# ── Save curves ─────────────────────────────────────────────────────────────
curves_path = os.path.join(OUTPUT_DIR, "family_curves.pkl")
with open(curves_path, 'wb') as f:
    pickle.dump(family_curves, f)
print(f"\nSaved family curves to {curves_path}")

# ── Nowcast Function ────────────────────────────────────────────────────────
def nowcast(current_count, days_remaining, family, curves=family_curves):
    """
    Simple nowcast: predicted_final = current_count / median_pct_at_T(family)
    Returns (point_estimate, lower_80, upper_80)
    """
    curve = curves.get(family, curves.get('__global__'))

    T = min(int(days_remaining), 120)
    T = max(T, 0)

    median_pct = curve['median_pct'][T]
    std_pct = curve['std_pct'][T]

    if median_pct < 0.01:
        # Too early, no meaningful prediction possible
        return None, None, None

    point_est = current_count / median_pct

    # CI from historical std of cumulative %
    low_pct = max(median_pct - 1.28 * std_pct, 0.01)  # 80% CI -> 1.28 z-score
    high_pct = min(median_pct + 1.28 * std_pct, 1.0)

    # Lower bound: if actual % is higher than expected, final count is lower
    lower = current_count / high_pct
    upper = current_count / low_pct

    return round(point_est), round(lower), round(upper)

# ── Validate: Blind Nowcast on 2025 Tournaments ────────────────────────────
print("\n── Blind Validation: Template Nowcast on 2025 ──")

test_tids = summary[
    (summary['tournament_year'] == 2025) &
    (summary['has_timestamps']) &
    (~summary['is_online'].fillna(False))
]

# Build training curves from 2022-2024 only (exclude 2025)
train_tids_set = summary[
    (summary['has_timestamps']) &
    (~summary['is_online'].fillna(False)) &
    (~summary['is_covid'].fillna(False)) &
    (summary['tournament_year'].isin([2022, 2023, 2024]))
]['tid'].values

train_daily = daily[daily['tid'].isin(train_tids_set)].copy()
train_tid_family = summary[summary['tid'].isin(train_tids_set)][['tid', 'family']]

# Build training curves (same logic as above, but train-only)
train_curves = {}
for family in train_tid_family['family'].unique():
    ftids = train_tid_family[train_tid_family['family'] == family]['tid'].values
    if len(ftids) < 2:  # need at least 2 for a template
        continue
    curves_at_T = {}
    for tid in ftids:
        ed = train_daily[train_daily['tid'] == tid].sort_values('T')
        if len(ed) < 5:
            continue
        try:
            fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                         bounds_error=False, fill_value=(1.0, 0.0))
            for t in T_GRID:
                curves_at_T.setdefault(t, []).append(float(fi(t)))
        except Exception:
            continue
    if curves_at_T:
        train_curves[family] = {
            'T': T_GRID,
            'median_pct': np.array([np.median(curves_at_T.get(t, [0])) for t in T_GRID]),
            'std_pct': np.array([np.std(curves_at_T.get(t, [0])) for t in T_GRID]),
        }

# Build global fallback from training data
all_train_at_T = {}
for tid in train_tids_set:
    ed = train_daily[train_daily['tid'] == tid].sort_values('T')
    if len(ed) < 5:
        continue
    try:
        fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                     bounds_error=False, fill_value=(1.0, 0.0))
        for t in T_GRID:
            all_train_at_T.setdefault(t, []).append(float(fi(t)))
    except Exception:
        continue

train_curves['__global__'] = {
    'T': T_GRID,
    'median_pct': np.array([np.median(all_train_at_T.get(t, [0])) for t in T_GRID]),
    'std_pct': np.array([np.std(all_train_at_T.get(t, [0])) for t in T_GRID]),
}

# Run blind nowcasts at various chop points
CHOP_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]
results = []

for _, row in test_tids.iterrows():
    tid = row['tid']
    family = row['family']
    actual = row['final_count']

    tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(tid_daily) < 5:
        continue

    for T_chop in CHOP_POINTS:
        # Count registrations at or before T_chop days before event
        regs_at_chop = tid_daily[tid_daily['T'] >= T_chop]['cum_regs'].max()
        if pd.isna(regs_at_chop) or regs_at_chop == 0:
            # No registrations yet at this lead time
            continue

        pred, lower, upper = nowcast(int(regs_at_chop), T_chop, family, train_curves)
        if pred is None:
            continue

        ape = abs(pred - actual) / actual * 100
        covered = lower <= actual <= upper if (lower and upper) else False

        results.append({
            'tid': tid,
            'family': family,
            'actual': actual,
            'T_chop': T_chop,
            'current_count': int(regs_at_chop),
            'predicted': pred,
            'lower_80': lower,
            'upper_80': upper,
            'APE': round(ape, 1),
            'covered': covered,
        })

results_df = pd.DataFrame(results)

if len(results_df) > 0:
    print(f"\n{len(results_df)} blind test predictions on 2025 data")

    # Summary by chop point
    chop_summary = results_df.groupby('T_chop').agg(
        n=('APE', 'size'),
        MAPE=('APE', 'mean'),
        Median_APE=('APE', 'median'),
        Max_APE=('APE', 'max'),
        Coverage=('covered', 'mean'),
        Within_10pct=('APE', lambda x: (x <= 10).mean()),
        Within_20pct=('APE', lambda x: (x <= 20).mean()),
    ).round(1)

    print("\nTemplate Nowcast Performance by Lead Time (2025 blind test):")
    print(chop_summary.to_string())

    # Chicago Open specific
    chicago_results = results_df[results_df['family'].str.contains('Chicago Open', na=False)]
    if len(chicago_results) > 0:
        print(f"\nChicago Open 2025 Nowcast Results:")
        print(chicago_results[['family', 'T_chop', 'current_count', 'predicted', 'actual', 'APE', 'covered']].to_string(index=False))

    results_df.to_csv(os.path.join(OUTPUT_DIR, "template_nowcast_2025_validation.csv"), index=False)

# ── Visualize template curves for key families ─────────────────────────────
print("\n── Plotting template curves for key families ──")

key_families = ['Chicago Open', 'World Open', 'North American Open', 'National Chess Congress',
                'Liberty Bell Open', 'Atlantic Open']

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
axes = axes.flatten()

for idx, family in enumerate(key_families):
    ax = axes[idx]
    curve = family_curves.get(family)
    if curve is None:
        ax.set_title(f"{family} (no data)")
        continue

    T = curve['T']
    median = curve['median_pct']
    std = curve['std_pct']

    ax.plot(T, median, 'b-', linewidth=2, label='Median')
    ax.fill_between(T, np.clip(median - 1.28*std, 0, 1), np.clip(median + 1.28*std, 0, 1),
                    alpha=0.2, color='blue', label='80% CI')
    ax.set_xlabel('Days Before Event')
    ax.set_ylabel('Cumulative %')
    ax.set_title(f"{family} (n={curve['n_editions']})")
    ax.invert_xaxis()
    ax.set_xlim(120, 0)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

plt.suptitle('Template Cumulative Registration Curves by Family', fontsize=14)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "template_curves.png"), dpi=150)
print(f"Saved template curves plot to output/template_curves.png")

# ── Print Family Stats ──────────────────────────────────────────────────────
print("\n── Template Curve Stats (% registered at each lead time) ──")
stats_df = pd.DataFrame(family_stats).T
stats_df = stats_df.sort_values('n_editions', ascending=False)
print(stats_df.head(20).round(3).to_string())

print(f"\n{'='*60}")
print(f"PHASE 2 COMPLETE")
print(f"{'='*60}")
