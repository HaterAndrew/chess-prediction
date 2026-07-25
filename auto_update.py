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
import os
import re
import sys
import hashlib
import json
import csv
import subprocess
import time
from datetime import datetime, timedelta

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
# The large data consts were externalized out of index.html (L15); the daily
# build now splices them into this file, so index.html itself stays static.
SITE_DATA_JS = os.path.join(SITE_DIR, "data", "site_data.js")
# Raw JSON served by Pages for the Ask Worker (v3 S1). Kept for callers that
# want the default location; step_update_html derives its own from SITE_DIR at
# write time so redirecting SITE_DIR redirects the write too. A module constant
# frozen at import cannot be redirected, and that is how a test ended up
# overwriting the published endpoint.
SITE_DATA_JSON = os.path.join(SITE_DIR, "data", "website_data.json")
UPDATE_LOG = os.path.join(OUTPUT_DIR, "update_log.csv")

RUN_TS = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


_PIPELINE_WARNINGS = []


def _harvest_warnings(step_name, stdout):
    """Pull lines starting with WARNING: out of a step's stdout into the
    pipeline-wide warning list. Exposed via output/audit_warnings.json so
    CI can surface them in the step summary instead of letting them rot
    in auto_update.log. AUDIT.md follow-up #2."""
    if not stdout:
        return
    for line in stdout.split('\n'):
        stripped = line.strip()
        # Match the audit-emitted format: "WARNING: <message>" anywhere on the line.
        if 'WARNING:' in stripped:
            # Strip leading whitespace + any leading "WARNING:" prefix from the captured text
            idx = stripped.find('WARNING:')
            text = stripped[idx + len('WARNING:'):].strip()
            _PIPELINE_WARNINGS.append({'step': step_name, 'text': text})


# Per-stage subprocess timeout (seconds). The default suits the fast scrapers
# and data-prep steps. 04e's leave-one-out evaluation refits the model once per
# completed 2026 tournament, so its cost grows through the season; it gets a
# higher cap so a normal-season run does not trip the timeout (v3 O-series /
# audit/AUDIT_2026-07-25.md — the uniform 300s cap caused the 2026-07-22 miss).
# Lines a step emits that must reach the run log even when they fall outside the
# 20-line tail (v3 O6): grades, coverage, and the audit's own exclusion notices.
KEEP_LOG_RE = re.compile(
    r'^\s*(Grade:|Evaluated |Excluded |Display clamp:|LOO-refit |Accepted )')

DEFAULT_STEP_TIMEOUT = 300
STEP_TIMEOUT_OVERRIDES = {
    "04e_performance_data.py": 1200,
}


def _step_timeout(cmd):
    for token in cmd:
        for script, secs in STEP_TIMEOUT_OVERRIDES.items():
            if isinstance(token, str) and token.endswith(script):
                return secs
    return DEFAULT_STEP_TIMEOUT


def run_step(description, cmd, timeout=None):
    """Run a subprocess step, printing status and handling errors."""
    print(f"\n{'─'*60}")
    print(f"  STEP: {description}")
    print(f"{'─'*60}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout if timeout is not None else _step_timeout(cmd)
    )
    # Print stdout (last 20 lines to keep output manageable), plus any line the
    # step marked as worth keeping.
    #
    # v3 O6 (audit/AUDIT_2026-07-25.md): tailing 20 lines meant 04e's grade and
    # coverage summary — printed well before its per-tournament listing ends —
    # was absent from every recent run log, so the one number most worth
    # watching never reached CI output. Lines matching KEEP_LOG_RE are surfaced
    # regardless of where in the output they appeared.
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        tail = lines[-20:]
        highlights = [ln for ln in lines[:-20] if KEEP_LOG_RE.search(ln)]
        for line in highlights:
            print(f"  {line}")
        if highlights:
            print("  ---")
        for line in tail:
            print(f"  {line}")
    _harvest_warnings(description, result.stdout)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-500:]}" if result.stderr else "")
        raise RuntimeError(f"Step failed with exit code {result.returncode}: {description}")
    return result


