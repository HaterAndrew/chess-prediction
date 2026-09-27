"""The forecast ledger records every published forecast with the code that
made it, and never loses or misaligns a row: it is the record the live
scoreboard grades, so a row it drops or shifts is a forecast nobody can check.
"""
import csv
import json
import os

import pytest

from pipeline import config, ledger
from shared import model_version

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _card(**over):
    card = dict(family="Graduated Open", year=2026, status="live", event_start="2026-10-09",
                current_count=58, gross_count=60, withdrawal_count=2, point_estimate=261,
                ci_lower=238, ci_upper=284, ci_level=0.8, days_remaining=12,
                prediction_source="model", prediction_tier="A", low_confidence=False)
    card.update(over)
    return card


def _website(*cards, **top):
    payload = {"generated": "2026-09-27", "is_stale": False, "tournaments": list(cards)}
    payload.update(top)
    return payload


def _rows(website, **kw):
    kw = {"run_ts": "2026-09-27 06:37:53", "model_label": "n5v4",
          "model_hash": "abc", "code_commit": "70f39a0", **kw}
    return ledger.ledger_rows(website, **kw)


def test_one_row_per_live_card_with_its_forecast_and_horizon():
    rows = _rows(_website(_card(), _card(family="Done Open", status="complete"),
                          _card(family="Old Open", status="historical")))
    assert [r["family"] for r in rows] == ["Graduated Open"]
    row = rows[0]
    assert row["as_of_date"] == "2026-09-27"
    assert row["T"] == 12, "days from the forecast date to the start"
    assert (row["point"], row["ci_lower"], row["ci_upper"]) == (261, 238, 284)
    assert (row["count"], row["gross_count"], row["withdrawal_count"]) == (58, 60, 2)
    assert (row["route"], row["tier"], row["published"]) == ("model", "A", 1)
    assert (row["model_hash"], row["code_commit"]) == ("abc", "70f39a0")


def test_a_stale_run_is_flagged_on_every_row():
    rows = _rows(_website(_card(), _card(family="B"), is_stale=True))
    assert {r["is_stale"] for r in rows} == {1}


def test_a_missing_start_date_leaves_the_horizon_blank():
    assert _rows(_website(_card(event_start=None)))[0]["T"] == ""
    assert _rows(_website(_card(event_start="soon")))[0]["T"] == ""


def test_append_writes_the_header_once_and_keeps_every_row(tmp_path):
    path = tmp_path / "forecast_ledger.csv"
    assert ledger.append_ledger(_rows(_website(_card())), path) == 1
    assert ledger.append_ledger(_rows(_website(_card(), _card(family="B"))), path) == 2
    with open(path, newline="") as fh:
        lines = list(csv.reader(fh))
    assert lines[0] == ledger.LEDGER_FIELDS
    assert len(lines) == 4


def test_append_refuses_a_file_under_another_header(tmp_path):
    path = tmp_path / "forecast_ledger.csv"
    path.write_text("as_of_date,family\n2026-09-26,Graduated Open\n")
    with pytest.raises(ValueError, match="not the ledger header"):
        ledger.append_ledger(_rows(_website(_card())), path)
    assert path.read_text().count("\n") == 2, "the refused file is left as it was"


def test_step_records_tonights_live_cards(tmp_path, monkeypatch):
    website = tmp_path / "website_data.json"
    website.write_text(json.dumps(_website(_card(), _card(family="B", status="complete"))))
    monkeypatch.setattr(config, "WEBSITE_JSON", str(website))
    monkeypatch.setattr(config, "FORECAST_LEDGER", str(tmp_path / "forecast_ledger.csv"))
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef")
    assert ledger.step_record_forecasts() == 1
    with open(tmp_path / "forecast_ledger.csv", newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["code_commit"] == "0123456789ab"
    assert row["model_label"] == model_version.MODEL_LABEL
    assert row["model_hash"] == model_version.model_hash()


def test_model_hash_is_stable_and_moves_when_a_source_file_changes(tmp_path):
    (tmp_path / "model").mkdir()
    src = tmp_path / "model" / "engine.py"
    src.write_text("K = 1\n")
    (tmp_path / "notes.md").write_text("not a model source\n")
    first = model_version.model_hash(tmp_path)
    assert model_version.model_hash(tmp_path) == first
    (tmp_path / "notes.md").write_text("edited\n")
    assert model_version.model_hash(tmp_path) == first, "files outside the sources do not count"
    src.write_text("K = 2\n")
    assert model_version.model_hash(tmp_path) != first


def test_code_commit_is_blank_outside_ci():
    assert model_version.code_commit({}) == ""
    assert model_version.code_commit({"GITHUB_SHA": "0123456789abcdef"}) == "0123456789ab"


def test_nightly_commits_the_ledger():
    """A ledger the workflow never stages is rebuilt from nothing every run."""
    path = os.path.join(PROJECT_ROOT, ".github", "workflows", "daily_update.yml")
    with open(path) as fh:
        yml = fh.read()
    commit_step = yml.split("Commit and push changes")[1].split("Publish degraded-state banner")[0]
    add_line = next(ln for ln in commit_step.splitlines() if ln.strip().startswith("git add output/"))
    assert "output/forecast_ledger.csv" in add_line


def test_pipeline_records_forecasts_after_logging_the_run():
    with open(os.path.join(PROJECT_ROOT, "auto_update.py")) as fh:
        src = fh.read()
    assert src.index("step_log_run()\n") < src.index("step_record_forecasts()\n")
