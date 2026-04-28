"""
Auto-update pipeline: scrape fresh entry counts, re-run predictions, update website.

Steps:
  1. Run scrape_entries.py to get fresh CCA entry counts
  2. Read latest scrape data from output/daily_scrape.csv
  3. Run 04c_final_model.py + 04d_website_data_v2.py to regenerate predictions
     (includes walk-in multiplier from output/walk_in_family_stats.csv)
  4. Regenerate output/website_data.json
  5. Update the TOURNAMENT_DATA block in docs/index.html
  6. Log the run to output/update_log.csv

Note: Walk-in multiplier data (06_walk_in_multipliers.py) is regenerated manually
after scrape_standings.py runs, not on every daily update.
"""

import argparse
import os
import sys
import json
import csv
import subprocess
import time
from datetime import datetime

from validate_scraped_data import validate_all
from verify_checksums import generate_manifest
from scrape_health import log_scrape_attempt, generate_health_html
from alerts import compute_pace_alerts, inject_alerts

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
SITE_DIR = os.path.join(PROJECT_DIR, "docs")
SCRAPE_CSV = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
WEBSITE_JSON = os.path.join(OUTPUT_DIR, "website_data.json")
INDEX_HTML = os.path.join(SITE_DIR, "index.html")
UPDATE_LOG = os.path.join(OUTPUT_DIR, "update_log.csv")

RUN_TS = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def run_step(description, cmd):
    """Run a subprocess step, printing status and handling errors."""
    print(f"\n{'─'*60}")
    print(f"  STEP: {description}")
    print(f"{'─'*60}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=300
    )
    # Print stdout (last 20 lines to keep output manageable)
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        for line in lines[-20:]:
            print(f"  {line}")
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-500:]}" if result.stderr else "")
        raise RuntimeError(f"Step failed with exit code {result.returncode}: {description}")
    return result


