"""Mode 1b, frozen-estimate: a main-path live card that sits on one estimate
across runs while its entries climb (the World Open U13 shape).

Split out of healthcheck/checks.py (2026-09-22) when the rule gained its
materiality gate and started reading tonight's card.
"""
from healthcheck.context import _canon

# A rise in entries has to be this large before an unmoved estimate counts as
# frozen. Both gates apply.
#
# Measured before being set, not guessed. The run log from 2026-03-23 to
# 2026-09-21 holds 91 sliding 3-run windows of model-served live cards whose
# entries rose. 6 of them kept an identical estimate while working as designed:
# Kings Island Open, Los Angeles Open x3 and Midwest Class Championships x2.
# The largest of those rises was 4 entries, or 1.4% of the estimate (Midwest,
# 279, T-19). Far from the event the model leans on last year's final (0.6
# anchor weight beyond T-28), so one new entry moves it about one point, and a
# day of lead time moves it back about half a point. The 2026-09-22 nightly
# aborted on exactly that: Kings Island Open at 350 for three runs while
# entries went 14 -> 15.
#
# The gates sit above every observed benign window and far below the
# regression fixtures (13 entries on an estimate of 110, 12%). A truly stuck
# estimator still fires: its window is every run since it took the card, so
# the rise keeps growing until it clears both gates. Re-measure before moving
# them.
FROZEN_MIN_RISE_ENTRIES = 3
FROZEN_MIN_RISE_FRAC = 0.02

# Fewest runs, tonight's card included, that can show a freeze.
FROZEN_MIN_RUNS = 3


def _is_roster_pending(t):
    return t.get("prediction_tier") == "roster-pending"


def _is_main_path(t):
    # v5 Cat R: roster-pending cards served by the MODEL are live predictions
    # and must move nightly — watch them like any main-path card. Only the
    # metadata_* interim cards keep the frozen-estimate exemption (those are
    # expected to sit still between metadata refreshes).
    if t.get("status") not in ("live", "complete"):
        return False
    return not _is_roster_pending(t) or t.get("prediction_source") == "model"


def _edition(t):
    """(canon_family, year): the identity a card shares with its scrape rows
    and its logged runs. The family alone stops being unique once next season's
    card opens beside this season's."""
    return _canon(t.get("family", "")), t.get("year")


def _current_estimator_runs(seq, source):
    """The trailing logged runs the card's CURRENT estimator produced.

    An estimate counts as frozen only while one estimator owns it. Midwest
    Class Championships (2026-08-23) sat on the interim metadata mean of 313
    for 97 runs — the behaviour that estimator is designed for — then graduated
    to the model path, and replaying those runs against the model's first night
    aborted the pipeline. Runs with no logged estimator predate the
    update_log.csv column and are attributable to nobody, so they end the
    window too.
    """
    if not source:
        return []
    window = []
    for run in reversed(seq):
        if run[2] != source:
            break
        window.append(run)
    window.reverse()
    return window


def _with_tonight(seq, t, data, ctx):
    """The logged runs plus tonight's card, the run about to be published.

    The scan runs before step_log_run, and an abort skips step_log_run, so the
    log alone never shows tonight. Reading only the log, a CRITICAL repeated
    every night on the same stale runs even after the estimate had moved: on
    2026-09-22 Kings Island Open had already moved to 349. A scan made after
    step_log_run finds tonight in the log already, so the card is not added
    twice.
    """
    tonight = data.get("last_updated")
    if tonight and tonight == getattr(ctx, "last_logged_run", None):
        return list(seq)
    return list(seq) + [(t.get("point_estimate"), t.get("current_count"),
                         t.get("prediction_source"))]


def _is_material_rise(rise, estimate):
    if not isinstance(estimate, (int, float)) or estimate <= 0:
        return rise >= FROZEN_MIN_RISE_ENTRIES
    return (rise >= FROZEN_MIN_RISE_ENTRIES
            and rise / estimate >= FROZEN_MIN_RISE_FRAC)


def frozen_estimate_findings(data, ctx, live_complete, report):
    """Mode 1b: covers model-served cards, including admitted roster-pending
    ones (v5 Cat R). Only metadata_* interim cards are expected to sit still
    between metadata refreshes."""
    for t in live_complete:
        if t.get("status") != "live" or not _is_main_path(t):
            continue
        seq = _with_tonight(ctx.log_hist.get(_edition(t), []), t, data, ctx)
        window = _current_estimator_runs(seq, t.get("prediction_source"))
        if len(window) < FROZEN_MIN_RUNS:
            continue
        ests = {run[0] for run in window}
        if len(ests) != 1:
            continue
        counts = [run[1] for run in window if isinstance(run[1], int)]
        if not counts:
            continue
        estimate = next(iter(ests))
        rise = max(counts) - min(counts)
        if not _is_material_rise(rise, estimate):
            continue
        report.add("CRITICAL", "frozen-estimate", t.get("family", "?"),
                   f"estimate stuck at {estimate} across {len(window)} "
                   f"{t.get('prediction_source')} runs "
                   f"while entries rose {min(counts)}->{max(counts)}")
