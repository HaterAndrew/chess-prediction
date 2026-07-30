"""
data_health.py — Health scan of the prediction OUTPUT (website_data.json).

Audits every tournament card for the degradation modes that produced the
World Open Under 13 / Eastern (in CT/NJ) bugs and adjacent issues. Read-only:
loads output/website_data.json and cross-references the input CSVs, ranks
findings by severity, and writes a markdown report + JSON summary.

Existing tools validate the INPUTS (validate_scraped_data.py) or operational
run health (scrape_health.py); nothing audited the per-tournament prediction
cards until now. Family-name folding reuses tournament_aliases so the scan
agrees with the pipeline on what counts as the same tournament.

CRITICAL/HIGH findings are printed as `WARNING: data-health ...` lines so that
auto_update._harvest_warnings folds them into output/audit_warnings.json with
no extra wiring.

Usage:
    python3 data_health.py            # scan, write reports, exit 0
    python3 data_health.py --strict   # exit 1 if any CRITICAL finding
"""

import json
import os
import sys
from datetime import datetime

# Legacy attribute surface (2026-07-30 decomposition): the scanner lives
# in healthcheck/ (report, context, checks); this file keeps the CLI and
# the names tests and callers import.
from healthcheck.checks import (  # noqa: F401
    DAILY_GAP_WARN_DAYS,
    PERF_FROZEN_CURVE_RATIO,
    WITHDRAWAL_GAP_WARN_FRAC,
    _is_main_path,
    _is_roster_pending,
    scan,
)
from healthcheck.context import (  # noqa: F401
    Context,
    _canon,
    _strip_year,
)
from healthcheck.report import SEVERITIES, HealthReport  # noqa: F401
from shared.paths import (  # noqa: F401
    METADATA_CSV,
    OUTPUT_DIR,
    PERFORMANCE_JSON,
    PROJECT_DIR,
    SUMMARY_CSV,
    UPDATE_LOG_CSV,
    WEBSITE_JSON,
)
from shared.paths import SCRAPE_CSV as DAILY_SCRAPE_CSV  # noqa: F401

HEALTH_JSON = os.path.join(OUTPUT_DIR, "data_health.json")
AUDIT_DIR = os.path.join(PROJECT_DIR, "audit", "data-health")


def load_website_data():
    if not os.path.exists(WEBSITE_JSON):
        raise SystemExit(f"ERROR: {WEBSITE_JSON} not found — run 04d_website_data_v2.py first")
    with open(WEBSITE_JSON) as fh:
        return json.load(fh)


def exit_code_for(report, strict, crashed=False):
    """Map a scan outcome to the process exit code (v5 Cat T).

    0: clean (or findings without --strict) · 3: --strict with a CRITICAL
    finding (the pipeline must abort and publish the degraded banner) ·
    4: the scanner itself crashed (telemetry loss, NOT a data verdict — the
    pipeline treats it as non-fatal so a scanner bug can't block publishing).
    Distinct codes because auto_update must tell "the data is bad" apart from
    "the scanner broke": the old blanket try/except treated both as ignorable,
    which silently defeated --strict.
    """
    if crashed:
        return 4
    if strict and report.has_critical():
        return 3
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv

    data = load_website_data()
    ctx = Context()
    try:
        report = scan(data, ctx)
    except Exception as e:  # scanner bug — loud, but distinct from a finding
        print(f"WARNING: data-health scanner crashed: {e}")
        return exit_code_for(None, strict, crashed=True)

    # Markdown report
    os.makedirs(AUDIT_DIR, exist_ok=True)
    md_path = os.path.join(AUDIT_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(md_path, "w") as fh:
        fh.write(report.to_markdown())

    # JSON summary
    with open(HEALTH_JSON, "w") as fh:
        json.dump(report.to_json(), fh, indent=2)

    # stdout: harvestable WARNING lines first, then the grouped summary
    for line in report.warning_lines():
        print(line)
    print(report.summary())
    print(f"  Report: {md_path}")
    print(f"  JSON:   {HEALTH_JSON}")

    return exit_code_for(report, strict)


if __name__ == "__main__":
    sys.exit(main())
