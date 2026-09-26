"""Tests for the theme contract in docs/boot.js and docs/theme.js.

Light is the default for everyone; dark is opt-in through the header toggle
and persists in localStorage; the OS colour-scheme preference is never
consulted. boot.js applies the stored choice before first paint, theme.js
owns the toggle. Runs the real files under node with a stub DOM
(tests/js/theme_driver.js). Skipped when node is unavailable.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "theme_driver.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                          cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_first_visit_is_light_even_when_the_os_prefers_dark(res):
    assert res["no_store_os_light"] == "light"
    assert res["no_store_os_dark"] == "light", (
        "boot.js consulted prefers-color-scheme; the owner's rule is light "
        "for everyone until the visitor chooses dark")


def test_a_stored_dark_choice_is_honoured(res):
    assert res["stored_dark"] == "dark"


def test_a_stored_light_choice_beats_the_os(res):
    assert res["stored_light_os_dark"] == "light"


def test_unknown_or_unreadable_storage_falls_back_to_light(res):
    assert res["stored_garbage"] == "light"
    assert res["storage_throws"] == "light", (
        "a throwing localStorage (private mode, blocked storage) must not "
        "break the page or default to dark")


def test_the_toggle_flips_persists_and_reflects_its_state(res):
    t = res["toggle"]
    assert t["before"] == {"theme": "light", "pressed": "false", "metaColor": "#F7F4EC"}
    first = t["afterFirst"]
    assert first["theme"] == "dark"
    assert first["stored"] == "dark", "the choice must persist across visits"
    assert first["pressed"] == "true"
    assert first["label"] == "Switch to the Light Theme"
    assert first["metaColor"] == "#0a0907", "meta theme-color must follow --void"
    assert first["switchingClassAdded"], "a switch cross-fades (theme-switching class)"
    assert t["afterSecond"] == {"theme": "light", "stored": "light"}


def test_reduced_motion_switches_without_the_cross_fade(res):
    assert res["toggle_reduced_motion"]["switchingClassAdded"] is False
