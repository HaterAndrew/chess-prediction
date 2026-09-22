"""Mode 1b, frozen-estimate (healthcheck/freeze.py).

The window is every run the card's current estimator produced, tonight's card
included. It fires only when the estimate never moved AND entries rose by a
material amount.
"""
from data_health import scan
from healthcheck import context
from pipeline import run_log
from tests.test_data_health import card, ctx

FROZEN = ("CRITICAL", "frozen-estimate")


def run(cards, last_updated=None, last_logged_run=None, **ctx_kw):
    data = {"generated": "2026-06-06", "tournaments": cards}
    if last_updated:
        data["last_updated"] = last_updated
    c = ctx(**ctx_kw)
    c.last_logged_run = last_logged_run
    report = scan(data, c)
    return {(f["severity"], f["mode"]) for f in report.findings}, report


def test_critical_frozen_main_path_estimate():
    keys, _ = run(
        [card(family="Frozen Open", point_estimate=110, current_count=33)],
        log_hist={("Frozen Open", 2026): [(110, 18, "model"), (110, 25, "model"),
                                          (110, 31, "model")]},
    )
    assert FROZEN in keys


def test_frozen_check_ignores_roster_pending():
    # roster-pending METADATA cards are EXPECTED to sit on the historical mean.
    keys, _ = run(
        [card(family="Pending Open", prediction_tier="roster-pending",
              prediction_source="metadata_historical_avg",
              point_estimate=110, current_count=33)],
        log_hist={("Pending Open", 2026): [(110, 18, "metadata_historical_avg"),
                                           (110, 25, "metadata_historical_avg"),
                                           (110, 31, "metadata_historical_avg")]},
    )
    assert FROZEN not in keys


def test_frozen_check_watches_model_served_roster_pending():
    # v5 Cat R: an admitted roster-pending card is model output and must move
    # nightly — freezing while entries climb is the World Open U13 shape.
    keys, _ = run(
        [card(family="Pending Open", prediction_tier="roster-pending",
              prediction_source="model", point_estimate=110, current_count=33)],
        log_hist={("Pending Open", 2026): [(110, 18, "model"), (110, 25, "model"),
                                           (110, 31, "model")]},
    )
    assert FROZEN in keys


# ── the freeze window belongs to one estimator (2026-08-23) ─────────────────
# Midwest Class Championships sat on the interim metadata mean of 313 for 97
# runs, which is what that estimator is supposed to do, then graduated to the
# model path. The scanner replayed all 97 interim runs against the model's
# first night, raised CRITICAL, and auto_update aborted the pipeline: the site
# served 08-22 data behind a degraded banner for a day over a card that was
# working as designed. An estimate is only frozen while ONE estimator owns it.


def test_freeze_window_resets_when_the_estimator_changes():
    interim = [(313, c, "metadata_historical_avg") for c in (5, 9, 12, 13)]
    keys, _ = run(
        [card(family="Graduated Open", prediction_tier="roster-pending",
              prediction_source="model", point_estimate=313, current_count=13,
              daily_data=[[0, 5], [1, 9], [2, 13]])],
        log_hist={("Graduated Open", 2026): interim + [(313, 13, "model")]},
    )
    assert FROZEN not in keys


def test_freeze_window_ignores_runs_logged_before_the_source_column():
    # Runs written before update_log.csv carried prediction_source cannot be
    # attributed to an estimator, so they count toward no card's freeze.
    legacy = [(110, c, None) for c in (18, 25, 31)]
    keys, _ = run(
        [card(family="Legacy Open", point_estimate=110, current_count=33)],
        log_hist={("Legacy Open", 2026): legacy + [(110, 33, "model")]},
    )
    assert FROZEN not in keys


def test_freeze_window_is_the_trailing_run_of_the_current_estimator():
    # A hand-back to the model re-arms after three of ITS runs; an older
    # stretch under the same name is not joined across the interruption.
    keys, _ = run(
        [card(family="Handback Open", point_estimate=110, current_count=33)],
        log_hist={("Handback Open", 2026): [(110, 18, "model"), (110, 25, "model"),
                                            (313, 28, "metadata_historical_avg"),
                                            (110, 31, "model")]},
    )
    assert FROZEN not in keys


