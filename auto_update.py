"""
Auto-update pipeline: scrape fresh entry counts, re-run predictions, update website.

Steps:
  1. Run scrape_entries.py to get fresh CCA entry counts
  2. Read latest scrape data from output/daily_scrape.csv
  3. Run 04c_final_model.py + 04d_website_data_v2.py to regenerate predictions
  4. Regenerate output/website_data.json
  5. Update the TOURNAMENT_DATA block in docs/index.html
  6. Log the run to output/update_log.csv
"""

import argparse
import os
import sys
import json
import csv
import subprocess
from datetime import datetime

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


def main():
    parser = argparse.ArgumentParser(description="Auto-update pipeline")
    parser.add_argument('--skip-scrape', action='store_true',
                        help="Skip the scraping step (use existing daily_scrape.csv)")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  AUTO-UPDATE PIPELINE — {RUN_TS}")
    print(f"{'='*60}")

    try:
        if args.skip_scrape:
            print("\n  Skipping scrape step (--skip-scrape)")
        else:
            step_scrape()
        step_update_model()
        step_performance()
        step_update_puzzles()
        step_update_html()
        step_log_run()

        print(f"\n{'='*60}")
        print(f"  PIPELINE COMPLETE — {RUN_TS}")
        print(f"{'='*60}")

    except Exception as e:
        print(f"\n{'!'*60}")
        print(f"  PIPELINE FAILED: {e}")
        print(f"{'!'*60}")
        sys.exit(1)


if __name__ == '__main__':
    main()
