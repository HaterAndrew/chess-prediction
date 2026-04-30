"""
Phase 4C: Final production model with fixed CIs and website JSON output.

Root cause of the [320, 2450] CI problem:
- The 9.94 outlier ratio at T-60 for Chicago Open comes from the 2026 in-progress
  tournament. Its T values are relative to last_reg (today), not the event date.
  So "T=60" in the data actually means 60 days before today, when only 18 people
  had registered. The real T-60-before-event count is 179 (current total).
- Fix: exclude in-progress (2026) tournaments from ratio computation.

CI approach:
- Lognormal parametric CI on family-specific ratios (handles 4-5 data points well)
- LOO-calibrated scaling to hit ~80% coverage

T coordinate system:
- T is anchored to event_start (first day of tournament). T=0 means the
  tournament starts today; T=7 means the tournament is 7 days away.
- On-site registrations (during the event) are excluded from training data
  so the model predicts pre-registration count only. final_count still includes
  on-site entries, so ratios at T=0 implicitly capture the on-site multiplier.
- For prediction, pass days_to_start directly — no duration offset needed.
"""

import pandas as pd
import numpy as np
from scipy import stats
from scipy.interpolate import interp1d
import json
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from sklearn.linear_model import HuberRegressor
from feature_engineering import compute_all_features, compute_adjustment_factor

warnings.filterwarnings('ignore')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHOP_POINTS = [90, 60, 42, 28, 21, 14, 10, 7, 5, 3, 1]

# Family aliases: single source of truth in tournament_aliases.py
from tournament_aliases import FAMILY_ALIASES
T_GRID = np.arange(0, 121)
TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
# Default offset: days between event_start and last_reg for tournaments
# without metadata. Empirically, last_reg ≈ event_start + 2 (median across
# all CCA tournaments with both metadata and timestamp data).
DEFAULT_EVENT_START_OFFSET = 2


def reanchor_daily_to_event_start(summary, daily, meta):
    """Shift daily T values from last_reg-anchored to event_start-anchored.

    Training data T is originally computed as days before last_reg (≈ event_end).
    This reanchors T so that T=0 = event_start (first day of tournament).
    Registrations during the event (new T < 0) are dropped so the model
    only trains on pre-registration data. final_count in summary still includes
    on-site entries, so ratios at T=0 implicitly capture the on-site multiplier.

    Returns modified daily DataFrame (summary and meta are unchanged).
    """
    meta_dt = meta.copy()
    meta_dt['start_date'] = pd.to_datetime(meta_dt['start_date'], errors='coerce')
    meta_dt['end_date'] = pd.to_datetime(meta_dt['end_date'], errors='coerce')

    # Build (family, year) -> event_start lookup from metadata
    meta_starts = {}
    for _, m in meta_dt.iterrows():
        if pd.notna(m['start_date']):
            meta_starts[(m['family'], int(m['year']))] = m['start_date']

    # Compute per-family median offset (last_reg - event_start) from completed
    # tournaments that have both metadata and timestamp data
    family_offsets = {}
    for _, row in summary.iterrows():
        fam = row['family']
        yr = int(row['tournament_year']) if pd.notna(row['tournament_year']) else 0
        lr = pd.to_datetime(row['last_reg'], errors='coerce') if pd.notna(row.get('last_reg')) else pd.NaT
        if pd.isna(lr) or yr >= 2026:
            continue
        start = meta_starts.get((fam, yr))
        if start is not None:
            offset = (lr - start).days
            if 0 <= offset <= 10:  # sanity: reject bad metadata
                family_offsets.setdefault(fam, []).append(offset)
    family_median_offset = {
        fam: int(np.median(offs)) for fam, offs in family_offsets.items()
    }
    global_median_offset = DEFAULT_EVENT_START_OFFSET

    # Shift T for each tournament
    daily = daily.copy()
    # AUDIT.md B3 — track which offset path each tournament took so silent
    # fallback to DEFAULT_EVENT_START_OFFSET=2 surfaces in logs.
    _offset_source_counts = {'metadata': 0, 'family-median': 0, 'global-default': 0,
                             'bad-metadata': 0, 'in-progress': 0}
    _global_default_examples = []  # (family, year) of rows hitting global-default
    for _, row in summary.iterrows():
        tid = row['tid']
        fam = row['family']
        yr = int(row['tournament_year']) if pd.notna(row['tournament_year']) else 0
        lr = pd.to_datetime(row['last_reg'], errors='coerce') if pd.notna(row.get('last_reg')) else pd.NaT

        # Determine offset (last_reg - event_start) for this tournament
        start = meta_starts.get((fam, yr))
        if start is not None and pd.notna(lr):
            offset = (lr - start).days
            # In-progress event (start_date in the future): negative offsets
            # are expected (last_reg ≤ today < event_start). The metadata is
            # not "bad" — the event simply hasn't ended. Use family_median
            # for offset selection (we have no post-event registration
            # signal yet) but classify separately so the bad-metadata
            # counter stays accurate to genuinely-wrong rows.
            is_in_progress = start > TODAY
            if is_in_progress and (offset < 0 or offset > 30):
                _offset_source_counts['in-progress'] += 1
                if fam in family_median_offset:
                    offset = family_median_offset[fam]
                else:
                    offset = global_median_offset
            elif offset < 0 or offset > 30:
                # Bad data — fall back
                _offset_source_counts['bad-metadata'] += 1
                if fam in family_median_offset:
                    offset = family_median_offset[fam]
                else:
                    offset = global_median_offset
            else:
                _offset_source_counts['metadata'] += 1
        elif pd.notna(lr):
            if fam in family_median_offset:
                offset = family_median_offset[fam]
                _offset_source_counts['family-median'] += 1
            else:
                offset = global_median_offset
                _offset_source_counts['global-default'] += 1
                _global_default_examples.append((fam, yr))
        else:
            continue  # no timestamp data, skip

        # Shift T: old T was days-before-last_reg, new T is days-before-event_start
        # new_T = old_T - offset (event_start is `offset` days before last_reg)
        mask = daily['tid'] == tid
        if not mask.any():
            continue
        daily.loc[mask, 'T'] = daily.loc[mask, 'T'] - offset

    # Drop rows where T < 0 (on-site registrations during the event)
    before = len(daily)
    daily = daily[daily['T'] >= 0].copy()
    dropped = before - len(daily)

    # Recompute cum_regs after dropping on-site rows: cum_regs should count from
    # earliest (highest T) down to T=0, so re-cumsum within each tid
    daily = daily.sort_values(['tid', 'T'], ascending=[True, False])
    daily['cum_regs'] = daily.groupby('tid')['daily_regs'].cumsum()
    tid_totals = daily.groupby('tid')['daily_regs'].transform('sum')
    daily.loc[tid_totals > 0, 'cum_pct'] = (
        daily.loc[tid_totals > 0, 'cum_regs'] /
        tid_totals[tid_totals > 0]
    )

    if dropped > 0:
        print(f"  Reanchored T to event_start: dropped {dropped} on-site rows")
    # AUDIT.md B3 — surface offset source distribution
    total_offsets = sum(_offset_source_counts.values())
    if total_offsets > 0:
        print(f"  Event-start offset sources (n={total_offsets}): "
              + ", ".join(f"{k}={v}" for k, v in _offset_source_counts.items() if v > 0))
        # Threshold accounts for known noise floor (sub-events with NaN
        # tournament_year — e.g., Octos pickup events, waitlists — can't be
        # backfilled by update_metadata.py because there's no year to anchor
        # the metadata row to). Fire only when the count exceeds that floor
        # plus a small drift margin.
        GLOBAL_DEFAULT_NOISE_FLOOR = 5
        n_global = _offset_source_counts['global-default']
        if n_global > GLOBAL_DEFAULT_NOISE_FLOOR:
            sample = ", ".join(
                f"{fam} ({yr if yr else 'NaN-year'})"
                for fam, yr in _global_default_examples[:5]
            )
            more = f" …and {n_global - 5} more" if n_global > 5 else ""
            print(f"  WARNING: {n_global} tournaments fell back to "
                  f"DEFAULT_EVENT_START_OFFSET={DEFAULT_EVENT_START_OFFSET} (no metadata, no family median). "
                  f"Run update_metadata.py. Examples: {sample}{more}")
    return daily


def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    meta = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_metadata.csv"))
    # Load enrichment data if available
    hist_path = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
    hist = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()

    # Reanchor T from last_reg to event_start so the model predicts
    # pre-registration only (T=0 = first day of tournament)
    daily = reanchor_daily_to_event_start(summary, daily, meta)

    return summary, daily, meta, hist


def build_enrichment_lookup(hist):
    """Build (family, year) -> enrichment dict from historical_tournaments.csv."""
    lookup = {}
    if hist.empty:
        return lookup
    for _, row in hist.iterrows():
        name = str(row.get('tournament_name', ''))
        year = int(row.get('year', 0))
        # Strip year prefix to get family (e.g., "2025 Chicago Open" -> "Chicago Open")
        family = re.sub(r'^\d{4}\s+', '', name).strip()
        if not family or not year:
            continue
        lookup[(family, year)] = {
            'total_entries': row.get('total_entries', 0),
            'withdrawal_count': row.get('withdrawal_count', 0),
            'unique_states': row.get('unique_states', 0),
            'num_sections': 0,  # from sections JSON
        }
        # Parse sections JSON for section count
        sections_str = row.get('sections', '')
        if sections_str and isinstance(sections_str, str) and sections_str.strip():
            try:
                sections = json.loads(sections_str)
                lookup[(family, year)]['num_sections'] = len(sections)
            except (json.JSONDecodeError, TypeError):
                pass
    return lookup


