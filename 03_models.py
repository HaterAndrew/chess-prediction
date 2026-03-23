"""
Phase 3: Model Bake-Off
All candidate models for Mode A (total count forecast) and Mode B (nowcast).
Each model class exposes:
  - fit(train_summary, train_daily)
  - predict_count(family, year, month) -> (point, lower, upper)  [Mode A]
  - predict_nowcast(current_count, days_remaining, family, features) -> (point, lower, upper)  [Mode B]
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression, ElasticNet
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import statsmodels.api as sm
import warnings
import pickle
import os

warnings.filterwarnings('ignore')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
T_GRID = np.arange(0, 121)


# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def build_mode_a_features(summary):
    """Build feature matrix for Mode A models from tournament summary."""
    df = summary.copy()
    df = df[df['tournament_year'].notna()].copy()

    # Lag features per family
    df = df.sort_values(['family', 'tournament_year'])
    df['lag1'] = df.groupby('family')['final_count'].shift(1)
    df['lag2'] = df.groupby('family')['final_count'].shift(2)
    df['rolling_3yr_mean'] = df.groupby('family')['final_count'].transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean()
    )

    # Family edition count (how many prior editions)
    df['family_edition_num'] = df.groupby('family').cumcount() + 1

    # COVID flag
    df['covid_flag'] = df['tournament_year'].isin([2020, 2021]).astype(int)

    # Month from tournament name or proxy (use last_reg month if available)
    df['month'] = pd.to_datetime(df['last_reg'], errors='coerce').dt.month
    # Fallback: try first_reg
    mask = df['month'].isna()
    df.loc[mask, 'month'] = pd.to_datetime(df.loc[mask, 'first_reg'], errors='coerce').dt.month
    df['month'] = df['month'].fillna(6).astype(int)  # default to June

    return df


def build_nowcast_snapshots(summary, daily, chop_points=None):
    """
    For each timestamped tournament, create training rows at various chop points.
    Each row: current_count, days_remaining, features -> final_count (target).
    """
    if chop_points is None:
        chop_points = [90, 60, 42, 28, 14, 7, 3, 1]

    rows = []
    for _, row in summary.iterrows():
        tid = row['tid']
        family = row['family']
        actual = row['final_count']
        year = row['tournament_year']

        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) < 5:
            continue

        for T_chop in chop_points:
            regs = tid_daily[tid_daily['T'] >= T_chop]
            if len(regs) == 0:
                continue
            current_count = int(regs['cum_regs'].max())
            if current_count == 0:
                continue

            # Features from the registration curve up to chop point
            recent_7d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 7)]
            recent_3d = tid_daily[(tid_daily['T'] >= T_chop) & (tid_daily['T'] < T_chop + 3)]
            rate_7d = recent_7d['daily_regs'].mean() if len(recent_7d) > 0 else 0
            rate_3d = recent_3d['daily_regs'].mean() if len(recent_3d) > 0 else 0

            # Early bird spike detection (was there a big day in T-55 to T-75?)
            eb_window = tid_daily[(tid_daily['T'] >= 55) & (tid_daily['T'] <= 75)]
            spike_detected = 0
            if len(eb_window) > 0:
                baseline = tid_daily[(tid_daily['T'] >= 76) & (tid_daily['T'] <= 90)]
                baseline_rate = baseline['daily_regs'].median() if len(baseline) > 0 else 1
                if baseline_rate < 1:
                    baseline_rate = 1
                if eb_window['daily_regs'].max() / baseline_rate >= 5:
                    spike_detected = 1

            rows.append({
                'tid': tid,
                'family': family,
                'year': year,
                'T_chop': T_chop,
                'current_count': current_count,
                'days_remaining': T_chop,
                'rate_7d': rate_7d,
                'rate_3d': rate_3d,
                'spike_detected': spike_detected,
                'actual': actual,
            })

    return pd.DataFrame(rows)


def build_template_curves(summary, daily):
    """Build family template curves from given data."""
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


def build_historical_ratios(summary, daily, chop_points=None):
    """
    For each family, compute historical final_count / count_at_T ratios.
    Returns dict: family -> {T -> list of ratios}
    """
    if chop_points is None:
        chop_points = [90, 60, 42, 28, 14, 7, 3, 1]

    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False))
    ]

    ratios = {}  # family -> {T -> [ratio1, ratio2, ...]}
    global_ratios = {}  # T -> [ratios across all families]

    for _, row in valid.iterrows():
        tid = row['tid']
        family = row['family']
        actual = row['final_count']

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
            ratios[family].setdefault(T, []).append(ratio)
            global_ratios.setdefault(T, []).append(ratio)

    ratios['__global__'] = global_ratios
    return ratios


# ═══════════════════════════════════════════════════════════════════════════
# MODE A MODELS — Total Count Forecast (no registration data)
# ═══════════════════════════════════════════════════════════════════════════

class M1_NaiveBaseline:
    """M1a: same as last year, M1b: 3-yr rolling mean, M1c: global median."""
    name = "M1_Naive"

    def fit(self, summary, daily=None):
        self.summary = build_mode_a_features(summary)
        self.global_median = summary['final_count'].median()

    def predict_count(self, family, year, month=None):
        fam = self.summary[self.summary['family'] == family].sort_values('tournament_year')
        if len(fam) == 0:
            p = self.global_median
            return p, p * 0.5, p * 1.5

        last = fam.iloc[-1]

        # M1a: same as last year
        pred_a = last['final_count']

        # M1b: 3-yr rolling mean
        recent = fam.tail(3)['final_count']
        pred_b = recent.mean()

        # Blend: use rolling mean as point, last year for reference
        point = pred_b
        spread = max(fam['final_count'].std(), point * 0.1)
        return round(point), round(point - 1.28 * spread), round(point + 1.28 * spread)


class M2_LinearRegression:
    """OLS with family effects."""
    name = "M2_OLS"

    def fit(self, summary, daily=None):
        df = build_mode_a_features(summary)
        df = df[~df['is_online'].fillna(False)]
        df = df.dropna(subset=['lag1'])

        self.le = LabelEncoder()
        df['family_enc'] = self.le.fit_transform(df['family'])
        self.families = set(df['family'])

        features = ['family_enc', 'tournament_year', 'month', 'covid_flag', 'lag1', 'lag2',
                    'rolling_3yr_mean', 'family_edition_num']
        df = df.dropna(subset=features)

        X = df[features].values
        y = df['final_count'].values

        self.model = LinearRegression()
        self.model.fit(X, y)
        self.features = features
        self.train_df = df
        self.residual_std = np.std(y - self.model.predict(X))

    def predict_count(self, family, year, month=6):
        if family not in self.families:
            # Fallback to global mean
            p = self.train_df['final_count'].mean()
            return round(p), round(p * 0.5), round(p * 1.5)

        fam = self.train_df[self.train_df['family'] == family].sort_values('tournament_year')
        last = fam.iloc[-1] if len(fam) > 0 else None

        family_enc = self.le.transform([family])[0]
        lag1 = last['final_count'] if last is not None else self.train_df['final_count'].mean()
        lag2 = last['lag1'] if (last is not None and pd.notna(last.get('lag1'))) else lag1
        rolling = last['rolling_3yr_mean'] if (last is not None and pd.notna(last.get('rolling_3yr_mean'))) else lag1
        edition = (last['family_edition_num'] + 1) if last is not None else 1
        covid = 1 if year in [2020, 2021] else 0

        X = np.array([[family_enc, year, month, covid, lag1, lag2, rolling, edition]])
        pred = self.model.predict(X)[0]
        pred = max(pred, 5)

        return round(pred), round(pred - 1.28 * self.residual_std), round(pred + 1.28 * self.residual_std)


class M4_XGBoost:
    """Gradient Boosted Trees with quantile regression for CIs."""
    name = "M4_XGBoost"

    def fit(self, summary, daily=None):
        df = build_mode_a_features(summary)
        df = df[~df['is_online'].fillna(False)]
        df = df.dropna(subset=['lag1'])

        self.le = LabelEncoder()
        df['family_enc'] = self.le.fit_transform(df['family'])
        self.families = set(df['family'])

        features = ['family_enc', 'tournament_year', 'month', 'covid_flag', 'lag1', 'lag2',
                    'rolling_3yr_mean', 'family_edition_num']
        df = df.dropna(subset=features)

        X = df[features].values
        y = df['final_count'].values

        # Point estimate model
        self.model = xgb.XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            reg_alpha=1, reg_lambda=1, random_state=42
        )
        self.model.fit(X, y)

        # Lower quantile
        self.model_low = xgb.XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            objective='reg:quantileerror', quantile_alpha=0.1, random_state=42
        )
        self.model_low.fit(X, y)

        # Upper quantile
        self.model_high = xgb.XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            objective='reg:quantileerror', quantile_alpha=0.9, random_state=42
        )
        self.model_high.fit(X, y)

        self.features = features
        self.train_df = df

    def predict_count(self, family, year, month=6):
        if family not in self.families:
            p = self.train_df['final_count'].mean()
            return round(p), round(p * 0.5), round(p * 1.5)

        fam = self.train_df[self.train_df['family'] == family].sort_values('tournament_year')
        last = fam.iloc[-1] if len(fam) > 0 else None

        family_enc = self.le.transform([family])[0]
        lag1 = last['final_count'] if last is not None else self.train_df['final_count'].mean()
        lag2 = last['lag1'] if (last is not None and pd.notna(last.get('lag1'))) else lag1
        rolling = last['rolling_3yr_mean'] if (last is not None and pd.notna(last.get('rolling_3yr_mean'))) else lag1
        edition = (last['family_edition_num'] + 1) if last is not None else 1
        covid = 1 if year in [2020, 2021] else 0

        X = np.array([[family_enc, year, month, covid, lag1, lag2, rolling, edition]])
        pred = max(self.model.predict(X)[0], 5)
        low = max(self.model_low.predict(X)[0], 1)
        high = max(self.model_high.predict(X)[0], pred)

        return round(pred), round(low), round(high)


class M5_RandomForest:
    """Random Forest with prediction intervals from tree variance."""
    name = "M5_RF"

    def fit(self, summary, daily=None):
        df = build_mode_a_features(summary)
        df = df[~df['is_online'].fillna(False)]
        df = df.dropna(subset=['lag1'])

        self.le = LabelEncoder()
        df['family_enc'] = self.le.fit_transform(df['family'])
        self.families = set(df['family'])

        features = ['family_enc', 'tournament_year', 'month', 'covid_flag', 'lag1', 'lag2',
                    'rolling_3yr_mean', 'family_edition_num']
        df = df.dropna(subset=features)

        X = df[features].values
        y = df['final_count'].values

        self.model = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42)
        self.model.fit(X, y)
        self.features = features
        self.train_df = df

    def predict_count(self, family, year, month=6):
        if family not in self.families:
            p = self.train_df['final_count'].mean()
            return round(p), round(p * 0.5), round(p * 1.5)

        fam = self.train_df[self.train_df['family'] == family].sort_values('tournament_year')
        last = fam.iloc[-1] if len(fam) > 0 else None

        family_enc = self.le.transform([family])[0]
        lag1 = last['final_count'] if last is not None else self.train_df['final_count'].mean()
        lag2 = last['lag1'] if (last is not None and pd.notna(last.get('lag1'))) else lag1
        rolling = last['rolling_3yr_mean'] if (last is not None and pd.notna(last.get('rolling_3yr_mean'))) else lag1
        edition = (last['family_edition_num'] + 1) if last is not None else 1
        covid = 1 if year in [2020, 2021] else 0

        X = np.array([[family_enc, year, month, covid, lag1, lag2, rolling, edition]])

        # Get predictions from individual trees for CI
        tree_preds = np.array([t.predict(X)[0] for t in self.model.estimators_])
        pred = np.mean(tree_preds)
        low = np.percentile(tree_preds, 10)
        high = np.percentile(tree_preds, 90)

        return round(max(pred, 5)), round(max(low, 1)), round(max(high, pred))


class M6_NegBinGLM:
    """Negative Binomial GLM for count data."""
    name = "M6_NegBin"

    def fit(self, summary, daily=None):
        df = build_mode_a_features(summary)
        df = df[~df['is_online'].fillna(False)]
        df = df.dropna(subset=['lag1'])
        df = df[df['final_count'] > 0]

        self.le = LabelEncoder()
        df['family_enc'] = self.le.fit_transform(df['family'])
        self.families = set(df['family'])

        features = ['family_enc', 'tournament_year', 'month', 'covid_flag', 'lag1',
                    'rolling_3yr_mean']
        df = df.dropna(subset=features)

        X = sm.add_constant(df[features].values.astype(float))
        y = df['final_count'].values.astype(float)

        try:
            self.model = sm.GLM(y, X, family=sm.families.NegativeBinomial()).fit(disp=False)
            self.fitted = True
        except Exception:
            self.fitted = False

        self.features = features
        self.train_df = df

    def predict_count(self, family, year, month=6):
        if not self.fitted or family not in self.families:
            p = self.train_df['final_count'].mean()
            return round(p), round(p * 0.5), round(p * 1.5)

        fam = self.train_df[self.train_df['family'] == family].sort_values('tournament_year')
        last = fam.iloc[-1] if len(fam) > 0 else None

        family_enc = self.le.transform([family])[0]
        lag1 = last['final_count'] if last is not None else self.train_df['final_count'].mean()
        rolling = last['rolling_3yr_mean'] if (last is not None and pd.notna(last.get('rolling_3yr_mean'))) else lag1
        covid = 1 if year in [2020, 2021] else 0

        X = np.array([[1, family_enc, year, month, covid, lag1, rolling]])
        try:
            pred_obj = self.model.get_prediction(X)
            pred = pred_obj.predicted_mean[0]
            ci = pred_obj.conf_int(alpha=0.2)  # 80% CI
            return round(max(pred, 5)), round(max(ci[0][0], 1)), round(max(ci[0][1], pred))
        except Exception:
            pred = max(self.model.predict(X)[0], 5)
            return round(pred), round(pred * 0.7), round(pred * 1.3)


# ═══════════════════════════════════════════════════════════════════════════
# MODE B MODELS — Nowcast (given current registrations)
# ═══════════════════════════════════════════════════════════════════════════

class N1_TemplateCurve:
    """Simple template curve divider: predicted = current / median_pct_at_T."""
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

        return round(point), round(current_count / high_pct), round(current_count / low_pct)


class N3_XGBoostNowcast:
    """XGBoost trained on snapshot features."""
    name = "N3_XGB_Nowcast"

    def fit(self, summary, daily):
        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ]
        snapshots = build_nowcast_snapshots(valid, daily)
        if len(snapshots) == 0:
            self.fitted = False
            return

        self.le = LabelEncoder()
        snapshots['family_enc'] = self.le.fit_transform(snapshots['family'])
        self.families = set(snapshots['family'])

        features = ['current_count', 'days_remaining', 'rate_7d', 'rate_3d',
                    'spike_detected', 'family_enc', 'year']
        X = snapshots[features].values
        y = snapshots['actual'].values

        self.model = xgb.XGBRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            reg_alpha=1, reg_lambda=1, random_state=42
        )
        self.model.fit(X, y)

        self.model_low = xgb.XGBRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            objective='reg:quantileerror', quantile_alpha=0.1, random_state=42
        )
        self.model_low.fit(X, y)

        self.model_high = xgb.XGBRegressor(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            objective='reg:quantileerror', quantile_alpha=0.9, random_state=42
        )
        self.model_high.fit(X, y)

        self.features = features
        self.fitted = True

    def predict_nowcast(self, current_count, days_remaining, family, rate_7d=0, rate_3d=0,
                        spike_detected=0, year=2025, **kwargs):
        if not self.fitted:
            return None, None, None

        if family in self.families:
            family_enc = self.le.transform([family])[0]
        else:
            family_enc = 0

        X = np.array([[current_count, days_remaining, rate_7d, rate_3d,
                       spike_detected, family_enc, year]])

        pred = max(self.model.predict(X)[0], current_count)
        low = max(self.model_low.predict(X)[0], current_count)
        high = max(self.model_high.predict(X)[0], pred)

        return round(pred), round(low), round(high)


class N5_HistoricalRatio:
    """Historical ratio model: predicted = current * median_ratio_at_T."""
    name = "N5_HistRatio"

    def fit(self, summary, daily):
        self.ratios = build_historical_ratios(summary, daily)

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        fam_ratios = self.ratios.get(family, self.ratios.get('__global__', {}))
        if not fam_ratios:
            fam_ratios = self.ratios.get('__global__', {})

        # Find closest chop point
        available_T = sorted(fam_ratios.keys())
        if not available_T:
            return None, None, None

        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        ratio_list = fam_ratios[closest_T]

        if not ratio_list:
            return None, None, None

        median_ratio = np.median(ratio_list)
        point = current_count * median_ratio

        if len(ratio_list) >= 3:
            low_ratio = np.percentile(ratio_list, 10)
            high_ratio = np.percentile(ratio_list, 90)
        else:
            low_ratio = min(ratio_list) * 0.9
            high_ratio = max(ratio_list) * 1.1

        low = current_count * low_ratio
        high = current_count * high_ratio

        return round(max(point, current_count)), round(max(low, current_count)), round(max(high, point))


class N6_ElasticNetNowcast:
    """Elastic Net on curve features."""
    name = "N6_ElasticNet"

    def fit(self, summary, daily):
        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ]
        snapshots = build_nowcast_snapshots(valid, daily)
        if len(snapshots) == 0:
            self.fitted = False
            return

        # Additional features
        # Family historical mean
        fam_means = valid.groupby('family')['final_count'].mean().to_dict()
        snapshots['family_mean'] = snapshots['family'].map(fam_means).fillna(valid['final_count'].mean())
        snapshots['pct_of_family_mean'] = snapshots['current_count'] / snapshots['family_mean'].clip(lower=1)

        features = ['current_count', 'days_remaining', 'rate_7d', 'rate_3d',
                    'spike_detected', 'pct_of_family_mean']
        X = snapshots[features].values
        y = snapshots['actual'].values

        self.model = ElasticNet(alpha=1.0, l1_ratio=0.5, random_state=42, max_iter=10000)
        self.model.fit(X, y)

        self.residual_std = np.std(y - self.model.predict(X))
        self.features = features
        self.fam_means = fam_means
        self.global_mean = valid['final_count'].mean()
        self.fitted = True

    def predict_nowcast(self, current_count, days_remaining, family, rate_7d=0, rate_3d=0,
                        spike_detected=0, **kwargs):
        if not self.fitted:
            return None, None, None

        fam_mean = self.fam_means.get(family, self.global_mean)
        pct = current_count / max(fam_mean, 1)

        X = np.array([[current_count, days_remaining, rate_7d, rate_3d, spike_detected, pct]])
        pred = max(self.model.predict(X)[0], current_count)
        low = pred - 1.28 * self.residual_std
        high = pred + 1.28 * self.residual_std

        return round(max(pred, current_count)), round(max(low, current_count)), round(high)


# ═══════════════════════════════════════════════════════════════════════════
# MODEL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

MODE_A_MODELS = [M1_NaiveBaseline, M2_LinearRegression, M4_XGBoost, M5_RandomForest, M6_NegBinGLM]
MODE_B_MODELS = [N1_TemplateCurve, N3_XGBoostNowcast, N5_HistoricalRatio, N6_ElasticNetNowcast]


if __name__ == "__main__":
    # Quick smoke test
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))

    print("=== Mode A Smoke Tests ===")
    for ModelClass in MODE_A_MODELS:
        m = ModelClass()
        try:
            m.fit(summary, daily)
            pred = m.predict_count('Chicago Open', 2025, 5)
            print(f"  {m.name}: Chicago Open 2025 -> {pred}")
        except Exception as e:
            print(f"  {m.name}: FAILED - {e}")

    print("\n=== Mode B Smoke Tests ===")
    for ModelClass in MODE_B_MODELS:
        m = ModelClass()
        try:
            m.fit(summary, daily)
            pred = m.predict_nowcast(300, 28, 'Chicago Open', rate_7d=10, rate_3d=15)
            print(f"  {m.name}: Chicago Open at T-28 with 300 regs -> {pred}")
        except Exception as e:
            print(f"  {m.name}: FAILED - {e}")
