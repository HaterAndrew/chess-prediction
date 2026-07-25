"""
Phase 4D: Clean website data generation.
Fix status detection, filter to main events, correct predictions.
"""

import pandas as pd
import numpy as np
from scipy.interpolate import interp1d
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m04c = import_module("04c_final_model")
from tournament_aliases import canonicalize_family, adjust_wo_top6_count
from prediction_window import registration_close_date, window_decayed_estimate
from pipeline_utils import (apply_plausibility_clamp, build_chart_series,
                            chart_series_start_date, is_event_complete)
# v3 T7: these two live in ratio_model now so the window-engine grader can
# import them without executing this script's pipeline body. Imported here
# under their original names, so every call site below is unchanged.
from ratio_model import build_ratio_model, predict_with_lognormal_ci


def _fam_eq(series, name):
    """Family equality that tolerates comma/whitespace variants via aliases."""
    canon = canonicalize_family(name)
    return series.map(canonicalize_family) == canon


# Canonical names that count as the post-split top-6 series
_WO_TOP6_TARGETS = {
    'World Open top 6 sections',
    'World Open, top 6 sections',
}


def _apply_wo_top6_adjustment(target_family, entries, strip_family=False):
    """Scale pre-split 'World Open' historical entries down to top-6-comparable
    counts when the chart's target series is the post-split top-6 family.

    Pre-2023 'World Open' totals include U1200, U900, and Unrated; the post-2023
    'World Open top 6 sections' tids exclude them. Without this adjustment the
    2019/2022 bars get plotted alongside a series that drops the bottom of the
    field, making year-over-year comparison apples-to-oranges.

    Returns the entries list (mutated copy) with adjusted counts and an
    'adjusted' flag on rows that were rewritten. If strip_family=True, the
    'family' key is removed from each entry (the third call site doesn't
    serialize it).
    """
    target_norm = (target_family or '').replace(',', '').strip()
    is_wo_top6 = target_norm == 'World Open top 6 sections'
    out = []
    for h in entries:
        h = dict(h)
        if is_wo_top6 and h.get('family') == 'World Open':
            adjusted = adjust_wo_top6_count(h['year'], h['count'])
            if adjusted != h['count']:
                h['count_raw'] = h['count']
                h['count'] = int(adjusted)
                h['adjusted'] = 'top6_pre_split'
        if strip_family:
            h.pop('family', None)
        out.append(h)
    return out


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
T_GRID = np.arange(0, 121)
TODAY = pd.Timestamp.now().normalize()

# Early-bird sanitization. Must match the display-layer rule in docs/app.js
# (hasValidEarlyBird). Defense-in-depth: drop bad EB data here so it never
# reaches the JSON output, even if a manual edit or future scraper writes
# bogus values into tournament_metadata.csv.
EARLY_BIRD_MIN_GAP_DAYS = 14


