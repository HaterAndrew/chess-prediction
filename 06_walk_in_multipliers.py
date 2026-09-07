"""
06_walk_in_multipliers.py — Compute walk-in entry multipliers per tournament family.

Compares actual final player counts (from standings/wall charts) against
pre-registration counts (from CCA registration archives) to derive the
walk-in delta: the ratio of actual entries to pre-registered entries.

Outputs:
  output/walk_in_multipliers.csv     — per family-year ratios
  output/walk_in_family_stats.csv    — per-family aggregate statistics
"""

import csv
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

# Map standings tournament names to summary family names — single source of
# truth in tournament_aliases.py (AUDIT.md A2).
from shared.season import CURRENT_SEASON
from tournament_aliases import STANDINGS_NAME_MAP

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

STANDINGS_CSV = os.path.join(OUTPUT_DIR, "historical_standings.csv")
SUMMARY_CSV = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
METADATA_CSV = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")

# Walk-in rates have declined significantly (1.68x in 2013 -> 1.23x in 2025), so
# only recent editions describe current behaviour. Module-level because
# check_history_depth names it when the cut is what starved a family's history.
MIN_DATA_YEAR = 2023
MULTIPLIER_CSV = os.path.join(OUTPUT_DIR, "walk_in_multipliers.csv")
FAMILY_STATS_CSV = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")

# COVID years — registration counts are unreliable (events cancelled,
# moved online, or drastically different format)
COVID_YEARS = {2020, 2021}

# Minimum standings count to consider valid (filters scraper failures)
MIN_STANDINGS_COUNT = 15

# Tournament type classification for fallback multipliers
# Class tournaments have much higher walk-in rates than open tournaments
CLASS_FAMILIES = {
    'Midwest Class Championships', 'Western Class Championships',
    'Southwest Class Championships', 'Eastern Class',
    'Chicago Class', 'Continental Class', 'Southern Class',
    'Eastern Class Championships', 'Southern Class Championships',
    'Continental Class Championships',
}


def load_standings():
    """Load standings data, filter bad entries, normalize names."""
    standings = {}  # (family, year) -> total_players
    with open(STANDINGS_CSV, "r") as f:
        for row in csv.DictReader(f):
            total = int(row["total_players"])
            if total < MIN_STANDINGS_COUNT:
                continue
            year = int(row["year"])
            if year in COVID_YEARS:
                continue
            name = row["tournament_name"]
            name = STANDINGS_NAME_MAP.get(name, name)
            standings[(name, year)] = total
    return standings


def load_in_progress_2026_families():
    """Return the set of 2026 families whose event end_date is today or later.

    Their summary.final_count is a moving mid-event scrape (01_data_prep raises
    it via raise-only merge) and must not feed walk-in ratios — the standings
    join would compare a partial post-hoc actual against a still-rising
    pre-registration count.
    """
    sys.path.insert(0, PROJECT_DIR)
    from pipeline_utils import is_event_complete
    in_progress = set()
    if not os.path.exists(METADATA_CSV):
        return in_progress
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    with open(METADATA_CSV, "r") as f:
        for row in csv.DictReader(f):
            try:
                year = int(float(row["year"]))
            except (ValueError, KeyError, TypeError):
                continue
            if year != CURRENT_SEASON:
                continue
            end = row.get("end_date") or None
            if not is_event_complete(end, today):
                in_progress.add(row["family"])
    return in_progress


def load_summary():
    """Load pre-registration final counts from tournament summary.

    2026 events whose end_date is today or later are excluded — their
    final_count is a moving mid-event scrape, not a real final.
    """
    in_progress = load_in_progress_2026_families()
    summary = {}  # (family, year) -> final_count
    with open(SUMMARY_CSV, "r") as f:
        for row in csv.DictReader(f):
            try:
                year = int(float(row["tournament_year"]))
                count = int(float(row["final_count"]))
            except (ValueError, KeyError):
                continue
            if year in COVID_YEARS:
                continue
            if count < 10:
                continue
            family = row["family"]
            if year == CURRENT_SEASON and family in in_progress:
                continue
            summary[(family, year)] = count
    return summary