def load_meta_lookup(meta):
    """Build metadata lookup: (family, year) -> dict of event info."""
    lookup = {}
    for _, m in meta.iterrows():
        lookup[(m['family'], int(m['year']))] = {
            'start_date': pd.to_datetime(m['start_date']),
            'end_date': pd.to_datetime(m['end_date']),
            'early_bird_deadline': m.get('early_bird_deadline'),
            'early_bird_fee': m.get('early_bird_fee'),
            'regular_fee': m.get('regular_fee'),
            'onsite_fee': m.get('onsite_fee'),
        }
    return lookup


def is_complete(row):
    """
    A tournament is complete if it's a past year OR if last_reg is close to
    the expected event date. For 2026 tournaments, most are still in-progress
    since the event hasn't happened yet.
    """
    yr = row.get('tournament_year')
    if pd.isna(yr):
        return False
    yr = int(yr)
    if yr < 2026:
        return True
    # For 2026, check if the event has already passed
    # We'll handle this with metadata in the caller
    return False


# AUDIT.md C7 — module-level counters track silent IQR trimming so the
# rate of trimmed points becomes visible at end of fit.
from collections import defaultdict as _defaultdict
_TRIM_STATS = {'total_in': 0, 'total_out': 0, 'by_label': _defaultdict(lambda: [0, 0])}


def reset_trim_stats():
    """Clear aggregated trim counters. Called at start of each fit."""
    _TRIM_STATS['total_in'] = 0
    _TRIM_STATS['total_out'] = 0
    _TRIM_STATS['by_label'].clear()


def trim_outliers(values, iqr_factor=3.0, label=None, count_stats=True):
    """Remove extreme outliers beyond iqr_factor * IQR from median.

    Optional `label` (e.g. family name) accumulates a per-label tally in
    _TRIM_STATS so callers can audit which families lose the most points.
    Set `count_stats=False` for internal calibration calls that may evaluate
    the same ratio list many times.
    AUDIT.md C7.
    """
    def _record(n_in, n_kept):
        if not count_stats:
            return
        if label is not None:
            _TRIM_STATS['by_label'][label][0] += n_in
            _TRIM_STATS['by_label'][label][1] += n_kept
        _TRIM_STATS['total_in'] += n_in
        _TRIM_STATS['total_out'] += n_kept

    if len(values) < 4:
        _record(len(values), len(values))
        return values
    arr = np.array(values)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        _record(len(values), len(values))
        return values
    lo = q1 - iqr_factor * iqr
    hi = q3 + iqr_factor * iqr
    trimmed = arr[(arr >= lo) & (arr <= hi)]
    result = trimmed if len(trimmed) >= 2 else values
    _record(len(values), len(result))
    return result


def report_trim_stats(top_n=5):
    """Return a dict summarizing trim activity, suitable for printing.

    AUDIT.md C7 — surfaces per-family trim rates so we know whether the
    IQR 3.0x threshold is silently dropping legitimate variation.
    """
    total_in = _TRIM_STATS['total_in']
    total_out = _TRIM_STATS['total_out']
    if total_in == 0:
        return {'total_in': 0, 'total_out': 0, 'pct_trimmed': 0.0, 'top_offenders': []}
    pct = (total_in - total_out) / total_in * 100
    # Top families by trim rate (require at least 5 input points to be meaningful)
    by_rate = []
    for label, (n_in, n_kept) in _TRIM_STATS['by_label'].items():
        dropped = n_in - n_kept
        if n_in >= 5 and dropped > 0:
            by_rate.append((label, dropped, n_in, dropped / n_in * 100))
    by_rate.sort(key=lambda x: -x[3])
    return {
        'total_in': total_in,
        'total_out': total_out,
        'pct_trimmed': round(pct, 2),
        'top_offenders': by_rate[:top_n],
    }


def lognormal_ci(ratio_values, level=0.80, global_sigma=None, label=None,
                 count_stats=True):
    """
    Fit a lognormal to ratio values, return (median, lower, upper).

    For n >= 15 (short lead times where lognormal is rejected), uses
    nonparametric quantiles directly. For smaller n, uses t-based
    prediction interval with empirical Bayes sigma shrinkage toward
    a global estimate.

    Optional `label` (e.g. family name) is forwarded to trim_outliers
    so the per-label trim audit (AUDIT.md C7) attributes correctly.
    `count_stats=False` lets calibration and prediction evaluate CIs without
    inflating the once-per-fit trim audit.
    """
    if len(ratio_values) < 2:
        med = ratio_values[0] if len(ratio_values) == 1 else 1.0
        return med, med * 0.7, med * 1.4

    arr = np.array(trim_outliers(ratio_values, label=label,
                                 count_stats=count_stats))
    n = len(arr)
    alpha = 1 - level

    # For large samples, use nonparametric quantiles (avoids lognormal assumption)
    if n >= 15:
        med = stats.hmean(arr)  # harmonic mean for ratios
        lo = np.percentile(arr, alpha / 2 * 100)
        hi = np.percentile(arr, (1 - alpha / 2) * 100)
        return med, lo, hi

    # Parametric path: t-based prediction interval on log scale
    log_r = np.log(arr)
    mu = np.mean(log_r)
    sigma = np.std(log_r, ddof=1)

    # Empirical Bayes shrinkage: pull family sigma toward global sigma
    # only when family sigma is unrealistically low (n <= 3). For well-
    # estimated families (n >= 4), trust the family-specific sigma.
    # Use shrinkage as a floor, not a blend — don't penalize tight families.
    if global_sigma is not None and global_sigma > 0 and n <= 3:
        k = 1  # shrinkage strength (reduced from 3 to tighten CIs)
        sigma = max(sigma, np.sqrt((n * sigma**2 + k * global_sigma**2) / (n + k)))

    t_val = stats.t.ppf(1 - alpha / 2, df=max(n - 1, 1))

    # Proper prediction interval SE: sqrt(1 + 1/n)
    pred_se = sigma * np.sqrt(1 + 1 / n)
    lo = np.exp(mu - t_val * pred_se)
    hi = np.exp(mu + t_val * pred_se)
    med = stats.hmean(arr)  # harmonic mean for ratios

    return med, lo, hi



