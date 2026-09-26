"""Regression tests for step_update_html after the data-file split.

The daily build splices the data consts into three generated files under
docs/data/: tournaments.js (what the page needs at first paint),
performance_data.js and chess_history.js (fetched by their tabs on demand).
These tests confirm it rewrites TOURNAMENT_DATA, compacts every payload it
writes, derives PERFORMANCE_SUMMARY without the per-tournament records, leaves
consts with no source untouched, stamps every data file's ?v= into the page,
keeps every write inside a redirected SITE_DIR, and fails loudly on a missing
target instead of silently writing nothing.
"""
import hashlib
import json
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import auto_update  # noqa: E402
import pipeline.config  # noqa: E402

DATA_FILES = ("tournaments.js", "performance_data.js", "chess_history.js")

# Minimal generated files carrying every const the splicer touches.
STUB_TOURNAMENTS = (
    'const TOURNAMENT_DATA = {"generated": "2020-01-01", "tournaments": []};\n'
    'const PERFORMANCE_SUMMARY = {"keep": 1};\n'
    'const PUZZLE_DATA = {"keep": 2};\n'
)
STUB_PERFORMANCE = 'const PERFORMANCE_DATA = {"keep": 3};\n'
STUB_HISTORY = 'const CHESS_HISTORY = {"keep": 4};\n'
# The page's data tag: the on-load file plus the two lazy ones as data-*.
STUB_INDEX = (
    '<script defer id="dataScript" src="data/tournaments.js?v=0000000000"'
    ' data-performance="data/performance_data.js?v=0000000000"'
    ' data-history="data/chess_history.js?v=0000000000"></script>\n'
)
PAYLOAD = {"generated": "2026-07-07", "tournaments": [{"family": "X", "year": 2026}]}
COMPACT_PAYLOAD = '{"generated":"2026-07-07","tournaments":[{"family":"X","year":2026}]}'


