"""Walk-in multiplier application (04c 2332-2417, verbatim)."""

import os

import numpy as np

from model.constants import OUTPUT_DIR

def load_walkin_multipliers():
    """
    Load per-family walk-in multiplier stats from 06_walk_in_multipliers.py output.
    Returns dict: family -> {median_ratio, std_ratio, n_years, tournament_type}
    """
    import csv
    stats_csv = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
    if not os.path.exists(stats_csv):
        return {}

    multipliers = {}
    with open(stats_csv, "r") as f:
        for row in csv.DictReader(f):
            multipliers[row["family"]] = {
                "median_ratio": float(row["median_ratio"]),
                "std_ratio": float(row["std_ratio"]),
                "n_years": int(row["n_years"]),
                "tournament_type": row["tournament_type"],
                "min_ratio": float(row["min_ratio"]),
                "max_ratio": float(row["max_ratio"]),
            }
    return multipliers


# J3: shrink a family's measured walk-in ratio toward the conservative 1.1
# baseline by sample size — ratio = 1.1 + (median-1.1)*n/(n+k). A family with
# many years of standings<->prereg history approaches its measured ratio; a
# 1-2 year family stays near 1.1. Replaces the old flat min(median,1.1) cap,
# which threw away all real walk-in signal above 1.1x. The former
# DEFAULT_WALKIN_MULTIPLIERS type table was dead code (unknown families fall
# back to the flat 1.1 estimate in apply_walkin_multiplier).
WALKIN_SHRINK_K = 4


def apply_walkin_multiplier(prereg_point, prereg_low, prereg_high, family,
                            multipliers=None):
    """
    Apply walk-in multiplier to pre-registration prediction to get total entry estimate.

    Returns (total_point, total_low, total_high, multiplier_used, multiplier_source)
    where multiplier_source is 'family', 'type', or 'none'.
    """
    if multipliers is None:
        multipliers = load_walkin_multipliers()

    if prereg_point is None:
        return None, None, None, None, "none"

    # Apply walk-in multiplier: family-specific if available, otherwise global guesstimate
    if family in multipliers:
        m = multipliers[family]
        n_years = m.get("n_years", 0)
        shrink = n_years / (n_years + WALKIN_SHRINK_K)   # J3: trust measurement with more history
        ratio = 1.1 + (m["median_ratio"] - 1.1) * shrink
        std = m["std_ratio"]
        source = "family"
    else:
        # Global guesstimate based on 2023+ median, capped at 1.1x
        ratio = 1.1
        std = 0.0
        source = "estimate"

    # Propagate CI through multiplier uncertainty
    # Use lognormal convolution with t-distribution for small samples
    if std > 0:
        n_years = multipliers.get(family, {}).get("n_years", 0) if family in multipliers else 0
        if n_years >= 3:
            from scipy.stats import t as t_dist
            t_crit = t_dist.ppf(0.95, df=max(n_years - 1, 1))
        else:
            t_crit = 1.645  # fallback to normal z for type-level
        log_mu = np.log(ratio)
        log_sigma = np.log(1 + std / ratio)
        m_low = np.exp(log_mu - t_crit * log_sigma)
        m_high = np.exp(log_mu + t_crit * log_sigma)
    else:
        m_low = ratio
        m_high = ratio

    total_point = int(round(prereg_point * ratio))
    total_low = int(round(prereg_low * m_low))
    total_high = int(round(prereg_high * m_high))

    return total_point, total_low, total_high, ratio, source