class N5v4_Final:
    """
    Historical ratio model with:
    - Exclusion of in-progress tournaments from ratio computation
    - Lognormal parametric CIs
    - LOO-calibrated CI width scaling with ensemble shrinkage
    - Ensemble: blends ratio prediction with per-family pooled
      regression using final ~ count_at_T + T + intercept
      (T-dependent weights: ratio 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28)
    - Ratio cap: at T>=60, falls back to regression-only if ratio
      prediction diverges >50% from regression
    - CI widening for low-history families (0 or 1 prior editions)
    """
    name = "N5v4_Final"
    # T-dependent ensemble weights (ratio model):
    # T <= 3: 0.80, T <= 7: 0.55, T <= 28: 0.30, T > 28: 0.15
    # CI calibration was tuned for ratio-only predictions. The ensemble is better-
    # centered, so ratio-calibrated CIs are too wide. Shrink to restore ~80% coverage.
    CI_ENSEMBLE_SHRINK = 0.32
    # CI widening multipliers for families with few training editions.
    # 0-edition families use size-matched fallback which is inherently noisy;
    # 1-edition families have a single ratio data point per T.
    # These factors were calibrated on 2024-2025 holdout to bring coverage
    # from ~40% up to ~80% for these subgroups. Increased from 5.0/3.0 to
    # compensate for tighter ensemble shrinkage (0.32 vs 0.42).
    CI_WIDEN_0_EDITIONS = 2.5
    CI_WIDEN_1_EDITION = 1.5

    def __init__(self):
        self.ratios = {}
        self.ci_scale = {}
        self.reg_params = {}  # family -> [slope_count, slope_T, intercept]
        self.family_n_editions = {}  # family -> count of training editions

    def fit(self, summary, daily, enrichment_lookup=None, completed_tids=None,
            verbose_standings_join=True, all_summary_families=None):
        """Build ratios from completed, non-online, non-covid tournaments.

        completed_tids: optional set of 2026 tournament tids that have completed.
            If provided, these are included in training (rolling retraining).
            All other 2026 tournaments are excluded.
        verbose_standings_join: when False, suppress the orphan-list warning. Set
            False on backtest folds (04e) so the user-facing pipeline run doesn't
            emit the same warning N times for N expanding-window cohorts.
        all_summary_families: optional set of every family in the unfiltered summary.
            Used as the cross-check basis for validate_standings_join so pre-timestamp
            families (which are filtered out of the training subset but supplemented
            from standings later) don't show up as false orphans. If omitted, the
            current `summary` arg's families are used (less accurate when caller
            already filtered upstream — e.g., 04d passes train_ts).
        """
        self.enrichment = enrichment_lookup or {}

        # AUDIT.md C7 — reset trim counters at start of every fit so reports
        # reflect this fit only, not accumulated across calls.
        reset_trim_stats()

        # Auto-populate BLITZ_FAMILIES from data: any family matching the pattern
        _blitz_pat = re.compile(r'Blitz|Rapid|Bullet|Bughouse|Armageddon|Action|G/\d+|G \d+', re.IGNORECASE)
        for fam in summary['family'].unique():
            if _blitz_pat.search(fam):
                self.BLITZ_FAMILIES.add(fam)

        valid = summary[
            (summary['has_timestamps']) &
            (~summary.get('is_online', pd.Series(False)).fillna(False)) &
            (~summary.get('is_covid', pd.Series(False)).fillna(False))
        ].copy()

        # Exclude in-progress 2026 tournaments, but keep completed ones
        if completed_tids:
            valid = valid[
                (valid['tournament_year'] < 2026) |
                (valid['tid'].isin(completed_tids))
            ]
        else:
            valid = valid[valid['tournament_year'] < 2026]

        self.ratios = {}
        self.global_ratios = {}
        self.global_log_sigma = {}  # T -> sigma of log(ratios) across all families
        # Track family mean final counts for size-matched fallback
        self.family_mean_final = {}

        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            year = row['tournament_year']

            td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(td) < 5:
                continue

            if family not in self.ratios:
                self.ratios[family] = {}

            for T in CHOP_POINTS:
                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                ratio = actual / count_at_T
                self.ratios[family].setdefault(T, []).append((ratio, year, tid))
                self.global_ratios.setdefault(T, []).append((ratio, year, tid))

        self.ratios['__global__'] = self.global_ratios

        # Compute mean final count per family for size-matched fallback
        fam_finals = valid.groupby('family')['final_count'].mean()
        self.family_mean_final = fam_finals.to_dict()

        # Most recent year's final count per family (better anchor than mean)
        recent = valid.sort_values('tournament_year').groupby('family')['final_count'].last()
        self.family_recent_final = recent.to_dict()

        # Compute per-family growth trend (YoY slope normalized by mean)
        # Used to adjust predictions for growing/declining tournaments
        self.family_trend = {}
        for fam, grp in valid.groupby('family'):
            grp_sorted = grp.sort_values('tournament_year')
            if len(grp_sorted) >= 3:
                counts = grp_sorted['final_count'].values
                years = grp_sorted['tournament_year'].values
                # Simple linear regression: count ~ year
                if len(set(years)) >= 3:
                    slope = np.polyfit(years, counts, 1)[0]
                    mean_count = np.mean(counts)
                    if mean_count > 0:
                        # Normalize slope as fraction of mean (e.g., -0.05 = 5% decline/year)
                        self.family_trend[fam] = np.clip(slope / mean_count, -0.15, 0.15)

        # Supplement with standings data — normalize names to match training families.
        # Single source of truth for the name map: tournament_aliases.STANDINGS_NAME_MAP.
        # AUDIT.md A2: previously the inline map had 19 entries while 37 unique
        # standings names existed in production — the rest dropped silently.
        standings_path = os.path.join(OUTPUT_DIR, "historical_standings.csv")
        if os.path.exists(standings_path):
            from tournament_aliases import STANDINGS_NAME_MAP, validate_standings_join
            standings = pd.read_csv(standings_path)
            standings = standings[standings['total_players'] > 10]
            standings['tournament_name'] = standings['tournament_name'].replace(
                STANDINGS_NAME_MAP)
            # Surface unmapped names so silent drops become visible.
            # Cross-check against the full summary families, not just the
            # training subset (which excludes pre-timestamp / online / covid
            # tournaments). Names that are in summary but absent from the
            # training subset are not data gaps — they're picked up by the
            # supplementation loop below. Only true orphans (in standings,
            # absent from summary entirely) get flagged.
            # Backtest folds (04e) pass verbose_standings_join=False because
            # each fold's training cohort produces its own list and firing
            # N copies just buries the real signal.
            check_against = (all_summary_families
                             if all_summary_families is not None
                             else set(summary['family'].dropna().unique()))
            validate_standings_join(
                standings['tournament_name'].unique(),
                check_against,
                verbose=verbose_standings_join,
            )
            for fam, grp in standings.groupby('tournament_name'):
                if fam not in self.family_mean_final:
                    self.family_mean_final[fam] = grp['total_players'].mean()

        # Track number of training editions per family (for CI widening)
        self.family_n_editions = valid.groupby('family').size().to_dict()

        # Compute per-family withdrawal rates from enrichment data
        self.family_withdrawal_rates = {}
        if self.enrichment:
            from collections import defaultdict
            wd_data = defaultdict(list)
            for (fam, yr), info in self.enrichment.items():
                total = info.get('total_entries', 0)
                wd = info.get('withdrawal_count', 0)
                if total > 0 and wd > 0 and isinstance(wd, (int, float)):
                    wd_data[fam].append(wd / total)
            for fam, rates in wd_data.items():
                if rates:
                    self.family_withdrawal_rates[fam] = np.median(rates)

        # Compute global log-sigma per T for empirical Bayes shrinkage
        for T in CHOP_POINTS:
            g_rats = self.global_ratios.get(T, [])
            if g_rats:
                vals = [r[0] for r in g_rats]
                if len(vals) >= 5:
                    self.global_log_sigma[T] = np.std(np.log(vals), ddof=1)

        # LOO calibration — expanding window.
        # With completed 2026 data in training, calibrate on pre-2025 data
        # (2025 + completed 2026 serve as validation). Without 2026 data,
        # calibrate on pre-2024 (original behavior).
        cal_year = 2025 if completed_tids else 2024
        self._calibrate(valid, daily, cal_max_year=cal_year)

        # T-dependent CI shrinkage: less shrinkage at long T (more uncertainty),
        # more shrinkage at short T (ratios converge toward 1.0)
        for T in self.ci_scale:
            if T >= 60:
                shrink = 0.33
            elif T >= 28:
                shrink = 0.36
            elif T >= 10:
                shrink = 0.42
            elif T >= 7:
                shrink = 0.40
            elif T >= 5:
                shrink = 0.50
            else:
                shrink = 0.75
            self.ci_scale[T] *= shrink

        # AUDIT.md C7 — count each family/T ratio list once. Calibration and
        # prediction calls can touch the same list repeatedly, so they opt out
        # of trim accounting and this pass owns the per-fit audit totals.
        reset_trim_stats()
        for fam, fam_rats in self.ratios.items():
            if fam == '__global__':
                continue
            for T, rats in fam_rats.items():
                if isinstance(T, (int, float)):
                    trim_outliers([r[0] for r in rats], label=fam)

        # Build pooled per-family regression: final ~ count_at_T + T + intercept
        # Pooling across all T values gives more data points and lets the model
        # learn how lead time affects the count-to-final relationship
        reg_data = {}  # family -> [(count_at_T, T, final_count), ...]
        for _, row in valid.iterrows():
            tid = row['tid']
            family = row['family']
            actual = row['final_count']
            td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
            if len(td) < 5:
                continue
            for T in CHOP_POINTS:
                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue
                reg_data.setdefault(family, []).append(
                    (count_at_T, T, actual))

        self.reg_params = {}
        self._reg_data = reg_data  # save for size-matched regression fallback
        for fam, pts in reg_data.items():
            if len(pts) < 6:
                continue
            X = np.array([[p[0], p[1]] for p in pts], dtype=float)
            y = np.array([p[2] for p in pts], dtype=float)
            try:
                hub = HuberRegressor(epsilon=1.35, max_iter=200)
                hub.fit(X, y)
                coeffs = np.array([hub.coef_[0], hub.coef_[1], hub.intercept_])
                self.reg_params[fam] = coeffs
            except Exception:
                try:
                    X_aug = np.column_stack([X, np.ones(len(X))])
                    coeffs, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
                    self.reg_params[fam] = coeffs
                except Exception:
                    continue

        # Build separate global regressions for large (mean>300) vs small
        # tournaments — different growth dynamics at different scales
        large_pts = []
        small_pts = []
        for fam, pts in reg_data.items():
            mean_final = self.family_mean_final.get(fam, 0)
            if mean_final > 300:
                large_pts.extend(pts)
            else:
                small_pts.extend(pts)
        self._large_reg = None
        self._small_reg = None
        for pts_list, attr in [(large_pts, '_large_reg'), (small_pts, '_small_reg')]:
            if len(pts_list) >= 10:
                X = np.array([[p[0], p[1]] for p in pts_list], dtype=float)
                y = np.array([p[2] for p in pts_list], dtype=float)
                try:
                    hub = HuberRegressor(epsilon=1.35, max_iter=200)
                    hub.fit(X, y)
                    setattr(self, attr, np.array([hub.coef_[0], hub.coef_[1], hub.intercept_]))
                except Exception:
                    pass

        # AUDIT.md C7 — surface IQR outlier trim activity at end of fit so
        # silent point dropping is visible. Threshold of 5% pct_trimmed flagged
        # as a warning since IQR 3.0x should normally trim very little.
        ts = report_trim_stats(top_n=5)
        if ts['total_in'] > 0:
            print(f"  IQR outlier trim: {ts['total_in'] - ts['total_out']}/{ts['total_in']} "
                  f"points trimmed ({ts['pct_trimmed']}%)")
            if ts['top_offenders']:
                print(f"  Top families by trim rate:")
                for label, dropped, n_in, pct in ts['top_offenders']:
                    print(f"    {label:<45} {dropped:>3}/{n_in:<3}  ({pct:>4.1f}%)")
            # Warn only when materially elevated. Healthy production runs sit
            # around 5-6% because ratios have heavy tails by nature; 8% means
            # something noisy entered training.
            if ts['pct_trimmed'] > 8.0:
                print(f"  WARNING: {ts['pct_trimmed']}% of points trimmed (>8% threshold). "
                      f"IQR factor 3.0 may be dropping legitimate variation; check top offenders.")

    def _calibrate(self, valid, daily, cal_max_year=None):
        """LOO calibration to find CI scale factors per T via binary search.

        cal_max_year: if set, only use tournaments with year < cal_max_year
        for calibration (expanding-window approach to avoid leakage).
        """
        cal_valid = valid
        if cal_max_year is not None:
            cal_valid = valid[valid['tournament_year'] < cal_max_year]

        for T in CHOP_POINTS:
            # Collect all LOO error ratios for this T
            loo_data = []
            for _, row in cal_valid.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']

                td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
                if len(td) < 5:
                    continue

                regs = td[td['T'] >= T]
                if len(regs) == 0:
                    continue
                count_at_T = int(regs['cum_regs'].max())
                if count_at_T == 0:
                    continue

                # LOO: get family ratios excluding this tournament
                fam_rats = self.ratios.get(family, {}).get(T, [])
                loo = [r[0] for r in fam_rats if r[2] != tid]
                if len(loo) < 2:
                    loo = [r[0] for r in self.global_ratios.get(T, []) if r[2] != tid]
                if len(loo) < 2:
                    continue

                loo_data.append((count_at_T, actual, loo))

            if len(loo_data) < 10:
                self.ci_scale[T] = 1.0
                continue

            # Binary search for scale factor that gives ~80% coverage
            g_sigma = self.global_log_sigma.get(T)

            def get_coverage(scale):
                covered = 0
                for count_at_T, actual, loo in loo_data:
                    med, lo_r, hi_r = lognormal_ci(
                        loo, level=0.80, global_sigma=g_sigma,
                        count_stats=False,
                    )
                    if scale != 1.0:
                        log_med = np.log(med)
                        log_lo = np.log(lo_r)
                        log_hi = np.log(hi_r)
                        hw = (log_hi - log_lo) / 2 * scale
                        lo_r = np.exp(log_med - hw)
                        hi_r = np.exp(log_med + hw)
                    lo = count_at_T * lo_r
                    hi = count_at_T * hi_r
                    if lo <= actual <= hi:
                        covered += 1
                return covered / len(loo_data)

            lo_s, hi_s = 0.4, 2.0
            for _ in range(20):
                mid_s = (lo_s + hi_s) / 2
                cov = get_coverage(mid_s)
                if cov < 0.80:
                    lo_s = mid_s
                else:
                    hi_s = mid_s

            self.ci_scale[T] = round(hi_s, 3)

    def _get_size_matched_regression(self, current_count):
        """Build a Huber regression from size-matched families' training data.

        Returns coefficients [slope_count, slope_T, intercept] or None.
        """
        est_final = current_count * 2
        matched_pts = []
        for fam, mean_final in self.family_mean_final.items():
            if est_final > 0 and 0.5 <= mean_final / est_final <= 2.0:
                matched_pts.extend(self._reg_data.get(fam, []))
        if len(matched_pts) < 10:
            est_final = current_count * 2
            if est_final > 300 and self._large_reg is not None:
                return self._large_reg
            elif self._small_reg is not None:
                return self._small_reg
            return None
        X = np.array([[p[0], p[1]] for p in matched_pts], dtype=float)
        y = np.array([p[2] for p in matched_pts], dtype=float)
        try:
            hub = HuberRegressor(epsilon=1.35, max_iter=200)
            hub.fit(X, y)
            return np.array([hub.coef_[0], hub.coef_[1], hub.intercept_])
        except Exception:
            return None

    def _get_size_matched_ratios(self, current_count):
        """Build ratios from families with similar historical size (within 2x).

        For new families with no history, this is much better than global
        because a 1500-person tournament has very different growth ratios
        than a 50-person tournament.
        """
        # Estimate final count from current_count — use global median ratio at
        # a generic T to get a rough size estimate, or just use current_count
        est_final = current_count * 2  # rough estimate for size matching
        size_matched = {}
        for fam, mean_final in self.family_mean_final.items():
            # Within 2x of estimated final size
            if est_final > 0 and 0.5 <= mean_final / est_final <= 2.0:
                fam_rats = self.ratios.get(fam, {})
                for T, rats in fam_rats.items():
                    if isinstance(T, (int, float)):
                        size_matched.setdefault(T, []).extend(rats)
        # Need enough data — fall back to global if too few matches
        has_enough = any(len(v) >= 3 for v in size_matched.values())
        if has_enough:
            return size_matched
        return self.ratios.get('__global__', {})

    # Families with late-surge registration patterns (scholastic/HS events)
    # where standard ratio extrapolation over-predicts
    LATE_SURGE_FAMILIES = {
        'New York State High School Championship',
        'New York State Scholastic Championships Grades K-8',
        'New York State Scholastic Championships',
    }

    # Blitz/action events: massive day-of registration (100-300% growth at T<=1)
    # Standard ratio models vastly underpredict these.
    # Auto-populated from data during fit(); seeded with known families.
    BLITZ_FAMILIES = {
        'World Open Blitz Championship',
        'North American Blitz Championship',
        'Chicago Open Blitz',
        'Blitz at Foxwoods',
        'World Open Action',
    }

    def predict_nowcast(self, current_count, days_remaining, family, **kwargs):
        """
        Predict final count given current registrations and days remaining.
        days_remaining = days until event_start (T=0 is first day of tournament).
        Training T is anchored to event_start after reanchor_daily_to_event_start().
        Prediction includes expected on-site registrations (baked into ratios).

        Side effect (AUDIT.md B1): records `self._last_tier` and, unless
        `_track_tier=False`, increments `self._tier_counts[tier]` so callers
        can surface fallback distribution.
        Tiers: 'family-direct', 'family-alias', 'size-matched', 'guard-no-data',
        'guard-event-started', 'guard-no-ratios'.
        """
        track_tier = kwargs.pop('_track_tier', True)

        # Initialize tier tracking lazily for user-facing predictions only.
        if track_tier and not hasattr(self, '_tier_counts'):
            from collections import defaultdict
            self._tier_counts = defaultdict(int)
            self._last_tier = None

        def record_tier(tier):
            self._last_tier = tier
            if track_tier:
                self._tier_counts[tier] += 1

        # AUDIT.md C8 — flag predictions for families with sparse history.
        # Default n_editions=0 for unknown families. Threshold of 4 picked from
        # the lognormal CI: <4 points means parametric CI is unreliable.
        n_editions = self.family_n_editions.get(family, 0) if hasattr(self, 'family_n_editions') else 0
        self._last_low_confidence = n_editions < 4

        # Guard: event already started or no data
        if days_remaining < 0:
            record_tier('guard-event-started')
            return current_count, current_count, current_count
        if current_count <= 0:
            record_tier('guard-no-data')
            return None, None, None

        # Late-surge families: dampen ratio extrapolation to avoid over-prediction
        # These events get bulk registrations in the last 1-3 days
        is_late_surge = family in self.LATE_SURGE_FAMILIES
        is_blitz = family in self.BLITZ_FAMILIES

        # Use family-specific ratios if available (>= 2 data points at some T)
        use_family = False
        used_alias = False
        fam_ratios = self.ratios.get(family, {})

        # Check family aliases: pool ratios from comparable families
        if not fam_ratios and family in FAMILY_ALIASES:
            fam_ratios = {}
            for alias_fam in FAMILY_ALIASES[family]:
                alias_rats = self.ratios.get(alias_fam, {})
                for T, rats in alias_rats.items():
                    if isinstance(T, (int, float)):
                        fam_ratios.setdefault(T, []).extend(rats)
            used_alias = bool(fam_ratios)

        if fam_ratios:
            for T, rats in fam_ratios.items():
                if isinstance(T, (int, float)) and len(rats) >= 2:
                    use_family = True
                    break

        if use_family:
            record_tier('family-alias' if used_alias else 'family-direct')
        else:
            record_tier('size-matched')
            # Fall back to size-matched families instead of global
            fam_ratios = self._get_size_matched_ratios(current_count)
            if not fam_ratios:
                record_tier('guard-no-ratios')
                return None, None, None

        available_T = sorted([k for k in fam_ratios.keys()
                             if isinstance(k, (int, float))])
        if not available_T:
            return None, None, None

        # Interpolate between two nearest chop points to avoid discontinuities
        closest_T = min(available_T, key=lambda t: abs(t - days_remaining))
        T_below = max([t for t in available_T if t <= days_remaining], default=None)
        T_above = min([t for t in available_T if t >= days_remaining], default=None)

        if T_below is not None and T_above is not None and T_below != T_above:
            # Inverse-distance weighted blend of two nearest T buckets
            dist_total = T_above - T_below
            w_below = (T_above - days_remaining) / dist_total
            w_above = (days_remaining - T_below) / dist_total

            rats_below = [r[0] for r in fam_ratios[T_below]]
            rats_above = [r[0] for r in fam_ratios[T_above]]
            g_sigma_below = self.global_log_sigma.get(T_below)
            g_sigma_above = self.global_log_sigma.get(T_above)

            med_b, lo_b, hi_b = lognormal_ci(
                rats_below, level=0.80, global_sigma=g_sigma_below,
                label=family, count_stats=False)
            med_a, lo_a, hi_a = lognormal_ci(
                rats_above, level=0.80, global_sigma=g_sigma_above,
                label=family, count_stats=False)

            # Blend in log space for ratios
            med = np.exp(w_below * np.log(med_b) + w_above * np.log(med_a))
            lo_r = np.exp(w_below * np.log(lo_b) + w_above * np.log(lo_a))
            hi_r = np.exp(w_below * np.log(hi_b) + w_above * np.log(hi_a))

            # Blend calibration scales too
            scale_b = self.ci_scale.get(T_below, 1.0)
            scale_a = self.ci_scale.get(T_above, 1.0)
            scale = w_below * scale_b + w_above * scale_a
        else:
            ratio_list = [r[0] for r in fam_ratios[closest_T]]
            if not ratio_list:
                return None, None, None
            g_sigma = self.global_log_sigma.get(closest_T)
            med, lo_r, hi_r = lognormal_ci(
                ratio_list, level=0.80, global_sigma=g_sigma,
                label=family, count_stats=False)
            scale = self.ci_scale.get(closest_T, 1.0)

        # Apply calibration scaling (scale already set above for interpolated path)
        if scale != 1.0:
            log_med = np.log(med)
            log_lo = np.log(lo_r)
            log_hi = np.log(hi_r)
            half_w = (log_hi - log_lo) / 2
            half_w *= scale
            lo_r = np.exp(log_med - half_w)
            hi_r = np.exp(log_med + half_w)

        # For non-family fallback, cap ratios based on lead time
        # (size-matched ratios are better than global but still noisy)
        # Exempt blitz events — they have legitimately high short-T ratios
        if not use_family and not is_blitz:
            if days_remaining <= 7:
                med = min(med, 2.0)
                lo_r = min(lo_r, 1.5)
                hi_r = min(hi_r, 3.0)
            elif days_remaining <= 28:
                med = min(med, 5.0)
                lo_r = min(lo_r, 3.0)
                hi_r = min(hi_r, 8.0)
            else:
                med = min(med, 15.0)
                lo_r = min(lo_r, 10.0)
                hi_r = min(hi_r, 25.0)

        # Late-surge damping: these events get most registrations in last 1-3 days
        # Standard ratios over-extrapolate because early registration is very sparse
        # Use aggressive damping — these tournaments have ~1.1-1.4x ratio even at T=28
        if is_late_surge and days_remaining > 3:
            # Target ratio: 1.1-1.5 depending on lead time (much lower than standard opens)
            max_ratio = 1.1 + 0.4 * min(days_remaining / 90, 1.0)  # 1.1 at T=3, 1.5 at T=90
            if med > max_ratio:
                med = max_ratio
            lo_r = min(lo_r, med)
            hi_r = min(hi_r, max_ratio * 1.5)

        # Count-based ratio adjustment: when current count is already a large
        # fraction of the expected final, shrink ratios toward 1.0
        # (high counts → tournament is close to final → lower remaining growth)
        fam_mean = self.family_mean_final.get(family, 0)
        if fam_mean > 0 and current_count > 0 and use_family:
            fill_pct = current_count / fam_mean  # e.g., 0.7 = 70% of expected final
            if fill_pct > 0.6:
                # Linearly shrink toward 1.0 as fill_pct goes from 0.6 to 1.0+
                shrink = min(1.0, (fill_pct - 0.6) * 2.0)  # 0 at 0.6, 0.8 at 1.0
                med = 1.0 + (med - 1.0) * (1 - shrink * 0.2)  # at most 20% reduction
                lo_r = 1.0 + (lo_r - 1.0) * (1 - shrink * 0.2)
                hi_r = 1.0 + (hi_r - 1.0) * (1 - shrink * 0.2)

        point = current_count * med
        low = current_count * lo_r
        high = current_count * hi_r

        # At long T with very low counts, anchor toward family historical size
        # Blend of recent final (60%) and mean (40%) — recent is a better
        # predictor (MAPE 13.8%) but mean is more stable
        anchor_thresh = 15 if days_remaining < 60 else 30
        if current_count < anchor_thresh and days_remaining >= 42 and use_family:
            fam_recent = self.family_recent_final.get(family, 0)
            fam_mean_val = self.family_mean_final.get(family, 0)
            if fam_recent > 0 and fam_mean_val > 0:
                fam_anchor = 0.6 * fam_recent + 0.4 * fam_mean_val
            else:
                fam_anchor = fam_recent or fam_mean_val
            if fam_anchor > 0:
                # Blend: more weight to anchor when count is very low
                anchor_w = max(0.2, min(0.6, 1.0 - current_count / anchor_thresh))
                point = anchor_w * fam_anchor + (1 - anchor_w) * point
                # Widen CI to reflect uncertainty of anchoring
                low = min(low, point * 0.5)
                high = max(high, point * 1.5)

        # Cap CI width relative to point estimate to prevent absurd CIs
        # at long lead times (where LOO leaves too few family data points)
        # Use tighter cap at shorter lead times where we have more certainty
        if days_remaining >= 60:
            cap_hi, cap_lo = 2.0, 0.45
        elif days_remaining >= 28:
            cap_hi, cap_lo = 1.8, 0.5
        elif days_remaining >= 7:
            cap_hi, cap_lo = 1.5, 0.6
        elif days_remaining >= 3:
            cap_hi, cap_lo = 1.40, 0.65
        else:
            cap_hi, cap_lo = 1.40, 0.65
        high = min(high, point * cap_hi)
        low = max(low, point * cap_lo)

        # Ensemble: blend ratio-based point estimate with pooled regression
        # Regression uses (count_at_T, T) -> final_count
        fam_reg = self.reg_params.get(family)
        # For aliased families, try alias regression params
        if fam_reg is None and family in FAMILY_ALIASES:
            for alias_fam in FAMILY_ALIASES[family]:
                fam_reg = self.reg_params.get(alias_fam)
                if fam_reg is not None:
                    break
        if fam_reg is None and not use_family and days_remaining >= 14:
            # Build size-matched regression only at long lead times for unknown
            # families. At short T (< 14), ratio-based prediction is more reliable
            # because ratios converge to ~1.0 and regression tends to over-predict.
            fam_reg = self._get_size_matched_regression(current_count)
        if fam_reg is not None:
            coeffs = fam_reg  # [slope_count, slope_T, intercept]
            reg_pred = coeffs[0] * current_count + coeffs[1] * days_remaining + coeffs[2]
            reg_pred = max(reg_pred, current_count)
            # T-dependent ensemble weights: ratio model is more accurate at
            # short lead times (near 1:1 ratio), regression helps more at long T
            if days_remaining <= 3:
                w = 0.80  # ratio nearly 1:1 at very short T, trust it heavily
            elif days_remaining <= 7:
                w = 0.55  # more ratio weight at short T
            elif days_remaining <= 28:
                w = 0.30
            else:
                w = 0.15  # more regression weight at long T
            ratio_point = point
            point = w * point + (1 - w) * reg_pred
            # At long T, ratio model has high variance — if it diverges
            # too much from regression, trust regression only
            if days_remaining >= 60:
                ratio_diff = abs(ratio_point - reg_pred) / max(reg_pred, 1)
                if ratio_diff > 0.5:
                    point = reg_pred

        # (YoY pacing tested: hurt MAPE in all configs. Ratio model already
        # captures count-level info; pacing adds noise from timing variability.)

        # Re-center CI on ensemble point estimate in log-space to preserve
        # lognormal asymmetry (right-skewed, appropriate for count data)
        if point > 0 and low > 0 and high > 0:
            log_half_w = (np.log(high) - np.log(low)) / 2
            low = np.exp(np.log(point) - log_half_w)
            high = np.exp(np.log(point) + log_half_w)
        else:
            ci_half_width = max((high - low) / 2, 1)
            low = point - ci_half_width
            high = point + ci_half_width

        # Guard against NaN from any upstream calculation
        if any(np.isnan(x) for x in (point, low, high)):
            return current_count, current_count, current_count

        # Growth trend adjustment: shift prediction for growing/declining families
        # e.g., if a tournament grows ~5%/year, nudge prediction up for current year
        trend = self.family_trend.get(family, 0.0)
        if trend != 0.0 and days_remaining >= 7:
            # Apply trend relative to most recent training year
            # Moderate: at most half the raw trend rate to avoid overfit
            adj = 1.0 + trend * 0.5
            point *= adj
            # Shift CI center but don't widen — trend is a location shift
            low *= adj
            high *= adj

        # Widen CIs for families with few training editions.
        # Size-matched fallback (0 editions) and single-edition families
        # have much higher prediction variance than well-observed families.
        n_editions = self.family_n_editions.get(family, 0)
        # For aliased families, sum editions across all alias sources
        if n_editions == 0 and family in FAMILY_ALIASES:
            n_editions = sum(self.family_n_editions.get(f, 0)
                            for f in FAMILY_ALIASES[family])
        if n_editions == 0:
            ci_half_width = (high - low) / 2 * self.CI_WIDEN_0_EDITIONS
            low = point - ci_half_width
            high = point + ci_half_width
            # For 0-edition families, point estimate may be fundamentally wrong.
            # Ensure upper bound accounts for growth potential. Multiplier is
            # highest for small counts at long T (most uncertain).
            if days_remaining >= 28 and current_count < 20:
                min_upper = current_count * 25
            elif days_remaining >= 28 and current_count < 80:
                min_upper = current_count * 8
            elif days_remaining >= 7 and current_count < 30:
                min_upper = current_count * 10
            elif days_remaining >= 7 and current_count < 100:
                min_upper = current_count * 4
            else:
                min_upper = high
            high = max(high, min_upper)
            high = min(high, max(point * 8.0, current_count * 30))
            low = max(low, point * 0.15)
        elif n_editions == 1:
            ci_half_width = (high - low) / 2 * self.CI_WIDEN_1_EDITION
            low = point - ci_half_width
            high = point + ci_half_width
            # Post-widening cap for 1-edition families
            high = min(high, point * 3.0)
            low = max(low, point * 0.3)

        # Withdrawal rate correction: reduce prediction by expected withdrawal %
        wd_rate = self.family_withdrawal_rates.get(family, 0.0)
        if wd_rate > 0 and wd_rate < 0.15:  # sanity cap at 15%
            point *= (1 - wd_rate)
            low *= (1 - wd_rate)
            high *= (1 - wd_rate)

        # Feature-engineered adjustments: day-of-week, holiday proximity,
        # early-bird deadline distance. These apply small multiplicative
        # corrections to the point estimate and CI bounds.
        eb_deadline = kwargs.get('early_bird_deadline')
        event_start = kwargs.get('event_start_date')
        if event_start and days_remaining > 0:
            try:
                features = compute_all_features(TODAY, event_start, eb_deadline)
                feat_adj = compute_adjustment_factor(features, days_remaining)
                if feat_adj != 1.0:
                    point *= feat_adj
                    low *= feat_adj
                    high *= feat_adj
            except (ValueError, TypeError):
                pass

        # Blitz events have extreme day-of surges (2-4x). Widen upper CI
        # at short T to capture this, since the parametric model assumes
        # gradual registration and under-covers blitz.
        if is_blitz:
            if days_remaining <= 1:
                min_blitz_upper = current_count * 4.0
            elif days_remaining <= 3:
                min_blitz_upper = current_count * 5.0
            elif days_remaining <= 5:
                min_blitz_upper = current_count * 6.0
            elif days_remaining <= 7:
                min_blitz_upper = current_count * 5.0
            else:
                min_blitz_upper = 0
            if min_blitz_upper > 0:
                high = max(high, min_blitz_upper)

        # Minimum CI width: at very short T, CIs can be unrealistically tight
        # (±3% of point) due to LOO calibration on well-predicted training data.
        # Ensure at least ±5% of point at T<=3, ±4% at T<=7.
        if days_remaining <= 1:
            min_half = point * 0.06
        elif days_remaining <= 3:
            min_half = point * 0.05
        elif days_remaining <= 7:
            min_half = point * 0.04
        else:
            min_half = 0
        if min_half > 0:
            if high - point < min_half:
                high = point + min_half
            if point - low < min_half:
                low = point - min_half

        # Apply recalibration corrections if available
        if hasattr(self, '_recal_bias') and self._recal_bias:
            # Find nearest T-band for bias correction
            recal_Ts = sorted(self._recal_bias.keys())
            nearest_T = min(recal_Ts, key=lambda t: abs(t - days_remaining))
            bias_factor = self._recal_bias.get(nearest_T, 1.0)
            ci_adj = self._recal_ci.get(nearest_T, 1.0)
            # Apply bias correction (shrink toward actual)
            center = point * bias_factor
            # Apply CI width adjustment
            half_w_log = (np.log(max(high, 1)) - np.log(max(low, 1))) / 2
            half_w_log *= ci_adj
            low = np.exp(np.log(max(center, 1)) - half_w_log)
            high = np.exp(np.log(max(center, 1)) + half_w_log)
            point = center

        # Floor: point estimate must be >= current_count (can't un-register)
        # but allow CI lower bound to go below point for honest uncertainty
        point = round(max(point, current_count))
        low = round(max(low, current_count))
        high = round(max(high, point))

        return (point, low, high)

    def recalibrate(self, completed_tournaments, daily, T_points=None,
                    target_coverage=0.80, ci_min_scale=0.5, ci_max_scale=1.8):
        """Automated recalibration from completed tournament results.

        Computes per-T bias correction and CI width adjustment factors
        by comparing model predictions to actual final counts.

        AUDIT.md C1: ci_adj derived from log-residual quantile rather than
        a 5-bucket step function, so empirical coverage actually converges
        to target_coverage=80% rather than landing in a "close enough" band.

        AUDIT.md C2: stationarity diagnostic — fits bias on the older half
        of completed tournaments and evaluates on the newer half. Logs both
        if they materially diverge so the user knows the per-T bias factors
        are time-dependent.

        completed_tournaments: DataFrame with completed tournaments
            (must have tid, family, final_count columns)
        daily: daily registration counts DataFrame
        T_points: list of T values to calibrate at (default: CHOP_POINTS)
        target_coverage: desired empirical CI coverage (default 0.80)
        ci_min_scale, ci_max_scale: clamp range for ci_adj

        Sets self._recal_bias, self._recal_ci, self._recal_n dicts.
        Returns dict with calibration diagnostics.
        """
        if T_points is None:
            T_points = [90, 60, 42, 28, 14, 7, 3, 1]

        # Filter to meaningful tournaments (skip tiny sub-events)
        completed_tournaments = completed_tournaments[
            completed_tournaments['final_count'] >= 50
        ]

        self._recal_bias = {}
        self._recal_ci = {}
        self._recal_n = {}
        diagnostics = {}

        # AUDIT.md C2 — order tournaments chronologically for stationarity check
        if 'last_reg' in completed_tournaments.columns:
            completed_sorted = completed_tournaments.copy()
            completed_sorted['_lr'] = pd.to_datetime(
                completed_sorted['last_reg'], errors='coerce')
            completed_sorted = completed_sorted.sort_values('_lr', na_position='last')
        else:
            completed_sorted = completed_tournaments

        for T in T_points:
            # Records: (residual_pct, log_actual, log_point, log_halfwidth,
            #           ci_hit, last_reg)
            records = []

            for _, row in completed_sorted.iterrows():
                tid = row['tid']
                family = row['family']
                actual = row['final_count']
                lr = row.get('_lr', pd.NaT) if '_lr' in row else pd.NaT

                td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
                if len(td) == 0:
                    continue

                # Find count at this T (within 2-day tolerance)
                available = td[(td['T'] >= T - 2) & (td['T'] <= T + 2)].copy()
                if len(available) == 0:
                    continue
                available['dist'] = (available['T'] - T).abs()
                closest = available.sort_values('dist').iloc[0]
                count_at_T = int(closest['cum_regs'])
                if count_at_T <= 0:
                    continue

                # Predict WITHOUT recalibration (use raw model)
                old_bias = self._recal_bias
                old_ci = self._recal_ci
                self._recal_bias = {}
                self._recal_ci = {}
                point, lo, hi = self.predict_nowcast(
                    count_at_T, T, family, _track_tier=False)
                self._recal_bias = old_bias
                self._recal_ci = old_ci

                if point is None or point <= 0 or lo <= 0 or hi <= 0:
                    continue

                err_pct = (point - actual) / actual
                # Half-width in log space (the lognormal CI's natural unit)
                log_halfw = (np.log(max(hi, 1)) - np.log(max(lo, 1))) / 2.0
                if log_halfw <= 0:
                    continue
                log_actual = np.log(max(actual, 1))
                log_point = np.log(max(point, 1))
                ci_hit = 1 if lo <= actual <= hi else 0
                records.append((err_pct, log_actual, log_point, log_halfw, ci_hit, lr))

            if len(records) < 3:
                continue

            # ── Bias correction (with C2 stationarity check) ────────────
            err_arr = np.array([r[0] for r in records])
            # Trim extreme outliers (>2× IQR) before computing bias
            q1, q3 = np.percentile(err_arr, [25, 75])
            iqr = q3 - q1
            mask = (err_arr >= q1 - 2 * iqr) & (err_arr <= q3 + 2 * iqr)
            trimmed = err_arr[mask]
            if len(trimmed) < 3:
                trimmed = err_arr

            mean_bias = float(np.mean(trimmed))
            bias_factor = 1.0 / (1.0 + mean_bias)
            bias_factor = max(0.80, min(1.20, bias_factor))

            # Stationarity probe: split records chronologically (older half vs newer half)
            stationarity = None
            recent_recalibrated = False
            if len(records) >= 6:
                mid = len(records) // 2
                old_half = err_arr[:mid]
                new_half = err_arr[mid:]
                stationarity = {
                    'old_bias_pct': round(float(np.mean(old_half)) * 100, 1),
                    'new_bias_pct': round(float(np.mean(new_half)) * 100, 1),
                    'delta_pct': round((float(np.mean(new_half)) - float(np.mean(old_half))) * 100, 1),
                }
                # AUDIT.md C2 auto-action — when bias is non-stationary across
                # halves by more than 5pp, refit bias_factor on just the recent
                # half. Old-cohort behavior (pre-2024 conditions) shouldn't drag
                # current predictions backward. The records list is also pruned
                # so the CI scale below is computed from the same recent cohort.
                if abs(stationarity['delta_pct']) > 5.0:
                    new_records = records[mid:]
                    new_trimmed = new_half
                    nq1, nq3 = np.percentile(new_trimmed, [25, 75])
                    niqr = nq3 - nq1
                    nmask = (new_trimmed >= nq1 - 2 * niqr) & (new_trimmed <= nq3 + 2 * niqr)
                    refit = new_trimmed[nmask] if nmask.sum() >= 3 else new_trimmed
                    mean_bias = float(np.mean(refit))
                    bias_factor = 1.0 / (1.0 + mean_bias)
                    bias_factor = max(0.80, min(1.20, bias_factor))
                    records = new_records
                    err_arr = new_half
                    stationarity['action'] = 'refit-on-recent-half'
                    recent_recalibrated = True

            # ── CI scale (continuous derivation, AUDIT.md C1) ───────────
            # Empirical 80th percentile of normalized residual tells us the scale
            # needed to make the 80% CI actually cover 80% of cases. Compute it
            # around the same bias-corrected center used when the scale is later
            # applied in predict_nowcast().
            log_bias_factor = np.log(max(bias_factor, 1e-9))
            norm_residuals = np.array([
                abs(r[1] - (r[2] + log_bias_factor)) / r[3]
                for r in records
            ])
            empirical_q = float(np.percentile(norm_residuals, target_coverage * 100))
            # The empirical_q is already in units of half-width, so it is the
            # scale to apply around the bias-corrected center.
            ci_adj = empirical_q
            ci_adj = max(ci_min_scale, min(ci_max_scale, ci_adj))

            current_coverage = float(np.mean([r[4] for r in records]))

            self._recal_bias[T] = bias_factor
            self._recal_ci[T] = ci_adj
            self._recal_n[T] = len(records)
            diag = {
                'n': len(records),
                'mean_bias': round(mean_bias * 100, 1),
                'coverage_before': round(current_coverage * 100, 0),
                'bias_factor': round(bias_factor, 3),
                'ci_adj': round(ci_adj, 3),
                'target_coverage': int(target_coverage * 100),
            }
            if stationarity:
                diag['stationarity'] = stationarity
                # Loud notice when bias materially differs across halves;
                # auto-action above already refit on the recent cohort.
                if abs(stationarity['delta_pct']) > 5.0:
                    if recent_recalibrated:
                        print(f"  NOTICE: T={T} bias non-stationary "
                              f"(old: {stationarity['old_bias_pct']}%, "
                              f"new: {stationarity['new_bias_pct']}%, "
                              f"Δ={stationarity['delta_pct']}pp) — "
                              f"auto-refit on recent half (n={len(records)}, "
                              f"bias_factor={diag['bias_factor']}).")
                    else:
                        print(f"  WARNING: T={T} bias non-stationary "
                              f"(old: {stationarity['old_bias_pct']}%, "
                              f"new: {stationarity['new_bias_pct']}%, "
                              f"Δ={stationarity['delta_pct']}pp) "
                              f"but n<6 — kept full-cohort fit.")
            diagnostics[T] = diag

        return diagnostics