def sanitize_early_bird(family, year, eb_deadline, eb_fee, reg_fee, event_start):
    """Return (eb_deadline, eb_fee) after applying real-EB rules.

    Rules:
      * eb_deadline AND eb_fee AND reg_fee must all be present
      * eb_fee < reg_fee (must be a real price hike, not a flat advance fee)
      * deadline must land at least EARLY_BIRD_MIN_GAP_DAYS before event_start
        (filters CCA advance/onsite 3-day steps like Cleveland, Pittsburgh,
        Mid-America, Golden State).
    On rejection, returns (None, None) and logs a one-line warning so the
    drift is visible at build time.
    """
    if eb_deadline is None or eb_fee is None or reg_fee is None:
        return None, None
    if event_start is None:
        # Without an anchor we can't check the gap. Be conservative: drop.
        print(f"  ⚠ EB-sanitize {family} {year}: dropping EB — no event_start to anchor gap check")
        return None, None
    if eb_fee >= reg_fee:
        print(f"  ⚠ EB-sanitize {family} {year}: dropping EB — eb_fee ${eb_fee} >= reg_fee ${reg_fee} (no price hike)")
        return None, None
    try:
        gap = (pd.Timestamp(event_start) - pd.Timestamp(eb_deadline)).days
    except (TypeError, ValueError):
        print(f"  ⚠ EB-sanitize {family} {year}: dropping EB — unparseable dates eb={eb_deadline} ev={event_start}")
        return None, None
    if gap < EARLY_BIRD_MIN_GAP_DAYS:
        print(f"  ⚠ EB-sanitize {family} {year}: dropping EB — deadline T-{gap} < T-{EARLY_BIRD_MIN_GAP_DAYS} (advance/onsite step, not early bird)")
        return None, None
    return eb_deadline, eb_fee


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
    # H13: publish ONE count semantic — gross (row-count, entry_count), matching
    # tournament_summary.csv, the performance tab, the freshness guard, and how
    # 04e grades. The old code overrode final_count with active_count (net), so
    # cards showed net while the perf tab showed gross (ACO 401 vs 424) and the
    # deployed model trained on net but was graded on gross. Track the net/
    # withdrawal delta in a separate column for display instead.
    if 'active_count' not in summary.columns:
        summary['active_count'] = pd.NA
    if 'withdrawal_count' not in summary.columns:
        summary['withdrawal_count'] = pd.NA
    updated = 0
    for _, s in latest_scrape.iterrows():
        # Match by family name (strip year prefix "2026 " from scrape name)
        scrape_name = s['tournament_name']
        family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
        mask = _fam_eq(summary['family'], family_name) & (summary['tournament_year'] == 2026)
        gross_count = int(s['entry_count']) if s['entry_count'] > 0 else int(s['active_count'])
        net_count = int(s['active_count']) if s['active_count'] > 0 else gross_count
        if mask.any() and gross_count > 0:
            old_count = summary.loc[mask, 'final_count'].iloc[0]
            summary.loc[mask, 'final_count'] = gross_count
            summary.loc[mask, 'active_count'] = net_count
            summary.loc[mask, 'withdrawal_count'] = max(gross_count - net_count, 0)
            if old_count != gross_count:
                updated += 1
    # Reanchor ALL daily T values from last_reg to event_start so the model
    # trains and predicts in a consistent coordinate system (T=0 = event start).
    daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)

    # Insert scrape rows using event_start-based T
    for _, s in scrape.iterrows():
        scrape_name = s['tournament_name']
        family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
        tid_match = summary[_fam_eq(summary['family'], family_name) & (summary['tournament_year'] == 2026)]
        if len(tid_match) == 0:
            continue
        tid = tid_match.iloc[0]['tid']
        last_reg = tid_match.iloc[0].get('last_reg')
        meta_row = meta[_fam_eq(meta['family'], family_name) & (meta['year'] == 2026)]
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
# WO exclusion logic lives in tournament_aliases.is_wo_excluded — single
# source of truth shared with 04e_performance_data.py.
from tournament_aliases import is_wo_excluded
_all_families = set(summary['family'].unique()) | set(meta['family'].unique())
EXCLUDE_FAMILIES = [fam for fam in _all_families if is_wo_excluded(fam)]
EXCLUDE_FAMILIES.extend([
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

# ── Build template curves ──

def build_template_curves(train_summary, train_daily):
    """Build median cumulative curves per family."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False)) &
        # H15: exclude in-progress 2026 editions — their injected scrape rows carry
        # cum_pct=1.0, which drags the "typical timeline" template toward 1.0 too
        # early (worst for 2-3 edition families). Parity with build_ratio_model.
        (train_summary['tournament_year'] < 2026)
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
    match = meta[_fam_eq(meta['family'], family) & (meta['year'] == year)]
    if len(match) > 0:
        return match.iloc[0]['start_date']

    # Estimate from historical last_reg dates for this family
    fam = summary[_fam_eq(summary['family'], family) & (~summary['is_online'].fillna(False))]
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
    match = meta[_fam_eq(meta['family'], family) & (meta['year'] == year)]
    if len(match) > 0 and pd.notna(match.iloc[0].get('end_date')):
        return pd.to_datetime(match.iloc[0]['end_date'])
    return None


def determine_status(row, event_date, event_end_date=None, registration_close=None):
    """Determine if tournament is live, in_progress, or complete.

    live: online registration still open — the model predicts. Includes the
          post-start window for multi-schedule events, where the 5-day
          schedule has begun but 4/3/2-day online entries are still arriving.
    in_progress: online registration has closed, event still running — the
          live scrape is the count, the model no longer predicts forward.
    complete: event is over (today > end)
    """
    if event_date is None:
        return 'unknown'

    # Use event_end if available; otherwise estimate as start + 5 days
    end = event_end_date if event_end_date else event_date + pd.Timedelta(days=5)
    # registration_close drives the live->in_progress flip. Without it, fall
    # back to event_date (legacy behaviour: stop predicting on start day).
    close = registration_close if registration_close is not None else event_date

    if TODAY > end:
        return 'complete'
    elif TODAY >= close:
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
    # Require event end_date strictly in the past. A start_date-only check
    # admitted mid-event tournaments (Chicago Open, May 21–25) whose
    # summary.final_count was still being raised by daily scrapes — corrupting
    # prod_model.fit() and recalibrate() with non-final truth labels.
    end_dt = get_event_end_date(family, 2026)
    if not is_event_complete(end_dt, TODAY):
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
               completed_tids=completed_tids if completed_tids else None,
               all_summary_families=set(summary['family'].dropna().unique()))

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
        cov = d.get('coverage_before', d.get('coverage', 0))
        print(f"    T-{T:>2}: bias {d['mean_bias']:>+5.1f}% → factor {d['bias_factor']:.3f}, "
              f"CI cov {cov:>3.0f}% → adj {d['ci_adj']:.3f} (n={d['n']})")
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

# H2: roster-pending skeletons (reconcile_final_counts appended them so the grade
# universe and freshness guard see the event) carry no registration timestamps and
# no roster. They must NOT enter the main model card path — that would replace their
# purpose-built metadata-path card (historical-band clamped, low_confidence) with a
# raw model estimate and drop the roster-pending disclosure. Let them fall through
# to the metadata loop below, which is designed for exactly this degraded mode.
if 'roster_pending' in t2026.columns:
    t2026 = t2026[~t2026['roster_pending'].fillna(False)].copy()

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
    registration_close = registration_close_date(event_date, event_end_date)
    status = determine_status(row, event_date, event_end_date, registration_close)

    # Two horizons. days_to_start drives the ratio model (training is anchored
    # to event_start). days_to_close is the online-registration horizon — for
    # multi-schedule events that runs days past event_start. days_into_window /
    # window_len locate TODAY inside the post-start registration window.
    if event_date is not None:
        days_to_start = max((event_date - TODAY).days, 0)
        days_into_window = max((TODAY - pd.Timestamp(event_date)).days, 0)
    else:
        days_to_start = 60
        days_into_window = 0
    if event_date is not None and registration_close is not None:
        days_to_close = max((registration_close - TODAY).days, 0)
        window_len = max((registration_close - pd.Timestamp(event_date)).days, 0)
    else:
        days_to_close = days_to_start
        window_len = 0

    # Displayed countdown: days to event_start before the event, then days to
    # registration close once the event is underway (entries still arriving).
    days_remaining = days_to_start if days_to_start > 0 else days_to_close

    # Exclude tournaments too far out — predictions are meaningless with 1-3 registrants
    if days_to_start > 250:
        continue

    # Get metadata
    m = meta[_fam_eq(meta['family'], family) & (meta['year'] == 2026)]
    eb_deadline = m.iloc[0]['early_bird_deadline'] if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_deadline')) else None
    eb_fee = float(m.iloc[0]['early_bird_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_fee')) else None
    reg_fee = float(m.iloc[0]['regular_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('regular_fee')) else None
    onsite_fee = float(m.iloc[0]['onsite_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('onsite_fee')) else None
    # Anchor the EB gap check to THIS card's event date, not a stale event_start
    # left over from an earlier loop (H14). Matches the sibling call below.
    eb_deadline, eb_fee = sanitize_early_bird(family, 2026, eb_deadline, eb_fee, reg_fee,
                                              event_date.strftime('%Y-%m-%d') if event_date else None)

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
    historical = _apply_wo_top6_adjustment(family, [
        {"year": int(h['tournament_year']), "count": int(h['final_count']),
         "family": h['family']}
        for _, h in hist.iterrows()
    ])

    # Predictions — use production model with guardrails
    hist_counts = [h['count'] for h in historical]
    prediction_source = 'model'
    if status == 'complete':
        point, ci_lo, ci_hi = current_count, current_count, current_count
        prediction_source = 'final'
    elif status == 'in_progress':
        # Online registration has closed (the 2-day schedule, the last entry
        # point, has started) — pass through the scraped count directly.
        # Does NOT include on-site/walk-up registrations (online pre-reg only).
        point, ci_lo, ci_hi = current_count, current_count, current_count
        prediction_source = 'live_scrape'
    elif status == 'live' and days_remaining > 0:
        if days_to_start == 0 and window_len > 0:
            # Post-start online-registration window: the 5-day schedule has
            # begun but 4/3/2-day online entries are still arriving. Take the
            # event-start (T=0) ratio bucket — the full count-at-start -> final
            # multiplier — and decay it toward 1.0 as registration close nears.
            # build_ratio_model's `ratios` carry a real T=0 bucket;
            # prod_model.predict_nowcast's finest bucket is T-1, so at T=0 it
            # would over-extrapolate from a one-day-earlier ratio.
            p0, lo0, hi0 = predict_with_lognormal_ci(
                current_count, 0, family, ratios)
            point, ci_lo, ci_hi = window_decayed_estimate(
                current_count, p0, lo0, hi0, days_into_window, window_len)
            prediction_source = 'model_online_window'
        else:
            point, ci_lo, ci_hi = prod_model.predict_nowcast(
                current_count, days_to_start, family,
                early_bird_deadline=eb_deadline,
                event_start_date=event_date)
            if point is None:
                point, ci_lo, ci_hi = predict_with_lognormal_ci(
                    current_count, days_to_start, family, ratios)

        # Plausibility check: if the point estimate is far outside the family's
        # historical range, blend toward the historical median while preserving
        # the model's CI width. Floors the result at current_count so a published
        # final can never sit below the entries already scraped (v3 N2).
        point, ci_lo, ci_hi = apply_plausibility_clamp(
            point, ci_lo, ci_hi, current_count, hist_counts, days_remaining)
    else:
        point, ci_lo, ci_hi = current_count, current_count, current_count

    # Daily data for chart. build_chart_series (pipeline_utils) dedupes per T,
    # converts to day_from_start, warns (never rescales) on A4 anomalies, and
    # drops non-increasing points. See v3 N1 / audit/AUDIT_2026-07-25.md.
    daily_data = build_chart_series(
        tid, daily, current_count,
        is_live=status in ('live', 'in_progress'))
    # Calendar date of the day_from_start==0 point, so the front end can date
    # every chart point from its own index value instead of counting array
    # positions back from the generation date (v3 P1).
    daily_start_date = chart_series_start_date(tid, daily, event_date)

    # Registration curve (template)
    curve = curves.get(family, curves.get('__global__', {}))
    reg_curve = []
    for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
        pct = curve.get(db, 0)
        reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})

    # Canonicalize family name so live and historical rows agree on form
    # (CCA emits "World Open, lower sections" with comma; canonical is the
    # no-comma form per tournament_aliases.FAMILY_GROUPS). Without this the
    # chart's histLookup and alerts.py's at-T comparator can't match the
    # 2026 live row against its 2023-2025 historical editions.
    display_family = canonicalize_family(family)

    # YoY pacing context: what was the count at the same T last year?
    prior_year_pace = None
    if status == 'live' and days_remaining > 0:
        # Find most recent prior year's tournament for this family
        _fam_mask = _fam_eq(summary['family'], family)
        prior_hist = summary[
            _fam_mask &
            (summary['tournament_year'] == summary[
                _fam_mask &
                (summary['tournament_year'] < 2026)
            ]['tournament_year'].max())
        ]
        if len(prior_hist) > 0:
            prior_tid = prior_hist.iloc[0]['tid']
            prior_daily = daily[daily['tid'] == prior_tid]
            if len(prior_daily) > 0:
                # Find prior count at the same days-to-event-start point
                # (prior_daily T is event_start-anchored, so compare against
                # days_to_start, not days_remaining which counts to reg close).
                prior_at_T = prior_daily[prior_daily['T'] >= days_to_start].sort_values('T')
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

    # AUDIT.md C8 / B1 — surface model confidence + tier on each prediction.
    # Count direct editions PLUS alias-family editions so a renamed/relocated
    # family (e.g. "DC International", whose history lives under "Philadelphia
    # International") reports its true edition count instead of 0 and isn't
    # wrongly flagged low-confidence. Mirrors the alias sum 04c uses for CI
    # widening; without it the JSON field under-reports for every alias family.
    if hasattr(prod_model, 'family_n_editions'):
        n_editions_for_family = prod_model.family_n_editions.get(family, 0)
        for _alias in m04c.FAMILY_ALIASES.get(family, []):
            n_editions_for_family += prod_model.family_n_editions.get(_alias, 0)
    else:
        n_editions_for_family = 0
    low_confidence = n_editions_for_family < 4
    # prod_model._last_tier only describes a predict_nowcast() call. The
    # online-window path uses predict_with_lognormal_ci instead, so leave the
    # tier null there rather than reporting a stale value from another row.
    tier_used = (getattr(prod_model, '_last_tier', None)
                 if status == 'live' and prediction_source != 'model_online_window'
                 else None)

    t_out = {
        "family": display_family,
        "year": 2026,
        "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
        "event_end": None,
        "registration_close": (registration_close.strftime('%Y-%m-%d')
                               if registration_close is not None else None),
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
        "daily_start_date": daily_start_date,
        "registration_curve": reg_curve,
        "status": 'live' if status == 'in_progress' else status,
        "prediction_source": prediction_source,
        "prior_year_pace": prior_year_pace,
        "low_confidence": low_confidence,
        "n_historical_editions": n_editions_for_family,
        "prediction_tier": tier_used,
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

# Consecutive scrape days at 0 entries before a near-event card is relabelled
# not_tracked (v3 N8). One zero is a scrape hiccup; several in a row is a real
# cancellation.
NOT_TRACKED_MIN_ZERO_DAYS = 3


def _consecutive_zero_scrape_days(family_name):
    """How many of the most recent consecutive scrape days show 0 entries.

    Returns a large number when the family has never been scraped at all, since
    "no scrape rows ever" is genuinely untracked rather than a transient miss.
    """
    if not os.path.exists(scrape_path):
        return NOT_TRACKED_MIN_ZERO_DAYS

    def _strip_year(n):
        return n[5:] if isinstance(n, str) and n.startswith('2026 ') else n

    ev = scrape[scrape['tournament_name'].apply(_strip_year) == family_name]
    if len(ev) == 0:
        return NOT_TRACKED_MIN_ZERO_DAYS

    by_day = {}
    for _, r in ev.iterrows():
        cnt = int(r['active_count']) if pd.notna(r.get('active_count')) and r['active_count'] > 0 else int(r['entry_count'])
        day = pd.to_datetime(r['date']).normalize()
        by_day[day] = max(by_day.get(day, 0), cnt)

    streak = 0
    for day in sorted(by_day, reverse=True):
        if by_day[day] == 0:
            streak += 1
        else:
            break
    return streak


def _scrape_daily_series(family_name, fallback_count):
    """Real [day_index, cumulative_count] entry-bar history for a 2026 event,
    read straight from daily_scrape.csv and matched by family name. Mirrors the
    main path's cummax cleaning. Falls back to a single point only when fewer
    than two scrapes exist — the chart needs >=3 points to draw bars, so the old
    hardcoded [[0, count]] rendered nothing for these events.

    Returns (series, start_date) where start_date is the 'YYYY-MM-DD' calendar
    date of day 0, or None when unknown. v3 P1: the front end dates every chart
    point from this anchor plus the point's own day index, so a gap in scraping
    can no longer shift the labels. v3 N9: this path now runs the same
    max-vs-count invariant as build_chart_series instead of going unchecked.
    """
    if not os.path.exists(scrape_path):
        return [[0, int(fallback_count)]], None

    def _strip_year(n):
        return n[5:] if isinstance(n, str) and n.startswith('2026 ') else n

    ev = scrape[scrape['tournament_name'].apply(_strip_year) == family_name].sort_values('date')
    if len(ev) < 2:
        return [[0, int(fallback_count)]], None
    by_day = {}
    min_date = ev['date'].min()
    for _, r in ev.iterrows():
        cnt = int(r['active_count']) if pd.notna(r.get('active_count')) and r['active_count'] > 0 else int(r['entry_count'])
        day = int((r['date'] - min_date).days)
        by_day[day] = max(by_day.get(day, 0), cnt)
    peak, series = 0, []
    for day in sorted(by_day):
        peak = max(peak, by_day[day])
        series.append([day, peak])

    # v3 N9: same post-build invariant the main path enforces. This series is
    # built from the scrape itself so it should never exceed the scraped count;
    # if it does, the family-name match pulled in another event's rows.
    if series and fallback_count and max(p[1] for p in series) > int(fallback_count):
        print(f"WARNING: roster-pending series max ({max(p[1] for p in series)}) "
              f"exceeds count ({int(fallback_count)}) for {family_name}; "
              f"check the family-name match.")

    start_date = pd.to_datetime(min_date).strftime('%Y-%m-%d')
    return series, start_date


# Canonical-aware so a metadata event ("... (in Connecticut)") isn't re-added
# when the main path already emitted its folded form ("Eastern Class
# Championships") once a fresh export pulls it into the roster.
existing_families = {canonicalize_family(t['family']) for t in tournaments_out}
for _, mrow in meta[meta['year'] == 2026].iterrows():
    mfamily = mrow['family']
    if canonicalize_family(mfamily) in existing_families or mfamily in EXCLUDE_FAMILIES:
        continue
    event_date = pd.to_datetime(mrow['start_date'])
    event_end = pd.to_datetime(mrow['end_date']) if pd.notna(mrow.get('end_date')) else event_date
    days_remaining = (event_date - TODAY).days
    # Far-future metadata (registration not meaningfully open yet) — skip.
    if days_remaining > 300:
        continue
    # Pick up live entry count from scrape data if available
    scrape_info = _scrape_lookup.get(mfamily, {})
    current_count = scrape_info.get('net', 0)
    gross_count = scrape_info.get('gross', current_count)
    withdrawal_count = scrape_info.get('wd', 0)
    # Historical data. Canonicalize first so a relocated edition ("... (in
    # Connecticut)") and CCA name variants ("World Open Under 13 Championship")
    # match their historical series via FAMILY_GROUPS/aliases instead of reading
    # as a brand-new family with zero history.
    canon_family = canonicalize_family(mfamily)
    _aliases = getattr(m04c, 'FAMILY_ALIASES', {})
    hist_families = list(dict.fromkeys(
        [mfamily, canon_family]
        + _aliases.get(mfamily, [])
        + _aliases.get(canon_family, [])
    ))
    hist = summary[
        (summary['family'].isin(hist_families)) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2019)
    ].sort_values('tournament_year')
    historical = _apply_wo_top6_adjustment(mfamily, [
        {"year": int(h['tournament_year']), "count": int(h['final_count']),
         "family": h['family']}
        for _, h in hist.iterrows()
    ])
    # H12: an event whose start date has already passed but that never entered
    # the roster path (a CCA sub-class the export folds into its parent — e.g.
    # World Open Under 13) used to be silently dropped by an
    # `event_date <= TODAY: continue` above. If live scrape counts exist, emit a
    # settled (event over) or in-progress (event running) card from the observed
    # count instead of losing the event. The point estimate is the observed
    # count, never a projection — we have no roster/model for it.
    if event_date <= TODAY:
        settled_count = current_count if current_count > 0 else gross_count
        if settled_count <= 0:
            # No roster and no live signal — nothing truthful to display.
            continue
        ended = event_end < TODAY
        curve = curves.get(mfamily, curves.get('__global__', {}))
        reg_curve = [{"days_before": db,
                      "cumulative_pct": round(float(curve.get(db, 0)), 4)}
                     for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]]
        eb_deadline = mrow.get('early_bird_deadline')
        eb_fee = float(mrow['early_bird_fee']) if pd.notna(mrow.get('early_bird_fee')) else None
        reg_fee = float(mrow['regular_fee']) if pd.notna(mrow.get('regular_fee')) else None
        onsite_fee = float(mrow['onsite_fee']) if pd.notna(mrow.get('onsite_fee')) else None
        _eb_dl_norm = str(eb_deadline)[:10] if pd.notna(eb_deadline) and str(eb_deadline) != 'nan' else None
        _eb_dl_norm, eb_fee = sanitize_early_bird(
            mfamily, 2026, _eb_dl_norm, eb_fee, reg_fee, event_date.strftime('%Y-%m-%d'))
        _rp_series, _rp_start = _scrape_daily_series(mfamily, settled_count)
        t_out = {
            "family": mfamily,
            "year": 2026,
            "event_start": event_date.strftime('%Y-%m-%d'),
            "event_end": str(mrow['end_date'])[:10] if pd.notna(mrow.get('end_date')) else None,
            "early_bird_deadline": _eb_dl_norm,
            "early_bird_fee": eb_fee,
            "regular_fee": reg_fee,
            "onsite_fee": onsite_fee,
            "current_count": int(settled_count),
            "gross_count": int(gross_count) if gross_count > 0 else int(settled_count),
            "withdrawal_count": int(withdrawal_count),
            "days_remaining": 0 if ended else max((event_end - TODAY).days, 0),
            "point_estimate": int(settled_count),
            "ci_lower": int(settled_count),
            "ci_upper": int(settled_count),
            "ci_level": 0.80,
            "historical": historical,
            "daily_data": _rp_series,
            "daily_start_date": _rp_start,
            "registration_curve": reg_curve,
            "status": "complete" if ended else "live",
            "n_historical_editions": len(historical),
            "low_confidence": True,
            "prediction_tier": "roster-pending",
            "prediction_source": "settled_actual" if ended else "in_progress_actual",
        }
        tournaments_out.append(t_out)
        print(f"  Added {'settled' if ended else 'in-progress'} from metadata: "
              f"{mfamily} (event {event_date.strftime('%Y-%m-%d')}, entries={settled_count})")
        continue
    # This event isn't in the trained model roster yet (registration opened
    # after the last all_registrations.csv export). Until a fresh export pulls
    # it into the main path, give an INTERIM estimate that still tracks live
    # registrations instead of a frozen historical average, and flag it
    # low-confidence so the card discloses the degraded mode.
    hist_counts = [h['count'] for h in historical]
    hist_mean = np.mean(hist_counts) if hist_counts else 100
    # Sanity check: 0 registrations close to event = likely cancelled/not tracked.
    #
    # v3 N8 (audit/AUDIT_2026-07-25.md): this is the same missing-scrape-day
    # failure class as the incident. A single scrape returning 0 for a live event
    # is indistinguishable here from a genuinely untracked one, and the card
    # silently disappeared from the live list. Require the zero to persist across
    # several consecutive scrape days before relabelling, and say so out loud
    # when it happens — a real cancellation stays at zero, a scrape hiccup does not.
    if days_remaining < 30 and current_count == 0:
        zero_days = _consecutive_zero_scrape_days(mfamily)
        if zero_days >= NOT_TRACKED_MIN_ZERO_DAYS:
            status_label = "not_tracked"
            print(f"WARNING: relabelling {mfamily} as not_tracked — 0 entries "
                  f"across {zero_days} consecutive scrape day(s), {days_remaining} "
                  f"day(s) out.")
        else:
            # Not enough evidence to call it untracked; keep it live.
            status_label = "live"
            print(f"WARNING: {mfamily} scraped 0 entries {days_remaining} day(s) "
                  f"out but only {zero_days} consecutive zero-day(s) "
                  f"(need {NOT_TRACKED_MIN_ZERO_DAYS}); keeping it live.")
    else:
        status_label = "live"

    days_to_start = max((pd.Timestamp(event_date) - TODAY).days, 0)
    prediction_source = "metadata_historical_avg"
    # Only extrapolate from live pace when the signal is informative: close to
    # the event AND enough registrations that 1-2 early sign-ups don't get
    # multiplied into an absurd projection (a 1-registrant event 170 days out
    # has no usable pace). Otherwise lean on the historical average — still
    # flagged low-confidence below.
    pace_usable = current_count >= 10 and days_to_start <= 45
    if hist_counts and pace_usable and status_label == "live":
        # Resolve the name the ratio model trained under (summary uses
        # 01_data_prep's canonical form, which can differ from the FAMILY_GROUPS
        # head — e.g. "World Open Under 13"); else predict falls to global ratios.
        ratio_family = canon_family
        for cand in hist_families:
            if cand in ratios:
                ratio_family = cand
                break
        p, lo, hi = predict_with_lognormal_ci(
            current_count, days_to_start, ratio_family, ratios)
        # Clamp into a sane band around observed history so a sparse, far-out
        # count can't produce an absurd interim number.
        lo_band, hi_band = min(hist_counts) * 0.6, max(hist_counts) * 1.5
        point_estimate = int(min(max(p, lo_band), hi_band))
        ci_lo = int(min(max(lo, lo_band), hi_band))
        ci_hi = int(min(max(hi, lo_band), hi_band))
        if ci_hi <= ci_lo:
            ci_lo, ci_hi = int(min(hist_counts)), int(max(hist_counts))
        prediction_source = "metadata_pace"
    else:
        point_estimate = int(hist_mean)
        # Variance-based CI from history when no live pace signal is usable.
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
    _eb_dl_norm = str(eb_deadline)[:10] if pd.notna(eb_deadline) and str(eb_deadline) != 'nan' else None
    _eb_dl_norm, eb_fee = sanitize_early_bird(mfamily, 2026, _eb_dl_norm, eb_fee, reg_fee, event_date.strftime('%Y-%m-%d'))
    _rp_series, _rp_start = _scrape_daily_series(mfamily, current_count)
    t_out = {
        "family": mfamily,
        "year": 2026,
        "event_start": event_date.strftime('%Y-%m-%d'),
        "event_end": str(mrow['end_date'])[:10] if pd.notna(mrow.get('end_date')) else None,
        "early_bird_deadline": _eb_dl_norm,
        "early_bird_fee": eb_fee,
        "regular_fee": reg_fee,
        "onsite_fee": onsite_fee,
        "current_count": int(current_count),
        "gross_count": int(gross_count),
        "withdrawal_count": int(withdrawal_count),
        "days_remaining": int(days_remaining),
        "point_estimate": point_estimate,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "ci_level": 0.80,
        "historical": historical,
        "daily_data": _rp_series,
        "daily_start_date": _rp_start,
        "registration_curve": reg_curve,
        "status": status_label,
        # Interim roster-fallback disclosure (see estimate logic above).
        "n_historical_editions": len(hist_counts),
        "low_confidence": True,
        "prediction_tier": "roster-pending",
        "prediction_source": prediction_source,
    }
    tournaments_out.append(t_out)
    print(f"  Added from metadata: {mfamily} (event {event_date.strftime('%Y-%m-%d')}, "
          f"{days_remaining} days out, entries={current_count}, est={point_estimate} "
          f"[{prediction_source}], status={status_label})")

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
    # Then canonicalize to strip comma variants (e.g. "World Open, lower
    # sections" → "World Open lower sections") so live/historical match.
    display_family = canonicalize_family(_alias_to_2026.get(family, family))

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
    historical = _apply_wo_top6_adjustment(display_family, [
        {"year": int(h['tournament_year']), "count": int(h['final_count']),
         "family": h['family']}
        for _, h in hist.iterrows()
    ], strip_family=True)

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
        "daily_start_date": chart_series_start_date(tid, daily, event_date),
        "registration_curve": reg_curve,
        "status": "historical",
    }
    tournaments_out.append(t_out)

# ── Deduplicate tournaments with variant names (e.g. comma vs no comma) ──
seen_keys = {}
deduped = []
for t_out in tournaments_out:
    # Canonicalize so comma variants AND venue-suffix variants ("... (in
    # Connecticut)") collapse to one key — not just comma/case normalization,
    # which let a relocated edition coexist with its folded form.
    key = (canonicalize_family(t_out["family"]), t_out["year"])
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
_walkin_by_source = {'family': 0, 'type': 0, 'estimate': 0, 'none': 0}
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
        _walkin_by_source[wsource] = _walkin_by_source.get(wsource, 0) + 1
print(f"\nWalk-in multiplier applied to {_walkin_applied} completed/historical tournaments")
print(f"  by source: {_walkin_by_source}")
# Loud warning if family-specific data is missing for nearly all events.
# Without walk_in_family_stats.csv the entire system silently degrades to the
# global estimate path — see AUDIT.md A1/B2.
_total_with_source = sum(_walkin_by_source.values())
if _total_with_source > 0:
    _est_pct = _walkin_by_source['estimate'] / _total_with_source
    if _est_pct > 0.5:
        print(f"  WARNING: {_est_pct:.0%} of walk-in multipliers used 'estimate' fallback. "
              f"Confirm output/walk_in_family_stats.csv exists and is fresh.")

# Sort: live first (by days_remaining desc), then 2026 complete, then historical
status_order = {'live': 0, 'complete': 1, 'historical': 2, 'unknown': 3}
tournaments_out.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

# Count by status
n_live = sum(1 for t in tournaments_out if t['status'] == 'live')
n_complete = sum(1 for t in tournaments_out if t['status'] == 'complete')
n_historical = sum(1 for t in tournaments_out if t['status'] == 'historical')

# K2: walk-in provenance computed at build time. The old string hardcoded
# "94 tournament-years, 24 families, MAPE 6.9%" — the actual stats file carries
# different counts and no MAPE is ever computed for the walk-in leg, so the MAPE
# was unverifiable. State the real family/year coverage and drop the MAPE.
_wi_stats_path = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
if os.path.exists(_wi_stats_path):
    _wi = pd.read_csv(_wi_stats_path)
    _walkin_prov = f"{int(_wi['n_years'].sum())} family-years across {len(_wi)} families"
else:
    _walkin_prov = "family-level historical standings-to-prereg ratios"

output = {
    "generated": TODAY.strftime('%Y-%m-%d'),
    "generated_time": pd.Timestamp.now(tz='America/New_York').isoformat(),
    "model": "N5v4_Final",
    "model_description": ("Ensemble model (N5v4): historical ratio (harmonic mean) + per-family pooled Huber regression (final ~ count_at_T + T). T anchored to event_start. T-dependent weights (ratio: 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). 80% CI from lognormal prediction intervals, LOO-calibrated with T-dependent shrinkage. Rolling retraining on completed 2026 tournaments. Automated bias + CI recalibration. Walk-in multiplier: post-hoc adjustment using historical standings-to-prereg ratios (" + _walkin_prov + ")."),
    "n_completed_in_training": len(completed_tids) if completed_tids else 0,
    "tournaments": tournaments_out
}

# Print summary
print(f"\nGenerated {len(tournaments_out)} tournaments ({n_live} live, {n_complete} complete 2026, {n_historical} historical)")

# AUDIT.md B1 — surface prediction-tier distribution so silent fallback is visible
if hasattr(prod_model, '_tier_counts'):
    tier_counts = dict(prod_model._tier_counts)
    total = sum(tier_counts.values())
    if total > 0:
        print(f"\nPrediction tier distribution (n={total}):")
        for tier, count in sorted(tier_counts.items(), key=lambda kv: -kv[1]):
            print(f"  {tier:<22} {count:>4}  ({100*count/total:>4.1f}%)")
        size_matched = tier_counts.get('size-matched', 0) + tier_counts.get('guard-no-ratios', 0)
        if total > 0 and size_matched / total > 0.20:
            print(f"  WARNING: {100*size_matched/total:.0f}% of predictions used size-matched fallback "
                  f"or had no ratios. Family coverage is degraded.")
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
    all_2026 = {canonicalize_family(t['family']): t['current_count'] for t in tournaments_out if t.get('year') == 2026}
    live_2026 = {canonicalize_family(t['family']): t['current_count'] for t in tournaments_out if t.get('year') == 2026 and t.get('status') == 'live'}
    # Tournaments that are intentionally excluded (completed, blitz, WO sub-events, etc.)
    excluded_or_complete = {canonicalize_family(f) for f in EXCLUDE_FAMILIES}
    excluded_or_complete.update(canonicalize_family(t['family']) for t in tournaments_out if t.get('year') == 2026 and t.get('status') in ('complete', 'in_progress'))
    link_warnings = []
    for _, s in latest_scrape.iterrows():
        sn = s['tournament_name']
        fam = sn.replace('2026 ', '', 1) if sn.startswith('2026 ') else sn
        fam_canon = canonicalize_family(fam)
        if fam_canon in excluded_or_complete:
            continue
        scrape_count = int(s['active_count']) if pd.notna(s['active_count']) and s['active_count'] > 0 else int(s['entry_count'])
        if scrape_count > 0 and fam_canon in live_2026 and live_2026[fam_canon] == 0:
            link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, website=0")
        elif scrape_count > 0 and fam_canon not in all_2026:
            link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, NOT IN OUTPUT")
    if link_warnings:
        print(f"\n{'!'*60}")
        print(f"  DATA LINKING WARNINGS — {len(link_warnings)} tournaments with scrape data not reflected in output:")
        for w in link_warnings:
            print(w)
        print(f"{'!'*60}")
    else:
        print("\n✓ Data linking check passed: all scraped tournaments reflected in output")
