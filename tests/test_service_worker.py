"""Tests for docs/sw.js — what the browser is allowed to serve from cache.

The service worker decides whether a returning visitor sees a corrected build
or yesterday's numbers, and none of that logic had a test. It runs the real
file under node with a stubbed ServiceWorkerGlobalScope and asserts on the
`init` the fetch handler passes for each kind of request.

Skipped when node is unavailable, matching tests/test_daily_series_js.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "sw_driver.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                          cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_the_document_is_never_served_from_a_stale_http_cache(res):
    """index.html carries every asset's ?v=, so it must be fetched no-store.

    Pages serves index.html with `Cache-Control: max-age=600`. Inside that
    window a returning visitor gets a ten-minute-old document, and that
    document points at the PREVIOUS data URL — so the content-hash
    cache-busting silently does nothing for exactly the visitor it exists to
    protect. Every other version pointer depends on the document being fresh.
    """
    nav = res["navigation"]
    assert nav["intercepted"], "the SW must handle navigations"
    assert nav["init"] == {"cache": "no-store"}, (
        "navigation was fetched without cache:'no-store', so the HTTP cache "
        f"can serve a stale document: init={nav['init']}")


def test_the_data_file_is_fetched_no_store(res):
    """v3 P5: site_data.js changes nightly under a stable path."""
    assert res["site_data"]["init"] == {"cache": "no-store"}


def test_content_hashed_assets_may_come_from_the_http_cache(res):
    """A hashed URL changes when its content does, so bypassing the cache for
    these would be pure waste — a new URL is already a guaranteed miss."""
    assert res["hashed_script"]["init"] is None


def test_cross_origin_requests_bypass_the_worker(res):
    """The Ask Worker is a different origin and must not be intercepted."""
    assert res["cross_origin"]["intercepted"] is False


def test_non_get_requests_bypass_the_worker(res):
    assert res["post"]["intercepted"] is False


def test_the_worker_registers_the_lifecycle_it_claims_to(res):
    assert res["registered_listeners"] == ["activate", "fetch", "install"]
