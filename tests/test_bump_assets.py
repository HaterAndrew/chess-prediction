"""Guards for the single-sourced asset versions (G5).

test_versions_consistent runs in the normal gate, so a hand-edit that bumps
styles.css?v / app.js?v in one file but not the other now fails CI instead of
shipping a stale asset.
"""
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import importlib  # noqa: E402

bump_assets = importlib.import_module("scripts.bump_assets")


def test_versions_consistent():
    """index.html and sw.js must agree on every asset version."""
    assert bump_assets.check() == 0


def _numeric_env(tmp_path, monkeypatch):
    """A site whose asset versions are still plain counters."""
    idx = tmp_path / "index.html"
    sw = tmp_path / "sw.js"
    idx.write_text('<link href="styles.css?v=3">\n<script src="app.js?v=7">\n')
    sw.write_text("const CACHE_NAME = 'cca-predictor-v9';\n"
                  "'styles.css?v=3', 'app.js?v=7'\n")
    monkeypatch.setattr(bump_assets, "INDEX", str(idx))
    monkeypatch.setattr(bump_assets, "SW", str(sw))
    return idx, sw


def test_bump_syncs_both_files(tmp_path, monkeypatch):
    """The counter path still works for any asset not content-hashed."""
    idx, sw = _numeric_env(tmp_path, monkeypatch)

    before = set(re.findall(r"app\.js\?v=(\d+)", idx.read_text()))
    assert bump_assets.bump(["js"]) == 0
    idx_v = set(re.findall(r"app\.js\?v=(\d+)", idx.read_text()))
    sw_v = set(re.findall(r"app\.js\?v=(\d+)", sw.read_text()))

    assert idx_v == sw_v                 # both files moved together
    assert idx_v != before               # and actually incremented
    assert bump_assets.check() == 0


def test_bump_refuses_to_touch_a_content_hashed_asset(tmp_path, monkeypatch, capsys):
    """Incrementing a hash is meaningless and the next pipeline run undoes it.

    app.js?v= is now derived from the file's content
    (auto_update._stamp_script_versions), so bump must say so rather than write
    something that looks like it worked.
    """
    idx = tmp_path / "index.html"
    sw = tmp_path / "sw.js"
    idx.write_text('<script src="app.js?v=8dda437d9b">\n')
    sw.write_text("const CACHE_NAME = 'cca-predictor-v9';\n'app.js?v=8dda437d9b'\n")
    monkeypatch.setattr(bump_assets, "INDEX", str(idx))
    monkeypatch.setattr(bump_assets, "SW", str(sw))

    assert bump_assets.bump(["js"]) == 1
    assert "REFUSING" in capsys.readouterr().out
    assert "8dda437d9b" in idx.read_text(), "the file must be left alone"


def test_check_compares_whole_hashes_not_leading_digits(tmp_path, monkeypatch):
    """The old `(\\d+)` pattern matched a hash's leading digits.

    `app.js?v=8dda437d9b` read as version 8, so it compared a fragment against
    whatever sw.js held and reported drift between two files that agreed — and
    would equally have missed drift between two hashes sharing a first digit.
    """
    idx = tmp_path / "index.html"
    sw = tmp_path / "sw.js"
    idx.write_text('<script src="app.js?v=8dda437d9b">\n')
    sw.write_text("'app.js?v=8dda437d9b'\n")
    monkeypatch.setattr(bump_assets, "INDEX", str(idx))
    monkeypatch.setattr(bump_assets, "SW", str(sw))
    assert bump_assets.check() == 0

    # Same leading digit, different hash: must still be caught as drift.
    sw.write_text("'app.js?v=8ffffffff0'\n")
    assert bump_assets.check() == 1
