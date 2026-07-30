"""Corpus stats, gradeability, tournament evaluation, truth-label
freshness (04e, verbatim). assert_truth_label_freshness reads this
module's OUTPUT_DIR at call time -- tests patch perf.evaluation.
"""
import os

import pandas as pd

from pipeline_utils import apply_plausibility_clamp
from shared.paths import OUTPUT_DIR
# Calibration rationale for the 0.60 threshold lives with the constant
# (shared/thresholds.py); is_curve_gradeable is its consumer here.
from shared.thresholds import FROZEN_CURVE_MIN_RATIO  # noqa: F401
from shared.clock import today_ts

from perf.grading import T_POINTS

TODAY = today_ts()


def _corpus_stats():
    """Size of the full tournament corpus, for the public footer claim (v3 T10).

    Deliberately reads tournament_summary.csv rather than any filtered frame:
    the footer describes everything the project is built on, not the subset that
    survives the evaluation filters.
    """
    path = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
    if not os.path.exists(path):
        return {"n_corpus_tournaments": None, "n_entry_records": None}
    s = pd.read_csv(path)
    return {
        "n_corpus_tournaments": int(s["tid"].nunique()),
        "n_entry_records": int(s["final_count"].fillna(0).sum()),
    }


def _hist_lookup(train_summary):
    """{family: [final_count, ...]} over the training rows, for the display
    clamp the evaluator now mirrors (v3 T2). Excludes online and COVID editions
    for the same reason 04d does: they are not representative turnout."""
    pool = train_summary[
        (~train_summary['is_online'].fillna(False))
        & (~train_summary['is_covid'].fillna(False))
        & (train_summary['final_count'] > 0)
    ]
    return pool.groupby('family')['final_count'].apply(
        lambda s: [int(v) for v in s]).to_dict()


def is_curve_gradeable(tid_daily, final, min_ratio=FROZEN_CURVE_MIN_RATIO):
    """Can this tournament's daily curve be graded against its final count?

    v3 T1 (audit/AUDIT_2026-07-25.md). Grading compares a prediction made from
    `count_at_T` — read off the daily curve — against `final_count`. That is only
    a fair test when both numbers describe the same event. For events whose
    registration export went stale, the curve freezes at a fraction of the final
    while reconcile_final_counts bumps `final_count` up to the true scraped
    total. The model is then scored on the gap between two unrelated numbers.

    Two 2026 events sat in exactly this state — Chicago Class (curve ~0.32x its
    288 final) and Pittsburgh Open (~0.30x of 170) — each recording ~40% T-3
    errors that the model did not cause. They alone dragged the published
    headline grade from C to D.

    A curve peaking below `min_ratio` of the final is frozen or truncated, not a
    model miss, so it is excluded from grading. Returns (ok, peak_ratio).
    """
    if final is None or final <= 0 or len(tid_daily) == 0:
        return False, 0.0
    peak = float(tid_daily['cum_regs'].max())
    ratio = peak / float(final)
    return ratio >= min_ratio, ratio


