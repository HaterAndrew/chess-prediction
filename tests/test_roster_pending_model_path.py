"""v5 Cat R (audit/AUDIT_2026-07-30.md): roster-pending model-path admission.

The 04d filter that dropped every roster_pending row from the model card path
had no direct coverage — and it kept 13 of 14 live events on flat interim
estimates while the manual export sat 4 months stale. Admission logic lives in
pipeline_utils.roster_pending_model_ok because importing 04d executes its whole
pipeline at module level; 04d calls the same function.

Contract: a roster-pending row rides the model path when it is a live,
future event with a metadata start_date, has entries, and starts within the
longest horizon the walk-forward grades, where no stand-in route beats the
model (perf.route_evidence). Ended / reg-closed / post-start-window / empty /
far-off rows fall through to the metadata loop exactly as before.
"""
import pandas as pd

from perf.grading import T_POINTS
from pipeline_utils import roster_pending_model_ok
from shared.thresholds import GRADED_HORIZON

EVENT_DATE = pd.Timestamp("2026-12-26")


def test_live_future_paced_event_is_admitted():
    assert roster_pending_model_ok(150, 30, "live", EVENT_DATE)


def test_ended_event_is_not_admitted():
    # Settled events keep their settled_actual card from the metadata loop.
    assert not roster_pending_model_ok(206, 0, "complete", EVENT_DATE)


def test_reg_closed_event_is_not_admitted():
    assert not roster_pending_model_ok(206, 2, "in_progress", EVENT_DATE)


def test_post_start_window_is_not_admitted():
    # days_to_start == 0 with registration still open: the online-window path
    # is not exercised for roster-pending rows; metadata loop keeps the card.
    assert not roster_pending_model_ok(206, 0, "live", EVENT_DATE)


def test_missing_event_date_is_not_admitted():
    # The injected daily curve's T values anchor to metadata start_date;
    # without it there is no usable curve.
    assert not roster_pending_model_ok(150, 30, "live", None)


def test_entries_within_the_graded_horizon_take_the_model():
    # National Chess Congress on 2026-09-27: 32 entries, 61 days out, a slow
    # curve that failed the old pace gate.
    for count, days in [(32, 61), (1, 90), (9, 10), (50, 75)]:
        assert roster_pending_model_ok(count, days, "live", EVENT_DATE)
    for count, days in [(0, 30), (2, 91), (1000, 120)]:
        assert not roster_pending_model_ok(count, days, "live", EVENT_DATE)


def test_the_routing_horizon_is_the_longest_graded_one():
    assert GRADED_HORIZON == max(T_POINTS)


# ── step_data_prep parity: export-present runs keep skeleton rows ───────────
# 01_data_prep rebuilds tournament_summary.csv from the export alone, which
# drops the roster-pending skeletons reconcile_final_counts appended. The CI
# path (export missing) already runs reconcile; the workstation path (export
# present) must too, or the two environments publish structurally different
# summaries — 13 live events silently fell off the model path locally.

def test_step_data_prep_runs_reconcile_after_rebuild(monkeypatch, tmp_path):
    import os

    import auto_update
    import reconcile_final_counts as rfc_module

    export = tmp_path / "all_registrations.csv"
    export.write_text("registration_time,tournament_name\n")

    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path, "expanduser",
        lambda p: str(export) if "all_registrations" in p else real_expanduser(p),
    )

    # step_data_prep lives in pipeline.steps since P5 — patch the consumer's
    # run_step and the defining module's warning list, not the shim copies.
    import pipeline.steps
    import pipeline.warns

    calls = []
    monkeypatch.setattr(
        pipeline.steps, "run_step",
        lambda name, cmd, **kw: calls.append(("run_step", name)),
    )
    monkeypatch.setattr(
        rfc_module, "reconcile_final_counts",
        lambda *a, **kw: calls.append(("reconcile", a)),
    )
    monkeypatch.setattr(pipeline.warns, "_PIPELINE_WARNINGS", [])

    auto_update.step_data_prep()

    assert [c[0] for c in calls] == ["run_step", "reconcile"], (
        "export-present path must run 01_data_prep THEN reconcile_final_counts"
    )
