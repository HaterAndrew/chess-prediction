"""Subprocess step runner + per-step timeouts (auto_update, verbatim)."""
import re
import subprocess

from pipeline import config, warns


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


def run_step(description, cmd, timeout=None, check=True):
    """Run a subprocess step, printing status and handling errors.

    check=False returns the CompletedProcess instead of raising on a non-zero
    exit, for callers that map specific exit codes to their own handling
    (v5 Cat T: step_data_health tells "CRITICAL finding" apart from "scanner
    crashed"). Stdout is tailed and harvested either way.
    """
    print(f"\n{'─'*60}")
    print(f"  STEP: {description}")
    print(f"{'─'*60}")
    result = subprocess.run(
        cmd,
        cwd=config.PROJECT_DIR,
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
    warns._harvest_warnings(description, result.stdout)
    if result.returncode != 0:
        print(f"  STDERR: {result.stderr[-500:]}" if result.stderr else "")
        if check:
            raise RuntimeError(f"Step failed with exit code {result.returncode}: {description}")
    return result
