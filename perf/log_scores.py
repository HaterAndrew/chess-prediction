"""Scale-free scores: the absolute log error and the log interval score.

A 10-entry miss on a 50-player event and a 100-entry miss on a 1,000-player
event are the same miss; on the log scale they score the same. ALE is twice
the pinball loss of the median and LIS the interval score of the 80% range
(Gneiting and Raftery 2007), so together they are a proper score for the
published 10/50/90 quantiles: reporting the true quantiles does best in
expectation, and a wider range cannot buy a better score. Lower is better.
"""
import numpy as np

from perf.scoring import DEFAULT_ALPHA


def absolute_log_error(final, point):
    return np.abs(np.log(np.asarray(point, float)) - np.log(np.asarray(final, float)))


def log_interval_score(final, low, high, alpha=DEFAULT_ALPHA):
    """Width of the log range, plus 2/alpha times how far outside it the final fell."""
    y, lo, hi = (np.log(np.asarray(v, float)) for v in (final, low, high))
    if np.any(hi < lo):
        raise ValueError("a range has its high below its low")
    return (hi - lo) + (2.0 / alpha) * (np.maximum(lo - y, 0) + np.maximum(y - hi, 0))