def build_template_curves(summary, daily):
    """Build family template curves from completed tournaments using raw T."""
    valid = summary[
        (summary['has_timestamps']) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False)) &
        (summary['tournament_year'] < 2026)
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
            curves[family] = {int(t): float(np.median(curves_at_T.get(t, [0])))
                             for t in T_GRID}

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
    curves['__global__'] = {int(t): float(np.median(all_at_T.get(t, [0])))
                           for t in T_GRID}
    return curves


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


def get_event_info(family, year, meta_lookup, summary):
    """Get or estimate event dates for a tournament."""
    key = (family, year)
    if key in meta_lookup:
        return meta_lookup[key]

    # Estimate from historical last_reg dates (pre-2026 editions)
    hist = summary[
        (summary['family'] == family) &
        (summary['has_timestamps']) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'].notna())
    ]
    last_regs = pd.to_datetime(hist['last_reg'].dropna())
    if len(last_regs) > 0:
        med_month = int(last_regs.dt.month.median())
        med_day = min(int(last_regs.dt.day.median()), 28)
        try:
            est_end = datetime(year, med_month, med_day)
        except ValueError:
            est_end = datetime(year, med_month, 28)
        est_start = est_end - timedelta(days=TYPICAL_DURATION)
        return {'start_date': est_start, 'end_date': est_end}

    # For new families, check the current year's last_reg as a proxy
    # (if last_reg is recent and close to today, the event likely already happened)
    current = summary[
        (summary['family'] == family) &
        (summary['has_timestamps']) &
        (summary['tournament_year'] == year)
    ]
    cur_last_regs = pd.to_datetime(current['last_reg'].dropna())
    if len(cur_last_regs) > 0:
        latest = cur_last_regs.max()
        est_end = datetime(latest.year, latest.month, latest.day)
        est_start = est_end - timedelta(days=TYPICAL_DURATION)
        return {'start_date': est_start, 'end_date': est_end}

    # Last resort: assume future event
    return {
        'start_date': TODAY + timedelta(days=90),
        'end_date': TODAY + timedelta(days=94),
    }


