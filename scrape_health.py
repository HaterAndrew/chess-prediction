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
HEALTH_HTML = os.path.join(OUTPUT_DIR, "scrape_health.html")


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


def generate_health_html(output_path=None):
    """Generate a standalone HTML health dashboard.

    Args:
        output_path: path for the HTML file (default: output/scrape_health.html)
    """
    if output_path is None:
        output_path = HEALTH_HTML

    stats = get_health_stats()

    # Load raw entries for the table and chart
    entries = []
    if os.path.exists(HEALTH_LOG):
        with open(HEALTH_LOG, "r") as f:
            try:
                entries = json.load(f)
            except (json.JSONDecodeError, ValueError):
                entries = []

    last_10 = entries[-10:] if entries else []
    last_10.reverse()  # most recent first

    # Determine status badge
    if stats["consecutive_failures"] == 0 and (stats["data_freshness_hours"] or 0) < 36:
        badge_color = "#22c55e"  # green
        badge_text = "HEALTHY"
    elif stats["consecutive_failures"] <= 2 and (stats["data_freshness_hours"] or 999) < 72:
        badge_color = "#eab308"  # yellow
        badge_text = "DEGRADED"
    else:
        badge_color = "#ef4444"  # red
        badge_text = "UNHEALTHY"

    # Build table rows
    table_rows = ""
    for e in last_10:
        status_dot = "&#9679;" if e["success"] else "&#9679;"
        dot_color = "#22c55e" if e["success"] else "#ef4444"
        status_label = "OK" if e["success"] else "FAIL"
        table_rows += f"""
        <tr>
          <td>{e['timestamp']}</td>
          <td><span style="color:{dot_color}">{status_dot}</span> {status_label}</td>
          <td>{e['row_count']}</td>
          <td>{e['error_count']}</td>
          <td>{e['warning_count']}</td>
          <td>{e['duration_seconds']}s</td>
        </tr>"""

    # Build daily bar chart data (last 30 days)
    # Aggregate by date: count successes and failures per day
    daily = {}
    cutoff = datetime.now() - timedelta(days=30)
    for e in entries:
        try:
            dt = datetime.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt < cutoff:
            continue
        day = dt.strftime("%Y-%m-%d")
        if day not in daily:
            daily[day] = {"ok": 0, "fail": 0}
        if e["success"]:
            daily[day]["ok"] += 1
        else:
            daily[day]["fail"] += 1

    # Sort by date
    sorted_days = sorted(daily.keys())

    # Build bar chart HTML (pure CSS)
    max_runs = max((d["ok"] + d["fail"] for d in daily.values()), default=1)
    chart_bars = ""
    for day in sorted_days:
        d = daily[day]
        d["ok"] + d["fail"]
        ok_pct = (d["ok"] / max_runs) * 100
        fail_pct = (d["fail"] / max_runs) * 100
        short_date = day[5:]  # MM-DD
        chart_bars += f"""
        <div class="bar-group" title="{day}: {d['ok']} ok, {d['fail']} fail">
          <div class="bar-stack">
            <div class="bar bar-ok" style="height:{ok_pct}%"></div>
            <div class="bar bar-fail" style="height:{fail_pct}%"></div>
          </div>
          <div class="bar-label">{short_date}</div>
        </div>"""

    # Format freshness
    freshness_display = "N/A"
    if stats["data_freshness_hours"] is not None:
        h = stats["data_freshness_hours"]
        if h < 1:
            freshness_display = f"{int(h * 60)}m"
        elif h < 48:
            freshness_display = f"{h:.1f}h"
        else:
            freshness_display = f"{h / 24:.1f}d"

    last_run_display = stats["last_successful_run"] or "Never"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Scrape Health Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a; color: #e2e8f0; padding: 2rem;
  }}
  h1 {{ font-size: 1.5rem; margin-bottom: 1.5rem; color: #f8fafc; }}
  .badge {{
    display: inline-block; padding: 0.35rem 1rem; border-radius: 9999px;
    font-weight: 700; font-size: 0.85rem; letter-spacing: 0.05em;
    background: {badge_color}; color: #fff; margin-left: 1rem;
    vertical-align: middle;
  }}
  .stats-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem; margin-bottom: 2rem;
  }}
  .stat-card {{
    background: #1e293b; border-radius: 0.75rem; padding: 1.25rem;
    text-align: center;
  }}
  .stat-card .label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase;
    letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
  .stat-card .value {{ font-size: 2rem; font-weight: 700; color: #f8fafc; }}
  .stat-card .sub {{ font-size: 0.75rem; color: #64748b; margin-top: 0.25rem; }}

  table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
  th {{ text-align: left; padding: 0.6rem 0.8rem; background: #1e293b;
    color: #94a3b8; font-size: 0.75rem; text-transform: uppercase;
    letter-spacing: 0.05em; }}
  td {{ padding: 0.6rem 0.8rem; border-bottom: 1px solid #1e293b;
    font-size: 0.85rem; }}
  tr:hover {{ background: #1e293b44; }}

  .chart-container {{ margin-bottom: 2rem; }}
  .chart-title {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem;
    text-transform: uppercase; letter-spacing: 0.05em; }}
  .chart {{
    display: flex; align-items: flex-end; gap: 3px;
    height: 120px; background: #1e293b; border-radius: 0.5rem;
    padding: 0.75rem 0.5rem 1.75rem; overflow-x: auto;
  }}
  .bar-group {{ display: flex; flex-direction: column; align-items: center;
    flex: 1; min-width: 18px; position: relative; }}
  .bar-stack {{ display: flex; flex-direction: column; width: 100%;
    height: 100px; justify-content: flex-end; }}
  .bar {{ width: 100%; border-radius: 2px 2px 0 0; min-height: 0; }}
  .bar-ok {{ background: #22c55e; }}
  .bar-fail {{ background: #ef4444; border-radius: 0; }}
  .bar-label {{
    font-size: 0.55rem; color: #64748b; position: absolute; bottom: -16px;
    white-space: nowrap; transform: rotate(-45deg); transform-origin: top left;
  }}

  .footer {{ font-size: 0.7rem; color: #475569; margin-top: 2rem; }}
</style>
</head>
<body>

<h1>Scrape Health <span class="badge">{badge_text}</span></h1>

<div class="stats-grid">
  <div class="stat-card">
    <div class="label">30-Day Success Rate</div>
    <div class="value">{stats['success_rate_30d']}%</div>
    <div class="sub">{stats['total_runs']} total runs</div>
  </div>
  <div class="stat-card">
    <div class="label">Data Freshness</div>
    <div class="value">{freshness_display}</div>
    <div class="sub">since last success</div>
  </div>
  <div class="stat-card">
    <div class="label">Consecutive Failures</div>
    <div class="value">{stats['consecutive_failures']}</div>
    <div class="sub">current streak</div>
  </div>
  <div class="stat-card">
    <div class="label">Last Success</div>
    <div class="value" style="font-size:1rem">{last_run_display}</div>
  </div>
</div>

<div class="chart-container">
  <div class="chart-title">Daily Runs (Last 30 Days)</div>
  <div class="chart">
    {chart_bars if chart_bars else '<div style="color:#64748b;margin:auto">No data yet</div>'}
  </div>
</div>

<h2 style="font-size:1rem;margin-bottom:0.75rem;color:#f8fafc">Last 10 Runs</h2>
<table>
  <thead>
    <tr>
      <th>Timestamp</th><th>Status</th><th>Rows</th>
      <th>Errors</th><th>Warnings</th><th>Duration</th>
    </tr>
  </thead>
  <tbody>
    {table_rows if table_rows else '<tr><td colspan="6" style="color:#64748b;text-align:center">No runs recorded</td></tr>'}
  </tbody>
</table>

<div class="footer">
  Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &mdash; scrape_health.py
</div>

</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


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
