"""Edition registry step: check every file's edition keys, then write
output/edition_registry.csv. Run by auto_update.py and run_enrichment.py.

A failed check raises. In the nightly that fails the run, so the stale
banner goes up over the last published data instead of a commit of broken
keys; in the enrichment run it blocks the commit of the scraped files.
"""
from pipeline import config
from registry.checks import build_registry, check_integrity, exemption_lines
from registry.io import load_frames, write_registry

MAX_LISTED_ERRORS = 20


def step_edition_registry(output_dir=None):
    output_dir = output_dir or config.OUTPUT_DIR
    print(f"\n{'─'*60}")
    print("  STEP: Edition registry integrity check")
    print(f"{'─'*60}")
    report, resolutions = check_integrity(load_frames(output_dir))
    for line in exemption_lines(resolutions):
        print(f"  {line}")
    if not report.passed:
        listed = "\n".join(f"  {e}" for e in report.errors[:MAX_LISTED_ERRORS])
        more = len(report.errors) - MAX_LISTED_ERRORS
        tail = f"\n  ... and {more} more" if more > 0 else ""
        raise RuntimeError(f"Edition registry check failed ({len(report.errors)} error(s)):\n{listed}{tail}")
    registry = build_registry(resolutions)
    path = write_registry(registry, output_dir)
    print(f"  {len(registry)} editions resolved across {len(resolutions)} files -> {path}")
    return registry
