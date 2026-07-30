"""Model-wide constants (moved verbatim from 04c_final_model.py 2026-07-30).

Original module docstring (the T-coordinate contract) follows.

Phase 4C: Final production model with fixed CIs and website JSON output.

Root cause of the [320, 2450] CI problem:
- The 9.94 outlier ratio at T-60 for Chicago Open comes from the 2026 in-progress
  tournament. Its T values are relative to last_reg (today), not the event date.
  So "T=60" in the data actually means 60 days before today, when only 18 people
  had registered. The real T-60-before-event count is 179 (current total).
- Fix: exclude in-progress (2026) tournaments from ratio computation.

CI approach:
- Lognormal parametric CI on family-specific ratios (handles 4-5 data points well)
- LOO-calibrated scaling to hit ~80% coverage

T coordinate system:
- T is anchored to event_start (first day of tournament). T=0 means the
  tournament starts today; T=7 means the tournament is 7 days away.
- On-site registrations (during the event) are excluded from training data
  so the model predicts pre-registration count only. final_count still includes
  on-site entries, so ratios at T=0 implicitly capture the on-site multiplier.
- For prediction, pass days_to_start directly — no duration offset needed.
"""

from datetime import datetime

import numpy as np

# __file__-derived paths do not survive relocation into a package — the
# repo-level constant is the truth (shared/paths.py, decomposition P1).
from shared.paths import OUTPUT_DIR  # noqa: F401  (re-exported)
# Family aliases: single source of truth in tournament_aliases.py
from tournament_aliases import FAMILY_ALIASES  # noqa: F401  (re-exported)

CHOP_POINTS = [90, 60, 42, 28, 21, 14, 10, 7, 5, 3, 1]
T_GRID = np.arange(0, 121)
TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
# Default offset: days between event_start and last_reg for tournaments
# without metadata. Empirically, last_reg ≈ event_start + 2 (median across
# all CCA tournaments with both metadata and timestamp data).
DEFAULT_EVENT_START_OFFSET = 2

# Recalibration cohort rules (v3 T3 → v5 Cat L). Since v5, recalibrate()
# defaults to per-record leave-one-out: each residual is computed with the
# tournament's own ratio excluded (predict_nowcast _exclude_tid), so the whole
# cohort is honest and these two constants only govern the loo=False fallback:
# prefer genuinely held-out records; below RECAL_MIN_OOS_RECORDS fall back to
# the in-sample cohort and widen the derived CI scale by
# RECAL_IN_SAMPLE_WIDENING to offset training-set optimism. (The v3 preference
# was dead code in production — every caller passed a subset of the fit frame,
# so the cohort was always in-sample and both corrections were ~null.)
RECAL_MIN_OOS_RECORDS = 5
RECAL_IN_SAMPLE_WIDENING = 1.15
# v5 Cat L: minimum records from the target year (recalibrate regime_year)
# before the bias correction is fitted on that regime subset instead of the
# pooled multi-year mean (which dilutes a current-regime shift toward zero).
# Below this — or when the cohort predates the target year — the pooled path
# with its stationarity auto-refit applies.
RECAL_REGIME_MIN_N = 10

# Ceiling on the withdrawal-rate correction (v3 N4). Rates above this are capped,
# not discarded — the previous `if wd_rate < 0.15` turned the correction OFF for
# the high-withdrawal families that most needed it.
MAX_WITHDRAWAL_CORRECTION = 0.15

# Ratio-vs-regression divergence handling at long T (v3 N5). Beyond the
# threshold the blend eases toward the regression and the interval widens,
# rather than the ratio model being discarded outright at a hard step.
ENSEMBLE_DIVERGENCE_THRESHOLD = 0.5
ENSEMBLE_DIVERGENCE_WIDENING = 0.5
# Typical tournament length in days, used by get_event_info() to estimate a
# start date from an end-date proxy when metadata is absent. A weekend swiss
# runs ~3 days; majors carry real metadata so they never hit this fallback.
TYPICAL_DURATION = 3