def normalize_name(s):
    """Normalize tournament name for fuzzy matching."""
    return re.sub(r'[^a-z]', '', s.lower())


def compute_multipliers(standings, summary):
    """
    Match standings to summary by family+year, compute walk-in ratios.
    Returns list of dicts for the per-year output.
    """
    # Build normalized lookup for summary
    summary_norm = {}
    for (fam, yr), count in summary.items():
        key = (normalize_name(fam), yr)
        # Keep the entry with the highest count if duplicates exist
        if key not in summary_norm or count > summary_norm[key][1]:
            summary_norm[key] = (fam, count)

    rows = []
    for (st_name, year), st_count in sorted(standings.items()):
        norm_key = (normalize_name(st_name), year)
        if norm_key in summary_norm:
            fam, prereg = summary_norm[norm_key]
            ratio = st_count / prereg
            # Ratio < 0.5 means fewer actual players than half the pre-reg
            # — almost certainly bad standings data, not a real outcome
            if ratio < 0.5:
                continue
            is_class = fam in CLASS_FAMILIES
            rows.append({
                "family": fam,
                "year": year,
                "prereg_count": prereg,
                "standings_count": st_count,
                "walk_in_ratio": round(ratio, 4),
                "walk_in_delta": st_count - prereg,
                "walk_in_pct": round((ratio - 1) * 100, 1),
                "tournament_type": "class" if is_class else "open",
            })

    return rows


def compute_family_stats(rows):
    """
    Compute per-family aggregate statistics from multiplier rows.
    Uses recency-weighted approach: only the most recent 3 years of data
    per family, since walk-in rates have declined significantly over time
    (1.68x in 2013 -> 1.23x in 2025).
    """
    by_family = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append((r["year"], r["walk_in_ratio"]))

    stats = []
    for fam in sorted(by_family):
        year_ratios = sorted(by_family[fam], key=lambda x: x[0], reverse=True)
        recent = [(y, r) for y, r in year_ratios if y >= MIN_DATA_YEAR]
        if not recent:
            continue  # skip families with only pre-2023 data
        ratios = [r for _, r in recent]
        years_used = [y for y, _ in recent]

        n = len(ratios)
        med = statistics.median(ratios)
        mean = statistics.mean(ratios)
        std = statistics.stdev(ratios) if n >= 2 else 0.0
        cv = std / mean if mean > 0 else 0.0
        is_class = fam in CLASS_FAMILIES

        stats.append({
            "family": fam,
            "n_years": n,
            "median_ratio": round(med, 4),
            "mean_ratio": round(mean, 4),
            "std_ratio": round(std, 4),
            "min_ratio": round(min(ratios), 4),
            "max_ratio": round(max(ratios), 4),
            "cv": round(cv, 4),
            "tournament_type": "class" if is_class else "open",
            "years_used": str(years_used),
        })

    return stats


# A family needs at least this many editions before its walk-in ratio is an
# estimate rather than a single observation. Below it, apply_walkin_multiplier's
# n/(n+k) shrinkage discards most of the measured signal and std_ratio is 0, so
# the multiplier contributes no interval width either.
MIN_HEALTHY_N_YEARS = 2


