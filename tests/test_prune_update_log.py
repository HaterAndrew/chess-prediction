"""Tests for update_log.csv time-window rotation (G10)."""
import csv
from datetime import datetime, timedelta
from importlib import import_module


auto_update = import_module("auto_update")

HEADER = ["run_timestamp", "family", "status", "current_count",
          "point_estimate", "ci_lower", "ci_upper", "days_remaining"]


def _write_log(path, timestamps):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for ts in timestamps:
            w.writerow([ts, "Test Open", "live", 100, 120, 100, 140, 10])


def test_prune_drops_old_keeps_recent(tmp_path):
    log = tmp_path / "update_log.csv"
    now = datetime.now()
    recent = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(days=200)).strftime("%Y-%m-%d %H:%M:%S")
    _write_log(log, [old, recent, old])
    kept, dropped = auto_update.prune_update_log(path=str(log), days=90)
    assert (kept, dropped) == (1, 2)
    with open(log) as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2                      # header + 1 recent row
    assert rows[0] == HEADER                   # header preserved
    assert rows[1][0].startswith(recent[:10])


def test_prune_keeps_unparseable_rows(tmp_path):
    log = tmp_path / "update_log.csv"
    _write_log(log, ["not-a-date"])
    kept, dropped = auto_update.prune_update_log(path=str(log), days=90)
    assert (kept, dropped) == (1, 0)


def test_prune_noop_when_missing(tmp_path):
    assert auto_update.prune_update_log(path=str(tmp_path / "nope.csv")) == (0, 0)
