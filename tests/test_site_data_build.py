"""Regression tests for step_update_html after the L15 data externalization.

The daily build used to splice the data consts into docs/index.html; it now
targets docs/data/site_data.js. These tests confirm it rewrites TOURNAMENT_DATA
in that file, leaves the sibling consts intact, and fails loudly on a missing
target instead of silently writing nothing.
"""
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import auto_update  # noqa: E402

# A minimal site_data.js carrying every const the splicer touches.
STUB_SITE_DATA = (
    'const TOURNAMENT_DATA = {"generated": "2020-01-01", "tournaments": []};\n'
    'const PUZZLE_DATA = {"keep": 1};\n'
    'const CHESS_HISTORY = {"keep": 2};\n'
    'const PERFORMANCE_DATA = {"keep": 3};\n'
)


@pytest.fixture
def build_env(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    docs_dir = tmp_path / "docs"
    data_dir = docs_dir / "data"
    data_dir.mkdir(parents=True)
    site_data = data_dir / "site_data.js"
    site_data.write_text(STUB_SITE_DATA)
    website_json = out / "website_data.json"

    monkeypatch.setattr(auto_update, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(auto_update, "SITE_DATA_JS", str(site_data))
    monkeypatch.setattr(auto_update, "WEBSITE_JSON", str(website_json))
    # SITE_DIR is monkeypatched to the tmp docs/ so a regression that re-adds a
    # docs/website_data.json copy is caught here instead of clobbering the real
    # tracked file (the isolation bug that motivated the G9 removal).
    monkeypatch.setattr(auto_update, "SITE_DIR", str(docs_dir))
    return {"site_data": site_data, "website_json": website_json, "docs_dir": docs_dir}


def test_splices_tournament_data_into_site_data(build_env):
    payload = {"generated": "2026-07-07", "tournaments": [{"family": "X", "year": 2026}]}
    build_env["website_json"].write_text(json.dumps(payload))

    auto_update.step_update_html()

    written = build_env["site_data"].read_text()
    assert '"generated": "2026-07-07"' in written           # new data landed
    assert '"generated": "2020-01-01"' not in written        # old data gone
    # sibling consts (no fixture source in this tmp OUTPUT_DIR) stay untouched
    assert 'const PUZZLE_DATA = {"keep": 1};' in written
    assert 'const CHESS_HISTORY = {"keep": 2};' in written
    assert 'const PERFORMANCE_DATA = {"keep": 3};' in written


def test_missing_target_raises(build_env):
    build_env["website_json"].write_text('{"generated": "2026-07-07", "tournaments": []}')
    build_env["site_data"].unlink()
    with pytest.raises(RuntimeError, match="Missing"):
        auto_update.step_update_html()


def test_no_docs_website_data_double_ship(build_env):
    """G9: step_update_html must NOT write a docs/website_data.json copy. The app
    reads docs/data/site_data.js since the L15 externalization; the old copy was
    a 1.4MB daily-churn double-ship (and it clobbered the real tracked file from
    tests because SITE_DIR wasn't isolated)."""
    payload = {"generated": "2026-07-07", "tournaments": [{"family": "X", "year": 2026}]}
    build_env["website_json"].write_text(json.dumps(payload))

    auto_update.step_update_html()

    assert not (build_env["docs_dir"] / "website_data.json").exists()
