"""
Regression tests for the entry-list pass of scrapers/entries.py.

Until 2026-10-20 the code table sent the Eastern Chess Congress to CCA_ECC,
which is the Eastern Class Championships' entry list. The withdrawal pass
treats that page as authoritative and overwrote the Congress gross count with
the Class event's 206 for the whole season, while the CCA index showed 328.
These tests pin both halves: the right code for each Eastern event, and a
guard that refuses an entry-list count far from the index count.
"""

import json

import pytest
import requests

from scrapers import entries
from scrapers.entries import _derive_entry_list_code, scrape_withdrawals


@pytest.mark.parametrize("name, code", [
    ("2026 Eastern Chess Congress (in New Jersey)", "ECCO"),
    ("Eastern Chess Congress", "ECCO"),
    ("2026 Eastern Class Championships (in Connecticut)", "ECC"),
    ("2026 Eastern Open", "EO"),
])
def test_eastern_codes(name, code):
    assert _derive_entry_list_code(name) == code


def _page(active, withdrawn):
    filler = "x" * 1200  # scrape_withdrawals ignores pages under 1000 chars
    return f"<html>{filler}<p>{active} Active Players [+{withdrawn} Withdrawn]</p></html>"


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, timeout=None):
        for code, text in self.pages.items():
            if f"CCA_{code}" in url:
                return _FakeResp(text)
        return _FakeResp("not found", status=404)


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setattr(entries.time, "sleep", lambda s: None)
    monkeypatch.setattr(entries, "MISMATCH_PATH", str(tmp_path / "scrape_mismatches.json"))

    def _run(pages, tournaments):
        monkeypatch.setattr(entries, "_create_session", lambda: _FakeSession(pages))
        scrape_withdrawals(tournaments)
        return tournaments, json.loads((tmp_path / "scrape_mismatches.json").read_text())

    return _run


def _t(name, count):
    return {"name": name, "year": 2026, "entry_count": count}


def test_matching_page_overrides_gross(run):
    rows, mismatches = run({"ECCO26": _page(328, 3)},
                           [_t("2026 Eastern Chess Congress (in New Jersey)", 328)])
    assert (rows[0]["entry_count"], rows[0]["active_count"], rows[0]["withdrawal_count"]) == (331, 328, 3)
    assert mismatches["mismatches"] == []


def test_wrong_page_keeps_index_count_and_records_mismatch(run):
    # The 2026-10-20 failure: the page read belongs to a different event.
    rows, mismatches = run({"ECCO26": _page(196, 10)},
                           [_t("2026 Eastern Chess Congress (in New Jersey)", 328)])
    assert (rows[0]["entry_count"], rows[0]["active_count"], rows[0]["withdrawal_count"]) == (328, 328, 0)
    [m] = mismatches["mismatches"]
    assert m["tournament"] == "2026 Eastern Chess Congress (in New Jersey)"
    assert (m["index_count"], m["entry_list_count"]) == (328, 206)


def test_missing_page_for_event_with_entries_is_recorded(run):
    rows, mismatches = run({}, [_t("2026 Eastern Open", 9)])
    assert rows[0]["entry_count"] == 9
    [m] = mismatches["mismatches"]
    assert m["tournament"] == "2026 Eastern Open"
    assert m["entry_list_count"] is None


def test_request_error_is_recorded(run, monkeypatch):
    class _Boom:
        def get(self, url, timeout=None):
            raise requests.ConnectionError("down")

    monkeypatch.setattr(entries, "_create_session", lambda: _Boom())
    scrape_withdrawals([_t("2026 Eastern Open", 9)])
    data = json.loads(open(entries.MISMATCH_PATH).read())
    assert data["mismatches"][0]["entry_list_count"] is None


def test_small_drift_is_tolerated(run):
    # Index and entry list refresh at slightly different times.
    rows, mismatches = run({"EO26": _page(10, 0)}, [_t("2026 Eastern Open", 9)])
    assert rows[0]["entry_count"] == 10
    assert mismatches["mismatches"] == []


def test_validation_gate_warns_on_todays_mismatches(tmp_path):
    from validation.scrape import validate_scrape_mismatches

    path = tmp_path / "scrape_mismatches.json"
    path.write_text(json.dumps({"date": "2026-10-20", "mismatches": [
        {"tournament": "2026 Eastern Chess Congress (in New Jersey)", "url": "u",
         "index_count": 328, "entry_list_count": 206},
        {"tournament": "2026 Eastern Open", "url": "v",
         "index_count": 9, "entry_list_count": None},
    ]}))
    report = validate_scrape_mismatches(str(path), today="2026-10-20")
    assert report.passed and len(report.warnings) == 2
    assert "328" in report.warnings[0] and "206" in report.warnings[0]
    # Yesterday's file is stale and says nothing about today's scrape.
    assert validate_scrape_mismatches(str(path), today="2026-10-21").warnings == []
    assert validate_scrape_mismatches(str(tmp_path / "absent.json")).warnings == []