def test_freeze_still_fires_on_three_runs_of_the_current_estimator():
    keys, _ = run(
        [card(family="Refrozen Open", point_estimate=110, current_count=33)],
        log_hist={("Refrozen Open", 2026): [(313, 12, "metadata_historical_avg"),
                                            (110, 18, "model"), (110, 25, "model"),
                                            (110, 31, "model")]},
    )
    assert FROZEN in keys


# ── tonight's card and the materiality gate (2026-09-22) ────────────────────
# The nightly aborted on Kings Island Open: 350 for three model runs while
# entries went 14 -> 14 -> 15 at T-55..T-53. The model was working (about one
# point per entry that far out) and tonight's card had already moved to 349,
# but the scan read only the log, and the abort kept tonight out of the log,
# so every later night would have aborted on the same three runs.

KINGS = "Kings Island Open"
KINGS_LOG = {(KINGS, 2026): [(350, 14, "model"), (350, 14, "model"),
                             (350, 15, "model")]}


def test_tonights_moved_estimate_ends_the_freeze():
    keys, _ = run([card(family=KINGS, point_estimate=349, current_count=15)],
                  log_hist=KINGS_LOG)
    assert FROZEN not in keys


def test_one_entry_rise_is_not_a_freeze():
    keys, _ = run([card(family=KINGS, point_estimate=350, current_count=15)],
                  log_hist=KINGS_LOG)
    assert FROZEN not in keys


def test_rise_below_the_fraction_gate_is_not_a_freeze():
    # 4 entries on 279 (1.4%): Midwest Class Championships, 2026-09-20.
    keys, _ = run(
        [card(family="Midwest Open", point_estimate=279, current_count=40)],
        log_hist={("Midwest Open", 2026): [(279, 36, "model"), (279, 38, "model")]},
    )
    assert FROZEN not in keys


def test_rise_below_the_entry_gate_is_not_a_freeze():
    # 2 entries on 40 is 5%, over the fraction gate, but under the entry gate.
    keys, _ = run(
        [card(family="Small Open", point_estimate=40, current_count=12)],
        log_hist={("Small Open", 2026): [(40, 10, "model"), (40, 11, "model")]},
    )
    assert FROZEN not in keys


def test_stuck_estimator_fires_once_the_rise_is_material():
    # +1 a night on 110: silent while the rise is small, loud once it clears
    # both gates (3 entries and 2%).
    creeping = [(110, c, "model") for c in (18, 19)]
    keys, _ = run([card(family="Creep Open", point_estimate=110, current_count=20)],
                  log_hist={("Creep Open", 2026): creeping})
    assert FROZEN not in keys
    keys, _ = run([card(family="Creep Open", point_estimate=110, current_count=21)],
                  log_hist={("Creep Open", 2026): creeping + [(110, 20, "model")]})
    assert FROZEN in keys


def test_tonight_already_logged_is_not_counted_twice():
    # A scan run after step_log_run: tonight is the log's last row. Counting it
    # again would turn two real runs into a three-run window.
    log = {("Twice Open", 2026): [(110, 18, "model"), (110, 31, "model")]}
    stamp = "2026-09-22 06:16:33"
    keys, _ = run([card(family="Twice Open", point_estimate=110, current_count=31)],
                  last_updated=stamp, last_logged_run=stamp, log_hist=log)
    assert FROZEN not in keys
    keys, _ = run([card(family="Twice Open", point_estimate=110, current_count=31)],
                  last_updated=stamp, last_logged_run="2026-09-21 06:23:27",
                  log_hist=log)
    assert FROZEN in keys


def test_last_run_timestamp_is_the_newest_logged_run(tmp_path):
    log = tmp_path / "update_log.csv"
    log.write_text(
        ",".join(run_log.LOG_FIELDS) + "\n"
        "2026-09-20 06:19:32,Kings Island Open,live,14,350,266,460,54,model,2026\n"
        "2026-09-21 06:23:27,Kings Island Open,live,15,350,324,377,53,model,2026\n")
    assert context.load_last_run_timestamp(str(log)) == "2026-09-21 06:23:27"
    assert context.load_last_run_timestamp(str(tmp_path / "absent.csv")) is None
