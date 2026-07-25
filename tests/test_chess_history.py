"""CHESS_HISTORY must be generated from a tracked source, not typed into the build.

v3 O5 (audit/AUDIT_2026-07-25.md). The splice in step_update_html was guarded on
output/chess_history.json, which no script wrote, so it had never fired: 146KB of
content lived only inside the generated docs/data/site_data.js, with no source to
review and nothing stopping a splicer regression from eating it silently.

These tests pin the two things that make the source authoritative — the emitted
bytes still match what shipped, and a malformed source fails loudly instead of
rendering an empty panel.
"""
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PROJECT_ROOT, "scripts")
for p in (PROJECT_ROOT, SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

import gen_chess_history as gch  # noqa: E402

SOURCE = os.path.join(PROJECT_ROOT, "content", "chess_history.json")


@pytest.fixture(scope="module")
def source():
    with open(SOURCE) as f:
        return json.load(f)


def test_the_tracked_source_exists_and_validates(source):
    """Without this file the const has no reviewable origin at all."""
    gch.validate(source)
    assert len(source) >= 365, f"only {len(source)} days covered"


def test_every_calendar_day_is_covered(source):
    """The panel reads today's MM-DD; a gap is a blank panel on that date."""
    missing = sorted(gch._valid_day_keys() - set(source))
    assert not missing, f"days with no history entry: {missing}"


def test_output_matches_the_const_already_shipped(source):
    """The generator must reproduce site_data.js byte for byte.

    This is the proof the extraction was lossless. If it ever fails, either the
    source drifted from the deployed content or the serializer changed shape —
    both are real, and both would otherwise show up as a 146KB reflow in a diff
    nobody reads.
    """
    site_data = os.path.join(PROJECT_ROOT, "docs", "data", "site_data.js")
    with open(site_data) as f:
        text = f.read()

    marker = "const CHESS_HISTORY = "
    start = text.find(marker)
    assert start != -1, "CHESS_HISTORY is missing from site_data.js"
    i = start + len(marker)
    depth = 0
    end = None
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    assert end, "could not find the end of the CHESS_HISTORY object"

    assert gch.serialize(source) == text[i:end], (
        "generated CHESS_HISTORY differs from what is deployed in site_data.js")


def test_a_bad_day_key_is_rejected():
    with pytest.raises(gch.HistoryError, match="MM-DD"):
        gch.validate({"13-01": [{"year": 1990, "event": "x", "category": "match"}]})


def test_an_unknown_category_is_rejected():
    with pytest.raises(gch.HistoryError, match="category"):
        gch.validate({"01-01": [{"year": 1990, "event": "x", "category": "gossip"}]})


def test_an_implausible_year_is_rejected():
    with pytest.raises(gch.HistoryError, match="outside"):
        gch.validate({"01-01": [{"year": 12, "event": "x", "category": "match"}]})


def test_an_empty_day_is_rejected():
    """An empty list renders as a present-but-blank panel, which reads as a bug."""
    with pytest.raises(gch.HistoryError, match="non-empty"):
        gch.validate({"01-01": []})


def test_a_missing_field_is_rejected():
    with pytest.raises(gch.HistoryError, match="missing"):
        gch.validate({"01-01": [{"year": 1990, "event": "x"}]})


def test_the_pipeline_wires_the_generator_in():
    """O5 was a dead splice. Assert the step exists and the guard has a producer."""
    import auto_update
    assert hasattr(auto_update, "step_chess_history"), \
        "no pipeline step renders chess_history.json; the splice is dead again"
    src = open(os.path.join(PROJECT_ROOT, "auto_update.py")).read()
    assert "step_chess_history()" in src, \
        "step_chess_history is defined but never called"
