"""Health scan and prediction log key on the edition, (family, year).

2026-09-17. Once the scraper keeps next season's events, the 2027 Atlantic
City Open and the finished 2026 one sit side by side. Keyed on the family
alone, the scan would call the 2027 scrape rows a dropped event (CRITICAL,
which aborts the nightly run), compare the finished card's 424 against the new
edition's handful of entries, and read both editions' logged runs as one card.
"""
import csv
import json

from data_health import scan
from healthcheck import context
from pipeline import config, run_log
from tests.test_data_health import card, ctx

ACO = "Atlantic City Open"


def _keys(cards, **ctx_kw):
    report = scan({"generated": "2026-09-17", "tournaments": cards}, ctx(**ctx_kw))
    return {(f["severity"], f["mode"]) for f in report.findings}


def test_next_season_scrape_with_its_card_is_not_a_dropped_event():
    cards = [card(family=ACO, year=2026, status="complete", current_count=424,
                  point_estimate=424, prediction_source="final"),
             card(family=ACO, year=2027, current_count=12)]
    keys = _keys(cards, scrape_latest={
        (ACO, 2026): {"net": 401, "gross": 424, "date": "2026-03-29"},
        (ACO, 2027): {"net": 12, "gross": 12, "date": "2026-09-17"},
    })
    assert ("CRITICAL", "dropped-event") not in keys
    assert ("HIGH", "stale-count") not in keys


def test_next_season_scrape_without_a_card_is_a_dropped_event():
    # The 2026 card of the same family must not hide the missing 2027 one.
    cards = [card(family=ACO, year=2026, status="complete", current_count=424,
                  point_estimate=424, prediction_source="final")]
    keys = _keys(cards, scrape_latest={
        (ACO, 2026): {"net": 401, "gross": 424, "date": "2026-03-29"},
        (ACO, 2027): {"net": 12, "gross": 12, "date": "2026-09-17"},
    })
    assert ("CRITICAL", "dropped-event") in keys


def test_frozen_check_reads_one_editions_runs():
    # Three identical 2026 estimates with rising counts would be a freeze, but
    # they belong to last season's card, not the 2027 one being scanned.
    keys = _keys([card(family=ACO, year=2027)], log_hist={
        (ACO, 2026): [(110, 18, "model"), (110, 25, "model"), (110, 31, "model")],
        (ACO, 2027): [(200, 5, "model")],
    })
    assert ("CRITICAL", "frozen-estimate") not in keys


def test_scrape_latest_is_loaded_per_edition(tmp_path, monkeypatch):
    scrape = tmp_path / "daily_scrape.csv"
    scrape.write_text(
        "date,tournament_name,entry_count,active_count,withdrawal_count,url\n"
        "2026-03-29,2026 Atlantic City Open,424,401,23,u\n"
        "2026-09-16,2027 Atlantic City Open,1,1,0,u\n"
        "2026-09-17,2027 Atlantic City Open,3,2,1,u\n")
    monkeypatch.setattr(context, "DAILY_SCRAPE_CSV", str(scrape))
    latest = context.Context._load_scrape_latest(None)
    assert latest[(ACO, 2026)] == {"net": 401, "gross": 424, "date": "2026-03-29"}
    assert latest[(ACO, 2027)] == {"net": 2, "gross": 3, "date": "2026-09-17"}


# ── prediction log ───────────────────────────────────────────────────────

def _log_cards(tmp_path, monkeypatch, cards):
    website = tmp_path / "website_data.json"
    website.write_text(json.dumps({"tournaments": cards}))
    log = tmp_path / "update_log.csv"
    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "WEBSITE_JSON", str(website))
    monkeypatch.setattr(config, "UPDATE_LOG", str(log))
    run_log.step_log_run()
    with open(log, newline="") as fh:
        return list(csv.DictReader(fh))


def _card(year, status="live", **over):
    base = dict(family=ACO, year=year, status=status, current_count=12,
                point_estimate=400, ci_lower=350, ci_upper=460,
                days_remaining=188, prediction_source="model")
    base.update(over)
    return base


def test_next_season_predictions_are_logged_with_their_year(tmp_path, monkeypatch):
    rows = _log_cards(tmp_path, monkeypatch, [
        _card(2026, status="complete", current_count=424, point_estimate=424),
        _card(2027),
        _card(2025, status="historical"),
    ])
    assert [(r["family"], r["year"], r["status"]) for r in rows] == [
        (ACO, "2026", "complete"), (ACO, "2027", "live")]


def test_log_history_keeps_editions_apart(tmp_path):
    log = tmp_path / "update_log.csv"
    log.write_text(
        ",".join(run_log.LOG_FIELDS) + "\n"
        "2026-03-20 02:00:00,Atlantic City Open,live,390,430,400,460,5,model,2026\n"
        "2026-09-17 02:00:00,Atlantic City Open,live,12,400,350,460,188,model,2027\n")
    hist = context.load_log_history(str(log))
    assert list(hist[(ACO, 2026)]) == [(430, 390, "model")]
    assert list(hist[(ACO, 2027)]) == [(400, 12, "model")]


def test_runs_logged_before_the_year_column_belong_to_the_season_they_ran_in(tmp_path):
    # Until the column existed the writer logged current-season cards only, so
    # the run's own year is the edition's year.
    log = tmp_path / "update_log.csv"
    log.write_text(
        ",".join(run_log.LOG_FIELDS) + "\n"
        "2026-08-22 02:00:00,Atlantic City Open,live,13,313,296,338,48,model,\n")
    hist = context.load_log_history(str(log))
    assert list(hist[(ACO, 2026)]) == [(313, 13, "model")]
