"""
Phase 4D: Clean website data generation.
Fix status detection, filter to main events, correct predictions.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
from scipy.stats import lognorm  # used by legacy predict_with_lognormal_ci fallback
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m04c = import_module("04c_final_model")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [120, 90, 60, 42, 28, 14, 7, 3, 1, 0]
T_GRID = np.arange(0, 121)
TODAY = pd.Timestamp('2026-03-23')

# Load data
summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
meta = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_metadata.csv"))
meta['start_date'] = pd.to_datetime(meta['start_date'])

# Filter exclusions: online, COVID, sub-events we don't want
EXCLUDE_FAMILIES = [
    # World Open sub-events (combined into "World Open" entry)
    'World Open  lower sections', 'World Open  top 6 sections',
    # Tiny side events with 1-6 registrants, not real tournaments
    'George Washington Saturday Octos', 'George Washington Sunday Octos',
    'World Open G 50 Championship',
]

# Exclude all blitz events
blitz_families = summary[summary['family'].str.contains('Blitz|blitz', na=False, regex=True)]['family'].unique().tolist()
EXCLUDE_FAMILIES.extend(blitz_families)
print(f"Excluding {len(blitz_families)} blitz families")

# ── Build ratio model (same as N5 but with lognormal CIs) ──

def build_ratio_model(train_summary, train_daily):
    """Build historical ratio model with lognormal CIs."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False))
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


# ── Build template curves ──

