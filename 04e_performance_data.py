"""Compatibility shim -- implementation lives in perf/ (2026-07-30
decomposition). The filename is load-bearing: auto_update.run_step, the
nightly workflow, the golden harness, and STEP_TIMEOUT_OVERRIDES all key
on it.
"""

from shared.paths import OUTPUT_DIR  # noqa: F401
from shared.thresholds import (  # noqa: F401
    FROZEN_CURVE_MIN_RATIO,
    MIN_FINAL_COUNT,
)
from perf.grading import (  # noqa: F401
    GRADE_RUBRIC,
    T_POINTS,
    _GRADE_ORDER,
    compute_aggregate,
    compute_grade,
    grade_from_aggregate,
)
from perf.evaluation import (  # noqa: F401
    TODAY,
    _corpus_stats,
    _hist_lookup,
    assert_truth_label_freshness,
    evaluate_tournaments,
    format_results,
    is_curve_gradeable,
)
from perf.folds import EVAL_YEARS, prepare_folds, run_year_folds  # noqa: F401
from perf.report import build_report  # noqa: F401
from perf.main import main  # noqa: F401

if __name__ == "__main__":
    main()
