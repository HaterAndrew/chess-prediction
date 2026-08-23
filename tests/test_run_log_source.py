"""The estimator that produced a run has to survive the update_log.csv round trip.

2026-08-23: the freeze scanner read 97 runs of interim metadata_historical_avg
history against a card the model had served for one night, called the pipeline
CRITICAL, and the site spent the day behind a degraded banner. update_log.csv
recorded no prediction_source, so nothing downstream could tell the two
estimators apart. Writer and loader are tested together because the column is
worthless unless both halves agree on it.
"""
import csv
import json

from tournament_aliases import canonicalize_family

from healthcheck import context
from pipeline import config, run_log

LEGACY_HEADER = ("run_timestamp,family,status,current_count,point_estimate,"
                 "ci_lower,ci_upper,days_remaining")


def _log_run(tmp_path, monkeypatch, log_path, **card_over):
    """Run the logger against one synthetic card, return the rows it left."""
    card = dict(family="Graduated Open", year=2026, status="live",
                current_count=13, point_estimate=313, ci_lower=296,
                ci_upper=338, days_remaining=48, prediction_source="model")
    card.update(card_over)
    website = tmp_path / "website_data.json"
    website.write_text(json.dumps({"tournaments": [card]}))

    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "WEBSITE_JSON", str(website))
    monkeypatch.setattr(config, "UPDATE_LOG", str(log_path))
    run_log.step_log_run()

    with open(log_path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_new_log_records_the_estimator_that_produced_the_row(tmp_path, monkeypatch):
    rows = _log_run(tmp_path, monkeypatch, tmp_path / "update_log.csv")
    assert rows[-1]["prediction_source"] == "model"


def test_existing_log_gains_the_column_without_losing_rows(tmp_path, monkeypatch):
    """Appending a wider row under the old header would misalign the whole
    file, so the writer migrates it first and pads the runs it cannot attribute."""
    log = tmp_path / "update_log.csv"
    log.write_text(LEGACY_HEADER + "\n"
                   "2026-08-22 02:29:07,Graduated Open,live,13,313,296,338,48\n")

    rows = _log_run(tmp_path, monkeypatch, log)

    assert len(rows) == 2
    assert rows[0]["days_remaining"] == "48"
    assert rows[0]["prediction_source"] == ""
    assert rows[1]["prediction_source"] == "model"


def test_migration_refuses_a_header_it_did_not_write(tmp_path):
    """A header that is not the old prefix means someone else owns this file.
    Padding it would shift every column one to the left, silently."""
    log = tmp_path / "update_log.csv"
    log.write_text("family,run_timestamp,status\nGraduated Open,2026-08-22,live\n")

    try:
        run_log.migrate_log_header(str(log))
    except ValueError as exc:
        assert "refusing to migrate" in str(exc)
    else:
        raise AssertionError("a foreign header must not be migrated in place")


def test_log_history_carries_the_estimator_per_run(tmp_path):
    log = tmp_path / "update_log.csv"
    log.write_text(
        LEGACY_HEADER + ",prediction_source\n"
        "2026-08-21 02:00:00,Graduated Open,live,12,313,296,338,49,metadata_historical_avg\n"
        "2026-08-22 02:00:00,Graduated Open,live,13,313,296,338,48,model\n"
    )

    hist = context.load_log_history(str(log))

    assert list(hist[canonicalize_family("Graduated Open")]) == [
        (313, 12, "metadata_historical_avg"),
        (313, 13, "model"),
    ]


def test_runs_predating_the_column_carry_no_estimator(tmp_path):
    """Unattributable runs read as None whether the column is absent (old file)
    or empty (migrated file) — the freeze check counts neither."""
    log = tmp_path / "update_log.csv"
    log.write_text(
        LEGACY_HEADER + ",prediction_source\n"
        "2026-08-21 02:00:00,Graduated Open,live,12,313,296,338,49,\n"
    )
    absent = tmp_path / "old_log.csv"
    absent.write_text(LEGACY_HEADER + "\n"
                      "2026-08-21 02:00:00,Graduated Open,live,12,313,296,338,49\n")

    fam = canonicalize_family("Graduated Open")
    assert [r.prediction_source for r in context.load_log_history(str(log))[fam]] == [None]
    assert [r.prediction_source for r in context.load_log_history(str(absent))[fam]] == [None]