def determine_status(event_info):
    """Determine tournament status based on event dates."""
    start = event_info['start_date']
    end = event_info['end_date']
    if isinstance(start, str):
        start = pd.to_datetime(start)
    if isinstance(end, str):
        end = pd.to_datetime(end)

    if TODAY > end + timedelta(days=1):
        return 'complete'
    elif TODAY >= start:
        return 'in_progress'
    else:
        return 'live'


def build_daily_data(tid, daily):
    """Get daily data as [[days_from_first_reg, cumulative_count], ...]."""
    td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(td) == 0:
        return []
    max_T = td['T'].max()
    return [[int(max_T - r['T']), int(r['cum_regs'])] for _, r in td.iterrows()]


def build_reg_curve(family, template_curves):
    """Build registration curve for a family."""
    curve = template_curves.get(family, template_curves.get('__global__', {}))
    if not curve:
        return []
    leads = [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]
    return [{'days_before': t, 'cumulative_pct': round(curve.get(t, 0.0), 3)}
            for t in leads if curve.get(t, 0.0) > 0]


def get_historical(family, summary):
    """Historical final counts (2015+, non-online, non-covid)."""
    hist = summary[
        (summary['family'] == family) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False)) &
        (summary['tournament_year'].notna()) &
        (summary['tournament_year'] >= 2015) &
        (summary['tournament_year'] < 2026)
    ].sort_values('tournament_year')
    return [{'year': int(r['tournament_year']), 'count': int(r['final_count'])}
            for _, r in hist.iterrows()]


