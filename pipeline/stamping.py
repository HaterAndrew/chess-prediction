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


# Local assets referenced with a `?v=` cache-buster. Each also appears in
# sw.js's precache list, and the G5 invariant is that the two files never
# disagree — see scripts/bump_assets.py.
STAMPED_SCRIPTS = (
    "app.js",
    "actions.js",
    "daily_series.js",
    "boot.js",
    "audit.js",
    "util_core.js",
    "foundation.js",
    "theme.js",
    "icons.js",
    "sheet.js",
    "shell.js",
    "cmdk.js",
    "tab_email.js",
    "tab_performance.js",
    "tab_puzzles.js",
    "pickers.js",
    "panels_info.js",
    "hero_kpi.js",
    "chart_main.js",
    "chart_hist.js",
    "panels_grid.js",
    "panels_cal.js",
    "tab_about.js",
    "tab_compare.js",
    "tab_ask.js",
    "styles/fonts.css",
    "styles/tokens.css",
    "styles/01-base.css",
    "styles/shell.css",
    "styles/controls.css",
    "styles/overlays.css",
    "styles/03-cmdk.css",
    "styles/picker.css",
    "styles/05-delta-banner.css",
    "styles/06-mobile-predictions.css",
    "styles/07-hero.css",
    "styles/08-chart.css",
    "styles/09-timeline.css",
    "styles/10-comparison.css",
    "styles/11-tables.css",
    "styles/12-calendar.css",
    "styles/cards.css",
    "styles/14-puzzles.css",
    "styles/15-data-entry.css",
    "styles/16-email.css",
    "styles/17-compare.css",
    "styles/18-performance.css",
    "styles/19-motion.css",
    "styles/20-mobile.css",
    "styles/21-panels.css",
    "styles/22-panels-shared.css",
    "styles/23-print.css",
    "styles/24-ask-audit.css",
    "styles/theme.css",
)

# The generated data files, stamped the same way but listed apart: sw.js does
# not precache them (its fetch handler caches them on first use), and
# scripts/bump_assets.py --check demands a matching sw.js entry for every
# STAMPED_SCRIPTS name. Referenced from the page's data tag and its data-*
# attributes (see pipeline/site_html.py).
STAMPED_DATA = (
    "data/tournaments.js",
    "data/performance_data.js",
    "data/chess_history.js",
)


def _stamp_script_versions():
    """Derive each local script's and data file's `?v=` from its content hash.

    v3 P5 introduced the data-derived hash for the data file: its CONTENT
    changes every night, so a hand-maintained `?v=40` let a returning visitor
    (and any installed PWA) keep serving yesterday's numbers long after a
    corrected build shipped. Scripts failed the same way in the other
    direction: a script's version only changed if someone remembered to bump
    it, and two app.js fixes once shipped behind the same `?v=40`.

    Hashing the file means the URL changes exactly when the content does —
    no bump to forget, and no cache-buster churn on nights when the code is
    untouched.

    Both index.html AND sw.js get rewritten. The scripts and stylesheets are
    referenced in each, and G5 (scripts/bump_assets.py --check) fails the
    build if they disagree. Stamping only index.html is a real drift, not a
    cosmetic one: the service worker would keep precaching the old URL.
    """
    targets = _stamp_targets()
    digests = {}
    for name in STAMPED_SCRIPTS + STAMPED_DATA:
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
