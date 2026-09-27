"""Each published forecast carries its PIT for the calibration strip.

The Performance view draws one dot per tournament at the point its final
landed in the published 80% range (perf_calibration.js). Those per-event
values must be the ones the histogram bins (perf/scoring.py record_pit is the
shared guard), and a final exactly on a range end must stay in its bin, which
rounding broke (0.8999... to 0.9).
"""
import json
import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from perf.scoring import pit_value, record_pit  # noqa: E402

DATA = os.path.join(PROJECT_DIR, "output", "performance_data.json")


def test_record_pit_is_pit_value_behind_the_summarize_guard():
    assert record_pit(120, 100, 80, 130) == pytest.approx(pit_value(120, 100, 80, 130))
    for bad in [(None, 100, 80, 130), (120, 0, 80, 130), (120, 100, 0, 130),
                (120, 100, 90, 80), (120, 140, 80, 130)]:
        assert record_pit(*bad) is None, bad


def test_a_final_on_the_range_end_sits_at_the_end():
    assert record_pit(130, 100, 80, 130) == pytest.approx(0.9)
    assert record_pit(80, 100, 80, 130) == pytest.approx(0.1)


def _views(data):
    yield "all", data
    for year, view in (data.get("years") or {}).items():
        yield year, view
    if data.get("cumulative"):
        yield "cumulative", data["cumulative"]


def test_the_published_records_bin_to_the_published_histograms():
    with open(DATA) as f:
        data = json.load(f)
    checked = 0
    for name, view in _views(data):
        for agg in view.get("aggregate", []):
            hist = agg.get("pit")
            if not hist or not hist.get("n"):
                continue
            pits = [p["pit"] for t in view["tournaments"] for p in t["predictions"]
                    if p["T"] == agg["T"] and "pit" in p]
            assert all(0.0 <= v <= 1.0 for v in pits), (name, agg["T"])
            assert len(pits) == hist["n"], (name, agg["T"], len(pits), hist["n"])
            counts = np.histogram(np.clip(pits, 0, 1), bins=hist["bins"], range=(0, 1))[0].tolist()
            assert counts == hist["counts"], (name, agg["T"], counts, hist["counts"])
            checked += 1
    assert checked, "no histogram in the published data to check against"