def evaluate_tournaments(model, test_tournaments, daily, frozen_skipped=None,
                         hist_lookup=None):
    """Run blind test predictions for a set of tournaments.

    test_tournaments: list of dicts with family, tid, final_count, event_start
    frozen_skipped: optional list; receives (name, final, peak_ratio) for every
    tournament excluded by the frozen-curve gate so callers can report them.
    hist_lookup: optional {family: [prior final_counts]} from the training years
    only. When supplied, predictions run through the same plausibility clamp the
    website applies before display (v3 T2), so the published grade is the grade
    of the published forecast rather than of a raw model output no visitor sees.
    Leave it None to grade the unclamped model.

    Returns list of result dicts with predictions at each T-point.
    """
    results = []

    for tinfo in test_tournaments:
        family = tinfo['family']
        tid = tinfo['tid']
        final = tinfo['final_count']

        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) == 0:
            continue

        # v3 T1: refuse to grade a frozen/truncated curve against a bumped final.
        gradeable, peak_ratio = is_curve_gradeable(tid_daily, final)
        if not gradeable:
            if frozen_skipped is not None:
                frozen_skipped.append(
                    (tinfo.get('tournament_name', family), int(final), round(peak_ratio, 3)))
            continue

        t_predictions = {}
        for T in T_POINTS:
            available = tid_daily[
                (tid_daily['T'] >= T - 2) & (tid_daily['T'] <= T + 2)
            ].copy()
            if len(available) == 0:
                continue
            available['dist'] = (available['T'] - T).abs()
            closest = available.sort_values('dist').iloc[0]
            count_at_T = int(closest['cum_regs'])

            if count_at_T <= 0:
                continue

            point, ci_lo, ci_hi = model.predict_nowcast(count_at_T, T, family)
            if point is None:
                continue

            point = int(round(point))
            ci_lo = int(round(ci_lo))
            ci_hi = int(round(ci_hi))

            # v3 T2: grade what the site actually shows. 04d applies this clamp
            # (and the current_count floor) between the model and the page, so
            # grading the raw output measured a forecast no visitor ever saw.
            if hist_lookup is not None:
                point, ci_lo, ci_hi = apply_plausibility_clamp(
                    point, ci_lo, ci_hi,
                    current_count=count_at_T,
                    hist_counts=hist_lookup.get(family, []),
                    days_remaining=T)

            error_pct = round((point - final) / final * 100, 1)
            t_predictions[T] = {
                "T": T,
                "count_at_T": count_at_T,
                "predicted": point,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "error_pct": error_pct,
                "abs_error_pct": abs(error_pct),
                "in_ci": 1 if ci_lo <= final <= ci_hi else 0,
            }

        if not t_predictions:
            continue

        results.append({
            "family": family,
            "final_count": final,
            "event_start": tinfo['event_start'],
            "predictions": t_predictions,
        })

    return results


def format_results(tournament_results):
    """Convert predictions dict to sorted list for JSON output."""
    out = []
    for tr in tournament_results:
        preds_list = sorted(tr['predictions'].values(), key=lambda p: -p['T'])
        out.append({
            "family": tr['family'],
            "final_count": tr['final_count'],
            "event_start": tr['event_start'],
            "predictions": preds_list,
        })
    return out


def assert_truth_label_freshness(summary, tolerance=5):
    """Abort if daily_scrape recorded a higher entry_count than summary.final_count
    for an event that has already ended.

    Defense-in-depth: 01_data_prep.py reconciles these values, so this should
    never fire under normal operation. If it does, the snapshot pipeline is
    out of sync with the live scrape and the model would be graded against
    stale truth labels (the bug that produced ACO 2026 final=184 vs real 424).
    Tolerance absorbs small timing differences between snapshot and scrape.

    In-progress events are excluded — their summary.final_count is a moving
    snapshot, not truth, and naturally lags scrape_peak. The check uses
    tournament_metadata.end_date < today; events without metadata are
    conservatively excluded (treated as in-progress).
    """
    scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
    if not os.path.exists(scrape_path):
        return
    scrape = pd.read_csv(scrape_path)
    peak = (scrape.groupby('tournament_name')['entry_count']
                  .max().reset_index()
                  .rename(columns={'entry_count': 'scrape_peak'}))
    merged = summary.merge(peak, on='tournament_name', how='inner')

    meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    today = pd.Timestamp.now().normalize()
    if os.path.exists(meta_path):
        meta = pd.read_csv(meta_path)
        meta['end_date'] = pd.to_datetime(meta['end_date'], errors='coerce')
        meta_keys = meta[['family', 'year', 'end_date']].rename(
            columns={'year': 'tournament_year'})
        merged = merged.merge(meta_keys, on=['family', 'tournament_year'], how='left')
        completed = merged['end_date'].notna() & (merged['end_date'] < today)
        merged = merged[completed]

    stale = merged[merged['scrape_peak'] > merged['final_count'] + tolerance]
    if len(stale) > 0:
        lines = ["STALE TRUTH LABELS — refusing to grade against snapshot data."]
        lines.append("daily_scrape.csv recorded higher entry_count than tournament_summary.final_count for completed events:")
        for _, r in stale.iterrows():
            lines.append(f"  {r['tournament_name']:<55} summary={int(r['final_count']):>5}  scrape_peak={int(r['scrape_peak']):>5}  delta=+{int(r['scrape_peak'] - r['final_count'])}")
        lines.append("Re-run 01_data_prep.py to reconcile, then retry.")
        raise RuntimeError("\n".join(lines))