def check_history_depth(stats, min_n=MIN_HEALTHY_N_YEARS):
    """Return a WARNING string when the walk-in history has collapsed, else None.

    2026-09-07 review: MIN_DATA_YEAR's hard 2023 cut, plus the frozen training
    corpus (the missing all_registrations.csv export), had left 37 of 38
    families at n_years=1. The per-family multiplier had quietly degenerated
    into the flat 1.1 baseline for almost the whole corpus (measured effective
    median 1.118), and every one of those families reported std_ratio=0, so the
    published interval claimed zero walk-in uncertainty.

    None of that surfaced anywhere: the three tests that would have caught it
    were marked xfail. This puts it on the site's warnings panel instead.
    """
    if not stats:
        return None
    n_years = [int(s["n_years"]) for s in stats]
    thin = [s for s in stats if int(s["n_years"]) < min_n]
    if len(thin) * 2 <= len(stats):
        return None
    median_n = statistics.median(n_years)
    zero_std = sum(1 for s in stats if float(s["std_ratio"]) == 0)
    return (
        f"walk-in history collapsed: {len(thin)} of {len(stats)} families have "
        f"fewer than {min_n} usable editions (median n_years={median_n:g}). "
        f"Per-family multipliers shrink toward the 1.1 baseline at this depth, "
        f"so the walk-in adjustment is close to inert, and {zero_std} family/ies "
        f"report std_ratio=0, contributing no interval width. Cause is usually "
        f"the MIN_DATA_YEAR={MIN_DATA_YEAR} recency cut combined with a frozen "
        f"training corpus (missing all_registrations.csv export)."
    )


def main():
    print("Loading standings data...")
    standings = load_standings()
    print(f"  {len(standings)} valid standings entries (excl. COVID, bad data)")

    print("Loading pre-registration summary...")
    summary = load_summary()
    print(f"  {len(summary)} valid summary entries")

    print("Computing walk-in multipliers...")
    rows = compute_multipliers(standings, summary)
    print(f"  {len(rows)} matched family-year pairs")

    # Write per-year multipliers
    fields = ["family", "year", "prereg_count", "standings_count",
              "walk_in_ratio", "walk_in_delta", "walk_in_pct", "tournament_type"]
    with open(MULTIPLIER_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {MULTIPLIER_CSV}")

    # Compute and write family stats
    stats = compute_family_stats(rows)
    print(f"  {len(stats)} tournament families with walk-in data")

    stats_fields = ["family", "n_years", "median_ratio", "mean_ratio",
                    "std_ratio", "min_ratio", "max_ratio", "cv", "tournament_type",
                    "years_used"]
    with open(FAMILY_STATS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=stats_fields)
        writer.writeheader()
        writer.writerows(stats)
    print(f"  Wrote {FAMILY_STATS_CSV}")

    # Surface a collapsed history on the site's warnings panel. The pipeline
    # harvests any line containing "WARNING:" out of this step's stdout
    # (pipeline/warns.py::_harvest_warnings).
    depth_warning = check_history_depth(stats)
    if depth_warning:
        print(f"  WARNING: {depth_warning}")

    # Print summary
    print("\n" + "=" * 70)
    print("WALK-IN MULTIPLIER SUMMARY")
    print("=" * 70)

    open_ratios = [r["walk_in_ratio"] for r in rows if r["tournament_type"] == "open"]
    class_ratios = [r["walk_in_ratio"] for r in rows if r["tournament_type"] == "class"]

    if open_ratios:
        print(f"\nOpen tournaments (n={len(open_ratios)}):")
        print(f"  Median ratio: {statistics.median(open_ratios):.3f}")
        print(f"  Mean ratio:   {statistics.mean(open_ratios):.3f}")
        print(f"  Std:          {statistics.stdev(open_ratios):.3f}")

    if class_ratios:
        print(f"\nClass tournaments (n={len(class_ratios)}):")
        print(f"  Median ratio: {statistics.median(class_ratios):.3f}")
        print(f"  Mean ratio:   {statistics.mean(class_ratios):.3f}")
        print(f"  Std:          {statistics.stdev(class_ratios):.3f}")

    print("\nPer-family breakdown:")
    print(f"{'Family':35s} | Type  | N | Median | Std    | CV")
    print("-" * 75)
    for s in stats:
        print(f"{s['family']:35s} | {s['tournament_type']:5s} | {s['n_years']} | "
              f"{s['median_ratio']:6.3f} | {s['std_ratio']:6.4f} | {s['cv']:.4f}")


if __name__ == "__main__":
    main()
