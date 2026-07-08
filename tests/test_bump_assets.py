"""Guards for the single-sourced asset versions (G5).

test_versions_consistent runs in the normal gate, so a hand-edit that bumps
styles.css?v / app.js?v in one file but not the other now fails CI instead of
shipping a stale asset.
"""
import os
import re
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import importlib  # noqa: E402

bump_assets = importlib.import_module("scripts.bump_assets")


def test_versions_consistent():
    """index.html and sw.js must agree on every asset version."""
    assert bump_assets.check() == 0


def test_bump_syncs_both_files(tmp_path, monkeypatch):
    idx = tmp_path / "index.html"
    sw = tmp_path / "sw.js"
    shutil.copy(bump_assets.INDEX, idx)
    shutil.copy(bump_assets.SW, sw)
    monkeypatch.setattr(bump_assets, "INDEX", str(idx))
    monkeypatch.setattr(bump_assets, "SW", str(sw))

    before = set(re.findall(r"app\.js\?v=(\d+)", idx.read_text()))
    bump_assets.bump(["js"])
    idx_v = set(re.findall(r"app\.js\?v=(\d+)", idx.read_text()))
    sw_v = set(re.findall(r"app\.js\?v=(\d+)", sw.read_text()))

    assert idx_v == sw_v                 # both files moved together
    assert idx_v != before               # and actually incremented
    assert bump_assets.check() == 0
