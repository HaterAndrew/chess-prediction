"""04d module head, verbatim (imports, shared defs, constants)."""

"""
Phase 4D: Clean website data generation.
Fix status detection, filter to main events, correct predictions.
"""

import pandas as pd
import numpy as np
import os
import sys

# __file__ now lives under sitebuild/ — the digit-prefixed modules sit one
# level up, so insert the repo root (relocation adjustment, P3b).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from importlib import import_module
m04c = import_module("04c_final_model")
from tournament_aliases import canonicalize_family, adjust_wo_top6_count
# v3 T7: these two live in ratio_model now so the window-engine grader can
# import them without executing this script's pipeline body. Imported here
# under their original names, so every call site below is unchanged.


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


# __file__-derived paths do not survive relocation into a package — the
# repo-level constant is the truth (shared/paths.py, decomposition P1).
from shared.paths import OUTPUT_DIR  # noqa: F401
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
