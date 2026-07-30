"""v4 U1/U2 regression guards (audit/AUDIT_2026-07-26.md).

Static guards in the repo's established style (test_csp_inline_handlers,
test_no_hardcoded_claims): chart date math must stay on one convention, and
series consumers must stay sanitised. Since the C-track split the chart code
spreads across several page-scope scripts, so the scan covers every docs/*.js
except a documented allowlist.

U1: the overlay day-drift came from round-tripping a local-midnight Date
through toISOString()'s UTC. Ban the call outright: every chart date is
either local-midnight (main chart axis) or arithmetic on day indexes, and a
UTC reprojection anywhere reintroduces the +1 day shift for
positive-UTC-offset viewers.

U2: every daily_data consumer routes through DailySeries.sanitizeSeries.
"""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

# Files exempt from the U1 toISOString ban, each for a stated reason:
#   audit.js   — stamps a generated-on date into an export payload; that is
#                metadata, not chart axis math.
#   actions.js — delegation tables only, no date math.
#   sw.js      — worker scope, no charts.
U1_EXEMPT = {"audit.js", "actions.js", "sw.js"}


def _chart_scripts():
    return sorted(p for p in DOCS.glob("*.js") if p.name not in U1_EXEMPT)


def test_no_utc_reprojection_in_chart_scripts():
    offenders = [p.name for p in _chart_scripts()
                 if ".toISOString(" in p.read_text()]
    assert not offenders, (
        f"{offenders} reintroduced a toISOString() round-trip; chart date "
        "math must stay local/arithmetic (v4 U1, audit/AUDIT_2026-07-26.md)"
    )


def test_all_daily_data_consumers_sanitise():
    # Raw daily_data reads feeding chart data: allow presence checks
    # (t.daily_data && ...), length checks, and sanitizeSeries arguments;
    # flag bare assignments like `const dd = real.daily_data;`.
    bare_reads = []
    sanitize_calls = 0
    for p in _chart_scripts():
        src = p.read_text()
        bare_reads += [f"{p.name}: {m.group(0)}"
                       for m in re.finditer(r"=\s*\w+\.daily_data\s*;", src)]
        sanitize_calls += src.count("DailySeries.sanitizeSeries(")
    assert not bare_reads, (
        f"unsanitised daily_data assignment(s): {bare_reads} — "
        "route through DailySeries.sanitizeSeries (v4 U2)"
    )
    # The three chart consumers (main actual, historical overlay, compare)
    # all call sanitizeSeries; keep at least those, wherever they now live.
    assert sanitize_calls >= 3
