"""Protected Season figures distinguish recorded receipts from projections."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_expected_and_actual_receipts_browser_consumers():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node not available')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, str(root / 'tests/js/entry_value_driver.js')],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert all(json.loads(result.stdout).values())
