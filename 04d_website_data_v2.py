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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m04c = import_module("04c_final_model")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [120, 90, 60, 42, 28, 14, 7, 3, 1, 0]
T_GRID = np.arange(0, 121)
TODAY = pd.Timestamp.now().normalize()

# Load data
summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
# Coerce tournament_year: fill NaN with 0, convert to int for clean comparisons
summary['tournament_year'] = pd.to_numeric(summary['tournament_year'], errors='coerce').fillna(0).astype(int)
daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
meta = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_metadata.csv"))
meta['start_date'] = pd.to_datetime(meta['start_date'])

# Merge fresh scrape data into summary for 2026 tournaments
# daily_scrape.csv has the latest entry counts from chessaction.com
# Use active_count (net of withdrawals) when available, fall back to entry_count
scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
if os.path.exists(scrape_path):
    scrape = pd.read_csv(scrape_path)
    scrape['date'] = pd.to_datetime(scrape['date'])
    # Backfill active_count for older rows that predate the withdrawal columns
    if 'active_count' not in scrape.columns:
        scrape['active_count'] = scrape['entry_count']
    else:
        scrape['active_count'] = scrape['active_count'].fillna(scrape['entry_count'])
    if 'withdrawal_count' not in scrape.columns:
        scrape['withdrawal_count'] = 0
    else:
        scrape['withdrawal_count'] = scrape['withdrawal_count'].fillna(0)
    # Get the most recent scrape per tournament
    latest_scrape = scrape.sort_values('date').groupby('tournament_name').last().reset_index()
    # Update 2026 tournament counts in summary using active (net) counts
    updated = 0
    for _, s in latest_scrape.iterrows():
        # Match by family name (strip year prefix "2026 " from scrape name)
        scrape_name = s['tournament_name']
        family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
        mask = (summary['family'] == family_name) & (summary['tournament_year'] == 2026)
        # Use active_count (net) for predictions; fall back to entry_count if 0
        net_count = int(s['active_count']) if s['active_count'] > 0 else int(s['entry_count'])
        if mask.any() and net_count > 0:
            old_count = summary.loc[mask, 'final_count'].iloc[0]
            summary.loc[mask, 'final_count'] = net_count
            if old_count != net_count:
                updated += 1
    # Reanchor ALL daily T values from last_reg to event_start so the model
    # trains and predicts in a consistent coordinate system (T=0 = event start).
    daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)

    # Insert scrape rows using event_start-based T
    for _, s in scrape.iterrows():
        scrape_name = s['tournament_name']
        family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
        tid_match = summary[(summary['family'] == family_name) & (summary['tournament_year'] == 2026)]
        if len(tid_match) == 0:
            continue
        tid = tid_match.iloc[0]['tid']
        last_reg = tid_match.iloc[0].get('last_reg')
        meta_row = meta[(meta['family'] == family_name) & (meta['year'] == 2026)]
        if len(meta_row) == 0:
            meta_row = meta[(meta['year'] == 2026) & (meta['start_date'] > pd.Timestamp.now())]
            meta_row = meta_row[meta_row['family'].str.contains(family_name.split()[0], case=False, na=False)]
        if len(meta_row) > 0:
            event_start = pd.to_datetime(meta_row.iloc[0]['start_date'])
            T = max((event_start - pd.to_datetime(s['date'])).days, 0)
        elif pd.notna(last_reg):
            T = max((pd.to_datetime(last_reg) - pd.to_datetime(s['date'])).days, 0)
        else:
            continue
        # Insert or update — use active_count (net) for curve data
        scrape_count = int(s['active_count']) if s['active_count'] > 0 else int(s['entry_count'])
        existing = daily[(daily['tid'] == tid) & (daily['T'] == T)]
        if len(existing) == 0 and scrape_count > 0:
            new_row = pd.DataFrame([{
                'tid': tid, 'T': T, 'daily_regs': 0,
                'cum_regs': scrape_count, 'cum_pct': 1.0
            }])
            daily = pd.concat([daily, new_row], ignore_index=True)
        elif len(existing) > 0 and scrape_count > existing.iloc[0]['cum_regs']:
            daily.loc[(daily['tid'] == tid) & (daily['T'] == T), 'cum_regs'] = scrape_count
    print(f"  Merged scrape data: {updated} tournament counts updated, {len(latest_scrape)} tournaments in scrape")

