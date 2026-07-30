"""update_log.csv writer + retention pruning (auto_update, verbatim)."""
import csv
import json
import os
from datetime import datetime, timedelta

from pipeline import config


def prune_update_log(path=None, days=90):
    """Bound update_log.csv growth (G10): keep only rows from the last `days`
    of runs so the committed file and its git churn stay bounded. Rows with an
    unparseable timestamp are kept (fail-safe). Returns (kept, dropped)."""
    path = path or config.UPDATE_LOG
    if not os.path.exists(path):
        return (0, 0)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return (len(rows), 0)
    header, data = rows[0], rows[1:]
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    for r in data:
        try:
            ts = datetime.strptime(r[0][:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, IndexError):
            kept.append(r)
            continue
        if ts >= cutoff:
            kept.append(r)
    if len(kept) != len(data):
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(kept)
    return (len(kept), len(data) - len(kept))


def step_log_run():
    """Log this run's predictions to update_log.csv."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # Initialize log if it doesn't exist
    write_header = not os.path.exists(config.UPDATE_LOG)

    with open(config.WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    lines_logged = 0
    with open(config.UPDATE_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                'run_timestamp', 'family', 'status', 'current_count',
                'point_estimate', 'ci_lower', 'ci_upper', 'days_remaining'
            ])
        for t in data.get('tournaments', []):
            if t.get('year') != 2026:
                continue
            if t.get('status') not in ('live', 'complete'):
                continue
            writer.writerow([
                config.RUN_TS, t['family'], t['status'], t['current_count'],
                t['point_estimate'], t['ci_lower'], t['ci_upper'],
                t['days_remaining']
            ])
            lines_logged += 1

    kept, dropped = prune_update_log()
    if dropped:
        print(f"  Pruned {dropped} update_log rows older than 90 days ({kept} kept)")
    print(f"  Logged {lines_logged} predictions to {config.UPDATE_LOG}")
