"""The pipeline step functions (auto_update, verbatim bodies; constants
read via config.X at call time).
"""
import csv
import json
import os
import sys
from datetime import datetime

from pipeline import config, warns
from pipeline.runner import run_step


def step_structure_check():
    """H6: non-blocking CCA markup drift alarm. Checks the tourlist endpoint the
    scraper depends on (via requests, no Chrome). Deviations become persisted
    warnings — a structure change should alert operators through
    audit_warnings.json, never halt the daily run. Errors are swallowed to a
    warning for the same reason."""
    print(f"\n{'─'*60}")
    print("  STEP: CCA structure drift check (non-blocking)")
    print(f"{'─'*60}")
    try:
        import structure_monitor as sm
        baseline = sm.CCA_BASELINE
        if os.path.exists(sm.BASELINE_PATH):
            with open(sm.BASELINE_PATH) as f:
                baseline = json.load(f)
        deviations = sm.check_structure(baseline.get("url", sm.CCA_INDEX_URL), baseline)
        for d in deviations:
            warns._PIPELINE_WARNINGS.append({'step': 'CCA structure drift', 'text': d})
        if deviations:
            print(f"  {len(deviations)} deviation(s) — CCA markup may have changed; scrapers at risk.")
        else:
            print("  CCA structure OK.")
    except Exception as e:
        warns._PIPELINE_WARNINGS.append({'step': 'CCA structure drift', 'text': f'structure check errored: {e}'})
        print(f"  Structure check errored (non-blocking): {e}")


