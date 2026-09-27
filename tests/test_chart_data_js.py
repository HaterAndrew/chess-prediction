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


def test_calibration_dots_stack_where_they_would_touch(res):
    c = res["cal"]
    assert (c["below"], c["inside"], c["above"], c["pct"]) == (2, 4, 2, 50)
    # x = pit x width, held r from each edge; a dot within 2r+1 of the last
    # one in a row moves up a row.
    assert c["placed"] == [[5, 0], [6, 1], [100, 0], [101, 1], [102, 2], [140, 0], [194, 0], [195, 1]]
    assert c["rows"] == 3


def test_a_segment_through_a_box_hits_it(res):
    assert res["seg_through"] is True
    assert res["seg_past"] is False


def test_a_label_takes_the_first_spot_clear_of_lines_and_labels(res):
    assert res["spot_free"] == [100, 86, True], "with nothing near, above the point"
    assert res["spot_below"] == [100, 114, True], "a line through 'above' moves it below"
    x, y, clear = res["spot_diag"]
    assert clear and x != 100, "above and below blocked: a diagonal"
    assert res["spot_none"] is False, "no spot fits the area: says so"
    assert res["spot_order"] == "left", "a caller's order wins"
    assert res["cross"] == [True, False]
    assert res["spot_sight"] == "below", "a label never sits across a line from its dot"
    assert res["spot_slide"] == [90, True], "a label below slides inside the area"
    assert res["spot_ring"] == [120, True], "blocked close in, it steps out a ring"
    assert res["spot_margin"] == ["above", "below"], "the margin keeps a line's width clear"
