"""The window-engine grade reads the daily curves as written.

grade_window_engine shifts the curves from last_reg to event start itself,
keeping the during-event rows the window route predicts from. The report
used to hand it curves the model's load_data() had already shifted, with
those rows dropped, so every curve moved twice: day 1 of the 2026
Atlantic City Open's window read 286 entries, its count three days before
the start, where the true figure was 411.
"""
import os

import pandas as pd
import pytest

from model.data_io import reanchor_daily_to_event_start
from perf import report


def test_raw_frames_are_the_files_as_written(tmp_output, monkeypatch):
    monkeypatch.setattr(report, "OUTPUT_DIR", tmp_output)
    summary, daily, meta = report.raw_frames()
    on_disk = pd.read_csv(os.path.join(tmp_output, "daily_registration_counts.csv"))
    pd.testing.assert_frame_equal(daily, on_disk)
    assert meta['start_date'].dtype.kind == 'M' and meta['end_date'].dtype.kind == 'M'


def test_shifting_twice_would_move_the_curves(tmp_output, monkeypatch):
    monkeypatch.setattr(report, "OUTPUT_DIR", tmp_output)
    summary, daily, meta = report.raw_frames()
    once = reanchor_daily_to_event_start(summary, daily.copy(), meta, keep_post_start=True)
    twice = reanchor_daily_to_event_start(
        summary, reanchor_daily_to_event_start(summary, daily.copy(), meta),
        meta, keep_post_start=True)
    assert not once.reset_index(drop=True).equals(twice.reset_index(drop=True))


class _Stop(Exception):
    pass


def test_build_report_grades_the_window_engine_on_raw_frames(monkeypatch):
    summary = pd.DataFrame({'is_online': [False], 'is_covid': [False]})
    frames = (summary, pd.DataFrame({'tid': [1], 'T': [0]}), pd.DataFrame())
    monkeypatch.setattr(report, "raw_frames", lambda: frames)
    seen = {}

    def capture(summary, daily_raw, meta, *args, **kwargs):
        seen['daily'], seen['meta'] = daily_raw, meta
        raise _Stop

    monkeypatch.setattr(report, "grade_window_engine", capture)
    with pytest.raises(_Stop):
        report.build_report(pd.DataFrame(), [])
    assert seen['daily'] is frames[1] and seen['meta'] is frames[2]
