"""v5 Cat T (audit/AUDIT_2026-07-30.md): the CI validation gate and --strict.

Three silent bypasses, one shape: validate_all()'s only call site sat inside
the branch --skip-scrape skips, and CI always passes --skip-scrape — so the
gate the README documents never ran in production. data_health --strict's
abort was likewise wrapped in a blanket try/except. And a scrape-step failure
killed the CI job before auto_update ran at all, leaving the stale-stamp
branch unreachable.

Contract: _validate_and_count runs (and blocks) regardless of who scraped;
its warnings reach the audit-warnings payload; --scrape-failed parses and
forces the stale path; data_health's exit codes map 0/3/4 as documented; the
workflow YAML keeps the continue-on-error + --scrape-failed wiring.
"""
import os
from types import SimpleNamespace

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import auto_update  # noqa: E402
import data_health  # noqa: E402


# ── _validate_and_count ──────────────────────────────────────────────────────

class _FakeReport(SimpleNamespace):
    @property
    def passed(self):
        return not self.errors

    def summary(self):
        return "FAKE REPORT"


def test_validate_and_count_blocks_on_errors(monkeypatch):
    monkeypatch.setattr(auto_update, "validate_all",
                        lambda: _FakeReport(errors=["bad row"], warnings=[]))
    with pytest.raises(RuntimeError, match="Data validation failed"):
        auto_update._validate_and_count()


def test_validate_and_count_reports_and_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_update, "validate_all",
                        lambda: _FakeReport(errors=[], warnings=["eb missing"]))
    scrape = tmp_path / "daily_scrape.csv"
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    scrape.write_text(
        "date,tournament_name,entry_count\n"
        f"{today},2026 A Open,5\n{today},2026 B Open,7\n"
        "2020-01-01,2020 Old Open,3\n")
    monkeypatch.setattr(auto_update, "SCRAPE_CSV", str(scrape))
    monkeypatch.setattr(auto_update, "_PIPELINE_WARNINGS", [])

    errors, warnings, rows = auto_update._validate_and_count()
    assert (errors, warnings) == (0, 1)
    assert rows == 2  # today's rows only
    # The gate's warnings finally reach the payload channel
    assert auto_update._PIPELINE_WARNINGS == [
        {"step": "Validate scraped data", "text": "eb missing"}]


def test_scrape_failed_flag_exists():
    """--scrape-failed must stay parseable — the workflow passes it when the
    external scrape step fails under continue-on-error."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scrape-failed', action='store_true')
    args = parser.parse_args(['--skip-scrape', '--scrape-failed'])
    assert args.scrape_failed
    # and the real module accepts it: source-level check keeps this honest
    # without executing main()'s pipeline body.
    import inspect
    src = inspect.getsource(auto_update.main)
    assert "--scrape-failed" in src
    assert "scrape_ok = False" in src


# ── data_health exit-code mapping ────────────────────────────────────────────

class _Report(SimpleNamespace):
    def has_critical(self):
        return self.critical


@pytest.mark.parametrize("strict,critical,crashed,expected", [
    (True, True, False, 3),    # --strict + CRITICAL: abort the pipeline
    (True, False, False, 0),
    (False, True, False, 0),   # advisory mode never blocks
    (True, False, True, 4),    # scanner crash: loud but non-fatal
    (False, False, True, 4),
])
def test_data_health_exit_codes(strict, critical, crashed, expected):
    report = None if crashed else _Report(critical=critical)
    assert data_health.exit_code_for(report, strict, crashed=crashed) == expected


def test_step_data_health_raises_only_on_critical(monkeypatch, capsys):
    def fake_run_step(desc, cmd, timeout=None, check=True):
        return SimpleNamespace(returncode=fake_run_step.rc, stdout="", stderr="")

    # step_data_health lives in pipeline.steps since P5 and calls run_step
    # through its own namespace — patch the consumer module, not the shim.
    import pipeline.steps
    monkeypatch.setattr(pipeline.steps, "run_step", fake_run_step)
    fake_run_step.rc = 0
    auto_update.step_data_health()  # clean: no raise

    fake_run_step.rc = 4
    auto_update.step_data_health()  # scanner crash: warn, no raise
    assert "non-fatal" in capsys.readouterr().out

    fake_run_step.rc = 3
    with pytest.raises(RuntimeError, match="data-health CRITICAL"):
        auto_update.step_data_health()


# ── workflow wiring (string-level, the repo's non-Python artifact pattern) ──

def test_daily_workflow_keeps_degraded_scrape_wiring():
    path = os.path.join(PROJECT_ROOT, ".github", "workflows", "daily_update.yml")
    with open(path) as fh:
        yml = fh.read()
    assert "continue-on-error: true" in yml
    assert "--scrape-failed" in yml
    # a degraded run must not read as a recovery
    assert "success() && steps.scrape.outcome != 'failure'" in yml
    # and must still feed the failure issue
    assert "failure() || steps.scrape.outcome == 'failure'" in yml


def test_degraded_banner_stages_every_file_the_rebuild_touches():
    """2026-08-23: the degraded step staged three of the five files
    step_update_html rewrites. The published site then disagreed with itself —
    index.html asked for site_data.js?v=1282b8f5e6 while sw.js still precached
    ?v=adcba11d88, and docs/data/website_data.json (the Ask Worker endpoint)
    reported is_stale false under a page banner that said stale. The file left
    unstaged also broke `git pull --rebase` in the same step.
    """
    path = os.path.join(PROJECT_ROOT, ".github", "workflows", "daily_update.yml")
    with open(path) as fh:
        yml = fh.read()
    degraded = yml.split("Publish degraded-state banner on failure")[1]
    add_line = next(ln for ln in degraded.splitlines()
                    if ln.strip().startswith("git add "))
    for target in ("output/website_data.json", "docs/index.html", "docs/sw.js",
                   "docs/data/site_data.js", "docs/data/website_data.json"):
        assert target in add_line, f"degraded step must stage {target}"