def build_template_curves(train_summary, train_daily):
    """Build median cumulative curves per family."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False))
    ]

    curves = {}
    for family in valid['family'].unique():
        ftids = valid[valid['family'] == family]['tid'].values
        if len(ftids) < 2:
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
            curves[family] = {t: np.median(curves_at_T.get(t, [0])) for t in T_GRID}

    # Global fallback
    all_at_T = {}
    for tid in valid['tid'].values:
        ed = train_daily[train_daily['tid'] == tid].sort_values('T')
        if len(ed) < 5:
            continue
        try:
            fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                         bounds_error=False, fill_value=(1.0, 0.0))
            for t in T_GRID:
                all_at_T.setdefault(t, []).append(float(fi(t)))
        except Exception:
            continue
    curves['__global__'] = {t: np.median(all_at_T.get(t, [0])) for t in T_GRID}

    return curves


# ── Determine tournament status ──

def get_event_date(family, year):
    """Get event start date from metadata, or estimate from historical data."""
    match = meta[(meta['family'] == family) & (meta['year'] == year)]
    if len(match) > 0:
        return match.iloc[0]['start_date']

    # Estimate from historical last_reg dates for this family
    fam = summary[(summary['family'] == family) & (~summary['is_online'].fillna(False))]
    hist_dates = pd.to_datetime(fam['last_reg'], errors='coerce').dropna()
    if len(hist_dates) > 0:
        avg_month = int(hist_dates.dt.month.median())
        avg_day = int(hist_dates.dt.day.median())
        try:
            return pd.Timestamp(year, avg_month, avg_day)
        except:
            pass
    return None


def determine_status(row, event_date):
    """Determine if tournament is live, upcoming, or complete."""
    if event_date is None:
        return 'unknown'

    if event_date <= TODAY:
        return 'complete'
    else:
        return 'live'


# ── Build website data ──

print("Building website data...")

# Use all non-COVID, non-online data for training
train = summary[
    (~summary['is_online'].fillna(False)) &
    (~summary['is_covid'].fillna(False))
]
train_ts = train[train['has_timestamps']]

# Use production model (N5v4_Final) with all fixes:
# - proper prediction intervals, empirical Bayes shrinkage
# - expanding-window calibration, T-interpolation
prod_model = m04c.N5v4_Final()
prod_model.fit(train_ts, daily)

ratios = build_ratio_model(train, daily)  # kept for families without timestamps
curves = build_template_curves(train, daily)

# ── Combine all World Open sub-events into "World Open" per year ──
# Aggregate all non-blitz World Open families into a single entry per year
wo_all = summary[
    (summary['family'].str.startswith('World Open')) &
    (~summary['family'].str.contains('Blitz', case=False, na=False)) &
    (~summary['is_online'].fillna(False)) &
    (summary['family'] != 'World Open')  # keep existing "World Open" rows as-is
]

wo_sub_families = wo_all['family'].unique().tolist()
print(f"Combining {len(wo_sub_families)} World Open sub-families into 'World Open'")

for yr in wo_all['tournament_year'].dropna().unique():
    yr_subs = wo_all[wo_all['tournament_year'] == yr]
    if len(yr_subs) == 0:
        continue
    combined_count = yr_subs['final_count'].sum()
    # Check if a "World Open" row already exists for this year
    existing_wo = summary[(summary['family'] == 'World Open') & (summary['tournament_year'] == yr)]
    if len(existing_wo) > 0:
        # Add sub-event counts to existing World Open row
        summary.loc[existing_wo.index[0], 'final_count'] += combined_count
    else:
        # Create new combined row
        wo_row = yr_subs.iloc[0].copy()
        wo_row['family'] = 'World Open'
        wo_row['final_count'] = combined_count
        summary = pd.concat([summary, pd.DataFrame([wo_row])], ignore_index=True)

    # Combine daily data
    sub_tids = yr_subs['tid'].values
    # Also include main World Open tid if it exists
    if len(existing_wo) > 0:
        main_tid = existing_wo.iloc[0]['tid']
        all_tids = list(sub_tids) + [main_tid]
        rep_tid = main_tid
    else:
        all_tids = list(sub_tids)
        rep_tid = sub_tids[0]

    sub_daily = daily[daily['tid'].isin(all_tids)]
    if len(sub_daily) > 0:
        agg = sub_daily.groupby('T').agg({'cum_regs': 'sum'}).reset_index()
        agg['tid'] = rep_tid
        max_regs = agg['cum_regs'].max()
        agg['cum_pct'] = agg['cum_regs'] / max_regs if max_regs > 0 else 0
        daily = pd.concat([daily[~daily['tid'].isin(all_tids)], agg], ignore_index=True)

# Remove all sub-event rows from summary (keep only "World Open")
summary = summary[~summary['family'].isin(wo_sub_families)]
# Also add sub-families to exclude list so they don't appear separately
EXCLUDE_FAMILIES.extend(wo_sub_families)
print(f"World Open combined across all years")

# Get 2026 tournaments
t2026 = summary[
    (summary['tournament_year'] == 2026) &
    (~summary['is_online'].fillna(False)) &
    (~summary['family'].isin(EXCLUDE_FAMILIES))
].copy()

print(f"Found {len(t2026)} 2026 tournaments (after filtering)")

tournaments_out = []

for _, row in t2026.iterrows():
    family = row['family']
    tid = row['tid']
    current_count = row['final_count']

    # Skip tiny sub-events and low-value entries
    if current_count < 1:
        continue
    # Skip completed tournaments with very few registrations (likely sub-events or data issues)
    hist_check = summary[
        (summary['family'] == family) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ]
    if current_count < 10 and len(hist_check) == 0:
        continue

    event_date = get_event_date(family, 2026)
    status = determine_status(row, event_date)

    if event_date is not None:
        days_remaining = max((event_date - TODAY).days, 0)
    else:
        days_remaining = 60

    # Exclude tournaments too far out — predictions are meaningless with 1-3 registrants
    if days_remaining > 250:
        continue

    # Convert days_to_start to days_to_end (T in training coordinates)
    # Training T is relative to last_reg/event_end, not event_start
    m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
    if len(m_row) > 0 and pd.notna(m_row.iloc[0].get('end_date')):
        event_end = pd.to_datetime(m_row.iloc[0]['end_date'])
        days_to_end = max((event_end - TODAY).days, 0)
    else:
        # Estimate: typical tournament is ~4 days
        days_to_end = days_remaining + 4

    # Get metadata
    m = meta[(meta['family'] == family) & (meta['year'] == 2026)]
    eb_deadline = m.iloc[0]['early_bird_deadline'] if len(m) > 0 else None
    eb_fee = float(m.iloc[0]['early_bird_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_fee')) else None
    reg_fee = float(m.iloc[0]['regular_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('regular_fee')) else None
    onsite_fee = float(m.iloc[0]['onsite_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('onsite_fee')) else None

    # Historical data (needed for guardrails and output)
    # Include alias families for tournaments with no direct history
    families_to_search = [family]
    if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
        families_to_search.extend(m04c.FAMILY_ALIASES[family])
    hist = summary[
        (summary['family'].isin(families_to_search)) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ].sort_values('tournament_year')
    historical = [{"year": int(h['tournament_year']), "count": int(h['final_count']),
                   "family": h['family']}
                  for _, h in hist.iterrows()]

    # Predictions — use production model with guardrails
    hist_counts = [h['count'] for h in historical]
    if status == 'complete':
        point, ci_lo, ci_hi = current_count, current_count, current_count
    elif status == 'live' and days_remaining > 0:
        # Guardrail: don't trust ratio-based predictions with < 10 regs
        # and > 60 days out — fall back to historical average
        if current_count < 10 and days_remaining > 60 and len(hist_counts) >= 1:
            hist_med = int(np.median(hist_counts))
            point = hist_med
            ci_lo = int(np.percentile(hist_counts, 10)) if len(hist_counts) >= 5 else int(hist_med * 0.7)
            ci_hi = int(np.percentile(hist_counts, 90)) if len(hist_counts) >= 5 else int(hist_med * 1.3)
        else:
            point, ci_lo, ci_hi = prod_model.predict_nowcast(current_count, days_to_end, family)
            if point is None:
                point, ci_lo, ci_hi = predict_with_lognormal_ci(current_count, days_to_end, family, ratios)

        # Plausibility check against historical range
        if len(hist_counts) >= 1:
            hist_min = min(hist_counts)
            hist_max = max(hist_counts)
            hist_med = int(np.median(hist_counts))
            hist_p25 = int(np.percentile(hist_counts, 25))
            # Far out + low prediction: ratio model unreliable, use historical median
            if days_remaining > 60 and point < hist_p25:
                point = hist_med
                ci_lo = int(np.percentile(hist_counts, 10)) if len(hist_counts) >= 5 else int(hist_med * 0.7)
                ci_hi = int(np.percentile(hist_counts, 90)) if len(hist_counts) >= 5 else int(hist_med * 1.3)
            elif point < hist_min * 0.5:
                # Prediction unreasonably low — use historical median
                point = hist_med
                ci_lo = int(np.percentile(hist_counts, 10)) if len(hist_counts) >= 5 else int(hist_med * 0.7)
                ci_hi = int(np.percentile(hist_counts, 90)) if len(hist_counts) >= 5 else int(hist_med * 1.3)
            elif point > hist_max * 3.0:
                point = int(hist_max * 1.5)
                ci_hi = min(ci_hi, int(hist_max * 2.5))
    else:
        point, ci_lo, ci_hi = current_count, current_count, current_count

    # Daily data for chart
    tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(tid_daily) > 0:
        # Convert T (days before event) to days from first registration
        max_T = tid_daily['T'].max()
        daily_data = []
        for _, d in tid_daily.iterrows():
            day_from_start = int(max_T - d['T'])
            daily_data.append([day_from_start, int(d['cum_regs'])])
        daily_data.sort(key=lambda x: x[0])
    else:
        daily_data = [[0, current_count]]

    # Registration curve (template)
    curve = curves.get(family, curves.get('__global__', {}))
    reg_curve = []
    for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
        pct = curve.get(db, 0)
        reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})

    # Fix known typos in family names
    display_family = family

    t_out = {
        "family": display_family,
        "year": 2026,
        "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
        "event_end": None,
        "early_bird_deadline": str(eb_deadline)[:10] if eb_deadline else None,
        "early_bird_fee": eb_fee,
        "regular_fee": reg_fee,
        "onsite_fee": onsite_fee,
        "current_count": int(current_count),
        "days_remaining": int(days_remaining),
        "point_estimate": int(point),
        "ci_lower": int(ci_lo),
        "ci_upper": int(ci_hi),
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": daily_data,
        "registration_curve": reg_curve,
        "status": status,
    }

    # Add event_end from metadata
    if len(m) > 0 and pd.notna(m.iloc[0].get('end_date')):
        t_out['event_end'] = str(m.iloc[0]['end_date'])[:10]

    tournaments_out.append(t_out)

# Add tournaments from metadata that have no registrations yet
existing_families = {t['family'] for t in tournaments_out}
for _, mrow in meta[meta['year'] == 2026].iterrows():
    mfamily = mrow['family']
    if mfamily in existing_families or mfamily in EXCLUDE_FAMILIES:
        continue
    event_date = pd.to_datetime(mrow['start_date'])
    if event_date <= TODAY:
        continue
    days_remaining = (event_date - TODAY).days
    if days_remaining > 300:
        continue
    # Historical data
    hist = summary[
        (summary['family'] == mfamily) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ].sort_values('tournament_year')
    historical = [{"year": int(h['tournament_year']), "count": int(h['final_count'])}
                  for _, h in hist.iterrows()]
    # Predict from historical mean
    hist_mean = np.mean([h['count'] for h in historical]) if historical else 100
    curve = curves.get(mfamily, curves.get('__global__', {}))
    reg_curve = []
    for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
        pct = curve.get(db, 0)
        reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})
    eb_deadline = mrow.get('early_bird_deadline')
    eb_fee = float(mrow['early_bird_fee']) if pd.notna(mrow.get('early_bird_fee')) else None
    reg_fee = float(mrow['regular_fee']) if pd.notna(mrow.get('regular_fee')) else None
    onsite_fee = float(mrow['onsite_fee']) if pd.notna(mrow.get('onsite_fee')) else None
    t_out = {
        "family": mfamily,
        "year": 2026,
        "event_start": event_date.strftime('%Y-%m-%d'),
        "event_end": str(mrow['end_date'])[:10] if pd.notna(mrow.get('end_date')) else None,
        "early_bird_deadline": str(eb_deadline)[:10] if pd.notna(eb_deadline) else None,
        "early_bird_fee": eb_fee,
        "regular_fee": reg_fee,
        "onsite_fee": onsite_fee,
        "current_count": 0,
        "days_remaining": int(days_remaining),
        "point_estimate": int(hist_mean),
        "ci_lower": int(hist_mean * 0.7),
        "ci_upper": int(hist_mean * 1.3),
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": [[0, 0]],
        "registration_curve": reg_curve,
        "status": "live",
    }
    tournaments_out.append(t_out)
    print(f"  Added from metadata: {mfamily} (event {event_date.strftime('%Y-%m-%d')}, {days_remaining} days out)")

# ── Add ALL historical tournament editions ──
# Every individual edition (non-online, non-covid, >=10 entries) gets its own entry
existing_tids = set()
for t in tournaments_out:
    # Track 2026 families to avoid duplicating them
    existing_tids.add(t.get('_tid'))

historical_valid = summary[
    (~summary['is_online'].fillna(False)) &
    (~summary['is_covid'].fillna(False)) &
    (summary['final_count'] >= 10) &
    (~summary['family'].isin(EXCLUDE_FAMILIES)) &
    (summary['tournament_year'] < 2026) &
    (summary['tournament_year'] >= 2015)
].sort_values(['family', 'tournament_year'])

print(f"\nAdding {len(historical_valid)} historical editions...")

for _, row in historical_valid.iterrows():
    family = row['family']
    tid = row['tid']
    yr = int(row['tournament_year'])
    count = int(row['final_count'])
    display_family = family

    # Get event date
    event_date = get_event_date(family, yr)

    # Same-family history
    hist = historical_valid[
        (historical_valid['family'] == family) &
        (historical_valid['tournament_year'] <= yr)
    ].sort_values('tournament_year')
    historical = [{"year": int(h['tournament_year']), "count": int(h['final_count'])}
                  for _, h in hist.iterrows()]

    # Registration curve
    curve = curves.get(family, curves.get('__global__', {}))
    reg_curve = []
    for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
        pct = curve.get(db, 0)
        reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})

    # Daily data for this specific edition
    tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(tid_daily) > 0:
        max_T = tid_daily['T'].max()
        daily_data = []
        for _, d in tid_daily.iterrows():
            day_from_start = int(max_T - d['T'])
            daily_data.append([day_from_start, int(d['cum_regs'])])
        daily_data.sort(key=lambda x: x[0])
    else:
        daily_data = [[0, count]]

    t_out = {
        "family": display_family,
        "year": yr,
        "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
        "event_end": None,
        "early_bird_deadline": None,
        "early_bird_fee": None,
        "regular_fee": None,
        "onsite_fee": None,
        "current_count": count,
        "days_remaining": 0,
        "point_estimate": count,
        "ci_lower": count,
        "ci_upper": count,
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": daily_data,
        "registration_curve": reg_curve,
        "status": "historical",
    }
    tournaments_out.append(t_out)

# Sort: live first (by days_remaining desc), then 2026 complete, then historical
status_order = {'live': 0, 'complete': 1, 'historical': 2, 'unknown': 3}
tournaments_out.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

# Count by status
n_live = sum(1 for t in tournaments_out if t['status'] == 'live')
n_complete = sum(1 for t in tournaments_out if t['status'] == 'complete')
n_historical = sum(1 for t in tournaments_out if t['status'] == 'historical')

output = {
    "generated": "2026-03-23",
    "model": "N5v4_Final",
    "model_description": "Ensemble model (N5v4): historical ratio (harmonic mean) + per-family pooled Huber regression (final ~ count_at_T + T). T-dependent weights (ratio: 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). 80% CI from lognormal prediction intervals, LOO-calibrated with ensemble shrinkage. Empirical Bayes sigma shrinkage, T-interpolation, expanding-window calibration, and plausibility guardrails.",
    "tournaments": tournaments_out
}

# Print summary
print(f"\nGenerated {len(tournaments_out)} tournaments ({n_live} live, {n_complete} complete 2026, {n_historical} historical)")
for t in tournaments_out:
    ci = f"[{t['ci_lower']}, {t['ci_upper']}]"
    print(f"  {t['status']:12s} {t['family']:45s}  yr={t['year']}  count={t['current_count']:>5}  pred={t['point_estimate']:>5}  CI={ci:>15}  days={t['days_remaining']:>3}")

# Save
out_path = os.path.join(OUTPUT_DIR, "website_data.json")
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nSaved to {out_path}")
