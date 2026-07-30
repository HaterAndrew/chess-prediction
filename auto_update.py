"""
Auto-update pipeline: scrape fresh entry counts, re-run predictions, update website.

Steps:
  1. Run scrape_entries.py to get fresh CCA entry counts
  2. Read latest scrape data from output/daily_scrape.csv
  3. Run 04c_final_model.py + 04d_website_data_v2.py to regenerate predictions
     (includes walk-in multiplier from output/walk_in_family_stats.csv)
  4. Regenerate output/website_data.json
  5. Update the TOURNAMENT_DATA block in docs/data/site_data.js
  6. Log the run to output/update_log.csv

Note: Walk-in multiplier data (06_walk_in_multipliers.py) is regenerated every
pipeline run from historical_standings.csv + tournament_summary.csv.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

from validate_scraped_data import validate_all
from verify_checksums import generate_manifest
from scrape_health import log_scrape_attempt
from alerts import compute_pace_alerts, inject_alerts

# Compatibility shim (2026-07-30 decomposition): the implementation lives in
# pipeline/. main() and _validate_and_count stay here so the CLI entrypoint,
# daily_update.yml's `import auto_update; auto_update.step_update_html()`
# call, and inspect-based tests keep one stable home. The re-exports below
# are the legacy attribute surface; NOTE that patching them on this module
# does not reach pipeline-internal callers -- patch the defining module
# (pipeline.config, pipeline.warns, ...) instead.
from pipeline.config import (  # noqa: F401
    INDEX_HTML,
    OUTPUT_DIR,
    PROJECT_DIR,
    RUN_TS,
    SCRAPE_CSV,
    SITE_DATA_JS,
    SITE_DATA_JSON,
    SITE_DIR,
    UPDATE_LOG,
    WEBSITE_JSON,
)
from pipeline.warns import (  # noqa: F401
    _PIPELINE_WARNINGS,
    _harvest_warnings,
    group_warnings,
    write_audit_warnings,
)
from pipeline.runner import (  # noqa: F401
    DEFAULT_STEP_TIMEOUT,
    KEEP_LOG_RE,
    STEP_TIMEOUT_OVERRIDES,
    _step_timeout,
    run_step,
)
from pipeline.steps import (  # noqa: F401
    EXPORT_STALE_WARN_DAYS,
    step_chess_history,
    step_data_health,
    step_data_prep,
    step_performance,
    step_scrape,
    step_structure_check,
    step_update_model,
    step_update_puzzles,
    step_verify_dates,
    step_walkin_multipliers,
)
from pipeline.site_html import step_update_html  # noqa: F401
from pipeline.run_log import prune_update_log, step_log_run  # noqa: F401
from pipeline.stamping import (  # noqa: F401
    STAMPED_SCRIPTS,
    _atomic_write_json,
    _stamp_script_versions,
    _stamp_site_data_version,
    _stamp_stale_flag,
    _stamp_targets,
)
from pipeline.degraded import mark_pipeline_degraded  # noqa: F401


def _validate_and_count():
    """Run the scrape validation gate and count today's scraped rows.

    v5 Cat T: this used to live inside the not-skip-scrape branch, so CI —
    which scrapes in its own workflow step and always passes --skip-scrape —
    never ran the gate the README documents, and scrape_health.json logged
    success=True row_count=0 every night. Now it runs regardless of who
    scraped. Raises on a failed validation; returns
    (validation_errors, validation_warnings, row_count).
    """
    print(f"\n{'─'*60}")
    print("  STEP: Validate scraped data")
    print(f"{'─'*60}")
    report = validate_all()
    print(report.summary())
    for w in report.warnings:
        _PIPELINE_WARNINGS.append({'step': 'Validate scraped data', 'text': w})
    if not report.passed:
        raise RuntimeError("Data validation failed (see errors above)")

    row_count = 0
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(SCRAPE_CSV):
        with open(SCRAPE_CSV, 'r') as f:
            reader = csv.DictReader(f)
            row_count = sum(1 for r in reader if r.get('date') == today)
    return len(report.errors), len(report.warnings), row_count


def main():
    parser = argparse.ArgumentParser(description="Auto-update pipeline")
    parser.add_argument('--skip-scrape', action='store_true',
                        help="Skip the scraping step (use existing daily_scrape.csv)")
    parser.add_argument('--scrape-failed', action='store_true',
                        help="The external scrape step (CI) failed: keep "
                             "last-known data, skip validation, stamp stale")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  AUTO-UPDATE PIPELINE — {RUN_TS}")
    print(f"{'='*60}")

    t_start = time.time()
    scrape_ok = True
    validation_errors = 0
    validation_warnings = 0
    row_count = 0

    # --- Scrape phase (failures are non-fatal) ---
    if args.scrape_failed:
        # v5 Cat T: CI runs the scraper as its own workflow step; when that
        # step fails it now passes this flag instead of killing the job, so
        # the stale-stamp path below finally runs in CI and the site says so.
        scrape_ok = False
        print(f"\n{'!'*60}")
        print("  SCRAPE FAILED in the external scrape step (--scrape-failed).")
        print("  Serving stale predictions with warning banner.")
        print(f"{'!'*60}")
    else:
        try:
            if args.skip_scrape:
                print("\n  Skipping scrape step (--skip-scrape); validating "
                      "existing daily_scrape.csv")
            else:
                step_scrape()
            # Validation + row telemetry run regardless of who scraped.
            validation_errors, validation_warnings, row_count = _validate_and_count()
        except Exception as e:
            scrape_ok = False
            print(f"\n{'!'*60}")
            print(f"  SCRAPE FAILED (graceful degradation): {e}")
            print("  Serving stale predictions with warning banner.")
            print(f"{'!'*60}")

    try:
        if scrape_ok:
            # Fresh data — refresh summary from snapshot+scrape, then regenerate model
            step_data_prep()
            step_walkin_multipliers()
            step_verify_dates()
            step_update_model()
            step_performance()

            # Renders from a tracked source with no network call, so unlike the
            # puzzle step a failure here means the committed JSON is malformed,
            # not that a third party is down. Fatal: the degraded path then
            # publishes last-known-good behind an honest banner, which beats
            # shipping a blank panel on a page that claims to be current.
            step_chess_history()

            # Puzzles are non-critical — don't let a Lichess outage block the pipeline
            try:
                step_update_puzzles()
            except Exception as e:
                print(f"\n  Warning: Puzzle step failed (non-fatal): {e}")
                print("  Continuing with existing puzzle data...")

            _stamp_stale_flag(is_stale=False)
        else:
            # Stale path — skip model regen, keep existing JSON, stamp stale
            print(f"\n{'─'*60}")
            print("  STEP: Skip model regeneration (stale mode)")
            print(f"{'─'*60}")
            print(f"  Keeping existing {WEBSITE_JSON} intact")
            _stamp_stale_flag(is_stale=True)

        # Compute and inject pace alerts
        if os.path.exists(WEBSITE_JSON):
            print(f"\n{'─'*60}")
            print("  STEP: Compute pace alerts")
            print(f"{'─'*60}")
            with open(WEBSITE_JSON, 'r') as f:
                wd = json.load(f)
            alerts = compute_pace_alerts(wd)
            inject_alerts(wd, alerts)
            with open(WEBSITE_JSON, 'w') as f:
                json.dump(wd, f, indent=2)
            n_alerts = sum(1 for a in alerts if a['status'] != 'on_pace')
            print(f"  {len(alerts)} tournaments checked, {n_alerts} pace alert(s)")

        # Scan the final prediction output for degraded tournament cards.
        # v5 Cat T: a CRITICAL finding aborts (step_data_health raises on the
        # scanner's exit 3) so the degraded-banner path publishes last-known-
        # good data; only a scanner crash (exit 4) is non-fatal, handled
        # inside the step. The blanket try/except that used to sit here
        # swallowed both and silently defeated --strict.
        step_data_health()

        # Always update HTML so the stale flag gets embedded in the page
        step_update_html()
        step_log_run()

        # Generate SHA-256 checksums for all output CSVs
        print(f"\n{'─'*60}")
        print("  STEP: Generate output checksums")
        print(f"{'─'*60}")
        generate_manifest(OUTPUT_DIR)

        # Log health
        duration = time.time() - t_start
        log_scrape_attempt(
            success=scrape_ok,
            row_count=row_count,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            duration_seconds=duration,
        )

        # Non-blocking CCA markup drift alarm (H6) — feeds the warning list below.
        step_structure_check()

        # Persist any WARNING lines emitted by sub-steps so CI can surface them.
        write_audit_warnings()

        status = "COMPLETE" if scrape_ok else "COMPLETE (STALE)"
        print(f"\n{'='*60}")
        print(f"  PIPELINE {status} — {RUN_TS}")
        print(f"{'='*60}")

    except Exception as e:
        # Log failure to health tracker
        duration = time.time() - t_start
        log_scrape_attempt(
            success=False,
            row_count=0,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            duration_seconds=duration,
        )

        # v3 O1 (audit/AUDIT_2026-07-25.md): a mid-run crash used to be entirely
        # invisible to visitors. _stamp_stale_flag, alerts, data-health and the
        # HTML splice all sit inside the try above, so a failure at 04e skipped
        # every one of them: is_stale stayed False and last_updated stayed frozen
        # at the previous success, and the site kept presenting day-old numbers as
        # current. Mark the degraded state here so the banner tells the truth even
        # when the run dies. Best-effort — nothing in this handler may mask the
        # original exception or change the non-zero exit.
        try:
            mark_pipeline_degraded(reason=str(e))
        except Exception as stamp_err:  # pragma: no cover - defensive
            print(f"  WARNING: could not stamp degraded state: {stamp_err}")

        print(f"\n{'!'*60}")
        print(f"  PIPELINE FAILED: {e}")
        print(f"{'!'*60}")
        sys.exit(1)


if __name__ == '__main__':
    main()
