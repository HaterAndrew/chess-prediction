"""The lognormal ratio model: build the count-at-T -> final multipliers, predict from them.

Extracted from 04d_website_data_v2.py (audit v3 T7) so it can be imported
without side effects. 04d is a script, not a module — its pipeline body runs at
import time and writes output/website_data.json. The window-engine grader needs
these two functions and nothing else, and grading a model should not rewrite the
site's data files as a side effect of importing it. 04d re-exports both names,
so its own call sites are unchanged.

This is the older of the two prediction engines. N5v4_Final.predict_nowcast
supersedes it for most of the site, but 04d still routes two paths through here:
the post-start online-registration window, and the fallback when predict_nowcast
declines to produce an estimate.
"""
import numpy as np
from scipy.stats import lognorm

# Lead times (days before event) at which count->final ratios are tabulated.
# T=0 is the event-start bucket the window engine depends on: the full
# count-at-start -> final multiplier, which implicitly includes on-site entries.
CHOP_POINTS = [120, 90, 60, 42, 28, 14, 7, 3, 1, 0]


def build_ratio_model(train_summary, train_daily, completed_tids=None):
    """Build historical ratio model with lognormal CIs.

    completed_tids (v5 Cat L): tids of COMPLETED current-year tournaments to
    admit alongside the pre-2026 corpus — the same rolling-retrain policy the
    main engine's fit() follows. Without it, no 2026 event can ever inform a
    2026 window prediction, which left this engine's 2026 coverage 27pp under
    its 2023-25 folds. Backtest folds (window_grading) deliberately do NOT
    pass it, so their train-on-<year cut stays leak-free.
    """
    year_ok = train_summary['tournament_year'] < 2026
    if completed_tids:
        year_ok = year_ok | train_summary['tid'].isin(completed_tids)
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False)) &
        year_ok
    ]

    ratios = {}  # family -> {T -> [ratio, ...]}
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


def ratio_observation_count(ratios):
    """How many ratio observations a built model actually holds.

    An empty model is not a weak model, it is an absent one:
    predict_with_lognormal_ci falls back to returning current_count with a
    zero-width CI, which scores as a confident, always-wrong prediction rather
    than as a missing one. Callers that backtest should check this and report
    the fold as ungraded. See window_grading.grade_window_engine.
    """
    if not ratios:
        return 0
    return sum(len(v) for fam in ratios.values() for v in fam.values())


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

    # Remove extreme outliers (>3 IQR)
    q1, q3 = np.percentile(ratio_list, [25, 75])
    iqr = q3 - q1
    filtered = [r for r in ratio_list if q1 - 3*iqr <= r <= q3 + 3*iqr]
    if len(filtered) < 2:
        filtered = ratio_list

    # Fit lognormal to filtered ratios
    log_ratios = np.log(filtered)
    mu = np.mean(log_ratios)
    sigma = max(np.std(log_ratios, ddof=1), 0.05)  # floor at 5% relative uncertainty

    # For families with few ratio observations, use global sigma as floor
    # For well-observed families (4+ ratios), trust the family-specific sigma
    n_ratios = len(filtered)
    if n_ratios < 4:
        global_ratios_at_T = ratios.get('__global__', {}).get(closest_T, [])
        if len(global_ratios_at_T) >= 5:
            global_sigma = max(np.std(np.log(global_ratios_at_T), ddof=1), 0.1)
        else:
            global_sigma = 0.3
        sigma = max(sigma, global_sigma * 0.5)

    # Point estimate: median of lognormal = exp(mu)
    median_ratio = np.exp(mu)

    # CI bounds
    alpha = (1 - ci_level) / 2
    lo_ratio = lognorm.ppf(alpha, s=sigma, scale=np.exp(mu))
    hi_ratio = lognorm.ppf(1 - alpha, s=sigma, scale=np.exp(mu))

    point = round(current_count * median_ratio)
    lo = round(current_count * lo_ratio)
    hi = round(current_count * hi_ratio)

    return max(point, current_count), max(lo, current_count), max(hi, point)
