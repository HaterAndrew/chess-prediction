"""
Test alternative nowcast model variants against the current N5_HistRatio baseline.

Variants tested:
  1. N5_HistRatio (baseline) — median of historical final/count_at_T ratios
  2. N1_Template (baseline) — current_count / median_pct_at_T
  3. N5_Weighted — exponential decay weighting (half-life=2yr) on ratios
  4. N5_Trimmed — trimmed mean (10% each end) instead of median
  5. N5_WeightedTrimmed — both weighted and trimmed

Evaluation: MAPE, coverage of 80% CI, by chop point and overall.
Test years: 2024-2025, plus Chicago Open leave-one-out.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
from scipy.stats import trim_mean
import os
import warnings

warnings.filterwarnings('ignore')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]
T_GRID = np.arange(0, 121)


# ═══════════════════════════════════════════════════════════════════════════
# MODEL VARIANTS
# ═══════════════════════════════════════════════════════════════════════════

def build_historical_ratios_with_years(summary, daily, chop_points=None):
    """
    Like build_historical_ratios but also tracks the tournament year for each ratio,
    enabling year-weighted aggregation at prediction time.
    Returns: family -> {T -> [(ratio, year), ...]}
    """
    if chop_points is None:
        chop_points = CHOP_POINTS

    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False))
    ]

    ratios = {}
    global_ratios = {}

    for _, row in valid.iterrows():
        tid = row['tid']
        family = row['family']
        actual = row['final_count']
        year = row['tournament_year']

        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) < 5:
            continue

        if family not in ratios:
            ratios[family] = {}

        for T in chop_points:
            regs = tid_daily[tid_daily['T'] >= T]
            if len(regs) == 0:
                continue
            count_at_T = int(regs['cum_regs'].max())
            if count_at_T == 0:
                continue

            ratio = actual / count_at_T
            ratios[family].setdefault(T, []).append((ratio, year))
            global_ratios.setdefault(T, []).append((ratio, year))

    ratios['__global__'] = global_ratios
    return ratios


def build_template_curves(summary, daily):
    """Build family template curves (median cum_pct at each T)."""
    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False))
    ]

    curves = {}
    for family in valid['family'].unique():
        ftids = valid[valid['family'] == family]['tid'].values
        if len(ftids) < 2:
            continue
        curves_at_T = {}
        for tid in ftids:
            ed = daily[daily['tid'] == tid].sort_values('T')
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
            curves[family] = {
                'T': T_GRID,
                'median_pct': np.array([np.median(curves_at_T.get(t, [0])) for t in T_GRID]),
                'std_pct': np.array([np.std(curves_at_T.get(t, [0])) for t in T_GRID]),
            }

    # Global fallback
    all_at_T = {}
    for tid in valid['tid'].values:
        ed = daily[daily['tid'] == tid].sort_values('T')
        if len(ed) < 5:
            continue
        try:
            fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                          bounds_error=False, fill_value=(1.0, 0.0))
            for t in T_GRID:
                all_at_T.setdefault(t, []).append(float(fi(t)))
        except Exception:
            continue
    curves['__global__'] = {
        'T': T_GRID,
        'median_pct': np.array([np.median(all_at_T.get(t, [0])) for t in T_GRID]),
        'std_pct': np.array([np.std(all_at_T.get(t, [0])) for t in T_GRID]),
    }

    return curves


class N5_HistRatio:
    """Baseline: median of historical ratios."""
    name = "N5_HistRatio (baseline)"

    def fit(self, summary, daily):
        self.ratios = build_historical_ratios_with_years(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        pairs = fam_ratios[closest_T]
        if not pairs:
            return None, None, None

        ratio_list = [r for r, y in pairs]
        median_ratio = np.median(ratio_list)
        point = current_count * median_ratio

        if len(ratio_list) >= 3:
            low_ratio = np.percentile(ratio_list, 10)
            high_ratio = np.percentile(ratio_list, 90)
        else:
            low_ratio = min(ratio_list) * 0.9
            high_ratio = max(ratio_list) * 1.1

        return (round(max(point, current_count)),
                round(max(current_count * low_ratio, current_count)),
                round(max(current_count * high_ratio, point)))


class N1_Template:
    """Template curve scaling: predicted = current / median_pct_at_T."""
    name = "N1_Template"

    def fit(self, summary, daily):
        self.curves = build_template_curves(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        curve = self.curves.get(family, self.curves.get('__global__'))
        T = min(max(int(days_remaining), 0), 120)

        median_pct = curve['median_pct'][T]
        std_pct = curve['std_pct'][T]

        if median_pct < 0.01:
            return None, None, None

        point = current_count / median_pct
        low_pct = max(median_pct - 1.28 * std_pct, 0.01)
        high_pct = min(median_pct + 1.28 * std_pct, 1.0)

        return (round(point),
                round(current_count / high_pct),
                round(current_count / low_pct))


class N5_Weighted:
    """Weighted ratio model: exponential decay, half-life=2 years."""
    name = "N5_Weighted (hl=2yr)"

    def fit(self, summary, daily):
        self.ratios = build_historical_ratios_with_years(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, year=2025, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        pairs = fam_ratios[closest_T]
        if not pairs:
            return None, None, None

        ratios = np.array([r for r, y in pairs])
        years = np.array([y for r, y in pairs])

        # Exponential decay weights: w = exp(-ln(2) * age / half_life)
        half_life = 2.0
        ages = year - years
        weights = np.exp(-np.log(2) * ages / half_life)
        weights = weights / weights.sum()

        # Weighted mean as point estimate
        weighted_ratio = np.average(ratios, weights=weights)
        point = current_count * weighted_ratio

        # Weighted CI: use weighted percentiles
        # Sort by ratio, compute cumulative weight, find 10th/90th
        sorted_idx = np.argsort(ratios)
        sorted_ratios = ratios[sorted_idx]
        sorted_weights = weights[sorted_idx]
        cum_weights = np.cumsum(sorted_weights)

        low_ratio = sorted_ratios[np.searchsorted(cum_weights, 0.10)]
        high_ratio = sorted_ratios[np.searchsorted(cum_weights, 0.90, side='right') - 1] \
            if np.searchsorted(cum_weights, 0.90, side='right') > 0 else sorted_ratios[-1]

        # Fallback if too few data points
        if len(ratios) < 3:
            low_ratio = ratios.min() * 0.9
            high_ratio = ratios.max() * 1.1

        return (round(max(point, current_count)),
                round(max(current_count * low_ratio, current_count)),
                round(max(current_count * high_ratio, point)))


class N5_Trimmed:
    """Trimmed mean ratio: trim 10% from each end."""
    name = "N5_Trimmed (10%)"

    def fit(self, summary, daily):
        self.ratios = build_historical_ratios_with_years(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        pairs = fam_ratios[closest_T]
        if not pairs:
            return None, None, None

        ratio_list = np.array([r for r, y in pairs])

        # Trimmed mean (trim 10% from each side), falls back to regular mean if <5 samples
        if len(ratio_list) >= 5:
            trimmed_ratio = trim_mean(ratio_list, proportiontocut=0.1)
        else:
            trimmed_ratio = np.mean(ratio_list)

        point = current_count * trimmed_ratio

        if len(ratio_list) >= 3:
            low_ratio = np.percentile(ratio_list, 10)
            high_ratio = np.percentile(ratio_list, 90)
        else:
            low_ratio = ratio_list.min() * 0.9
            high_ratio = ratio_list.max() * 1.1

        return (round(max(point, current_count)),
                round(max(current_count * low_ratio, current_count)),
                round(max(current_count * high_ratio, point)))


class N5_WeightedTrimmed:
    """Weighted + trimmed: drop 10% outliers, then weight by recency."""
    name = "N5_WtdTrimmed"

    def fit(self, summary, daily):
        self.ratios = build_historical_ratios_with_years(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, year=2025, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        pairs = fam_ratios[closest_T]
        if not pairs:
            return None, None, None

        ratios = np.array([r for r, y in pairs])
        years = np.array([y for r, y in pairs])

        # Trim 10% from each end
        if len(ratios) >= 5:
            p10, p90 = np.percentile(ratios, [10, 90])
            mask = (ratios >= p10) & (ratios <= p90)
            ratios = ratios[mask]
            years = years[mask]

        if len(ratios) == 0:
            return None, None, None

        # Exponential decay weights
        half_life = 2.0
        ages = year - years
        weights = np.exp(-np.log(2) * ages / half_life)
        weights = weights / weights.sum()

        weighted_ratio = np.average(ratios, weights=weights)
        point = current_count * weighted_ratio

        # CI from the trimmed set
        if len(ratios) >= 3:
            low_ratio = np.percentile(ratios, 10)
            high_ratio = np.percentile(ratios, 90)
        else:
            low_ratio = ratios.min() * 0.9
            high_ratio = ratios.max() * 1.1

        return (round(max(point, current_count)),
                round(max(current_count * low_ratio, current_count)),
                round(max(current_count * high_ratio, point)))


ALL_MODELS = [N5_HistRatio, N1_Template, N5_Weighted, N5_Trimmed, N5_WeightedTrimmed]


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION
# ═══════════════════════════════════════════════════════════════════════════

def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    return summary, daily


def run_blind_nowcast(summary, daily, test_years=(2024, 2025)):
    """Mode B blind nowcast for each model variant."""
    s = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    all_results = []

    for test_year in test_years:
        train = s[s['tournament_year'] < test_year].copy()
        test = s[s['tournament_year'] == test_year].copy()
        train_daily = daily[daily['tid'].isin(train['tid'])].copy()
        test_daily = daily[daily['tid'].isin(test['tid'])].copy()

        if len(test) == 0 or len(train) == 0:
            continue

        for ModelClass in ALL_MODELS:
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
                yr = row['tournament_year']

                tid_daily = test_daily[test_daily['tid'] == tid].sort_values('T', ascending=False)
                if len(tid_daily) < 5:
                    continue

                for T_chop in CHOP_POINTS:
                    regs = tid_daily[tid_daily['T'] >= T_chop]
                    if len(regs) == 0:
                        continue
                    current_count = int(regs['cum_regs'].max())
                    if current_count == 0:
                        continue

                    try:
                        pred, lower, upper = model.predict_nowcast(
                            current_count, T_chop, family, year=yr
                        )
                        if pred is None:
                            continue
                    except Exception:
                        continue

                    ape = abs(pred - actual) / max(actual, 1) * 100
                    covered = (lower <= actual <= upper) if (lower is not None and upper is not None) else False

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
                    })

    return pd.DataFrame(all_results)


def run_chicago_loo(summary, daily):
    """Chicago Open leave-one-out test."""
    s = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    chicago = s[s['family'] == 'Chicago Open'].copy()
    all_others = s[s['family'] != 'Chicago Open'].copy()
    all_results = []

    for _, leave_out_row in chicago.iterrows():
        leave_out_tid = leave_out_row['tid']
        leave_out_year = leave_out_row['tournament_year']
        actual = leave_out_row['final_count']

        train_chicago = chicago[chicago['tournament_year'] < leave_out_year]
        train = pd.concat([all_others[all_others['tournament_year'] < leave_out_year], train_chicago])
        train_daily = daily[daily['tid'].isin(train['tid'])].copy()

        test_daily = daily[daily['tid'] == leave_out_tid].sort_values('T', ascending=False)
        if len(test_daily) < 5:
            continue

        for ModelClass in ALL_MODELS:
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

                try:
                    pred, lower, upper = model.predict_nowcast(
                        current_count, T_chop, 'Chicago Open', year=leave_out_year
                    )
                    if pred is None:
                        continue
                except Exception:
                    continue

                ape = abs(pred - actual) / max(actual, 1) * 100
                covered = (lower <= actual <= upper) if (lower is not None and upper is not None) else False

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

def report(nowcast_results, chicago_results):
    """Print comparison tables."""

    print("\n" + "=" * 70)
    print("OVERALL NOWCAST PERFORMANCE (2024-2025)")
    print("=" * 70)

    if len(nowcast_results) > 0:
        overall = nowcast_results.groupby('model').agg(
            n=('APE', 'size'),
            MAPE=('APE', 'mean'),
            Median_APE=('APE', 'median'),
            Within_10=('APE', lambda x: (x <= 10).mean() * 100),
            Coverage_80=('covered', lambda x: x.mean() * 100),
        ).round(1).sort_values('MAPE')
        print(overall.to_string())

        print("\n\nMAPE BY CHOP POINT:")
        pivot = nowcast_results.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
        pivot = pivot[sorted(pivot.columns, reverse=True)]
        print(pivot.to_string())

        print("\n\nCOVERAGE BY CHOP POINT:")
        cov = nowcast_results.groupby(['model', 'T_chop'])['covered'].mean().unstack(fill_value=np.nan).round(2)
        cov = cov[sorted(cov.columns, reverse=True)]
        print(cov.to_string())

    print("\n" + "=" * 70)
    print("CHICAGO OPEN LEAVE-ONE-OUT")
    print("=" * 70)

    if len(chicago_results) > 0:
        chi_overall = chicago_results.groupby('model').agg(
            n=('APE', 'size'),
            MAPE=('APE', 'mean'),
            Median_APE=('APE', 'median'),
            Coverage_80=('covered', lambda x: x.mean() * 100),
        ).round(1).sort_values('MAPE')
        print(chi_overall.to_string())

        print("\n\nChicago Open MAPE by Chop Point:")
        chi_pivot = chicago_results.groupby(['model', 'T_chop'])['APE'].mean().unstack(fill_value=np.nan).round(1)
        chi_pivot = chi_pivot[sorted(chi_pivot.columns, reverse=True)]
        print(chi_pivot.to_string())

    # Verify mathematical equivalence between Template and HistRatio
    print("\n" + "=" * 70)
    print("TEMPLATE vs RATIO EQUIVALENCE CHECK")
    print("=" * 70)
    if len(nowcast_results) > 0:
        template = nowcast_results[nowcast_results['model'] == 'N1_Template'][['tid', 'T_chop', 'predicted']].copy()
        ratio = nowcast_results[nowcast_results['model'] == 'N5_HistRatio (baseline)'][['tid', 'T_chop', 'predicted']].copy()
        merged = template.merge(ratio, on=['tid', 'T_chop'], suffixes=('_template', '_ratio'))
        if len(merged) > 0:
            diff = (merged['predicted_template'] - merged['predicted_ratio']).abs()
            pct_diff = (diff / merged['predicted_ratio'].clip(lower=1) * 100)
            print(f"  Mean absolute difference: {diff.mean():.1f} registrants")
            print(f"  Mean pct difference: {pct_diff.mean():.1f}%")
            print(f"  Max pct difference: {pct_diff.max():.1f}%")
            print(f"  Correlation: {merged['predicted_template'].corr(merged['predicted_ratio']):.4f}")
        else:
            print("  No overlapping predictions to compare.")


if __name__ == "__main__":
    print("Loading data...")
    summary, daily = load_data()

    print("Running blind nowcast tests (2024-2025)...")
    nowcast_results = run_blind_nowcast(summary, daily)

    print("Running Chicago Open leave-one-out...")
    chicago_results = run_chicago_loo(summary, daily)

    report(nowcast_results, chicago_results)
