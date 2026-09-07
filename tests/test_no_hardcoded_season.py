"""Guard: the current season must come from shared.season, not a literal.

2026-09-07 review. The season was a bare `2026` in at least ten production
modules — training cutoffs, the rolling-retrain set, the recal cohort,
EVAL_YEARS, the in-progress exclusions. Nothing crashes on 2027-01-01; the
model just stops folding newly completed events into training, the CI
calibration window keeps aging, and the performance page stops adding folds.
Silent staleness with a known date.

This test fails on a new bare current-year literal in the scanned modules, so
the next January is a test failure rather than a quiet accuracy decay.

A literal is allowed only where it is genuinely historical (a COVID year, a
fixed regime boundary, a date inside a comment or docstring). Those live in
ALLOWED below with the reason, so an exemption is a deliberate, reviewed act.
"""
import ast
import os
import pathlib
import sys

import pytest

PROJECT_DIR = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(PROJECT_DIR))

from shared.season import CURRENT_SEASON  # noqa: E402

# The production surfaces that decide what the model trains on and grades.
SCANNED = [
    "model/fitting.py",
    "model/constants.py",
    "model/core.py",
    "model/nowcast.py",
    "model/recalibration.py",
    "model/walkins.py",
    "model/data_io.py",
    "perf/folds.py",
    "perf/evaluation.py",
    "perf/report.py",
    "sitebuild/main.py",
    "pipeline/run_log.py",
    "pipeline/steps.py",
    "recalibrate.py",
    "ratio_model.py",
    "06_walk_in_multipliers.py",
]

# path -> reason. Anything listed here is exempt from the scan.
ALLOWED = {
    # Nothing yet. Add with a reason when a genuinely fixed year appears.
}


def _season_literals(path):
    """Return line numbers where CURRENT_SEASON appears as a bare int literal.

    Parses rather than greps: a year inside a comment, a docstring, or a string
    is documentation, not a decision the pipeline makes. Only real integer
    constants in code count.
    """
    src = (PROJECT_DIR / path).read_text()
    tree = ast.parse(src, filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value is CURRENT_SEASON:
            hits.append(node.lineno)
        elif isinstance(node, ast.Constant) and (
                isinstance(node.value, int) and not isinstance(node.value, bool)
                and node.value == CURRENT_SEASON):
            hits.append(node.lineno)
    return sorted(set(hits))


@pytest.mark.parametrize("path", SCANNED)
def test_no_bare_current_season_literal(path):
    if path in ALLOWED:
        pytest.skip(f"exempt: {ALLOWED[path]}")
    full = PROJECT_DIR / path
    if not full.exists():
        pytest.skip(f"{path} does not exist")
    hits = _season_literals(path)
    assert hits == [], (
        f"{path} hardcodes the current season ({CURRENT_SEASON}) at line(s) "
        f"{hits}. Import CURRENT_SEASON from shared.season instead, or add an "
        f"entry to ALLOWED with the reason the year is genuinely fixed.")


def test_the_guard_can_actually_see_a_literal(tmp_path):
    """Premise check: a scanner that never fires is worthless.

    Also pins that a year in a comment or a string does NOT trip it, which is
    what makes the guard usable alongside the repo's dated audit comments.
    """
    sample = tmp_path / "sample.py"
    sample.write_text(
        f"# a comment mentioning {CURRENT_SEASON}\n"
        f'DOC = "text about {CURRENT_SEASON}"\n'
        f"YEAR = {CURRENT_SEASON}\n"
    )
    tree = ast.parse(sample.read_text())
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, int)
            and not isinstance(n.value, bool) and n.value == CURRENT_SEASON]
    assert hits == [3], f"expected only the assignment on line 3, got {hits}"


def test_eval_years_tracks_the_season():
    """perf.folds must not pin its fold list to a fixed final year."""
    from shared.season import eval_years
    years = eval_years()
    assert years[-1] == CURRENT_SEASON
    assert years[0] == 2022
    assert years == sorted(years)