def step_scrape():
    """Run the daily scraper."""
    run_step("Scrape CCA entry counts", [sys.executable, "scrape_entries.py"])

    if not os.path.exists(config.SCRAPE_CSV):
        raise RuntimeError(f"Scraper did not produce {config.SCRAPE_CSV}")

    # Print latest scrape summary
    today = datetime.now().strftime('%Y-%m-%d')
    count = 0
    with open(config.SCRAPE_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['date'] == today:
                count += 1
    print(f"  Scrape complete: {count} tournaments for {today}")


def step_update_puzzles():
    """Generate daily chess puzzles."""
    puzzle_script = os.path.join(config.PROJECT_DIR, "scrape_puzzles.py")
    if os.path.exists(puzzle_script):
        run_step("Generate daily puzzles", [sys.executable, "scrape_puzzles.py"])
    else:
        print("  Skipping puzzles (scrape_puzzles.py not found)")


def step_chess_history():
    """Emit output/chess_history.json so the CHESS_HISTORY splice has a source.

    v3 O5: the splice below was guarded on a file nothing wrote, so it had
    never fired and the 146KB const lived only inside the generated
    site_data.js. content/chess_history.json is now the tracked source and this
    step renders it, which makes the const reviewable and the splice real.
    A malformed source fails the run rather than shipping a blank panel.
    """
    run_step("Render chess history (scripts/gen_chess_history.py)",
             [sys.executable, os.path.join("scripts", "gen_chess_history.py")])


# A present-but-old all_registrations.csv freezes the TRAINING side of the
# roster. Since v5 Cat R, live prediction no longer depends on it — scraped
# events get roster-pending skeleton rows (reconcile_final_counts) and ride the
# model path off injected scrape curves. What a stale export still freezes:
# per-registration timestamps (has_timestamps/first_reg/last_reg — the event
# can never join the training corpus), early-bird-spike features,
# snapshot_last_reg (04e's grading tier), truth labels for never-scraped
# events, and sub-event TID folding. Warn loudly past this age instead of
# degrading silently.
EXPORT_STALE_WARN_DAYS = 14


def step_data_prep():
    """Refresh tournament_summary.csv from the registrations snapshot + live scrape.

    Without this step, tournament_summary.csv goes stale whenever
    ~/Downloads/all_registrations.csv goes stale, and the model grades itself
    against a low-water snapshot (see ACO 2026: snapshot 184 vs real 424).
    01_data_prep.py reconciles snapshot final_count with daily_scrape.csv peak,
    so this step is safe to run even when the manual export is days old — but a
    badly stale export still hides newly-opened tournaments, so it warns.
    """
    src = os.path.expanduser("~/Downloads/all_registrations.csv")
    if not os.path.exists(src):
        # The export only adds NEW tournaments to the roster — so without it the
        # roster is frozen (warn below). But the final_count reconcile that keeps
        # *existing* events' truth labels fresh needs only daily_scrape.csv, so
        # run that here instead of skipping outright. Otherwise a completed event
        # keeps its stale early-registration count and trips 04e's truth-label
        # freshness guard the day its end_date passes (June 2026 Hartford/Cleveland).
        msg = (f"all_registrations.csv export missing at {src} — live predictions "
               f"still run from scrape data, but the training corpus is frozen: "
               f"newly scraped events carry no registration timestamps, so they "
               f"can never join model training or 04e grading, and early-bird "
               f"spike features stay absent. Re-export from the CCA admin.")
        print(f"\n{'─'*60}")
        print("  STEP: Refresh tournament summary (export missing — reconcile-only)")
        print(f"{'─'*60}")
        print(f"  WARNING: {msg}")
        warns._PIPELINE_WARNINGS.append({'step': 'Refresh tournament summary', 'text': msg})
        from reconcile_final_counts import reconcile_final_counts
        reconcile_final_counts(config.OUTPUT_DIR)
        return
    export_date = datetime.fromtimestamp(os.path.getmtime(src))
    age_days = (datetime.now() - export_date).days
    if age_days >= EXPORT_STALE_WARN_DAYS:
        msg = (f"all_registrations.csv export is {age_days} days old "
               f"(dated {export_date.strftime('%Y-%m-%d')}). Live predictions still "
               f"run from scrape data, but events that opened registration after "
               f"that date have no timestamps — they cannot join model training or "
               f"04e grading until a fresh export. Re-export from the CCA admin.")
        print(f"\n  WARNING: {msg}")
        warns._PIPELINE_WARNINGS.append({'step': 'Refresh tournament summary', 'text': msg})
    run_step("Refresh tournament summary (01_data_prep.py)",
             [sys.executable, "01_data_prep.py"])
    # v5 Cat R follow-through: 01_data_prep rebuilds the summary from the
    # export alone, which drops the roster-pending skeleton rows that put
    # scraped-but-never-exported events on the model path. Re-append them so
    # a workstation run (export present) and a CI run (export missing) produce
    # the same summary shape. Idempotent — safe on every run.
    from reconcile_final_counts import reconcile_final_counts
    reconcile_final_counts(config.OUTPUT_DIR)


def step_walkin_multipliers():
    """Regenerate walk_in_family_stats.csv from historical_standings.csv.

    Without this step, the file is missing in production and apply_walkin_multiplier
    falls back to the global 'estimate' path for every tournament — silently
    degrading the per-family walk-in CI propagation. AUDIT.md A1.

    Idempotent: reads historical_standings.csv (updated by scrape_standings.py)
    and tournament_summary.csv (refreshed by step_data_prep). Skips if either
    input is missing.
    """
    standings = os.path.join(config.OUTPUT_DIR, "historical_standings.csv")
    summary = os.path.join(config.OUTPUT_DIR, "tournament_summary.csv")
    if not os.path.exists(standings) or not os.path.exists(summary):
        print(f"\n{'─'*60}")
        print("  STEP: Refresh walk-in multipliers (SKIPPED)")
        print(f"{'─'*60}")
        print("  Missing input(s); using stale walk-in stats if any exist.")
        return
    run_step("Refresh walk-in multipliers (06_walk_in_multipliers.py)",
             [sys.executable, "06_walk_in_multipliers.py"])


def step_verify_dates():
    """Verify current-year tournament_metadata.csv dates against
    chesstour.com canonical schedule.

    Warning-only by design — drift > 1 day gets harvested into
    audit_warnings.json via the "WARNING:" line format. Source-fetch
    failures don't block the pipeline either; they just emit a warning
    that the daily run wasn't independently verified.

    Originally added after the d76ea14 incident where wrong event_start
    dates (Cleveland 2025 off by 7 days) silently propagated through
    the T-axis, daily_data anchors, and pace alerts.
    """
    run_step("Verify dates against canonical sources (tools/verify_dates.py)",
             [sys.executable, "tools/verify_dates.py"])


def step_update_model():
    """Re-run the prediction model and website data generator."""
    # 04d_website_data_v2.py imports and runs 04c_final_model internally
    run_step("Generate predictions (04d_website_data_v2.py)",
             [sys.executable, "04d_website_data_v2.py"])


def step_performance():
    """Generate model performance / blind test data."""
    run_step("Generate performance data (04e_performance_data.py)",
             [sys.executable, "04e_performance_data.py"])

    if not os.path.exists(config.WEBSITE_JSON):
        raise RuntimeError(f"Model did not produce {config.WEBSITE_JSON}")

    with open(config.WEBSITE_JSON, 'r') as f:
        data = json.load(f)
    n_tournaments = len(data.get('tournaments', []))
    print(f"  Generated predictions for {n_tournaments} tournaments")


def step_data_health():
    """Scan the prediction output (website_data.json) for degraded tournament
    cards — frozen estimates, collapsed charts, misassembled daily curves,
    name/roster mismatches, alias mislabels, missing fees, etc. CRITICAL/HIGH
    findings print WARNING: lines that _harvest_warnings folds into
    audit_warnings.json (and the CI step summary).

    Runs with --strict (v3 Q1 → v5 Cat T): exit 3 = CRITICAL finding, and this
    step RAISES so the pipeline aborts and the degraded banner publishes
    last-known-good data — the 2026-07-25 corrupted-curve incident shipped
    because the scan was advisory. Exit 4 = the scanner itself crashed; that
    is telemetry loss, not a data verdict, so it stays non-fatal. The old
    blanket try/except around this call treated both cases as ignorable and
    silently defeated --strict."""
    result = run_step("Scan prediction data health (data_health.py)",
                      [sys.executable, "data_health.py", "--strict"],
                      check=False)
    if result.returncode == 3:
        raise RuntimeError(
            "data-health CRITICAL — aborting so the degraded banner publishes "
            "last-known-good data instead of these findings")
    if result.returncode != 0:
        print(f"\n  Warning: data-health scanner failed "
              f"(exit {result.returncode}, non-fatal) — findings unavailable "
              f"this run")
