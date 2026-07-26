"""v4 U1/U2 regression guards (audit/AUDIT_2026-07-26.md).

Static guards in the repo's established style (test_csp_inline_handlers,
test_no_hardcoded_claims): app.js's chart date math must stay on one
convention, and series consumers must stay sanitised.

U1: the overlay day-drift came from round-tripping a local-midnight Date
through toISOString()'s UTC. Ban the call outright: every chart date in
app.js is either local-midnight (main chart axis) or arithmetic on day
indexes, and a UTC reprojection anywhere reintroduces the +1 day shift for
positive-UTC-offset viewers.

U2: every daily_data consumer routes through DailySeries.sanitizeSeries.
"""

import re
from pathlib import Path

APP_JS = Path(__file__).resolve().parent.parent / "docs" / "app.js"


def test_no_utc_reprojection_in_app_js():
    src = APP_JS.read_text()
    assert ".toISOString(" not in src, (
        "app.js reintroduced a toISOString() round-trip; chart date math "
        "must stay local/arithmetic (v4 U1, audit/AUDIT_2026-07-26.md)"
    )


def test_all_daily_data_consumers_sanitise():
    src = APP_JS.read_text()
    # Raw daily_data reads feeding chart data: allow presence checks
    # (t.daily_data && ...), length checks, and sanitizeSeries arguments;
    # flag bare assignments like `const dd = real.daily_data;`.
    bare_reads = [
        m.group(0)
        for m in re.finditer(r"=\s*\w+\.daily_data\s*;", src)
    ]
    assert not bare_reads, (
        f"unsanitised daily_data assignment(s) in app.js: {bare_reads} — "
        "route through DailySeries.sanitizeSeries (v4 U2)"
    )
    # The three chart consumers (main actual, historical overlay, compare)
    # all call sanitizeSeries; keep at least those.
    assert src.count("DailySeries.sanitizeSeries(") >= 3
