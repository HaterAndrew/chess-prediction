"""Uncertainty for the walk-forward's numbers.

Events of one family move together across seasons, so the standard errors
come from a family-block bootstrap: resample whole families with
replacement, recompute the mean. Seeded, so the published figures repeat.
"""
import numpy as np
from scipy import stats

BOOTSTRAP_DRAWS = 2000
SEED = 20260927


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n, in percent."""
    if n == 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(float((centre - half) * 100), 1), round(float((centre + half) * 100), 1)


def median_ci(values, level=0.95):
    """Distribution-free interval for the median from order statistics."""
    x = np.sort(np.asarray(values, float))
    n = len(x)
    if n == 0:
        return None, None
    lo = int(stats.binom.ppf((1 - level) / 2, n, 0.5))
    hi = int(stats.binom.isf((1 - level) / 2, n, 0.5))
    return float(x[max(lo - 1, 0)]), float(x[min(hi, n - 1)])


def family_weights(n_families, draws=BOOTSTRAP_DRAWS, seed=SEED):
    """How many times each family appears in each bootstrap draw."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_families, np.full(n_families, 1 / n_families), size=draws)


def block_se(values, families, weights=None):
    """Standard error of the mean of `values`, resampling whole families."""
    values = np.asarray(values, float)
    codes, uniques = _codes(families)
    if len(values) < 2 or len(uniques) < 2:
        return None
    sums = np.bincount(codes, weights=values, minlength=len(uniques))
    counts = np.bincount(codes, minlength=len(uniques)).astype(float)
    w = family_weights(len(uniques)) if weights is None else weights
    means = (w @ sums) / np.maximum(w @ counts, 1)
    return float(means.std(ddof=1))


def _codes(labels):
    uniques, codes = np.unique(np.asarray(labels, dtype=str), return_inverse=True)
    return codes, uniques
