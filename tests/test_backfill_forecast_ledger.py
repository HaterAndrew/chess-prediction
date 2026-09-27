"""The backfill turns each committed website payload into ledger rows stamped
with that commit and the model hash of its own tree."""
import csv
import importlib.util
import json
import os
import subprocess

import pytest

from pipeline.ledger import LEDGER_FIELDS
from shared.model_version import model_hash

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "backfill_forecast_ledger", os.path.join(PROJECT_ROOT, "scripts", "backfill_forecast_ledger.py"))
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def _git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=env).stdout.decode().strip()


def _commit_run(repo, generated, cards, model_src=None, message="run"):
    (repo / "output").mkdir(exist_ok=True)
    (repo / "output" / "website_data.json").write_text(json.dumps(
        {"generated": generated, "last_updated": f"{generated} 06:00:00",
         "model": "N5v4_Final", "tournaments": cards}))
    if model_src is not None:
        (repo / "model").mkdir(exist_ok=True)
        (repo / "model" / "engine.py").write_text(model_src)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _card(family, count, point):
    return {"family": family, "year": 2026, "status": "live", "event_start": "2026-10-09",
            "current_count": count, "point_estimate": point, "ci_lower": point - 20,
            "ci_upper": point + 20}


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    return tmp_path


def test_each_committed_run_becomes_rows_stamped_with_its_commit_and_code(repo):
    first = _commit_run(repo, "2026-09-01", [_card("A", 10, 200), _card("B", 5, 100)], "K = 1\n")
    (repo / "README").write_text("unrelated\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    second = _commit_run(repo, "2026-09-02", [_card("A", 12, 205)], "K = 2\n")

    rows = backfill.backfill_rows(repo, "main")
    assert [(r["as_of_date"], r["family"]) for r in rows] == [
        ("2026-09-01", "A"), ("2026-09-01", "B"), ("2026-09-02", "A")]
    assert {r["origin"] for r in rows} == {"backfill"}
    assert rows[0]["code_commit"] == first[:12] and rows[2]["code_commit"] == second[:12]
    assert rows[0]["T"] == 38
    assert rows[0]["model_label"] == "N5v4_Final"
    assert rows[0]["model_hash"] != rows[2]["model_hash"], "a model change starts a new era"
    assert rows[2]["model_hash"] == model_hash(repo), "the tree hash equals the on-disk hash"


def test_the_written_file_carries_the_ledger_header(repo, tmp_path):
    _commit_run(repo, "2026-09-01", [_card("A", 10, 200)], "K = 1\n")
    out = tmp_path / "backfill.csv"
    assert backfill.main(["--repo", str(repo), "--ref", "main", "--out", str(out)]) == 0
    with open(out, newline="") as fh:
        lines = list(csv.reader(fh))
    assert lines[0] == LEDGER_FIELDS and len(lines) == 2


def test_model_sources_match_whole_paths_only():
    from shared.model_version import is_model_source
    assert is_model_source("model/core.py")
    assert not is_model_source("model/sub/core.py")
    assert is_model_source("ratio_model.py")
    assert not is_model_source("scripts/ratio_model.py")
    assert not is_model_source("model/notes.md")
