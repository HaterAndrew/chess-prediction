"""Grade rubric + aggregation (04e, verbatim) + proper scoring rules."""
import numpy as np

from perf.scoring import summarize


# Naive point forecasts published beside the model so "MAE 9.9%" has something
# to be measured against (2026-09-07 review). Keys match the fields
# perf.evaluation attaches to each prediction record.
BASELINES = ("baseline_last_year", "baseline_ratio")

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
    """Compute aggregate metrics at each T-point from tournament results.

    MAE and coverage stay exactly as they were, so the published history remains
    comparable. The interval score and PIT block are added alongside them
    (2026-09-07 review): MAE plus coverage is gameable in one direction, since
    widening every interval raises coverage and leaves MAE untouched, so it
    cannot distinguish a well-calibrated interval from a merely large one.
    """
    aggregate = []
    for T in T_POINTS:
        baseline_scored = {name: [] for name in BASELINES}
        errors = []
        abs_errors = []
        ci_hits = []
        scored = []          # records for the proper scoring rules
        for tr in tournament_results:
            pred = tr['predictions'].get(T)
            if pred:
                errors.append(pred['error_pct'])
                abs_errors.append(pred['abs_error_pct'])
                ci_hits.append(pred['in_ci'])
                scored.append({
                    "actual": tr.get('final_count'),
                    "point": pred.get('predicted'),
                    "lo": pred.get('ci_lower'),
                    "hi": pred.get('ci_upper'),
                })
                for name in BASELINES:
                    bp = pred.get(name)
                    if bp:
                        baseline_scored[name].append(
                            {"actual": tr.get('final_count'), "point": bp})

        if not abs_errors:
            continue

        row = {
            "T": T,
            "n": len(abs_errors),
            "mae_pct": round(np.mean(abs_errors), 1),
            "median_ape_pct": round(np.median(abs_errors), 1),
            "ci_coverage": round(np.mean(ci_hits) * 100, 0),
            "bias_pct": round(np.mean(errors), 1),
        }
        scores = summarize(scored)
        if scores:
            row["interval_score_pct"] = scores["interval_score_pct"]
            row["pit"] = scores["pit"]
        # Naive baselines at the same horizon. Point forecasts only, so they
        # report MAE and nothing that would let them look good by skipping the
        # interval-width charge.
        bl = {}
        for name, recs in baseline_scored.items():
            bs = summarize(recs)
            if bs:
                bl[name] = {"n": bs["n"], "mae_pct": bs["mae_pct"],
                            "median_ape_pct": bs["median_ape_pct"]}
        if bl:
            row["baselines"] = bl
        aggregate.append(row)
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