# Load enrichment data if available
hist_path = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
hist_enrich = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
enrichment_lookup = m04c.build_enrichment_lookup(hist_enrich)

# Filter exclusions: online, COVID, sub-events we don't want
# Use regex to catch name variants (G/50 vs G 50, Women's vs Womens, etc.)
_WO_EXCLUDE_PATTERN = re.compile(
    r'World Open\s+(G[\s/]\d+|Action|Womens?|Women.s|Senior|Junior|Amateur|Blitz)',
    re.IGNORECASE
)
EXCLUDE_FAMILIES = [fam for fam in summary['family'].unique() if _WO_EXCLUDE_PATTERN.search(fam)]
EXCLUDE_FAMILIES.extend([
    # The old combined "World Open" family (pre-2023) — superseded by
    # top-6/lower split; exclude to avoid double-counting
    'World Open',
    # Tiny side events with 1-6 registrants, not real tournaments
    'George Washington Saturday Octos', 'George Washington Sunday Octos',
])

# Exclude all blitz/rapid side events (not useful for logistical planning)
blitz_families = summary[summary['family'].str.contains(
    r'Blitz|Rapid|Bullet|Bughouse|Armageddon', case=False, na=False, regex=True
)]['family'].unique().tolist()
EXCLUDE_FAMILIES.extend(blitz_families)
print(f"Excluding {len(blitz_families)} blitz/rapid families")

# ── Build ratio model (same as N5 but with lognormal CIs) ──

