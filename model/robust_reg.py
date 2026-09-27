"""The Huber regressions behind the model's regression leg, in one place.

Three copies fitted HuberRegressor(epsilon=1.35, max_iter=200) with the
model's warnings silenced, so a fit that stopped at the iteration cap was
indistinguishable from one that converged. This raises the cap and counts
the fits that still hit it, so the fit report can say so.
"""
import numpy as np
from sklearn.linear_model import HuberRegressor

MAX_ITER = 1000

_UNCONVERGED = []


def fit_huber(points, label=""):
    """Fit final ~ count + T on (count, T, final) points.

    Returns [slope_count, slope_T, intercept]. Raises whatever
    HuberRegressor raises, so each caller keeps its own fallback.
    """
    X = np.array([[p[0], p[1]] for p in points], dtype=float)
    y = np.array([p[2] for p in points], dtype=float)
    hub = HuberRegressor(epsilon=1.35, max_iter=MAX_ITER)
    hub.fit(X, y)
    if hub.n_iter_ >= MAX_ITER:
        _UNCONVERGED.append(label)
    return np.array([hub.coef_[0], hub.coef_[1], hub.intercept_])


def reset_unconverged():
    _UNCONVERGED.clear()


def unconverged():
    """Labels of the fits since the last reset that stopped at the cap."""
    return list(_UNCONVERGED)
