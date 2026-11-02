"""Changes to Python's CI/runtime setup must run the Python PR gate."""
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(path):
    # BaseLoader keeps GitHub's `on` key a string (YAML 1.1 calls it a bool).
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def _python_workflows():
    return [path.relative_to(ROOT).as_posix() for path in sorted(WORKFLOWS.glob("*.yml"))
            if any(step.get("uses", "").startswith("actions/setup-python@")
                   for job in _workflow(path)["jobs"].values()
                   for step in job.get("steps", []))]


@pytest.mark.parametrize("changed_path", [*_python_workflows(), ".github/workflows/new_python_runtime.yml"])
def test_python_runtime_workflow_changes_run_the_python_gate(changed_path):
    gate = _workflow(WORKFLOWS / "python_ci.yml")
    patterns = gate["on"]["pull_request"]["paths"]
    assert any(fnmatchcase(changed_path, pattern) for pattern in patterns), (
        f"{changed_path} changes Python runtime setup but does not trigger Python CI"
    )
