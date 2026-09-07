"""One place to answer "which season is the model predicting?".

2026-09-07 review: the current season was a bare `2026` literal in at least ten
production modules — the training cutoff in model.fitting, the rolling-retrain
set and recal cohort in sitebuild.main, EVAL_YEARS and the LOO branch in
perf.folds, the completed-event selection in recalibrate, the in-progress
exclusion in 06_walk_in_multipliers, ratio_model's cutoff, update_metadata's
generation window, merge_fees, and pipeline.run_log's filter.

Nothing crashes on 2027-01-01. The model simply stops folding newly completed
events into training, the CI calibration window keeps aging, the performance
page stops adding folds, and the bias correction stays fitted on the 2026 regime
while predicting 2027. Silent staleness with a known date, which is the worst
shape a data bug can take.

A CCA season is a calendar year, so the season is just the current year. The
value is frozen at import, matching shared.clock's deliberate freeze-at-import
semantics: the pipeline compares it against row years throughout a run, and a
run that straddles midnight on New Year's Eve must not change its mind halfway.

Tests and backfills override it with CHESS_PREDICTION_SEASON.
"""

import os
from datetime import date

_ENV_VAR = "CHESS_PREDICTION_SEASON"


def current_season() -> int:
    """The season the pipeline is predicting, read live.

    Honours CHESS_PREDICTION_SEASON so a test or a rerun of a past season does
    not have to monkeypatch every consumer. An unparseable value is a
    configuration error and raises rather than silently falling back to the
    clock: a typo'd override that quietly predicted the wrong year would be
    exactly the failure this module exists to prevent.
    """
    raw = os.environ.get(_ENV_VAR)
    if raw is None or raw.strip() == "":
        return date.today().year
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(
            f"{_ENV_VAR}={raw!r} is not an integer year") from e


# Frozen at import for the same reason shared.clock freezes TODAY: consumers
# hold `from shared.season import CURRENT_SEASON` at module top and compare it
# against row years all through a run.
CURRENT_SEASON = current_season()

# The first season the model is allowed to train on as "completed history".
# Everything strictly before CURRENT_SEASON is settled; the current season only
# contributes the editions that have actually finished (the completed_tids
# rolling-retrain path).
TRAINING_CUTOFF = CURRENT_SEASON


def is_current_season(year) -> bool:
    """True when `year` is the season being predicted. Tolerates None/NaN/str."""
    if year is None:
        return False
    try:
        return int(year) == CURRENT_SEASON
    except (TypeError, ValueError):
        return False


def eval_years(first=2022, last=None):
    """Expanding-window fold years, inclusive of the current season.

    perf.folds hardcoded [2022, 2023, 2024, 2025, 2026], so the performance page
    would have stopped adding folds the moment the season rolled over.
    """
    end = CURRENT_SEASON if last is None else int(last)
    return list(range(int(first), end + 1))
