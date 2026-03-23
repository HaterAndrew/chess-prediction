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


def step_update_model():
    """Re-run the prediction model and website data generator."""
    # 04d_website_data_v2.py imports and runs 04c_final_model internally
    run_step("Generate predictions (04d_website_data_v2.py)",
             [sys.executable, "04d_website_data_v2.py"])

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
