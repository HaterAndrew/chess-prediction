"""Grade rubric + aggregation (04e, verbatim)."""
import numpy as np


# T-points to evaluate (days before event)
T_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]

# Grading rubric based on T-14 MAE% and CI coverage
GRADE_RUBRIC = [
    ("A+", 5, 85), ("A", 8, 75), ("A-", 10, 72),
    ("B+", 12, 68), ("B", 14, 65), ("B-", 16, 60),
    ("C+", 18, 55), ("C", 20, 50), ("C-", 22, 48),
    ("D", 25, 45), ("F", 999, 0),
]


def compute_grade(mae_pct, ci_coverage):
    """Assign letter grade from T-14 MAE% and CI coverage."""
    for grade, max_mae, min_cov in GRADE_RUBRIC:
        if mae_pct <= max_mae and ci_coverage >= min_cov:
            return grade
    return "F"


def compute_aggregate(tournament_results):
    """Compute aggregate metrics at each T-point from tournament results."""
    aggregate = []
    for T in T_POINTS:
        errors = []
        abs_errors = []
        ci_hits = []
        for tr in tournament_results:
            pred = tr['predictions'].get(T)
            if pred:
                errors.append(pred['error_pct'])
                abs_errors.append(pred['abs_error_pct'])
                ci_hits.append(pred['in_ci'])

        if not abs_errors:
            continue

        aggregate.append({
            "T": T,
            "n": len(abs_errors),
            "mae_pct": round(np.mean(abs_errors), 1),
            "median_ape_pct": round(np.median(abs_errors), 1),
            "ci_coverage": round(np.mean(ci_hits) * 100, 0),
            "bias_pct": round(np.mean(errors), 1),
        })
    return aggregate


_GRADE_ORDER = [g[0] for g in GRADE_RUBRIC]   # best -> worst


def grade_from_aggregate(aggregate):
    """J6: composite grade = the WORST letter across the planning horizons
    T-14 / T-7 / T-3, so the headline can't cherry-pick the model's T-14 sweet
    spot while hiding that near-event coverage collapses (T-3 ~56%, T-1 ~50%).
    Falls back to the nearest available horizon (labelled) when those are absent.
    """
    by_T = {a['T']: a for a in aggregate}
    graded = [(T, by_T[T]) for T in (14, 7, 3) if T in by_T]
    if graded:
        scored = [(compute_grade(a['mae_pct'], a['ci_coverage']), T, a) for T, a in graded]
        # worst = the grade furthest down the rubric
        grade, T, a = max(
            scored,
            key=lambda s: _GRADE_ORDER.index(s[0]) if s[0] in _GRADE_ORDER else len(_GRADE_ORDER),
        )
        detail = (f"worst of T-14/7/3 → T-{T}: MAE {a['mae_pct']}%, "
                  f"CI coverage {a['ci_coverage']}%")
        return grade, detail
    if aggregate:
        best = min(aggregate, key=lambda a: a['T'])
        grade = compute_grade(best['mae_pct'], best['ci_coverage'])
        return grade, (f"T-{best['T']} MAE: {best['mae_pct']}%, "
                       f"CI coverage: {best['ci_coverage']}% (fallback horizon)")
    return "N/A", "No data"
