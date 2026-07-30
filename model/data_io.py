"""Frame loading, enrichment lookups, reanchoring (04c 199-430, verbatim)."""

import json
import os
import re

import numpy as np
import pandas as pd

from model.constants import DEFAULT_EVENT_START_OFFSET, OUTPUT_DIR, TODAY

def reanchor_daily_to_event_start(summary, daily, meta, keep_post_start=False):
    """Shift daily T values from last_reg-anchored to event_start-anchored.

    Training data T is originally computed as days before last_reg (≈ event_end).
    This reanchors T so that T=0 = event_start (first day of tournament).
    Registrations during the event (new T < 0) are dropped so the model
    only trains on pre-registration data. final_count in summary still includes
    on-site entries, so ratios at T=0 implicitly capture the on-site multiplier.

    keep_post_start=True retains the during-event rows (negative T) instead.
    Only the window-engine grader uses it; see the comment at the drop site.

    Returns modified daily DataFrame (summary and meta are unchanged).
    """
    meta_dt = meta.copy()
    meta_dt['start_date'] = pd.to_datetime(meta_dt['start_date'], errors='coerce')
    meta_dt['end_date'] = pd.to_datetime(meta_dt['end_date'], errors='coerce')

    # Build (family, year) -> event_start / event_end lookups from metadata
    meta_starts = {}
    meta_ends = {}
    for _, m in meta_dt.iterrows():
        if pd.notna(m['start_date']):
            meta_starts[(m['family'], int(m['year']))] = m['start_date']
        if pd.notna(m['end_date']):
            meta_ends[(m['family'], int(m['year']))] = m['end_date']

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
    _offset_source_counts = {'metadata': 0, 'negative-accepted': 0, 'family-median': 0,
                             'global-default': 0, 'bad-metadata': 0, 'in-progress': 0}
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
            is_in_progress = start > TODAY
            end = meta_ends.get((fam, yr))
            is_complete = end is not None and pd.notna(end) and end < TODAY
            # v3 N1 (audit/AUDIT_2026-07-25.md): for an event that has NOT yet
            # concluded, a negative offset means last_reg predates event_start —
            # normal when the registration export is stale relative to a live or
            # upcoming event. Shifting by the TRUE (negative) offset is
            # arithmetically correct; substituting a positive family-median offset
            # slides the archive curve toward T=0 and, when a missing scrape day
            # later exposes it, triggers the A4 rescale that corrupted
            # Bradley/Pacific Coast. Accept the negative offset only for
            # not-yet-complete events (bounded -365..0). Completed events keep the
            # prior substitution behavior unchanged; any latent misplacement there
            # is an audit finding, not a Phase-0 behavior change.
            if 0 <= offset <= 30:
                _offset_source_counts['metadata'] += 1
            elif offset < 0 and offset >= -365 and not is_complete:
                _offset_source_counts['negative-accepted'] += 1
            else:
                _offset_source_counts['in-progress' if is_in_progress else 'bad-metadata'] += 1
                if fam in family_median_offset:
                    offset = family_median_offset[fam]
                else:
                    offset = global_median_offset
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

    # Drop rows where T < 0 (on-site registrations during the event).
    #
    # keep_post_start retains them instead, for the one caller that needs them:
    # grading the post-start online-registration window engine (v3 T7,
    # window_grading.py). That engine predicts from inside the window, so a
    # backtest of it cannot use a table with the window removed. Nothing in the
    # training or prediction path passes this — the model must keep training on
    # pre-registration data only, or T=0 ratios would double-count the on-site
    # multiplier they are supposed to imply.
    before = len(daily)
    if not keep_post_start:
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
