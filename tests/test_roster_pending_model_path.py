"""v5 Cat R (audit/AUDIT_2026-07-30.md): roster-pending model-path admission.

The 04d filter that dropped every roster_pending row from the model card path
had no direct coverage — and it kept 13 of 14 live events on flat interim
estimates while the manual export sat 4 months stale. Admission logic lives in
pipeline_utils.roster_pending_model_ok because importing 04d executes its whole
pipeline at module level; 04d calls the same function.

Contract: a roster-pending row rides the model path only when it is a live,
future event with a metadata start_date AND pace_gate_ok passes — the same
threshold the interim metadata_pace path uses, so the model path and the
fallback flip at the same point. Ended / reg-closed / post-start-window /
unpaced rows fall through to the metadata loop exactly as before.
"""
import pandas as pd

from pipeline_utils import pace_gate_ok, roster_pending_model_ok

FAST_CURVE = {90: 0.06, 42: 0.30, 14: 0.75, 0: 1.0}
SLOW_CURVE = {120: 0.005, 90: 0.012, 75: 0.019, 42: 0.10, 14: 0.55, 0: 1.0}
EVENT_DATE = pd.Timestamp("2026-12-26")


def test_live_future_paced_event_is_admitted():
    assert roster_pending_model_ok(150, 30, "live", EVENT_DATE, FAST_CURVE)


def test_ended_event_is_not_admitted():
    # Settled events keep their settled_actual card from the metadata loop.
    assert not roster_pending_model_ok(206, 0, "complete", EVENT_DATE, FAST_CURVE)


def test_reg_closed_event_is_not_admitted():
    assert not roster_pending_model_ok(206, 2, "in_progress", EVENT_DATE, FAST_CURVE)


def test_post_start_window_is_not_admitted():
    # days_to_start == 0 with registration still open: the online-window path
    # is not exercised for roster-pending rows; metadata loop keeps the card.
    assert not roster_pending_model_ok(206, 0, "live", EVENT_DATE, FAST_CURVE)


def test_missing_event_date_is_not_admitted():
    # The injected daily curve's T values anchor to metadata start_date;
    # without it there is no usable curve.
    assert not roster_pending_model_ok(150, 30, "live", None, FAST_CURVE)


def test_pace_gate_parity_with_interim_path():
    # The admission threshold IS pace_gate_ok: wherever the interim path would
    # refuse to extrapolate, the model path refuses to admit.
    for count, days, curve in [
        (9, 10, FAST_CURVE),      # under 10 registrations
        (50, 75, SLOW_CURVE),     # 46-90d, curve share is noise
        (1000, 91, FAST_CURVE),   # beyond 90 days
        (50, 60, {}),             # unknown curve in the extension band
    ]:
        assert not pace_gate_ok(count, days, curve)
        assert not roster_pending_model_ok(count, days, "live", EVENT_DATE, curve)
    for count, days, curve in [
        (10, 45, {}),             # legacy 45-day gate
        (10, 60, FAST_CURVE),     # extension where curve carries signal
    ]:
        assert pace_gate_ok(count, days, curve)
        assert roster_pending_model_ok(count, days, "live", EVENT_DATE, curve)


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
