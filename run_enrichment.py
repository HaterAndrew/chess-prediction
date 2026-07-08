"""Weekly enrichment scraper orchestrator (H4).

The fee / standings / historical scrapers run in a separate weekly workflow. Run
directly, their WARNING: lines only ever land in the GitHub Actions log and expire
with it. This wrapper streams each scraper (so live progress is still visible in
the Actions log) while harvesting its WARNING: lines through auto_update's warning
machinery and persisting them to output/audit_warnings.json + docs/, exactly like
the daily pipeline. Operators then see enrichment issues in the model-health tab,
not only in a buried run log.

Usage:
    python run_enrichment.py [fees|standings|historical|all]

Exit code is non-zero if any requested scraper failed, so the workflow still
surfaces a hard failure — but every scraper is attempted and its warnings are
persisted first.
"""
import os
import subprocess
import sys

import auto_update

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

SCRAPERS = {
    "fees": [sys.executable, "scrape_fees.py"],
    "standings": [sys.executable, "scrape_standings.py"],
    "historical": [sys.executable, "scrape_historical.py"],
}


def _run_streamed(name, cmd):
    """Run a scraper, streaming its output live while capturing it for warning
    harvest. Returns the exit code."""
    print(f"\n{'─' * 60}\n  ENRICHMENT: {name}\n{'─' * 60}", flush=True)
    proc = subprocess.Popen(
        cmd, cwd=PROJECT_DIR, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    captured = []
    for line in proc.stdout:
        print(line, end="")
        captured.append(line)
    proc.wait()
    auto_update._harvest_warnings(f"Enrichment: {name}", "".join(captured))
    return proc.returncode


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which != "all" and which not in SCRAPERS:
        print(f"Unknown scraper {which!r}; choose from {list(SCRAPERS)} or 'all'.")
        sys.exit(2)
    targets = SCRAPERS if which == "all" else {which: SCRAPERS[which]}

    failed = []
    for name, cmd in targets.items():
        try:
            rc = _run_streamed(name, cmd)
        except Exception as e:  # noqa: BLE001 - a scraper crash must not lose the others
            auto_update._PIPELINE_WARNINGS.append(
                {"step": f"Enrichment: {name}", "text": f"scraper errored: {e}"})
            failed.append(name)
            continue
        if rc != 0:
            auto_update._PIPELINE_WARNINGS.append(
                {"step": f"Enrichment: {name}", "text": f"scraper exited {rc}"})
            failed.append(name)

    auto_update.write_audit_warnings()

    if failed:
        print(f"\nEnrichment scrapers failed: {failed}")
        sys.exit(1)
    print("\nAll requested enrichment scrapers completed.")


if __name__ == "__main__":
    main()