def write_audit_warnings():
    """Write pipeline warnings to output/audit_warnings.json for CI consumption.
    AUDIT.md follow-up #2."""
    out_path = os.path.join(OUTPUT_DIR, "audit_warnings.json")
    payload = {
        'generated': RUN_TS,
        'count': len(_PIPELINE_WARNINGS),
        'warnings': _PIPELINE_WARNINGS,
    }
    with open(out_path, 'w') as f:
        json.dump(payload, f, indent=2)
    site_path = os.path.join(SITE_DIR, "audit_warnings.json")
    with open(site_path, 'w') as f:
        json.dump(payload, f, indent=2)
    if _PIPELINE_WARNINGS:
        print(f"\n  Captured {len(_PIPELINE_WARNINGS)} pipeline warning(s) → {out_path}")
        for w in _PIPELINE_WARNINGS:
            print(f"    [{w['step']}] {w['text'][:120]}")
    else:
        print(f"\n  No pipeline warnings captured → {out_path}")
    print("  Copied audit_warnings.json to docs/")


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
            _PIPELINE_WARNINGS.append({'step': 'CCA structure drift', 'text': d})
        if deviations:
            print(f"  {len(deviations)} deviation(s) — CCA markup may have changed; scrapers at risk.")
        else:
            print("  CCA structure OK.")
    except Exception as e:
        _PIPELINE_WARNINGS.append({'step': 'CCA structure drift', 'text': f'structure check errored: {e}'})
        print(f"  Structure check errored (non-blocking): {e}")


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


# A present-but-old all_registrations.csv silently freezes the tournament
# roster: 01_data_prep reconciles *existing* events' counts against the live
# scrape, but the set of tournaments only comes from the export. Anything that
# opened registration after the export date is invisible to the model and falls
# back to a flat historical-average estimate with no live daily chart (the
# June 2026 World Open U13 / Eastern incident: a 75-day-old export). Warn loudly
# past this age instead of degrading silently.
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
        msg = (f"all_registrations.csv export missing at {src} — tournament roster "
               f"is frozen; tournaments that opened registration since the last "
               f"export are invisible to the model and show a flat historical "
               f"average. Re-export from the CCA admin.")
        print(f"\n{'─'*60}")
        print("  STEP: Refresh tournament summary (export missing — reconcile-only)")
        print(f"{'─'*60}")
        print(f"  WARNING: {msg}")
        _PIPELINE_WARNINGS.append({'step': 'Refresh tournament summary', 'text': msg})
        from reconcile_final_counts import reconcile_final_counts
        reconcile_final_counts(OUTPUT_DIR)
        return
    export_date = datetime.fromtimestamp(os.path.getmtime(src))
    age_days = (datetime.now() - export_date).days
    if age_days >= EXPORT_STALE_WARN_DAYS:
        msg = (f"all_registrations.csv export is {age_days} days old "
               f"(dated {export_date.strftime('%Y-%m-%d')}). Tournaments that opened "
               f"registration after that date are absent from the roster and will "
               f"show a flat historical-average estimate with no live entry chart. "
               f"Re-export from the CCA admin to restore live forecasts.")
        print(f"\n  WARNING: {msg}")
        _PIPELINE_WARNINGS.append({'step': 'Refresh tournament summary', 'text': msg})
    run_step("Refresh tournament summary (01_data_prep.py)",
             [sys.executable, "01_data_prep.py"])


def step_walkin_multipliers():
    """Regenerate walk_in_family_stats.csv from historical_standings.csv.

    Without this step, the file is missing in production and apply_walkin_multiplier
    falls back to the global 'estimate' path for every tournament — silently
    degrading the per-family walk-in CI propagation. AUDIT.md A1.

    Idempotent: reads historical_standings.csv (updated by scrape_standings.py)
    and tournament_summary.csv (refreshed by step_data_prep). Skips if either
    input is missing.
    """
    standings = os.path.join(OUTPUT_DIR, "historical_standings.csv")
    summary = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
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

    if not os.path.exists(WEBSITE_JSON):
        raise RuntimeError(f"Model did not produce {WEBSITE_JSON}")

    with open(WEBSITE_JSON, 'r') as f:
        data = json.load(f)
    n_tournaments = len(data.get('tournaments', []))
    print(f"  Generated predictions for {n_tournaments} tournaments")


def step_data_health():
    """Scan the prediction output (website_data.json) for degraded tournament
    cards — frozen estimates, collapsed charts, misassembled daily curves,
    name/roster mismatches, alias mislabels, missing fees, etc. CRITICAL/HIGH
    findings print WARNING: lines that _harvest_warnings folds into
    audit_warnings.json (and the CI step summary).

    Runs with --strict (v3 Q1, audit/AUDIT_2026-07-25.md): the scanner exits 1
    on any CRITICAL finding and run_step aborts the pipeline. Before this, the
    scan was advisory-only, so the 2026-07-25 corrupted-curve incident was free
    to reach the published site. A CRITICAL here means the output is not fit to
    publish — better to serve yesterday's data behind a stale banner (the flag
    O1 now guarantees) than today's fabricated numbers."""
    run_step("Scan prediction data health (data_health.py)",
             [sys.executable, "data_health.py", "--strict"])


