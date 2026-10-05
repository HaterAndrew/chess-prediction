"""historical_tournaments.csv: write it, summarize a run, and compare a
full refresh with the file on record."""
import csv
import statistics
from collections import Counter

FIELDNAMES = [
    "tournament_name", "year", "start_date", "end_date", "state",
    "total_entries", "sections", "schedule_dist", "unique_states",
    "withdrawal_count", "rating_mean", "rating_median", "rating_std",
]


def save_results(results, path):
    """Write results to CSV."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results):
    """Print summary statistics."""
    n = len(results)
    if n == 0:
        print("No tournaments processed.")
        return

    years = [r["year"] for r in results if r["year"]]
    entries = [r["total_entries"] for r in results if r["total_entries"]]
    with_sections = sum(1 for r in results if r["sections"])
    with_schedule = sum(1 for r in results if r["schedule_dist"])
    with_ratings = sum(1 for r in results if r["rating_mean"])
    with_states = sum(1 for r in results if r["unique_states"])
    with_withdrawals = sum(1 for r in results if r["withdrawal_count"])

    print(f"\n{'='*60}")
    print("  HISTORICAL SCRAPE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total tournaments processed:  {n}")
    if years:
        print(f"  Year range:                   {min(years)} - {max(years)}")
    if entries:
        print(f"  Entry counts:                 min={min(entries)}, max={max(entries)}, "
              f"mean={statistics.mean(entries):.0f}, median={statistics.median(entries):.0f}")
    print(f"  With section breakdown:       {with_sections} ({with_sections/n*100:.1f}%)")
    print(f"  With schedule distribution:   {with_schedule} ({with_schedule/n*100:.1f}%)")
    print(f"  With rating stats:            {with_ratings} ({with_ratings/n*100:.1f}%)")
    print(f"  With geographic diversity:    {with_states} ({with_states/n*100:.1f}%)")
    print(f"  With withdrawal count:        {with_withdrawals} ({with_withdrawals/n*100:.1f}%)")

    # Per-year breakdown
    if years:
        year_counts = Counter(years)
        print(f"\n  {'Year':<8} {'Tournaments':>12} {'Avg Entries':>12}")
        print(f"  {'-'*8} {'-'*12} {'-'*12}")
        for yr in sorted(year_counts.keys()):
            yr_entries = [r["total_entries"] for r in results
                         if r["year"] == yr and r["total_entries"]]
            avg = statistics.mean(yr_entries) if yr_entries else 0
            print(f"  {yr:<8} {year_counts[yr]:>12} {avg:>12.0f}")

    print(f"{'='*60}")


def read_results(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _same(a, b):
    """Equal as written: a resumed run writes a blank as "nan", and a
    count read back through pandas as "12.0"."""
    a, b = ("" if v in ("", "nan") else v for v in (a, b))
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def by_edition(rows):
    return {(r["tournament_name"], r["year"]): r for r in rows}


def refresh_diff(old, new):
    """(added keys, removed keys, {key: changed columns}) between two
    by_edition maps."""
    changed = {}
    for key in sorted(old.keys() & new.keys()):
        cols = [c for c in FIELDNAMES if not _same(old[key].get(c, ""), new[key].get(c, ""))]
        if cols:
            changed[key] = cols
    return sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys()), changed


def print_refresh_diff(old_path, new_path):
    old, new = by_edition(read_results(old_path)), by_edition(read_results(new_path))
    added, removed, changed = refresh_diff(old, new)
    print(f"\nFull refresh against {old_path}: {len(added)} added, {len(removed)} removed, "
          f"{len(changed)} changed, {len(new) - len(added) - len(changed)} unchanged")
    for name, year in added:
        print(f"  ADDED    {name} {year}")
    for name, year in removed:
        print(f"  REMOVED  {name} {year}")
    by_column = Counter(c for cols in changed.values() for c in cols)
    print("  Changed columns: " + (", ".join(f"{c} {n}" for c, n in by_column.most_common()) or "none"))
    for key, cols in changed.items():
        diffs = "; ".join(f"{c} {old[key].get(c, '')!r} -> {new[key].get(c, '')!r}" for c in cols)
        print(f"  CHANGED  {key[0]} {key[1]}: {diffs}")
