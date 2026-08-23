"""update_log.csv writer + retention pruning (auto_update, verbatim)."""
import csv
import json
import os
from datetime import datetime, timedelta

from pipeline import config

# prediction_source joined the schema on 2026-08-23: without the estimator that
# produced a row, the freeze scanner counted months of interim metadata runs
# against a card the model had just taken over and aborted the pipeline.
LOG_FIELDS = ['run_timestamp', 'family', 'status', 'current_count',
              'point_estimate', 'ci_lower', 'ci_upper', 'days_remaining',
              'prediction_source']


def migrate_log_header(path=None, fields=None):
    """Widen an existing log to the current column set, padding old rows.

    Appending a wider row under a narrower header misaligns the file instead of
    failing, and every reader downstream would then see the new column as
    permanently absent. Returns True when the file was rewritten.
    """
    path = path or config.UPDATE_LOG
    fields = fields or LOG_FIELDS
    if not os.path.exists(path):
        return False
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] == fields:
        return False
    header = rows[0]
    if header != fields[:len(header)]:
        raise ValueError(
            f"{path} header {header} is not a prefix of {fields} — "
            f"refusing to migrate a file this writer does not own"
        )
    pad = [''] * (len(fields) - len(header))
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(r + pad for r in rows[1:])
    return True


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
    if not write_header and migrate_log_header(config.UPDATE_LOG):
        print(f"  Migrated {config.UPDATE_LOG} to the {len(LOG_FIELDS)}-column schema")

    with open(config.WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    lines_logged = 0
    with open(config.UPDATE_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(LOG_FIELDS)
        for t in data.get('tournaments', []):
            if t.get('year') != 2026:
                continue
            if t.get('status') not in ('live', 'complete'):
                continue
            writer.writerow([
                config.RUN_TS, t['family'], t['status'], t['current_count'],
                t['point_estimate'], t['ci_lower'], t['ci_upper'],
                t['days_remaining'], t.get('prediction_source') or ''
            ])
            lines_logged += 1

    kept, dropped = prune_update_log()
    if dropped:
        print(f"  Pruned {dropped} update_log rows older than 90 days ({kept} kept)")
    print(f"  Logged {lines_logged} predictions to {config.UPDATE_LOG}")