@pytest.fixture
def build_env(tmp_path, monkeypatch):
    out = tmp_path / "output"
    out.mkdir()
    docs_dir = tmp_path / "docs"
    data_dir = docs_dir / "data"
    data_dir.mkdir(parents=True)
    files = {name: data_dir / name for name in DATA_FILES}
    files["tournaments.js"].write_text(STUB_TOURNAMENTS)
    files["performance_data.js"].write_text(STUB_PERFORMANCE)
    files["chess_history.js"].write_text(STUB_HISTORY)
    # An index.html inside the isolated docs/, so the cache-buster stamp has
    # somewhere to land here instead of reaching for the repo's real one.
    index_html = docs_dir / "index.html"
    index_html.write_text(STUB_INDEX)
    website_json = out / "website_data.json"
    website_json.write_text(json.dumps(PAYLOAD, indent=2))

    # Patch the DEFINING module (pipeline.config), not the auto_update shim:
    # the splicer and stampers read config.X at call time, and a patch on the
    # shim's re-exported copy never reaches them — running this suite against
    # the shim seam stomped the real docs/ files once already.
    monkeypatch.setattr(pipeline.config, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(pipeline.config, "WEBSITE_JSON", str(website_json))
    # SITE_DIR is monkeypatched to the tmp docs/ so a regression that writes
    # into the repo's docs/ is caught here instead of clobbering tracked files.
    monkeypatch.setattr(pipeline.config, "SITE_DIR", str(docs_dir))
    return {"out": out, "files": files, "website_json": website_json,
            "docs_dir": docs_dir, "index_html": index_html}


def test_splices_tournament_data_compact(build_env):
    auto_update.step_update_html()

    written = build_env["files"]["tournaments.js"].read_text()
    assert f"const TOURNAMENT_DATA = {COMPACT_PAYLOAD};" in written  # compact, new data landed
    assert '"generated": "2020-01-01"' not in written                # old data gone
    # sibling consts (no fixture source in this tmp OUTPUT_DIR) stay untouched
    assert 'const PERFORMANCE_SUMMARY = {"keep": 1};' in written
    assert 'const PUZZLE_DATA = {"keep": 2};' in written
    assert build_env["files"]["performance_data.js"].read_text() == STUB_PERFORMANCE
    assert build_env["files"]["chess_history.js"].read_text() == STUB_HISTORY


def test_optional_consts_follow_their_sources(build_env):
    """Each optional const is spliced only when its source exists, compacted
    except CHESS_HISTORY (whose generator's bytes are pinned elsewhere), and
    PERFORMANCE_SUMMARY is the performance payload minus every per-tournament
    list, at any depth."""
    out = build_env["out"]
    (out / "daily_puzzles.json").write_text(json.dumps({"puzzles": [{"id": 1}]}, indent=2))
    perf = {
        "generated": "2026-07-07", "aggregate": [{"T": 14, "mae_pct": 5.0}],
        "tournaments": [{"family": "X"}],
        "years": {"2026": {"n_tournaments": 1, "aggregate": [], "tournaments": [{"family": "X"}]}},
        "cumulative": {"n_tournaments": 1, "tournaments": [{"family": "X"}]},
    }
    (out / "performance_data.json").write_text(json.dumps(perf, indent=2))
    history = '{\n  "01-01": [\n    {"year": 1990, "event": "x", "category": "match"}\n  ]\n}'
    (out / "chess_history.json").write_text(history + "\n")

    auto_update.step_update_html()

    tournaments = build_env["files"]["tournaments.js"].read_text()
    assert 'const PUZZLE_DATA = {"puzzles":[{"id":1}]};' in tournaments
    summary = re.search(r"const PERFORMANCE_SUMMARY = (.*?);\n", tournaments).group(1)
    assert "\n" not in summary and ": " not in summary, "summary was not compacted"
    summary_obj = json.loads(summary)

    def keys_at_any_depth(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys_at_any_depth(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys_at_any_depth(v)

    assert "tournaments" not in set(keys_at_any_depth(summary_obj)), \
        "per-tournament records leaked into the summary"
    assert summary_obj["aggregate"] == perf["aggregate"]
    assert summary_obj["years"]["2026"]["n_tournaments"] == 1
    assert summary_obj["cumulative"]["n_tournaments"] == 1

    performance = build_env["files"]["performance_data.js"].read_text()
    assert performance == f"const PERFORMANCE_DATA = {json.dumps(perf, separators=(',', ':'))};\n"

    assert build_env["files"]["chess_history.js"].read_text() == f"const CHESS_HISTORY = {history};\n"


@pytest.mark.parametrize("missing", DATA_FILES)
def test_missing_target_raises(build_env, missing):
    build_env["files"][missing].unlink()
    with pytest.raises(RuntimeError, match="Missing"):
        auto_update.step_update_html()


def test_ask_endpoint_is_written_compact_inside_the_isolated_docs_dir(build_env):
    """The Ask Worker's JSON endpoint must land in the tmp docs/, not the repo's.

    step_update_html writes docs/data/website_data.json for the Worker (v3 S1).
    That write once used a module constant computed at import from the real
    SITE_DIR, so monkeypatching SITE_DIR did not redirect it, and running this
    very suite overwrote the published endpoint with a two-line stub. Assert
    the write lands in the fixture's docs/ and that the real one is never
    touched.
    """
    real_endpoint = os.path.join(PROJECT_ROOT, "docs", "data", "website_data.json")
    before = (os.path.getmtime(real_endpoint)
              if os.path.exists(real_endpoint) else None)

    auto_update.step_update_html()

    isolated = build_env["docs_dir"] / "data" / "website_data.json"
    assert isolated.exists(), "endpoint was not written inside the isolated docs/"
    assert isolated.read_text() == COMPACT_PAYLOAD

    after = (os.path.getmtime(real_endpoint)
             if os.path.exists(real_endpoint) else None)
    assert before == after, (
        "step_update_html wrote the repo's published docs/data/website_data.json "
        "during a test")


def test_every_data_file_is_stamped_into_the_page(build_env):
    """Each data file's ?v= in the page is that file's own content hash.

    A hand-maintained version only changes when someone edits the code, but
    these files' CONTENT changes every night; a returning visitor (and any
    installed PWA) would otherwise keep serving yesterday's numbers from cache
    long after a corrected build shipped. The stamp must also stay inside the
    isolated docs/: the stampers once wrote through a module constant frozen
    at import, and every run of this suite rewrote the published index.html
    with the fixture's hash, which then shipped in the nightly commit.
    """
    real_index = os.path.join(PROJECT_ROOT, "docs", "index.html")
    with open(real_index, "rb") as fh:
        before = fh.read()

    auto_update.step_update_html()

    stamped = build_env["index_html"].read_text()
    assert "0000000000" not in stamped, "the isolated index.html was never stamped"
    for name in DATA_FILES:
        digest = hashlib.sha256(build_env["files"][name].read_bytes()).hexdigest()[:10]
        assert f"data/{name}?v={digest}" in stamped, f"{name} stamp is not its content hash"

    with open(real_index, "rb") as fh:
        after = fh.read()
    assert before == after, \
        "step_update_html rewrote the repo's published docs/index.html during a test"


def test_no_docs_website_data_double_ship(build_env):
    """G9: step_update_html must NOT write a docs/website_data.json copy. The app
    reads docs/data/*.js since the L15 externalization; the old copy was a
    1.4MB daily-churn double-ship (and it clobbered the real tracked file from
    tests because SITE_DIR wasn't isolated)."""
    auto_update.step_update_html()

    assert not (build_env["docs_dir"] / "website_data.json").exists()