def step_update_html():
    """Splice the data consts into docs/data/site_data.js (externalized L15)."""
    if not os.path.exists(WEBSITE_JSON):
        raise RuntimeError(f"Missing {WEBSITE_JSON}")
    if not os.path.exists(SITE_DATA_JS):
        raise RuntimeError(f"Missing {SITE_DATA_JS}")

    with open(WEBSITE_JSON, 'r') as f:
        json_data = f.read().strip()

    with open(SITE_DATA_JS, 'r') as f:
        html = f.read()

    # Find and replace the TOURNAMENT_DATA block
    # Pattern: "const TOURNAMENT_DATA = {" ... "};" (the closing }; on its own line)
    start_marker = 'const TOURNAMENT_DATA = '
    start_idx = html.find(start_marker)
    if start_idx == -1:
        raise RuntimeError("Could not find 'const TOURNAMENT_DATA = ' in site_data.js")

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
        raise RuntimeError("Could not find end of TOURNAMENT_DATA block in site_data.js")

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
                print("  Updated PUZZLE_DATA in site_data.js")

    # Also embed CHESS_HISTORY if available.
    #
    # v3 O5 (audit/AUDIT_2026-07-25.md): no script in this repo writes
    # output/chess_history.json, so this splice has never fired in production —
    # the const in site_data.js is whatever was hand-authored there. Documented
    # as a deliberately manual artifact rather than left looking automated; if
    # the content ever needs to change, edit site_data.js directly or add a
    # generator that writes the JSON here.
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
                print("  Updated CHESS_HISTORY in site_data.js")

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
                print("  Updated PERFORMANCE_DATA in site_data.js")

    with open(SITE_DATA_JS, 'w') as f:
        f.write(new_html)

    print(f"  Updated TOURNAMENT_DATA in {SITE_DATA_JS}")

    # v3 S1: publish the raw JSON where GitHub Pages actually serves it. The
    # Ask Worker's DATA_URL pointed at /chess-prediction/website_data.json, which
    # 404s — Pages serves docs/, and the data lived only inside site_data.js as a
    # JS const the Worker cannot parse. Every /ask request therefore failed at
    # 502. Writing the JSON alongside site_data.js gives the Worker a real
    # endpoint without teaching it to scrape a JavaScript file.
    # Derived here rather than read from the module constant so that redirecting
    # SITE_DIR actually redirects this write. SITE_DATA_JSON is computed at
    # import from the real SITE_DIR, so a test that monkeypatches SITE_DIR still
    # wrote here — to the published file. tests/test_site_data_build.py did
    # exactly that, and left a two-tournament stub
    # ({"generated": "2026-07-07", ... "family": "X"}) sitting in
    # docs/data/website_data.json, which is the endpoint the Ask Worker fetches.
    # The file is untracked, so it would have been committed in that state.
    # Its own fixture comment warns about this class of bug; S1 reintroduced it
    # through a constant the fixture did not know to patch.
    site_data_json = os.path.join(SITE_DIR, "data", "website_data.json")
    with open(site_data_json, 'w') as f:
        f.write(json_data)
    print(f"  Wrote {site_data_json} (Ask Worker data endpoint)")

    _stamp_site_data_version(json_data)

    # Post-write verification: re-read and confirm embedded data matches source
    with open(SITE_DATA_JS, 'r') as f:
        verify_html = f.read()
    verify_idx = verify_html.find(start_marker)
    if verify_idx == -1:
        raise RuntimeError("Post-write verification failed: TOURNAMENT_DATA marker missing from written site_data.js")
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
    # G9: the app reads docs/data/site_data.js (L15 externalization); the old
    # docs/website_data.json double-ship (a 1.4MB daily-churn copy nothing
    # fetches) is gone. output/website_data.json remains the source of truth.


