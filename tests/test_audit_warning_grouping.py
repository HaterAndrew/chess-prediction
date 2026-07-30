"""v5 Cat V (audit/AUDIT_2026-07-30.md): audit-warnings payload dedup.

The payload carried every duplicate verbatim — 200 of 216 entries were one
recalibration sentence repeated per T bucket, burying the single warning that
mattered, precaching 50KB of duplicates into the service worker, and printing
216 rows into the CI step summary nightly.

Contract: group_warnings folds identical (step, text) pairs into one entry
with a count, first-seen order; `count` means DISTINCT warnings so the site's
count===0 green pill and the step summary's zero-branch hold (0 distinct is
equivalent to 0 total); total_occurrences preserves raw magnitude. The site
renderer escapes step and text before innerHTML insertion.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from auto_update import group_warnings  # noqa: E402


def _w(step, text):
    return {"step": step, "text": text}


def test_folds_duplicates_with_counts():
    payload = group_warnings([
        _w("Generate predictions", "T=90 recal in-sample"),
        _w("Refresh tournament summary", "export missing"),
        _w("Generate predictions", "T=90 recal in-sample"),
        _w("Generate predictions", "T=90 recal in-sample"),
    ])
    assert payload["count"] == 2
    assert payload["total_occurrences"] == 4
    assert payload["warnings"][0] == {
        "step": "Generate predictions", "text": "T=90 recal in-sample",
        "count": 3}
    assert payload["warnings"][1]["count"] == 1


def test_preserves_first_seen_order():
    payload = group_warnings([_w("b", "2"), _w("a", "1"), _w("b", "2")])
    assert [w["text"] for w in payload["warnings"]] == ["2", "1"]


def test_same_text_different_step_stays_distinct():
    payload = group_warnings([_w("step1", "same"), _w("step2", "same")])
    assert payload["count"] == 2


def test_empty_means_zero_everywhere():
    payload = group_warnings([])
    assert payload == {"count": 0, "total_occurrences": 0, "warnings": []}


def test_site_renderer_escapes_warning_fields():
    """Source-level pin (test_csp_inline_handlers pattern): the warnings
    renderer must wrap w.step and w.text in esc() before innerHTML insertion —
    the pre-v5 renderer concatenated w.text raw."""
    with open(os.path.join(PROJECT_ROOT, "docs", "app.js")) as fh:
        src = fh.read()
    assert "esc(w.text)" in src
    assert "esc(w.step.split('(')[0].trim())" in src