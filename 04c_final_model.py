"""Compatibility shim — the implementation lives in model/ (2026-07-30
decomposition). Kept so importlib.import_module("04c_final_model") sites
(04d, 04e, window_grading, scripts/, 10 test files), m04c.<attr> reads, and
`python 04c_final_model.py` keep working unchanged.

Importing this module imports model.constants, which (for now) still applies
the historical module-level warnings filter — descoped in the next commit.
"""

from model.constants import (  # noqa: F401
    CHOP_POINTS,
    DEFAULT_EVENT_START_OFFSET,
    ENSEMBLE_DIVERGENCE_THRESHOLD,
    ENSEMBLE_DIVERGENCE_WIDENING,
    FAMILY_ALIASES,
    MAX_WITHDRAWAL_CORRECTION,
    OUTPUT_DIR,
    RECAL_IN_SAMPLE_WIDENING,
    RECAL_MIN_OOS_RECORDS,
    RECAL_REGIME_MIN_N,
    T_GRID,
    TODAY,
    TYPICAL_DURATION,
)
from model.ci_floors import (  # noqa: F401
    _predict_nowcast_ci_tail,
    apply_ci_floors,
)
from model.data_io import (  # noqa: F401
    build_enrichment_lookup,
    is_complete,
    load_data,
    load_meta_lookup,
    reanchor_daily_to_event_start,
)
from model.stats import (  # noqa: F401
    _TRIM_STATS,
    _filter_ratios,
    lognormal_ci,
    report_trim_stats,
    reset_trim_stats,
    trim_outliers,
)
from model.core import N5v4_Final  # noqa: F401
from model.curves import build_template_curves  # noqa: F401
from model.blind_test import run_blind_test  # noqa: F401
from model.legacy_site import (  # noqa: F401
    build_daily_data,
    build_reg_curve,
    build_website_json,
    determine_status,
    get_event_info,
    get_historical,
)
from model.demo import main  # noqa: F401
from model.walkins import (  # noqa: F401
    WALKIN_SHRINK_K,
    apply_walkin_multiplier,
    load_walkin_multipliers,
)

if __name__ == "__main__":
    main()