def prune_update_log(path=None, days=90):
    """Bound update_log.csv growth (G10): keep only rows from the last `days`
    of runs so the committed file and its git churn stay bounded. Rows with an
    unparseable timestamp are kept (fail-safe). Returns (kept, dropped)."""
    path = path or UPDATE_LOG
    if not os.path.exists(path):
        return (0, 0)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return (len(rows), 0)
    header, data = rows[0], rows[1:]
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    for r in data:
        try:
            ts = datetime.strptime(r[0][:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, IndexError):
            kept.append(r)
            continue
        if ts >= cutoff:
            kept.append(r)
    if len(kept) != len(data):
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(kept)
    return (len(kept), len(data) - len(kept))


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

    kept, dropped = prune_update_log()
    if dropped:
        print(f"  Pruned {dropped} update_log rows older than 90 days ({kept} kept)")
    print(f"  Logged {lines_logged} predictions to {UPDATE_LOG}")


def _stamp_site_data_version(json_data):
    """Point index.html + sw.js at a data-derived site_data.js query string.

    v3 P5. A hand-maintained `?v=40` only changes when someone edits the code,
    but this file's CONTENT changes every night. A returning visitor — and any
    installed PWA — could therefore keep serving yesterday's numbers from cache
    long after a corrected build shipped, which is exactly the population that
    saw the bad Bradley Open figures first. Deriving the query string from a
    hash of the data means every rebuild is a new URL and the cache cannot
    outlive its contents.
    """
    digest = hashlib.sha256(json_data.encode('utf-8')).hexdigest()[:10]
    pattern = re.compile(r'(site_data\.js\?v=)([A-Za-z0-9]+)')
    for path in (INDEX_HTML, os.path.join(SITE_DIR, "sw.js")):
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        new_text, n = pattern.subn(rf'\g<1>{digest}', text)
        if n and new_text != text:
            with open(path, 'w') as f:
                f.write(new_text)
            print(f"  Stamped site_data.js?v={digest} in {os.path.basename(path)}")
    return digest


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
    if not os.path.exists(WEBSITE_JSON):
        print(f"  WARNING: {WEBSITE_JSON} not found — cannot stamp stale flag")
        return

    with open(WEBSITE_JSON, 'r') as f:
        data = json.load(f)

    data['last_updated'] = RUN_TS
    data['is_stale'] = is_stale
    # A successful run clears any degraded marker left by a previous failure.
    if not is_stale:
        data.pop('pipeline_degraded', None)
        data.pop('degraded_reason', None)
        data.pop('degraded_at', None)

    _atomic_write_json(WEBSITE_JSON, data)

    flag = "STALE" if is_stale else "FRESH"
    print(f"  Stamped website_data.json — is_stale={is_stale} ({flag}), last_updated={RUN_TS}")


def mark_pipeline_degraded(reason, website_json=None):
    """Stamp the published data as stale after a mid-run pipeline failure.

    v3 O1 (audit/AUDIT_2026-07-25.md). The daily run regenerates
    website_data.json early (04d) and only stamps freshness late, so a crash in
    between leaves a half-built file on disk carrying the PREVIOUS run's
    `is_stale: false`. The site then presents whatever survived as current data.

    This marks the failure honestly:
      * is_stale = True and pipeline_degraded = True, so app.js's staleness gate
        fires and the banner renders;
      * degraded_reason records what failed, for the health dashboard;
      * last_updated is NOT advanced — the data genuinely is not from this run,
        and moving the timestamp would relabel stale numbers as fresh.

    Then re-splices site_data.js so the flag actually reaches the browser (the
    page reads site_data.js, not website_data.json).

    Returns True if the flag was written. Never raises on a missing file: this
    runs from an exception handler and must not mask the original failure.
    """
    path = website_json or WEBSITE_JSON
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found — cannot mark degraded state")
        return False

    with open(path, 'r') as f:
        data = json.load(f)

    data['is_stale'] = True
    data['pipeline_degraded'] = True
    data['degraded_reason'] = str(reason)[:300]
    data['degraded_at'] = RUN_TS

    _atomic_write_json(path, data)
    print(f"  Stamped DEGRADED — is_stale=True, reason={str(reason)[:120]}")

    # Push the flag through to the file the browser actually loads.
    try:
        step_update_html()
        print("  Re-spliced site_data.js with the degraded flag")
    except Exception as e:
        print(f"  WARNING: could not re-splice site_data.js: {e}")

    # Persist the warning trail even though the run is aborting.
    _PIPELINE_WARNINGS.append({
        'step': 'PIPELINE FAILURE',
        'text': f'Run aborted; serving last-known data behind a stale banner. Reason: {reason}',
    })
    try:
        write_audit_warnings()
    except Exception as e:
        print(f"  WARNING: could not write audit warnings: {e}")
    return True


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
            print("  STEP: Validate scraped data")
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
        # Read-only + non-blocking: findings surface via audit_warnings.json,
        # a scanner failure must never abort the daily run.
        try:
            step_data_health()
        except Exception as e:
            print(f"\n  Warning: Data-health scan failed (non-fatal): {e}")

        # Always update HTML so the stale flag gets embedded in the page
        step_update_html()
        step_log_run()

        # Generate SHA-256 checksums for all output CSVs
        print(f"\n{'─'*60}")
        print("  STEP: Generate output checksums")
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
        generate_health_html()

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