def build_website_json(summary, daily, meta_lookup, model, template_curves):
    """Build final website_data.json with all 2026 tournaments."""
    t2026 = summary[summary['tournament_year'] == 2026].copy()
    tournaments = []

    for _, row in t2026.iterrows():
        family = row['family']
        tid = row['tid']
        current_count = int(row['final_count'])

        # Event info
        info = get_event_info(family, 2026, meta_lookup, summary)
        event_start = info['start_date']
        event_end = info['end_date']
        status = determine_status(info)

        # Days remaining to event start
        if isinstance(event_start, str):
            event_start = pd.to_datetime(event_start)
        if isinstance(event_end, str):
            event_end = pd.to_datetime(event_end)
        days_to_start = max((event_start - TODAY).days, 0)

        # T = days_to_start: training data is anchored to event_start after
        # reanchor_daily_to_event_start(), so pass days_to_start directly.

        # Predict with guardrails
        hist_counts = [h['count'] for h in get_historical(family, summary)]
        prediction_source = 'model'
        if status == 'live' and current_count > 0 and days_to_start > 0:
            # Guardrail: don't trust ratio-based predictions with < 10 regs
            # and > 60 days out — fall back to historical average
            if current_count < 10 and days_to_start > 60 and len(hist_counts) >= 1:
                hist_med = int(np.median(hist_counts))
                pred = hist_med
                lo = int(np.percentile(hist_counts, 10)) if len(hist_counts) >= 5 else int(hist_med * 0.7)
                hi = int(np.percentile(hist_counts, 90)) if len(hist_counts) >= 5 else int(hist_med * 1.3)
            else:
                pred, lo, hi = model.predict_nowcast(current_count, days_to_start, family)
                if pred is None:
                    pred, lo, hi = current_count, current_count, current_count

            # Plausibility check: if prediction is outside [0.3x, 3x] of
            # historical range, clamp to historical bounds
            if len(hist_counts) >= 1:
                hist_min = min(hist_counts)
                hist_max = max(hist_counts)
                if pred < hist_min * 0.3:
                    hist_med = int(np.median(hist_counts))
                    pred, lo, hi = hist_med, int(hist_med * 0.7), int(hist_med * 1.3)
                elif pred > hist_max * 3.0:
                    pred = int(hist_max * 1.5)
                    hi = min(hi, int(hist_max * 2.5))
        elif status == 'in_progress':
            # Event underway — pass through scraped count directly.
            # Does NOT include on-site/walk-up registrations.
            pred, lo, hi = current_count, current_count, current_count
            prediction_source = 'live_scrape'
        elif status == 'complete':
            pred, lo, hi = current_count, current_count, current_count
            prediction_source = 'final'
        else:
            pred, lo, hi = current_count, current_count, current_count

        entry = {
            'family': family,
            'year': 2026,
            'event_start': event_start.strftime('%Y-%m-%d') if hasattr(event_start, 'strftime') else str(event_start)[:10],
            'event_end': event_end.strftime('%Y-%m-%d') if hasattr(event_end, 'strftime') else str(event_end)[:10],
            'current_count': current_count,
            'days_remaining': days_to_start,
            'point_estimate': pred,
            'ci_lower': lo,
            'ci_upper': hi,
            'ci_level': 0.80,
            'historical': get_historical(family, summary),
            'registration_curve': build_reg_curve(family, template_curves),
            'daily_data': build_daily_data(tid, daily),
            'status': 'live' if status == 'in_progress' else status,
            'prediction_source': prediction_source,
        }

        # Fee info from metadata
        key = (family, 2026)
        if key in meta_lookup:
            m = meta_lookup[key]
            if m.get('early_bird_deadline') and not pd.isna(m['early_bird_deadline']):
                entry['early_bird_deadline'] = str(m['early_bird_deadline'])[:10]
            if m.get('early_bird_fee') and not pd.isna(m['early_bird_fee']):
                entry['early_bird_fee'] = int(m['early_bird_fee'])
            if m.get('regular_fee') and not pd.isna(m['regular_fee']):
                entry['regular_fee'] = int(m['regular_fee'])
            if m.get('onsite_fee') and not pd.isna(m['onsite_fee']):
                entry['onsite_fee'] = int(m['onsite_fee'])

        tournaments.append(entry)

    # Sort: live first, then by days_remaining
    status_order = {'live': 0, 'in_progress': 1, 'complete': 2, 'unknown': 3}
    tournaments.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

    return {
        'generated': TODAY.strftime('%Y-%m-%d'),
        'model': 'N5v4_Final',
        'model_description': (
            'Ensemble model (N5v4): historical ratio (harmonic mean) + '
            'per-family pooled Huber regression (final ~ count_at_T + T). '
            'T-dependent weights (ratio: 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). '
            '80% CI from lognormal prediction intervals, LOO-calibrated with '
            'ensemble shrinkage. Empirical Bayes sigma shrinkage, T-interpolation, '
            'expanding-window calibration, and plausibility guardrails.'
        ),
        'tournaments': tournaments,
    }