def build_ratio_model(train_summary, train_daily):
    """Build historical ratio model with lognormal CIs."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False)) &
        (train_summary['tournament_year'] < 2026)  # exclude in-progress 2026 data
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
        except (ValueError, OverflowError):
            pass
    return None


def get_event_end_date(family, year):
    """Get event end date from metadata."""
    match = meta[(meta['family'] == family) & (meta['year'] == year)]
    if len(match) > 0 and pd.notna(match.iloc[0].get('end_date')):
        return pd.to_datetime(match.iloc[0]['end_date'])
    return None


def determine_status(row, event_date, event_end_date=None):
    """Determine if tournament is live, in_progress, or complete.

    live: event hasn't started yet (pre-event, model predicts)
    in_progress: event is underway (start <= today <= end, scrape passthrough)
    complete: event is over (today > end)
    """
    if event_date is None:
        return 'unknown'

    # Use event_end if available; otherwise estimate as start + 5 days
    end = event_end_date if event_end_date else event_date + pd.Timedelta(days=5)

    if TODAY > end:
        return 'complete'
    elif event_date <= TODAY:
        return 'in_progress'
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

# Identify completed 2026 tournaments (last_reg in the past) for rolling retraining
completed_2026 = summary[
    (summary['tournament_year'] == 2026) &
    (~summary['is_online'].fillna(False)) &
    (summary['has_timestamps'])
].copy()
completed_2026['last_reg'] = pd.to_datetime(completed_2026['last_reg'])
completed_tids = set()
for _, row in completed_2026.iterrows():
    family = row['family']
    lr = row['last_reg']
    if pd.isna(lr) or lr > TODAY:
        continue
    # Check metadata — if event_start is in the future, it's still live
    m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
    if len(m_row) > 0 and pd.notna(m_row.iloc[0]['start_date']) and m_row.iloc[0]['start_date'] > TODAY:
        continue
    completed_tids.add(row['tid'])

if completed_tids:
    print(f"  Rolling retraining: {len(completed_tids)} completed 2026 tournaments included in training")

# Use production model (N5v4_Final) with all fixes:
# - proper prediction intervals, empirical Bayes shrinkage
# - expanding-window calibration, T-interpolation
# - rolling retraining: completed 2026 tournaments fold into training data
prod_model = m04c.N5v4_Final()
prod_model.fit(train_ts, daily, enrichment_lookup=enrichment_lookup,
               completed_tids=completed_tids if completed_tids else None)

# Automated recalibration: learn from ALL completed tournaments (2024-2025 + 2026)
# Recent data is weighted more heavily (2026 conditions > 2019 conditions)
recal_data = summary[
    (summary['has_timestamps']) &
    (~summary['is_online'].fillna(False)) &
    (~summary['is_covid'].fillna(False)) &
    (summary['final_count'] >= 50) &
    (
        (summary['tournament_year'].isin([2024, 2025])) |
        (summary['tid'].isin(completed_tids))
    )
].copy()
if len(recal_data) >= 5:
    recal_diag = prod_model.recalibrate(recal_data, daily)
    n_2026 = len(recal_data[recal_data['tournament_year'] == 2026])
    n_older = len(recal_data) - n_2026
    print(f"  Recalibration from {len(recal_data)} tournaments ({n_older} from 2024-25, {n_2026} from 2026):")
    for T, d in sorted(recal_diag.items()):
        print(f"    T-{T:>2}: bias {d['mean_bias']:>+5.1f}% → factor {d['bias_factor']:.3f}, "
              f"CI cov {d['coverage']:>3.0f}% → adj {d['ci_adj']:.3f} (n={d['n']})")
else:
    print(f"  Recalibration skipped: need ≥5 completed tournaments, have {len(recal_data)}")

ratios = build_ratio_model(train, daily)  # kept for families without timestamps
curves = build_template_curves(train, daily)

# ── World Open: keep only Under 13, top 6, lower as separate families ──
# All other WO sub-events are already in EXCLUDE_FAMILIES.
# Exclude any remaining WO variants that slipped through naming differences.
WO_KEEP = {'World Open Under 13', 'World Open top 6 sections', 'World Open lower sections',
           'World Open, top 6 sections', 'World Open, lower sections',
           'World Open Under 13 Championship'}
wo_extra_exclude = summary[
    (summary['family'].str.startswith('World Open')) &
    (~summary['family'].isin(WO_KEEP))
]['family'].unique().tolist()
if wo_extra_exclude:
    EXCLUDE_FAMILIES.extend(wo_extra_exclude)
    print(f"Excluding {len(wo_extra_exclude)} additional World Open sub-families: {wo_extra_exclude}")
print(f"World Open: keeping {WO_KEEP & set(summary['family'].unique())}")

# Get 2026 tournaments
t2026 = summary[
    (summary['tournament_year'] == 2026) &
    (~summary['is_online'].fillna(False)) &
    (~summary['family'].isin(EXCLUDE_FAMILIES))
].copy()

print(f"Found {len(t2026)} 2026 tournaments (after filtering)")

# Build withdrawal lookup from latest scrape data (family -> withdrawal_count)
withdrawal_lookup = {}
if os.path.exists(scrape_path):
    for _, s in latest_scrape.iterrows():
        scrape_name = s['tournament_name']
        fam = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
        wd = int(s.get('withdrawal_count', 0)) if pd.notna(s.get('withdrawal_count')) else 0
        gross = int(s.get('entry_count', 0))
        withdrawal_lookup[fam] = {'withdrawal_count': wd, 'gross_count': gross}

tournaments_out = []

for _, row in t2026.iterrows():
    family = row['family']
    tid = row['tid']
    current_count = row['final_count']

    # Skip tiny sub-events and low-value entries
    if current_count < 1:
        continue
    # Skip completed tournaments with very few registrations (likely sub-events or data issues)
    # Expand family aliases so renamed tournaments (e.g. DC Open ↔ Philadelphia Open) find their history
    hist_families = [family]
    if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
        hist_families.extend(m04c.FAMILY_ALIASES[family])
    hist_check = summary[
        (summary['family'].isin(hist_families)) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ]
    if current_count < 10 and len(hist_check) == 0:
        continue

    event_date = get_event_date(family, 2026)
    event_end_date = get_event_end_date(family, 2026)
    status = determine_status(row, event_date, event_end_date)

    if event_date is not None:
        days_remaining = max((event_date - TODAY).days, 0)
    else:
        days_remaining = 60

    # Exclude tournaments too far out — predictions are meaningless with 1-3 registrants
    if days_remaining > 250:
        continue

    # T = days_remaining (days to event_start). Training data is anchored to
    # event_start after reanchor_daily_to_event_start(), so pass directly.

    # Get metadata
    m = meta[(meta['family'] == family) & (meta['year'] == 2026)]
    eb_deadline = m.iloc[0]['early_bird_deadline'] if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_deadline')) else None
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
    prediction_source = 'model'
    if status == 'complete':
        point, ci_lo, ci_hi = current_count, current_count, current_count
        prediction_source = 'final'
    elif status == 'in_progress':
        # Event is underway — pass through scraped count directly.
        # Model stops predicting at event_start; live scrape is the real count.
        # Does NOT include on-site/walk-up registrations (online pre-reg only).
        point, ci_lo, ci_hi = current_count, current_count, current_count
        prediction_source = 'live_scrape'
    elif status == 'live' and days_remaining > 0:
        point, ci_lo, ci_hi = prod_model.predict_nowcast(
            current_count, days_remaining, family,
            early_bird_deadline=eb_deadline)
        if point is None:
            point, ci_lo, ci_hi = predict_with_lognormal_ci(current_count, days_remaining, family, ratios)

        # Plausibility check: if point estimate is far outside historical range,
        # blend with historical median but preserve model's CI width
        if len(hist_counts) >= 3:
            hist_min = min(hist_counts)
            hist_max = max(hist_counts)
            hist_med = int(np.median(hist_counts))
            ci_width = ci_hi - ci_lo
            if days_remaining > 60 and point < hist_med * 0.7:
                # Far out + low: blend model with historical median (50/50)
                point = int(0.5 * point + 0.5 * hist_med)
                ci_lo = int(point - ci_width / 2)
                ci_hi = int(point + ci_width / 2)
            elif point < hist_min * 0.3:
                # Extremely low — re-center on historical median
                point = hist_med
                ci_lo = int(point - ci_width / 2)
                ci_hi = int(point + ci_width / 2)
            elif point > hist_max * 3.0:
                point = int(hist_max * 1.5)
                ci_lo = int(point - ci_width / 2)
                ci_hi = int(point + ci_width / 2)
    else:
        point, ci_lo, ci_hi = current_count, current_count, current_count

    # Daily data for chart
    tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(tid_daily) > 0:
        max_T = tid_daily['T'].max()
        # Build daily_data: keep highest count at each T
        by_T = {}
        for _, d in tid_daily.iterrows():
            T = int(d['T'])
            count = int(d['cum_regs'])
            if T not in by_T or count > by_T[T]:
                by_T[T] = count
        daily_data = []
        for T in sorted(by_T.keys(), reverse=True):
            day_from_start = int(max_T - T)
            daily_data.append([day_from_start, by_T[T]])
        daily_data.sort(key=lambda x: x[0])
        # Stitch archive + scrape: archive counts are from an earlier
        # snapshot and undercount. When a >3x jump occurs (scrape start),
        # scale the preceding archive points proportionally so the curve
        # is smooth from registration open through today.
        for i in range(1, len(daily_data)):
            if daily_data[i][1] > daily_data[i-1][1] * 3 and daily_data[i][1] > 50:
                # Scale all prior points by the ratio at the jump
                scale = daily_data[i][1] / max(daily_data[i-1][1], 1)
                for j in range(i):
                    daily_data[j][1] = int(daily_data[j][1] * scale)
                break
        # Enforce monotonically non-decreasing
        peak = 0
        cleaned = []
        for pt in daily_data:
            if pt[1] >= peak:
                peak = pt[1]
                cleaned.append(pt)
        daily_data = cleaned
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

    # YoY pacing context: what was the count at the same T last year?
    prior_year_pace = None
    if status == 'live' and days_remaining > 0:
        # Find most recent prior year's tournament for this family
        prior_hist = summary[
            (summary['family'] == family) &
            (summary['tournament_year'] == summary[
                (summary['family'] == family) &
                (summary['tournament_year'] < 2026)
            ]['tournament_year'].max())
        ]
        if len(prior_hist) > 0:
            prior_tid = prior_hist.iloc[0]['tid']
            prior_daily = daily[daily['tid'] == prior_tid]
            if len(prior_daily) > 0:
                # Find count at closest T to current days_remaining
                prior_at_T = prior_daily[prior_daily['T'] >= days_remaining].sort_values('T')
                if len(prior_at_T) > 0:
                    prior_count_at_T = int(prior_at_T.iloc[0]['cum_regs'])
                    prior_year_val = int(prior_hist.iloc[0]['tournament_year'])
                    prior_year_pace = {
                        "year": prior_year_val,
                        "count_at_same_point": prior_count_at_T,
                        "final": int(prior_hist.iloc[0]['final_count']),
                    }

    # Withdrawal data from scrape
    wd_info = withdrawal_lookup.get(family, {})
    withdrawal_count = wd_info.get('withdrawal_count', 0)
    gross_count = wd_info.get('gross_count', int(current_count))

    t_out = {
        "family": display_family,
        "year": 2026,
        "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
        "event_end": None,
        "early_bird_deadline": str(eb_deadline)[:10] if eb_deadline and str(eb_deadline) != 'nan' else None,
        "early_bird_fee": eb_fee,
        "regular_fee": reg_fee,
        "onsite_fee": onsite_fee,
        "current_count": int(current_count),
        "gross_count": int(gross_count),
        "withdrawal_count": int(withdrawal_count),
        "days_remaining": int(days_remaining),
        "point_estimate": int(point),
        "ci_lower": int(ci_lo),
        "ci_upper": int(ci_hi),
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": daily_data,
        "registration_curve": reg_curve,
        "status": 'live' if status == 'in_progress' else status,
        "prediction_source": prediction_source,
        "prior_year_pace": prior_year_pace,
    }

    # Add event_end from metadata
    if len(m) > 0 and pd.notna(m.iloc[0].get('end_date')):
        t_out['event_end'] = str(m.iloc[0]['end_date'])[:10]

    tournaments_out.append(t_out)

# Add tournaments from metadata that have no registrations yet
# Build scrape lookup so metadata-only tournaments can pick up live entry counts
_scrape_lookup = {}
if os.path.exists(scrape_path):
    for _, s in latest_scrape.iterrows():
        sn = s['tournament_name']
        fam = sn.replace('2026 ', '', 1) if sn.startswith('2026 ') else sn
        net = int(s['active_count']) if pd.notna(s['active_count']) and s['active_count'] > 0 else int(s['entry_count'])
        gross = int(s.get('entry_count', 0))
        wd = int(s.get('withdrawal_count', 0)) if pd.notna(s.get('withdrawal_count')) else 0
        _scrape_lookup[fam] = {'net': net, 'gross': gross, 'wd': wd}

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
    # Pick up live entry count from scrape data if available
    scrape_info = _scrape_lookup.get(mfamily, {})
    current_count = scrape_info.get('net', 0)
    gross_count = scrape_info.get('gross', current_count)
    withdrawal_count = scrape_info.get('wd', 0)
    # Historical data (expand aliases for renamed tournaments)
    hist_families = [mfamily]
    if hasattr(m04c, 'FAMILY_ALIASES') and mfamily in m04c.FAMILY_ALIASES:
        hist_families.extend(m04c.FAMILY_ALIASES[mfamily])
    hist = summary[
        (summary['family'].isin(hist_families)) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ].sort_values('tournament_year')
    historical = [{"year": int(h['tournament_year']), "count": int(h['final_count']),
                   "family": h['family']}
                  for _, h in hist.iterrows()]
    # Predict from historical data with proper variance-based CI
    hist_counts = [h['count'] for h in historical]
    hist_mean = np.mean(hist_counts) if hist_counts else 100
    # Sanity check: 0 registrations close to event = likely cancelled/not tracked
    if days_remaining < 30 and current_count == 0:
        status_label = "not_tracked"
    else:
        status_label = "live"
    # Use actual variance for CI when enough history exists
    if len(hist_counts) >= 5:
        ci_lo = int(np.percentile(hist_counts, 10))
        ci_hi = int(np.percentile(hist_counts, 90))
    elif len(hist_counts) >= 2:
        ci_lo = int(min(hist_counts))
        ci_hi = int(max(hist_counts))
    else:
        ci_lo = int(hist_mean * 0.7)
        ci_hi = int(hist_mean * 1.3)
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
        "early_bird_deadline": str(eb_deadline)[:10] if pd.notna(eb_deadline) and str(eb_deadline) != 'nan' else None,
        "early_bird_fee": eb_fee,
        "regular_fee": reg_fee,
        "onsite_fee": onsite_fee,
        "current_count": int(current_count),
        "gross_count": int(gross_count),
        "withdrawal_count": int(withdrawal_count),
        "days_remaining": int(days_remaining),
        "point_estimate": int(hist_mean),
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": [[0, current_count]],
        "registration_curve": reg_curve,
        "status": status_label,
    }
    tournaments_out.append(t_out)
    print(f"  Added from metadata: {mfamily} (event {event_date.strftime('%Y-%m-%d')}, {days_remaining} days out, entries={current_count}, status={status_label})")

# ── Build reverse alias map for 2026 families ──
# If "DC International" is a 2026 family with alias "Philadelphia International",
# historical "Philadelphia International" editions should display under "DC International"
# so the website shows one unified tournament card with full history.
_alias_to_2026 = {}
for t in tournaments_out:
    fam = t['family']
    if hasattr(m04c, 'FAMILY_ALIASES') and fam in m04c.FAMILY_ALIASES:
        for alias in m04c.FAMILY_ALIASES[fam]:
            _alias_to_2026[alias] = fam

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
    # Remap alias families to their 2026 canonical name
    # e.g. historical "Philadelphia International" → "DC International"
    display_family = _alias_to_2026.get(family, family)

    # Get event date
    event_date = get_event_date(family, yr)

    # Same-family history (include alias families so remapped entries show full lineage)
    hist_families = [family]
    if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
        hist_families.extend(m04c.FAMILY_ALIASES[family])
    # Also check reverse: if this family is an alias of a 2026 family, include the 2026 family
    if family in _alias_to_2026:
        canonical = _alias_to_2026[family]
        if canonical not in hist_families:
            hist_families.append(canonical)
    hist = historical_valid[
        (historical_valid['family'].isin(hist_families)) &
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

# ── Deduplicate tournaments with variant names (e.g. comma vs no comma) ──
seen_keys = {}
deduped = []
for t_out in tournaments_out:
    # Normalize: strip commas, lowercase for comparison
    norm = t_out["family"].replace(",", "").lower().strip()
    key = (norm, t_out["year"])
    if key in seen_keys:
        # Keep the one with more data (higher current_count)
        existing = seen_keys[key]
        if t_out["current_count"] > existing["current_count"]:
            deduped.remove(existing)
            seen_keys[key] = t_out
            deduped.append(t_out)
    else:
        seen_keys[key] = t_out
        deduped.append(t_out)
if len(tournaments_out) != len(deduped):
    print(f"\nDeduplication: {len(tournaments_out)} -> {len(deduped)} tournaments")
tournaments_out = deduped

# ── Apply walk-in multiplier — only for completed tournaments (after event start) ──
from importlib import import_module
_m04c = import_module("04c_final_model")
_walkin_mults = _m04c.load_walkin_multipliers()
_walkin_applied = 0
for t_out in tournaments_out:
    # Only apply walk-in estimates after the event has started
    if t_out["status"] in ("live", "not_tracked"):
        continue
    family = t_out["family"]
    tp, tl, th, ratio, wsource = _m04c.apply_walkin_multiplier(
        t_out["point_estimate"], t_out["ci_lower"], t_out["ci_upper"],
        family, _walkin_mults)
    if ratio:
        t_out["walkin_multiplier"] = round(ratio, 3)
        t_out["walkin_source"] = wsource
        t_out["total_estimate"] = tp
        t_out["total_ci_lower"] = tl
        t_out["total_ci_upper"] = th
        _walkin_applied += 1
print(f"\nWalk-in multiplier applied to {_walkin_applied} completed/historical tournaments")

# Sort: live first (by days_remaining desc), then 2026 complete, then historical
status_order = {'live': 0, 'complete': 1, 'historical': 2, 'unknown': 3}
tournaments_out.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

# Count by status
n_live = sum(1 for t in tournaments_out if t['status'] == 'live')
n_complete = sum(1 for t in tournaments_out if t['status'] == 'complete')
n_historical = sum(1 for t in tournaments_out if t['status'] == 'historical')

output = {
    "generated": TODAY.strftime('%Y-%m-%d'),
    "generated_time": pd.Timestamp.now(tz='America/New_York').isoformat(),
    "model": "N5v4_Final",
    "model_description": "Ensemble model (N5v4): historical ratio (harmonic mean) + per-family pooled Huber regression (final ~ count_at_T + T). T anchored to event_start. T-dependent weights (ratio: 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). 80% CI from lognormal prediction intervals, LOO-calibrated with T-dependent shrinkage. Rolling retraining on completed 2026 tournaments. Automated bias + CI recalibration. Walk-in multiplier: post-hoc adjustment using historical standings-to-prereg ratios (94 tournament-years, 24 families, MAPE 6.9%).",
    "n_completed_in_training": len(completed_tids) if completed_tids else 0,
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

# ── Data linking validation ──────────────────────────────────────────────
# Compare scrape counts to website output. Flag any tournament where the
# scrape has entries but the website shows 0 — that's a linking failure.
if os.path.exists(scrape_path):
    all_2026 = {t['family']: t['current_count'] for t in tournaments_out if t.get('year') == 2026}
    live_2026 = {t['family']: t['current_count'] for t in tournaments_out if t.get('year') == 2026 and t.get('status') == 'live'}
    # Tournaments that are intentionally excluded (completed, blitz, WO sub-events, etc.)
    excluded_or_complete = set(EXCLUDE_FAMILIES)
    excluded_or_complete.update(t['family'] for t in tournaments_out if t.get('year') == 2026 and t.get('status') in ('complete', 'in_progress'))
    link_warnings = []
    for _, s in latest_scrape.iterrows():
        sn = s['tournament_name']
        fam = sn.replace('2026 ', '', 1) if sn.startswith('2026 ') else sn
        if fam in excluded_or_complete:
            continue
        scrape_count = int(s['active_count']) if pd.notna(s['active_count']) and s['active_count'] > 0 else int(s['entry_count'])
        if scrape_count > 0 and fam in live_2026 and live_2026[fam] == 0:
            link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, website=0")
        elif scrape_count > 0 and fam not in all_2026:
            link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, NOT IN OUTPUT")
    if link_warnings:
        print(f"\n{'!'*60}")
        print(f"  DATA LINKING WARNINGS — {len(link_warnings)} tournaments with scrape data not reflected in output:")
        for w in link_warnings:
            print(w)
        print(f"{'!'*60}")
    else:
        print(f"\n✓ Data linking check passed: all scraped tournaments reflected in output")
