"""
Scrape health dashboard — tracks daily scrape success rate, data freshness,
and last successful run.

Appends to output/scrape_health.json (append-only log).
Generates output/scrape_health.html (standalone dashboard).

Usage:
    python scrape_health.py          # print current health stats
"""

import json
import os
from datetime import datetime, timedelta

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
HEALTH_LOG = os.path.join(OUTPUT_DIR, "scrape_health.json")


def log_scrape_attempt(success, row_count, validation_errors, validation_warnings,
                       duration_seconds=0.0):
    """Append a scrape attempt entry to the health log.

    Args:
        success: bool — did the pipeline complete without error?
        row_count: int — rows scraped (0 on failure)
        validation_errors: int — blocking validation errors
        validation_warnings: int — non-blocking validation warnings
        duration_seconds: float — wall-clock time for the pipeline run
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Read existing log (append-only)
    entries = []
    if os.path.exists(HEALTH_LOG):
        with open(HEALTH_LOG, "r") as f:
            try:
                entries = json.load(f)
            except (json.JSONDecodeError, ValueError):
                # v5 Cat T: never reset silently — the log is the only scrape
                # telemetry history and a truncated write used to erase it
                # without a trace.
                print(f"WARNING: {HEALTH_LOG} unreadable — starting a fresh "
                      f"scrape-health log (previous history lost)")
                entries = []

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "success": bool(success),
        "row_count": int(row_count),
        "error_count": int(validation_errors),
        "warning_count": int(validation_warnings),
        "duration_seconds": round(float(duration_seconds), 1),
    }
    entries.append(entry)

    with open(HEALTH_LOG, "w") as f:
        json.dump(entries, f, indent=2)

    return entry


def get_health_stats():
    """Read the health log and return summary statistics.

    Returns:
        dict with keys: last_successful_run, last_data_run, success_rate_30d,
        total_runs, consecutive_failures, data_freshness_hours
    """
    empty = {
        "last_successful_run": None,
        "last_data_run": None,
        "success_rate_30d": 0.0,
        "total_runs": 0,
        "consecutive_failures": 0,
        "data_freshness_hours": None,
    }
    if not os.path.exists(HEALTH_LOG):
        return empty

    with open(HEALTH_LOG, "r") as f:
        try:
            entries = json.load(f)
        except (json.JSONDecodeError, ValueError):
            print(f"WARNING: {HEALTH_LOG} unreadable — health stats reset")
            entries = []

    if not entries:
        return empty

    def _ts(e):
        """Parse an entry timestamp, or None on malformed data (v5 Cat T —
        one corrupt entry used to crash the whole stats pass)."""
        try:
            return datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, TypeError, ValueError):
            print(f"WARNING: scrape-health entry with malformed timestamp "
                  f"skipped: {e.get('timestamp') if isinstance(e, dict) else e!r}")
            return None

    now = datetime.now()
    cutoff_30d = now - timedelta(days=30)

    # Last successful run
    last_success_ts = None
    for e in reversed(entries):
        if e.get("success"):
            last_success_ts = e["timestamp"]
            break

    # v5 Cat T: last run that actually captured data. A run can succeed while
    # scraping nothing (the CI --skip-scrape era logged success=True with
    # row_count=0 every night), so freshness keyed off bare success lied.
    last_data_ts = None
    for e in reversed(entries):
        if e.get("success") and e.get("row_count", 0) > 0:
            last_data_ts = e["timestamp"]
            break

    # 30-day success rate
    recent = [e for e in entries
              if (t := _ts(e)) is not None and t >= cutoff_30d]
    if recent:
        success_count = sum(1 for e in recent if e.get("success"))
        success_rate = round(100.0 * success_count / len(recent), 1)
    else:
        success_rate = 0.0

    # Consecutive failures (from most recent backwards)
    consecutive_failures = 0
    for e in reversed(entries):
        if not e.get("success"):
            consecutive_failures += 1
        else:
            break

    # Data freshness — hours since data was last CAPTURED, not since the
    # pipeline last exited zero.
    freshness_hours = None
    if last_data_ts:
        last_dt = _ts({"timestamp": last_data_ts})
        if last_dt is not None:
            freshness_hours = round((now - last_dt).total_seconds() / 3600, 1)

    return {
        "last_successful_run": last_success_ts,
        "last_data_run": last_data_ts,
        "success_rate_30d": success_rate,
        "total_runs": len(entries),
        "consecutive_failures": consecutive_failures,
        "data_freshness_hours": freshness_hours,
    }


# The standalone HTML dashboard (generate_health_html -> output/scrape_health.html)
# was retired 2026-07-30 (owner-approved): nothing published or linked it.
# The JSON telemetry above (scrape_health.json) remains the health surface.


def main():
    """CLI: print current health stats."""
    stats = get_health_stats()

    print(f"\n{'='*50}")
    print("  SCRAPE HEALTH STATUS")
    print(f"{'='*50}")
    print(f"  Last successful run:    {stats['last_successful_run'] or 'Never'}")
    print(f"  30-day success rate:    {stats['success_rate_30d']}%")
    print(f"  Total runs:             {stats['total_runs']}")
    print(f"  Consecutive failures:   {stats['consecutive_failures']}")
    freshness = stats['data_freshness_hours']
    if freshness is not None:
        print(f"  Data freshness:         {freshness:.1f} hours")
    else:
        print("  Data freshness:         N/A (no successful run)")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