def step_scrape():
    """Run the daily scraper."""
    run_step("Scrape CCA entry counts", [sys.executable, "scrape_entries.py"])

    if not os.path.exists(SCRAPE_CSV):
        raise RuntimeError(f"Scraper did not produce {SCRAPE_CSV}")

    # Print latest scrape summary
    today = datetime.now().strftime('%Y-%m-%d')
    count = 0
    with open(SCRAPE_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['date'] == today:
                count += 1
    print(f"  Scrape complete: {count} tournaments for {today}")


def step_update_puzzles():
    """Generate daily chess puzzles."""
    puzzle_script = os.path.join(PROJECT_DIR, "scrape_puzzles.py")
    if os.path.exists(puzzle_script):
        run_step("Generate daily puzzles", [sys.executable, "scrape_puzzles.py"])
    else:
        print("  Skipping puzzles (scrape_puzzles.py not found)")


def step_data_prep():
    """Refresh tournament_summary.csv from the registrations snapshot + live scrape.

    Without this step, tournament_summary.csv goes stale whenever
    ~/Downloads/all_registrations.csv goes stale, and the model grades itself
    against a low-water snapshot (see ACO 2026: snapshot 184 vs real 424).
    01_data_prep.py reconciles snapshot final_count with daily_scrape.csv peak,
    so this step is safe to run even when the manual export is days old.
    """
    src = os.path.expanduser("~/Downloads/all_registrations.csv")
    if not os.path.exists(src):
        print(f"\n{'─'*60}")
        print(f"  STEP: Refresh tournament summary (SKIPPED)")
        print(f"{'─'*60}")
        print(f"  {src} not found — keeping existing tournament_summary.csv.")
        print(f"  04e_performance_data.py freshness assertion will abort if grading "
              f"would be against stale truth.")
        return
    run_step("Refresh tournament summary (01_data_prep.py)",
             [sys.executable, "01_data_prep.py"])


def step_update_model():
    """Re-run the prediction model and website data generator."""
    # 04d_website_data_v2.py imports and runs 04c_final_model internally
    run_step("Generate predictions (04d_website_data_v2.py)",
             [sys.executable, "04d_website_data_v2.py"])


def step_performance():
    """Generate model performance / blind test data."""
    run_step("Generate performance data (04e_performance_data.py)",
             [sys.executable, "04e_performance_data.py"])

    if not os.path.exists(WEBSITE_JSON):
        raise RuntimeError(f"Model did not produce {WEBSITE_JSON}")

    with open(WEBSITE_JSON, 'r') as f:
        data = json.load(f)
    n_tournaments = len(data.get('tournaments', []))
    print(f"  Generated predictions for {n_tournaments} tournaments")


def step_update_html():
    """Replace the TOURNAMENT_DATA block in docs/index.html."""
    if not os.path.exists(WEBSITE_JSON):
        raise RuntimeError(f"Missing {WEBSITE_JSON}")
    if not os.path.exists(INDEX_HTML):
        raise RuntimeError(f"Missing {INDEX_HTML}")

    with open(WEBSITE_JSON, 'r') as f:
        json_data = f.read().strip()

    with open(INDEX_HTML, 'r') as f:
        html = f.read()

    # Find and replace the TOURNAMENT_DATA block
    # Pattern: "const TOURNAMENT_DATA = {" ... "};" (the closing }; on its own line)
    start_marker = 'const TOURNAMENT_DATA = '
    start_idx = html.find(start_marker)
    if start_idx == -1:
        raise RuntimeError("Could not find 'const TOURNAMENT_DATA = ' in index.html")

    # Find the end: we need to find the matching closing brace
    # The block ends with "};" on its own line after the JSON object
    data_start = start_idx + len(start_marker)

    # Count braces to find the matching close
    brace_depth = 0
    end_idx = None
    for i in range(data_start, len(html)):
        if html[i] == '{':
            brace_depth += 1
        elif html[i] == '}':
            brace_depth -= 1
            if brace_depth == 0:
                # Include the semicolon after the closing brace
                end_idx = i + 1
                if end_idx < len(html) and html[end_idx] == ';':
                    end_idx += 1
                break

    if end_idx is None:
        raise RuntimeError("Could not find end of TOURNAMENT_DATA block in index.html")

    # Replace
    new_html = html[:start_idx] + f'const TOURNAMENT_DATA = {json_data};' + html[end_idx:]

    # Also embed PUZZLE_DATA if available
    puzzle_json_path = os.path.join(OUTPUT_DIR, "daily_puzzles.json")
    if os.path.exists(puzzle_json_path):
        with open(puzzle_json_path, 'r') as f:
            puzzle_json = f.read().strip()
        puzzle_marker = 'const PUZZLE_DATA = '
        p_start = new_html.find(puzzle_marker)
        if p_start != -1:
            p_data_start = p_start + len(puzzle_marker)
            p_brace = 0
            p_end = None
            for i in range(p_data_start, len(new_html)):
                if new_html[i] == '{': p_brace += 1
                elif new_html[i] == '}':
                    p_brace -= 1
                    if p_brace == 0:
                        p_end = i + 1
                        if p_end < len(new_html) and new_html[p_end] == ';': p_end += 1
                        break
            if p_end:
                new_html = new_html[:p_start] + f'const PUZZLE_DATA = {puzzle_json};' + new_html[p_end:]
                print(f"  Updated PUZZLE_DATA in index.html")

    # Also embed CHESS_HISTORY if available
    history_json_path = os.path.join(OUTPUT_DIR, "chess_history.json")
    if os.path.exists(history_json_path):
        with open(history_json_path, 'r') as f:
            history_json = f.read().strip()
        history_marker = 'const CHESS_HISTORY = '
        h_start = new_html.find(history_marker)
        if h_start != -1:
            h_data_start = h_start + len(history_marker)
            h_brace = 0
            h_end = None
            for i in range(h_data_start, len(new_html)):
                if new_html[i] == '{': h_brace += 1
                elif new_html[i] == '}':
                    h_brace -= 1
                    if h_brace == 0:
                        h_end = i + 1
                        if h_end < len(new_html) and new_html[h_end] == ';': h_end += 1
                        break
            if h_end:
                new_html = new_html[:h_start] + f'const CHESS_HISTORY = {history_json};' + new_html[h_end:]
                print(f"  Updated CHESS_HISTORY in index.html")

    # Embed PERFORMANCE_DATA if available
    perf_json_path = os.path.join(OUTPUT_DIR, "performance_data.json")
    if os.path.exists(perf_json_path):
        with open(perf_json_path, 'r') as f:
            perf_json = f.read().strip()
        perf_marker = 'const PERFORMANCE_DATA = '
        pf_start = new_html.find(perf_marker)
        if pf_start != -1:
            pf_data_start = pf_start + len(perf_marker)
            pf_brace = 0
            pf_end = None
            for i in range(pf_data_start, len(new_html)):
                if new_html[i] == '{': pf_brace += 1
                elif new_html[i] == '}':
                    pf_brace -= 1
                    if pf_brace == 0:
                        pf_end = i + 1
                        if pf_end < len(new_html) and new_html[pf_end] == ';': pf_end += 1
                        break
            if pf_end:
                new_html = new_html[:pf_start] + f'const PERFORMANCE_DATA = {perf_json};' + new_html[pf_end:]
                print(f"  Updated PERFORMANCE_DATA in index.html")

    with open(INDEX_HTML, 'w') as f:
        f.write(new_html)

    print(f"  Updated TOURNAMENT_DATA in {INDEX_HTML}")

    # Post-write verification: re-read HTML and confirm embedded data matches source
    with open(INDEX_HTML, 'r') as f:
        verify_html = f.read()
    verify_idx = verify_html.find(start_marker)
    if verify_idx == -1:
        raise RuntimeError("Post-write verification failed: TOURNAMENT_DATA marker missing from written HTML")
    source_data = json.loads(json_data)
    source_gen = source_data.get('generated', '')
    source_count = len(source_data.get('tournaments', []))
    # Extract embedded generated date for quick sanity check
    import re as _re
    gen_match = _re.search(r'"generated"\s*:\s*"([^"]+)"', verify_html[verify_idx:verify_idx+500])
    if gen_match:
        embedded_gen = gen_match.group(1)
        if embedded_gen != source_gen:
            raise RuntimeError(
                f"STALE DATA DETECTED: embedded generated={embedded_gen} but source={source_gen}. "
                f"The HTML was not updated correctly."
            )
    print(f"  Verified: embedded data matches source (generated={source_gen}, {source_count} tournaments)")

    # Also copy JSON to site directory
    site_json = os.path.join(SITE_DIR, "website_data.json")
    with open(site_json, 'w') as f:
        f.write(json_data)
    print(f"  Copied website_data.json to docs/")


def step_log_run():
    """Log this run's predictions to update_log.csv."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Initialize log if it doesn't exist
    write_header = not os.path.exists(UPDATE_LOG)

    with open(WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    lines_logged = 0
    with open(UPDATE_LOG, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                'run_timestamp', 'family', 'status', 'current_count',
                'point_estimate', 'ci_lower', 'ci_upper', 'days_remaining'
            ])
        for t in data.get('tournaments', []):
            if t.get('year') != 2026:
                continue
            if t.get('status') not in ('live', 'complete'):
                continue
            writer.writerow([
                RUN_TS, t['family'], t['status'], t['current_count'],
                t['point_estimate'], t['ci_lower'], t['ci_upper'],
                t['days_remaining']
            ])
            lines_logged += 1

    print(f"  Logged {lines_logged} predictions to {UPDATE_LOG}")


def _stamp_stale_flag(is_stale):
    """Add/update last_updated and is_stale fields in website_data.json.

    Preserves existing predictions when the scrape fails so stale data
    can still be served with a warning banner.
    """
    if not os.path.exists(WEBSITE_JSON):
        print(f"  WARNING: {WEBSITE_JSON} not found — cannot stamp stale flag")
        return

    with open(WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    data['last_updated'] = RUN_TS
    data['is_stale'] = is_stale

    with open(WEBSITE_JSON, 'w') as f:
        json.dump(data, f, indent=2)

    flag = "STALE" if is_stale else "FRESH"
    print(f"  Stamped website_data.json — is_stale={is_stale} ({flag}), last_updated={RUN_TS}")


def main():
    parser = argparse.ArgumentParser(description="Auto-update pipeline")
    parser.add_argument('--skip-scrape', action='store_true',
                        help="Skip the scraping step (use existing daily_scrape.csv)")
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
    if args.skip_scrape:
        print("\n  Skipping scrape step (--skip-scrape)")
    else:
        try:
            step_scrape()

            # Validate scraped data before proceeding
            print(f"\n{'─'*60}")
            print(f"  STEP: Validate scraped data")
            print(f"{'─'*60}")
            report = validate_all()
            validation_errors = len(report.errors)
            validation_warnings = len(report.warnings)
            print(report.summary())
            if not report.passed:
                raise RuntimeError("Data validation failed (see errors above)")

            # Count rows scraped today
            today = datetime.now().strftime('%Y-%m-%d')
            if os.path.exists(SCRAPE_CSV):
                with open(SCRAPE_CSV, 'r') as f:
                    reader = csv.DictReader(f)
                    row_count = sum(1 for r in reader if r.get('date') == today)
        except Exception as e:
            scrape_ok = False
            print(f"\n{'!'*60}")
            print(f"  SCRAPE FAILED (graceful degradation): {e}")
            print(f"  Serving stale predictions with warning banner.")
            print(f"{'!'*60}")

    try:
        if scrape_ok:
            # Fresh data — refresh summary from snapshot+scrape, then regenerate model
            step_data_prep()
            step_update_model()
            step_performance()

            # Puzzles are non-critical — don't let a Lichess outage block the pipeline
            try:
                step_update_puzzles()
            except Exception as e:
                print(f"\n  Warning: Puzzle step failed (non-fatal): {e}")
                print(f"  Continuing with existing puzzle data...")

            _stamp_stale_flag(is_stale=False)
        else:
            # Stale path — skip model regen, keep existing JSON, stamp stale
            print(f"\n{'─'*60}")
            print(f"  STEP: Skip model regeneration (stale mode)")
            print(f"{'─'*60}")
            print(f"  Keeping existing {WEBSITE_JSON} intact")
            _stamp_stale_flag(is_stale=True)

        # Compute and inject pace alerts
        if os.path.exists(WEBSITE_JSON):
            print(f"\n{'─'*60}")
            print(f"  STEP: Compute pace alerts")
            print(f"{'─'*60}")
            with open(WEBSITE_JSON, 'r') as f:
                wd = json.load(f)
            alerts = compute_pace_alerts(wd)
            inject_alerts(wd, alerts)
            with open(WEBSITE_JSON, 'w') as f:
                json.dump(wd, f, indent=2)
            n_alerts = sum(1 for a in alerts if a['status'] != 'on_pace')
            print(f"  {len(alerts)} tournaments checked, {n_alerts} pace alert(s)")

        # Always update HTML so the stale flag gets embedded in the page
        step_update_html()
        step_log_run()

        # Generate SHA-256 checksums for all output CSVs
        print(f"\n{'─'*60}")
        print(f"  STEP: Generate output checksums")
        print(f"{'─'*60}")
        generate_manifest(OUTPUT_DIR)

        # Log health and generate dashboard
        duration = time.time() - t_start
        log_scrape_attempt(
            success=scrape_ok,
            row_count=row_count,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
            duration_seconds=duration,
        )
        generate_health_html()

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
        generate_health_html()

        print(f"\n{'!'*60}")
        print(f"  PIPELINE FAILED: {e}")
        print(f"{'!'*60}")
        sys.exit(1)


if __name__ == '__main__':
    main()
