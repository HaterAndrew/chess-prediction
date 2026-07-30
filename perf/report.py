"""Window-engine evaluation + performance_data.json assembly
(04e main() tail, verbatim).
"""
import json
import os
from importlib import import_module

import pandas as pd

from shared.clock import today_ts
from shared.paths import OUTPUT_DIR
from window_grading import grade_from_by_day, grade_window_engine

from perf.evaluation import (_corpus_stats, _hist_lookup,
                             format_results, is_curve_gradeable)
from perf.folds import EVAL_YEARS
from perf.grading import (_GRADE_ORDER, compute_aggregate,
                          compute_grade, grade_from_aggregate)

m04c = import_module("04c_final_model")

TODAY = today_ts()


def build_report(summary, year_results, all_tournament_results):
    cum_agg = compute_aggregate(all_tournament_results)
    cum_grade, cum_detail = grade_from_aggregate(cum_agg)

    # ── Second engine: the post-start online-registration window (v3 T7) ──
    # Reloads the daily table from disk deliberately. The `daily` in scope has
    # already been reanchored with during-event rows dropped, and the window
    # engine predicts from inside exactly those rows — grading it against this
    # frame would score it on data it never sees.
    print(f"\n{'─'*60}")
    print("  Evaluating the online-window engine (second engine)")
    print(f"{'─'*60}")
    raw_summary, raw_daily, raw_meta, _ = m04c.load_data()
    raw_meta['start_date'] = pd.to_datetime(raw_meta['start_date'], errors='coerce')
    raw_meta['end_date'] = pd.to_datetime(raw_meta['end_date'], errors='coerce')
    # Train on the frame 04d actually uses (online/COVID filtered only), score
    # on the evaluation frame (blitz and World Open sub-events dropped). Passing
    # the evaluation frame for both trains a ratio model production never runs —
    # it moved the window grade a full letter when I had it wired that way.
    window_train = raw_summary[
        (~raw_summary['is_online'].fillna(False))
        & (~raw_summary['is_covid'].fillna(False))
    ].copy()
    window_engine, _window_records = grade_window_engine(
        summary, raw_daily, raw_meta, EVAL_YEARS, _hist_lookup,
        gradeable_fn=is_curve_gradeable, train_summary=window_train)
    if window_engine.get('n'):
        w_grade, w_detail = grade_from_by_day(
            window_engine['by_day'], compute_grade, _GRADE_ORDER)
        window_engine['grade'] = w_grade
        window_engine['grade_detail'] = w_detail
        print(f"  Window engine grade: {w_grade} ({w_detail})")
        print(f"  Display clamp altered {window_engine['clamp_activations']} "
              f"of {window_engine['n']} window prediction(s)")
    else:
        window_engine['grade'] = 'N/A'
        window_engine['grade_detail'] = 'No gradeable window predictions'
        print("  Window engine: N/A — no gradeable window predictions")

    # ── Build output ──
    # Top-level fields use 2026 (YTD) for backward compatibility with bias correction
    ytd = year_results.get(2026, {})

    output = {
        "generated": TODAY.strftime('%Y-%m-%d'),
        "model": "N5v4_Final",
        # YTD (2026) — used by bias correction and existing code
        "n_tournaments": ytd.get('n_tournaments', 0),
        "grade": ytd.get('grade', 'N/A'),
        "grade_detail": ytd.get('grade_detail', ''),
        "aggregate": ytd.get('aggregate', []),
        "tournaments": ytd.get('tournaments', []),
        # v3 T10: the corpus size the About tab and footer quote. Sourced from
        # the data instead of the hardcoded "192K entry records across 778
        # tournaments", which had drifted from the real 781 / 194.5K.
        #
        # Read from the FULL summary on disk, not the `summary` frame in scope
        # here: that one is filtered for evaluation, which describes the graded
        # set rather than the corpus the footer is talking about. Counting
        # entries from `daily` would be wrong for the same reason — only 322 of
        # 781 editions carry a timestamped curve, so it would undercount by more
        # than half.
        **_corpus_stats(),
        # v3 T7: the second engine. Everything above grades predict_nowcast.
        # 04d also routes live multi-schedule events through the T=0 ratio +
        # window-decay chain, and until now that path was published ungraded —
        # a visitor reading the headline while a major was live was reading a
        # number computed from a different engine than the figure in front of
        # them. Kept as its own block, with its own horizon note, because the
        # two letters are not comparable.
        "window_engine": window_engine,
        # Multi-year breakdown
        "years": year_results,
        # Cumulative across all years
        "cumulative": {
            "n_tournaments": len(all_tournament_results),
            "grade": cum_grade,
            "grade_detail": cum_detail,
            "aggregate": cum_agg,
            "tournaments": format_results(all_tournament_results),
        },
    }

    out_path = os.path.join(OUTPUT_DIR, "performance_data.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Print overall summary
    print(f"\n{'='*60}")
    print("  MULTI-YEAR PERFORMANCE SUMMARY")
    print(f"{'='*60}")
    for yr in EVAL_YEARS:
        yr_data = year_results.get(yr, {})
        print(f"  {yr}: {yr_data.get('grade', 'N/A'):>3}  ({yr_data.get('n_tournaments', 0)} tournaments)")
    print(f"  {'─'*40}")
    print(f"  Cumulative: {cum_grade:>3}  ({len(all_tournament_results)} tournaments)")
    print(f"  {cum_detail}")
    print(f"\n  Output: {out_path}")
