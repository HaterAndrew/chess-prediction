"""docs/chart_data.js: the charts' pure data shaping.

Every canvas carries a data table only screen readers reach; a cell that is
not escaped would inject markup, and a missing value must read as a dash, not
vanish. Runs tests/js/chart_data_driver.js under node and asserts on its JSON.
Skipped when node is unavailable, matching test_motion_js.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "chart_data_driver.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True, cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_the_table_has_a_caption_headers_and_row_headers(res):
    t = res["table"]
    assert t.startswith("<caption>Entries by edition</caption>")
    assert '<th scope="col">Edition</th><th scope="col">Entries</th>' in t
    assert '<th scope="row">2024</th><td>312</td>' in t


def test_every_cell_is_escaped(res):
    t = res["table"]
    assert "<b>" not in t
    assert "&lt;b&gt;2025&lt;/b&gt;" in t
    assert "2026 &quot;est&quot;" in t


def test_a_missing_value_reads_as_a_dash(res):
    t = res["table"]
    assert "<td>—</td>" in t
    assert t.count("—") == 2


def test_an_empty_table_still_parses(res):
    assert res["table_empty"] == '<thead><tr><th scope="col">A</th></tr></thead><tbody></tbody>'


def test_a_series_holds_its_last_value_until_the_next_point(res):
    assert res["step_before"] is None, "before the series starts there is no value"
    assert res["step_on"] == 5
    assert res["step_between"] == 5
    assert res["step_after"] is None, "past the series' end there is no value"
    assert res["step_empty"] is None


def test_weekly_rows_count_back_from_event_day(res):
    assert res["weekly"] == [[9, 25], [10, 2], [10, 9]]


def test_missing_years_between_editions_become_one_gap_slot(res):
    assert res["slots"] == [
        ["2018", 300, "past", None],
        ["2019*", 310, "past", 420],
        ["2020\u201321", None, "gap", None],
        ["2022", 280, "past", None],
        ["2023", 305, "past", None],
        ["2024", None, "gap", None],
        ["2025", 330, "current", None],
    ]
    assert res["slots_none"] == [["2026", "current"]]


def test_the_pace_gap_reads_in_whole_points(res):
    assert res["pace_behind"]["text"] == "10 pts behind"
    assert res["pace_ahead_one"]["text"] == "1 pt ahead"
    assert res["pace_on"]["text"] == "on pace"