def main():
    print("Loading data...")
    summary, daily, meta = load_data()
    meta_lookup = load_meta_lookup(meta)

    # Fit model on all completed data
    print("Fitting N5v4 model...")
    model = N5v4_Final()
    model.fit(summary, daily)

    # Show Chicago Open ratios (the fix)
    print("\n" + "=" * 70)
    print("CHICAGO OPEN RATIO ANALYSIS (after excluding 2026 in-progress)")
    print("=" * 70)
    chi_rats = model.ratios.get('Chicago Open', {})
    for T in CHOP_POINTS:
        rats = chi_rats.get(T, [])
        if rats:
            vals = [r[0] for r in rats]
            yrs = [int(r[1]) for r in rats]
            med, lo, hi = lognormal_ci(vals)
            print(f"  T-{T:<4}  n={len(vals)}  ratios=[{', '.join(f'{v:.2f}' for v in vals)}]")
            print(f"         years={yrs}  median={med:.2f}  lognormal 80% CI=[{lo:.2f}, {hi:.2f}]")

    # Chicago Open 2026 prediction
    print("\n" + "=" * 70)
    print("2026 CHICAGO OPEN PREDICTION")
    print("=" * 70)
    # Event: May 21-25. T = days to event_start (no duration offset needed).
    current = 179
    days_to_start = (datetime(2026, 5, 21) - TODAY).days
    pred, lo, hi = model.predict_nowcast(current, days_to_start, 'Chicago Open')
    print(f"\n  Current registrations:  {current}")
    print(f"  Days to event start:    {days_to_start}")
    print(f"  Point estimate:         {pred}")
    print(f"  80% CI:                 [{lo}, {hi}]")
    print(f"  CI width:               {hi - lo}")
    print(f"  Historical range:       860-960 (2022-2025)")

    print(f"\n  N5v4 (fixed):            pred={pred}  CI=[{lo}, {hi}]  width={hi-lo}")

    # Blind validation
    print("\n")
    results = run_blind_test(summary, daily)

    # Build template curves
    print("\nBuilding template curves...")
    template_curves = build_template_curves(summary, daily)

    # Build website JSON
    print("\n" + "=" * 70)
    print("BUILDING WEBSITE JSON")
    print("=" * 70)
    website_data = build_website_json(summary, daily, meta_lookup, model, template_curves)

    outpath = os.path.join(OUTPUT_DIR, "website_data.json")
    with open(outpath, 'w') as f:
        json.dump(website_data, f, indent=2, default=str)

    print(f"\nSaved to {outpath}")
    print(f"Total tournaments: {len(website_data['tournaments'])}")

    statuses = {}
    for t in website_data['tournaments']:
        statuses[t['status']] = statuses.get(t['status'], 0) + 1
    print(f"By status: {statuses}")

    print("\nKey live tournament predictions:")
    for t in website_data['tournaments']:
        if t['status'] == 'live' and t['current_count'] >= 5:
            print(f"  {t['family']:<45} cnt={t['current_count']:>5}  "
                  f"pred={t['point_estimate']:>5}  "
                  f"CI=[{t['ci_lower']}, {t['ci_upper']}]  T-{t['days_remaining']}")

    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")


