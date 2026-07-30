"""v5 Cat T (audit/AUDIT_2026-07-30.md): truthful scrape-health telemetry.

The CI --skip-scrape bypass logged success=True row_count=0 every night while
daily_scrape.csv actually gained ~15 rows, and data_freshness_hours keyed off
bare success — so a pipeline that scraped nothing for a month would still
read "fresh". The log also reset itself silently on corrupt JSON and crashed
whole-stats on one malformed timestamp.

Contract: freshness keys off the last run that CAPTURED data (success AND
row_count > 0); corrupt logs and malformed entries warn loudly and degrade
per-entry, never wholesale.
"""
import json
from datetime import datetime, timedelta


import scrape_health  # noqa: E402


def _entry(ts, success=True, rows=0):
    return {"timestamp": ts, "success": success, "row_count": rows,
            "error_count": 0, "warning_count": 0, "duration_seconds": 1.0}


def _ts(hours_ago):
    return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _use_log(monkeypatch, tmp_path, entries):
    log = tmp_path / "scrape_health.json"
    log.write_text(json.dumps(entries))
    monkeypatch.setattr(scrape_health, "HEALTH_LOG", str(log))
    return log


def test_freshness_keys_off_last_data_run(monkeypatch, tmp_path):
    """A run that succeeded but scraped nothing must not refresh freshness —
    the exact shape every CI night had under the --skip-scrape bypass."""
    _use_log(monkeypatch, tmp_path, [
        _entry(_ts(50), success=True, rows=16),   # last real data, 50h ago
        _entry(_ts(26), success=True, rows=0),    # "successful" empty run
        _entry(_ts(2), success=True, rows=0),     # another one
    ])
    stats = scrape_health.get_health_stats()
    assert stats["last_data_run"] is not None
    assert stats["data_freshness_hours"] is not None
    assert stats["data_freshness_hours"] >= 49, (
        "freshness must track the last run that captured rows, "
        f"got {stats['data_freshness_hours']}h"
    )
    # last_successful_run keeps its old meaning (most recent success)
    assert stats["last_successful_run"] == stats["last_data_run"] or (
        stats["last_successful_run"] > stats["last_data_run"])


def test_corrupt_log_warns_before_reset(monkeypatch, tmp_path, capsys):
    log = tmp_path / "scrape_health.json"
    log.write_text("{not json")
    monkeypatch.setattr(scrape_health, "HEALTH_LOG", str(log))
    monkeypatch.setattr(scrape_health, "OUTPUT_DIR", str(tmp_path))

    entry = scrape_health.log_scrape_attempt(True, 5, 0, 0, 1.0)
    out = capsys.readouterr().out
    assert "WARNING" in out and "unreadable" in out
    assert entry["row_count"] == 5
    # The fresh log holds exactly the new entry
    assert json.loads(log.read_text()) == [entry]


def test_malformed_timestamp_skipped_not_fatal(monkeypatch, tmp_path, capsys):
    _use_log(monkeypatch, tmp_path, [
        _entry("garbage-timestamp", success=True, rows=10),
        _entry(_ts(1), success=True, rows=12),
    ])
    stats = scrape_health.get_health_stats()  # must not raise
    out = capsys.readouterr().out
    assert "malformed timestamp" in out
    assert stats["total_runs"] == 2
    assert stats["data_freshness_hours"] is not None


def test_empty_and_missing_log_shapes(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape_health, "HEALTH_LOG",
                        str(tmp_path / "does_not_exist.json"))
    stats = scrape_health.get_health_stats()
    assert stats["last_data_run"] is None
    assert stats["data_freshness_hours"] is None
    assert stats["total_runs"] == 0
