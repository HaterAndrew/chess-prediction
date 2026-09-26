"""Tests for docs/sw.js: what the browser is allowed to serve from cache.

The service worker decides whether a returning visitor sees a corrected build
or yesterday's numbers, and whether a cold visit's bandwidth goes to the page
or to a precache. It runs the real file under node with a stubbed
ServiceWorkerGlobalScope and a Map-backed Cache (tests/js/sw_driver.js) and
asserts on what each kind of request fetched and what the cache held after.

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


def test_the_worker_registers_the_lifecycle_it_claims_to(res):
    assert res["registered_listeners"] == ["activate", "fetch", "install"]


def test_the_document_is_never_served_from_a_stale_http_cache(res):
    """index.html carries every asset's ?v=, so it must be fetched no-store.

    Pages serves index.html with `Cache-Control: max-age=600`. Inside that
    window a returning visitor gets a ten-minute-old document, and that
    document points at the PREVIOUS data URL, so the content-hash
    cache-busting silently does nothing for exactly the visitor it exists to
    protect. Every other version pointer depends on the document being fresh.
    """
    nav = res["navigation"]
    assert nav["intercepted"], "the SW must handle navigations"
    assert nav["init"] == {"cache": "no-store"}, (
        "navigation was fetched without cache:'no-store', so the HTTP cache "
        f"can serve a stale document: init={nav['init']}")


def test_install_precaches_only_the_app_shell(res):
    """The data file (2.4 MB) and the CDN scripts are not precached: they are
    cached on first use by the fetch handler. Precaching them during the first
    visit competed with the page's own requests for bandwidth."""
    urls = [c["url"] for c in res["install"]["fetched"]]
    assert "./" in urls and "index.html" in urls and "manifest.json" in urls
    assert any(u.startswith("styles/") for u in urls)
    assert any(u.startswith("fonts/") for u in urls)
    assert not any("site_data" in u or u.startswith("data/") for u in urls), urls
    assert not any(u.startswith("http") for u in urls), urls
    assert "audit_warnings.json" not in urls


def test_install_refetches_only_the_document(res):
    """The document is fetched no-cache so the precached copy is the current
    deploy; every other entry was just fetched by the page and may come from
    the HTTP cache for free."""
    inits = {c["url"]: c["init"] for c in res["install"]["fetched"]}
    assert inits["./"] == {"cache": "no-cache"}
    assert inits["index.html"] == {"cache": "no-cache"}
    others = {u: i for u, i in inits.items() if u not in ("./", "index.html")}
    assert others and all(i is None for i in others.values()), others


def test_hashed_assets_are_served_cache_first(res):
    """A `?v=` URL changes when its content does, so a miss goes to the network
    once (with the default cache mode) and every later request is a cache hit
    that never touches the network."""
    miss, hit = res["hashed_miss"], res["hashed_hit"]
    assert miss["intercepted"] and miss["fetched"] and miss["init"] is None
    assert "app.js?v=8dda437d9b" in miss["cached_after"]
    assert hit["intercepted"] and not hit["fetched"], hit
    assert hit["body"] == miss["body"]


def test_the_data_file_is_cached_like_any_other_hashed_asset(res):
    """v3 P5 fetched site_data.js no-store on every visit because its path was
    stable. Its URL is derived from a hash of its content now, so a stale
    entry is impossible and the nightly 2.4 MB re-download was pure waste."""
    assert res["data_miss"]["fetched"] and res["data_miss"]["init"] is None
    assert not res["data_hit"]["fetched"]


def test_fonts_are_served_cache_first(res):
    assert res["font_miss"]["fetched"]
    assert not res["font_hit"]["fetched"]


def test_a_new_hash_evicts_the_old_entry_for_the_same_path(res):
    """Without pruning, every nightly restamp left the previous data file in
    the cache: 2.4 MB per night until the CACHE_NAME bumped."""
    after = res["restamp"]["cached_after"]
    assert "app.js?v=8dda437d9b" in after and "app.js?v=0000000000" not in after, after
    assert "data/site_data.js?v=abc1234567" in after
    assert "data/site_data.js?v=1111111111" not in after, after


def test_unhashed_files_stay_network_first(res):
    """audit_warnings.json changes nightly under a stable path, so every online
    request goes to the network; the copy kept in cache is the offline fallback."""
    first, second = res["unhashed_first"], res["unhashed_second"]
    assert first["fetched"] and second["fetched"]
    assert first["init"] is None
    assert "audit_warnings.json" in second["cached_after"]


def test_offline_falls_back_to_the_cache(res):
    assert res["offline_navigation"]["status"] == 200
    assert res["offline_navigation"]["body"] == "cached:./"
    assert res["offline_unhashed"]["body"] == "cached:audit_warnings.json"
    assert res["offline_hashed_hit"]["body"] == "cached:app.js?v=8dda437d9b"


def test_offline_with_nothing_cached_is_a_visible_failure(res):
    """A navigation with no cached document gets the offline page (503), and a
    missing asset gets a 504 rather than a hung request."""
    nav = res["offline_navigation_nothing_cached"]
    assert nav["status"] == 503 and "Offline" in nav["body"]
    assert res["offline_hashed_miss"]["status"] == 504


def test_pinned_cdn_scripts_are_served_cache_first(res):
    """Chart.js is SRI-locked and version-pinned; a repeat or offline load must
    not go to the CDN (the bypass used to produce "Chart is not defined")."""
    assert res["cdn_miss"]["intercepted"] and res["cdn_miss"]["fetched"]
    assert not res["cdn_hit"]["fetched"]


def test_cross_origin_requests_bypass_the_worker(res):
    assert res["cross_origin"]["intercepted"] is False


def test_same_origin_api_routes_bypass_the_worker(res):
    """One Worker serves the page and /ask, /health, /cca-tourlist and
    /cca-entrylist on the same origin. Those responses are dynamic (rate
    limits, budgets, live scrapes) and must never be cached or served from
    cache, so the worker leaves them to the network entirely."""
    assert res["api_health"]["intercepted"] is False
    assert res["api_entrylist"]["intercepted"] is False


def test_non_get_requests_bypass_the_worker(res):
    assert res["post"]["intercepted"] is False