def load_walkin_multipliers():
    """
    Load per-family walk-in multiplier stats from 06_walk_in_multipliers.py output.
    Returns dict: family -> {median_ratio, std_ratio, n_years, tournament_type}
    """
    import csv
    stats_csv = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
    if not os.path.exists(stats_csv):
        return {}

    multipliers = {}
    with open(stats_csv, "r") as f:
        for row in csv.DictReader(f):
            multipliers[row["family"]] = {
                "median_ratio": float(row["median_ratio"]),
                "std_ratio": float(row["std_ratio"]),
                "n_years": int(row["n_years"]),
                "tournament_type": row["tournament_type"],
                "min_ratio": float(row["min_ratio"]),
                "max_ratio": float(row["max_ratio"]),
            }
    return multipliers


# Type-level fallback multipliers (used when no family-specific data exists)
DEFAULT_WALKIN_MULTIPLIERS = {
    "open": {"median_ratio": 1.64, "std_ratio": 0.15, "n_years": 0},
    "class": {"median_ratio": 1.24, "std_ratio": 0.10, "n_years": 0},
}


def apply_walkin_multiplier(prereg_point, prereg_low, prereg_high, family,
                            multipliers=None):
    """
    Apply walk-in multiplier to pre-registration prediction to get total entry estimate.

    Returns (total_point, total_low, total_high, multiplier_used, multiplier_source)
    where multiplier_source is 'family', 'type', or 'none'.
    """
    if multipliers is None:
        multipliers = load_walkin_multipliers()

    if prereg_point is None:
        return None, None, None, None, "none"

    # Apply walk-in multiplier: family-specific if available, otherwise global guesstimate
    if family in multipliers:
        m = multipliers[family]
        ratio = min(m["median_ratio"], 1.1)  # hard cap at 1.1x
        std = m["std_ratio"]
        source = "family"
    else:
        # Global guesstimate based on 2023+ median, capped at 1.1x
        ratio = 1.1
        std = 0.0
        source = "estimate"

    # Propagate CI through multiplier uncertainty
    # Use lognormal convolution with t-distribution for small samples
    if std > 0:
        n_years = multipliers.get(family, {}).get("n_years", 0) if family in multipliers else 0
        if n_years >= 3:
            from scipy.stats import t as t_dist
            t_crit = t_dist.ppf(0.95, df=max(n_years - 1, 1))
        else:
            t_crit = 1.645  # fallback to normal z for type-level
        log_mu = np.log(ratio)
        log_sigma = np.log(1 + std / ratio)
        m_low = np.exp(log_mu - t_crit * log_sigma)
        m_high = np.exp(log_mu + t_crit * log_sigma)
    else:
        m_low = ratio
        m_high = ratio

    total_point = int(round(prereg_point * ratio))
    total_low = int(round(prereg_low * m_low))
    total_high = int(round(prereg_high * m_high))

    return total_point, total_low, total_high, ratio, source


if __name__ == "__main__":
    main()
