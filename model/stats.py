"""Trim stats, lognormal CI, ratio filtering (04c 432-577, verbatim).

_TRIM_STATS is mutated in place, never reassigned — the 04c shim re-export
must keep observing mutations (tests read it through the shim).
"""

import numpy as np
from scipy import stats

from collections import defaultdict as _defaultdict
_TRIM_STATS = {'total_in': 0, 'total_out': 0, 'by_label': _defaultdict(lambda: [0, 0])}


def reset_trim_stats():
    """Clear aggregated trim counters. Called at start of each fit."""
    _TRIM_STATS['total_in'] = 0
    _TRIM_STATS['total_out'] = 0
    _TRIM_STATS['by_label'].clear()


def trim_outliers(values, iqr_factor=3.0, label=None, count_stats=True):
    """Remove extreme outliers beyond iqr_factor * IQR from median.

    Optional `label` (e.g. family name) accumulates a per-label tally in
    _TRIM_STATS so callers can audit which families lose the most points.
    Set `count_stats=False` for internal calibration calls that may evaluate
    the same ratio list many times.
    AUDIT.md C7.
    """
    def _record(n_in, n_kept):
        if not count_stats:
            return
        if label is not None:
            _TRIM_STATS['by_label'][label][0] += n_in
            _TRIM_STATS['by_label'][label][1] += n_kept
        _TRIM_STATS['total_in'] += n_in
        _TRIM_STATS['total_out'] += n_kept

    if len(values) < 4:
        _record(len(values), len(values))
        return values
    arr = np.array(values)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        _record(len(values), len(values))
        return values
    lo = q1 - iqr_factor * iqr
    hi = q3 + iqr_factor * iqr
    trimmed = arr[(arr >= lo) & (arr <= hi)]
    result = trimmed if len(trimmed) >= 2 else values
    _record(len(values), len(result))
    return result


def report_trim_stats(top_n=5):
    """Return a dict summarizing trim activity, suitable for printing.

    AUDIT.md C7 — surfaces per-family trim rates so we know whether the
    IQR 3.0x threshold is silently dropping legitimate variation.
    """
    total_in = _TRIM_STATS['total_in']
    total_out = _TRIM_STATS['total_out']
    if total_in == 0:
        return {'total_in': 0, 'total_out': 0, 'pct_trimmed': 0.0, 'top_offenders': []}
    pct = (total_in - total_out) / total_in * 100
    # Top families by trim rate (require at least 5 input points to be meaningful)
    by_rate = []
    for label, (n_in, n_kept) in _TRIM_STATS['by_label'].items():
        dropped = n_in - n_kept
        if n_in >= 5 and dropped > 0:
            by_rate.append((label, dropped, n_in, dropped / n_in * 100))
    by_rate.sort(key=lambda x: -x[3])
    return {
        'total_in': total_in,
        'total_out': total_out,
        'pct_trimmed': round(pct, 2),
        'top_offenders': by_rate[:top_n],
    }


def lognormal_ci(ratio_values, level=0.80, global_sigma=None, label=None,
                 count_stats=True):
    """
    Fit a lognormal to ratio values, return (median, lower, upper).

    For n >= 15 (short lead times where lognormal is rejected), uses
    nonparametric quantiles directly. For smaller n, uses t-based
    prediction interval with empirical Bayes sigma shrinkage toward
    a global estimate.

    Optional `label` (e.g. family name) is forwarded to trim_outliers
    so the per-label trim audit (AUDIT.md C7) attributes correctly.
    `count_stats=False` lets calibration and prediction evaluate CIs without
    inflating the once-per-fit trim audit.
    """
    if len(ratio_values) < 2:
        med = ratio_values[0] if len(ratio_values) == 1 else 1.0
        return med, med * 0.7, med * 1.4

    arr = np.array(trim_outliers(ratio_values, label=label,
                                 count_stats=count_stats))
    n = len(arr)
    alpha = 1 - level

    # For large samples, use nonparametric quantiles (avoids lognormal assumption)
    if n >= 15:
        med = stats.hmean(arr)  # harmonic mean for ratios
        lo = np.percentile(arr, alpha / 2 * 100)
        hi = np.percentile(arr, (1 - alpha / 2) * 100)
        return med, lo, hi

    # Parametric path: t-based prediction interval on log scale
    log_r = np.log(arr)
    mu = np.mean(log_r)
    sigma = np.std(log_r, ddof=1)

    # Empirical Bayes shrinkage: pull family sigma toward global sigma
    # only when family sigma is unrealistically low (n <= 3). For well-
    # estimated families (n >= 4), trust the family-specific sigma.
    # Use shrinkage as a floor, not a blend — don't penalize tight families.
    if global_sigma is not None and global_sigma > 0 and n <= 3:
        k = 1  # shrinkage strength (reduced from 3 to tighten CIs)
        sigma = max(sigma, np.sqrt((n * sigma**2 + k * global_sigma**2) / (n + k)))

    t_val = stats.t.ppf(1 - alpha / 2, df=max(n - 1, 1))

    # Proper prediction interval SE: sqrt(1 + 1/n)
    pred_se = sigma * np.sqrt(1 + 1 / n)
    lo = np.exp(mu - t_val * pred_se)
    hi = np.exp(mu + t_val * pred_se)
    med = stats.hmean(arr)  # harmonic mean for ratios

    return med, lo, hi


def _filter_ratios(fam_ratios, exclude_tid):
    """Return fam_ratios with every entry belonging to exclude_tid removed.

    Ratio entries are (ratio, year, tid) tuples everywhere (family, global,
    and size-matched pools all carry the same shape). Used by recalibrate()'s
    per-record LOO (v5 Cat L): excluding the target tournament's own ratio is
    what makes a fit-cohort residual honest — with it included, an hmean over
    3-4 family ratios nearly reproduces the actual, and measured bias reads ~0
    against a real out-of-sample bias several times larger. Mirrors the LOO
    _calibrate() already does (r[2] != tid).

    Always returns a new dict; never mutates the input (which may be a live
    reference into self.ratios).
    """
    if exclude_tid is None:
        return fam_ratios
    return {T: [r for r in rats if r[2] != exclude_tid]
            for T, rats in fam_ratios.items()}

