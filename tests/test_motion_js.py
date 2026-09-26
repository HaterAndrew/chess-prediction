"""docs/motion.js: the house motion's pure maths.

The phone's sheet drag and view swipe (gestures.js) hand a finger's release
velocity to a spring and pick the resting point by projecting the momentum;
a wrong spring jumps or never settles, a wrong projection snaps the wrong
way. Runs tests/js/motion_driver.js under node and asserts on its JSON.
Skipped when node is unavailable, matching test_daily_series_js.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "motion_driver.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True, cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_a_critically_damped_spring_settles_without_overshoot(res):
    c = res["critical"]
    assert c["done"] and abs(c["final"] - 100) < 0.01
    assert c["max"] <= 100.01, f"critically damped spring overshot to {c['max']}"
    assert 0.2 < c["settledAt"] < 0.8, f"settled at {c['settledAt']}s for a 0.4 s response"


def test_an_underdamped_spring_overshoots_then_settles(res):
    b = res["bouncy"]
    assert b["max"] > 105, "damping 0.6 should overshoot"
    assert b["done"] and abs(b["final"] - 100) < 0.01


def test_retargeting_mid_flight_continues_from_the_live_value(res):
    r = res["retarget"]
    assert r["jump"] < 3, f"the value jumped {r['jump']}px on retarget"
    assert r["done"] and abs(r["final"]) < 0.01


def test_a_long_frame_is_substepped(res):
    s = res["substep"]
    assert s["diff"] < 0.5, s
    assert 0 < s["longFrames"] < 100


def test_momentum_projection_is_the_exponential_decay_form(res):
    p = res["project"]
    # (v / 1000) * rate / (1 - rate): 1000 px/s at 0.998 travels 499 px, at 0.99 travels 99 px.
    assert abs(p["atRate998"] - 499) < 0.01
    assert abs(p["atRate99"] - 99) < 0.01
    assert p["negative"] < 0 and p["zero"] == 0
    assert p["defaultRate"] == 0.998


def test_rubber_banding_resists_more_the_further_past_the_edge(res):
    r = res["rubber"]
    assert r["monotonic"]
    # The travel approaches the dimension itself; the constant sets the slope at the edge.
    assert all(v < 400 for v in r["samples"])
    assert r["samples"][-1] > 0.8 * 400, "far past the edge it approaches the dimension"
    assert abs(r["mirror"] + r["samples"][3]) < 1e-9, "symmetric in sign"
    assert 0.5 < r["small"] < 1, "near the edge it follows the finger almost 1:1"


def test_the_nearest_snap_point_wins(res):
    assert res["snap"] == {"a": 0, "b": 300, "c": 0}


def test_the_velocity_tracker_reads_the_last_hundred_milliseconds(res):
    t = res["tracker"]
    assert abs(t["moving"] - 625) < 1, t
    assert t["paused"] == 0
    assert t["single"] == 0


def test_the_designer_pair_maps_to_the_physics_pair(res):
    p = res["params"]
    omega = 2 * 3.141592653589793 / 0.4
    assert abs(p["stiffness"] - omega * omega) < 1e-6
    assert abs(p["damping"] - 2 * omega) < 1e-6
