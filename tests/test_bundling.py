"""The page loads generated bundles; these keep them honest.

A bundle is the split sources over again, in a pinned order, minified. It is
committed, so a source edit that skips the rebuild would ship the old code
behind a freshly stamped page: the first test rebuilds from the sources and
compares. The rest pin the registry shape: every page script and stylesheet
is bundled exactly once, the outputs and the vendored chart library are
stamped, and the vendored files are the published builds byte for byte.
"""
import base64
import glob
import hashlib
import os
import shutil
import subprocess

import pytest

from pipeline import bundling
from pipeline.stamping import STAMPED_SCRIPTS

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _read(name):
    with open(os.path.join(DOCS, name), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("output", sorted(bundling.BUNDLES))
def test_the_committed_bundle_matches_its_sources(output):
    assert _read(output) == bundling.bundle_text(DOCS, output), (
        f"docs/{output} is stale: run `python3 -m pipeline.bundling` and commit the result")


def test_every_page_script_is_bundled_once():
    on_disk = {os.path.basename(p) for p in glob.glob(os.path.join(DOCS, "*.js"))}
    outputs = {n for n in bundling.BUNDLES if n.endswith(".js")}
    listed = set(bundling.SCRIPT_SOURCES) | set(bundling.UNBUNDLED_SCRIPTS) | outputs
    assert on_disk == listed, (
        f"scripts on disk the bundle order does not list: {sorted(on_disk - listed)}; "
        f"listed but missing on disk: {sorted(listed - on_disk)}")
    assert len(bundling.SCRIPT_SOURCES) == len(set(bundling.SCRIPT_SOURCES)), "a script is listed twice"


def test_every_stylesheet_is_bundled_once():
    on_disk = {"styles/" + os.path.basename(p) for p in glob.glob(os.path.join(DOCS, "styles", "*.css"))}
    outputs = {n for n in bundling.BUNDLES if n.endswith(".css")}
    listed = set(bundling.STYLE_SOURCES) | outputs
    assert on_disk == listed, (
        f"stylesheets on disk the cascade order does not list: {sorted(on_disk - listed)}; "
        f"listed but missing on disk: {sorted(listed - on_disk)}")
    assert len(bundling.STYLE_SOURCES) == len(set(bundling.STYLE_SOURCES)), "a stylesheet is listed twice"


def test_the_bundles_and_the_vendored_library_are_stamped():
    for name in list(bundling.BUNDLES) + list(bundling.VENDOR_SRI):
        assert name in STAMPED_SCRIPTS, f"{name} is served but not in STAMPED_SCRIPTS"


def test_the_vendored_library_is_the_published_build():
    for name, pinned in bundling.VENDOR_SRI.items():
        with open(os.path.join(DOCS, name), "rb") as f:
            digest = "sha384-" + base64.b64encode(hashlib.sha384(f.read()).digest()).decode()
        assert digest == pinned, f"docs/{name} is not the build its pinned hash names"


def test_the_bundle_keeps_the_load_order():
    """The reasons are in pipeline/bundling.py next to SCRIPT_SOURCES."""
    s = bundling.SCRIPT_SOURCES
    assert s[-1] == "actions.js" and s[-2] == "app.js"
    assert s.index("util_core.js") < s.index("foundation.js") < s.index("theme.js")
    assert s.index("audit.js") < s.index("app.js")
    assert s.index("tab_ask.js") < s.index("app.js")
    assert s.index("motion.js") < s.index("gestures.js")
    assert s.index("sheet.js") < s.index("shell.js") < s.index("app.js")
    c = bundling.STYLE_SOURCES
    assert c[0] == "styles/fonts.css" and c[1] == "styles/tokens.css" and c[-1] == "styles/theme.css"


def test_the_page_loads_the_bundles_not_the_sources():
    html = _read("index.html")
    for name in bundling.SCRIPT_SOURCES + bundling.STYLE_SOURCES:
        assert f'"{name}?v=' not in html, f"index.html still loads the source {name}"
    for name in list(bundling.BUNDLES) + list(bundling.VENDOR_SRI):
        assert f'"{name}?v=' in html, f"index.html does not load {name}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_the_script_bundle_parses():
    proc = subprocess.run(["node", "--check", os.path.join(DOCS, "site.js")],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_every_template_literal_ships_byte_for_byte():
    """rjsmin strips spaces in nested templates; the bundle must not."""
    from pipeline import js_templates
    bundle = _read("site.js")
    for name in bundling.SCRIPT_SOURCES:
        src = _read(name)
        for start, end in js_templates.template_spans(src):
            literal = src[start:end]
            assert literal in bundle, f"{name}: a template literal changed in the bundle: {literal[:80]!r}"
