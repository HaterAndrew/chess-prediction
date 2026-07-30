"""Cache-buster stamping + freshness flags (auto_update, verbatim;
targets derive from config.SITE_DIR at call time).
"""
import hashlib
import json
import os
import re

from pipeline import config


def _stamp_targets():
    """The two files carrying `?v=` cache-busters, resolved at call time.

    Both are derived from config.SITE_DIR on every call rather than read from a
    constant frozen at import. index.html used to come from INDEX_HTML while
    sw.js was built from config.SITE_DIR, so a caller that redirected config.SITE_DIR — every
    test in tests/test_site_data_build.py — redirected one and not the other,
    and the stamp for index.html landed on the repo's published copy. Deriving
    both from the same place makes the pair impossible to split.
    """
    return (os.path.join(config.SITE_DIR, "index.html"),
            os.path.join(config.SITE_DIR, "sw.js"))


def _stamp_site_data_version(json_data):
    """Point index.html + sw.js at a data-derived site_data.js query string.

    v3 P5. A hand-maintained `?v=40` only changes when someone edits the code,
    but this file's CONTENT changes every night. A returning visitor — and any
    installed PWA — could therefore keep serving yesterday's numbers from cache
    long after a corrected build shipped, which is exactly the population that
    saw the bad Bradley Open figures first. Deriving the query string from a
    hash of the data means every rebuild is a new URL and the cache cannot
    outlive its contents.
    """
    digest = hashlib.sha256(json_data.encode('utf-8')).hexdigest()[:10]
    pattern = re.compile(r'(site_data\.js\?v=)([A-Za-z0-9]+)')
    for path in _stamp_targets():
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        new_text, n = pattern.subn(rf'\g<1>{digest}', text)
        if n and new_text != text:
            with open(path, 'w') as f:
                f.write(new_text)
            print(f"  Stamped site_data.js?v={digest} in {os.path.basename(path)}")
    _stamp_script_versions()
    return digest


# Local assets referenced with a `?v=` cache-buster. styles.css and app.js also
# appear in sw.js, and the G5 invariant is that the two files never disagree —
# see scripts/bump_assets.py.
STAMPED_SCRIPTS = ("app.js", "actions.js", "daily_series.js", "boot.js",
                   "audit.js", "styles.css", "util_core.js", "foundation.js",
                   "cmdk.js", "tab_email.js")


def _stamp_script_versions():
    """Derive each local script's `?v=` from its own content hash.

    P5 fixed this for the data file and left the scripts on hand-numbers, which
    fails the same way in the other direction: the data file's content changes
    nightly and its version did not, while a script's version only changes if
    someone remembers to bump it. Two app.js fixes shipped in this session
    behind `?v=40`, so every returning visitor and every installed PWA would
    have kept running the old file and never seen either one.

    Hashing the file means the URL changes exactly when the content does —
    no bump to forget, and no cache-buster churn on nights when the code is
    untouched.

    Both index.html AND sw.js get rewritten. styles.css and app.js are
    referenced in each, and G5 (scripts/bump_assets.py --check) fails the build
    if they disagree. Stamping only index.html is a real drift, not a cosmetic
    one: the service worker would keep precaching the old URL.
    """
    targets = _stamp_targets()
    digests = {}
    for name in STAMPED_SCRIPTS:
        asset_path = os.path.join(config.SITE_DIR, name)
        if not os.path.exists(asset_path):
            continue
        with open(asset_path, 'rb') as f:
            digests[name] = hashlib.sha256(f.read()).hexdigest()[:10]

    announced = set()
    for path in targets:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        original = text
        for name, digest in digests.items():
            pattern = re.compile(rf'({re.escape(name)}\?v=)([A-Za-z0-9]+)')
            before = text
            text, n = pattern.subn(rf'\g<1>{digest}', text)
            # Only announce a real change; a nightly run that touched no code
            # should be quiet here rather than printing a no-op line per asset.
            if n and text != before and name not in announced:
                print(f"  Stamped {name}?v={digest}")
                announced.add(name)
        if text != original:
            with open(path, 'w') as f:
                f.write(text)


def _atomic_write_json(path, data):
    """Write JSON via a temp file + os.replace so a crash mid-write can never
    leave a truncated website_data.json on disk. The degraded-state stamp runs
    from an exception handler, often while the machine is already unhappy, and a
    half-written data file would take the site down entirely rather than just
    showing a stale banner."""
    tmp = f"{path}.tmp"
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _stamp_stale_flag(is_stale):
    """Add/update last_updated and is_stale fields in website_data.json.

    Preserves existing predictions when the scrape fails so stale data
    can still be served with a warning banner.
    """
    if not os.path.exists(config.WEBSITE_JSON):
        print(f"  WARNING: {config.WEBSITE_JSON} not found — cannot stamp stale flag")
        return

    with open(config.WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    data['last_updated'] = config.RUN_TS
    data['is_stale'] = is_stale
    # A successful run clears any degraded marker left by a previous failure.
    if not is_stale:
        data.pop('pipeline_degraded', None)
        data.pop('degraded_reason', None)
        data.pop('degraded_at', None)

    _atomic_write_json(config.WEBSITE_JSON, data)

    flag = "STALE" if is_stale else "FRESH"
    print(f"  Stamped website_data.json — is_stale={is_stale} ({flag}), last_updated={config.RUN_TS}")
