"""Grade the post-start online-registration window engine (audit v3 T7).

THE GAP THIS CLOSES

The site publishes one accuracy grade, and until now that grade described one
prediction engine. predict_nowcast produces most of the numbers on the page and
is backtested every run. It is not the only engine. When a CCA major has started
its 5-day schedule but online entries are still arriving for the 4/3/2-day
schedules, 04d switches to a different path entirely: the T=0 ratio bucket from
predict_with_lognormal_ci, geometrically decayed toward the live count as
registration close approaches (04d_website_data_v2.py, prediction_source
'model_online_window').

That path had never been graded. The published grade covered it by implication
only, which meant a visitor reading "C+" during exactly the window when a major
is live was reading a number computed from a different engine than the one
producing the figure in front of them.

WHAT IS GRADED

The number the user actually sees, not an idealised core. That means the full
published chain — T=0 lognormal ratio, window decay, then the plausibility clamp
04d applies before display — so the reported error is the error of the figure on
the page. Clamp activations are counted separately so a good score cannot come
from the clamp quietly rescuing a bad prediction.

WHY IT NEEDS ITS OWN DATA PATH

reanchor_daily_to_event_start drops during-event registrations, deliberately:
the model must train on pre-registration data only. But the window engine
predicts from INSIDE that window, so grading it against a table with the window
removed would be grading it on data it never sees. The grader re-reanchors with
keep_post_start=True. That flag exists for this module and nothing else.

Sample: 255 of 329 events carry post-start rows, concentrated at one and two
days into the window, which is where the real windows mostly sit.
"""
import os
import sys
from importlib import import_module

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_utils import apply_plausibility_clamp
from prediction_window import window_decayed_estimate
from ratio_model import (build_ratio_model, predict_with_lognormal_ci,
                         ratio_observation_count)

m04c = import_module("04c_final_model")

MIN_FINAL_COUNT = 50


def count_at_window_day(tid_daily, day_into_window):
    """Cumulative registrations as of the end of `day_into_window`.

    Reanchored T counts down to 0 at event start, so day d into the window is
    T = -d. Rows are sparse — a day with no registrations has no row — so this
    takes the most recent row at or before the target day rather than requiring
    an exact match.
    """
    target_T = -day_into_window
    at_or_before = tid_daily[tid_daily['T'] >= target_T]
    if at_or_before.empty:
        return None
    row = at_or_before.sort_values('T').iloc[0]  # smallest T >= target
    val = row['cum_regs']
    return None if pd.isna(val) else int(val)


def eligible_events(summary, meta, year=None):
    """Events with a real post-start registration window.

    Mirrors 04d's entry condition for the window path: a registration close date
    strictly after event start. Events whose metadata puts close on or before
    start never take that path in production and must not be graded as if they
    did.
    """
    sm = summary.copy()
    sm['last_reg'] = pd.to_datetime(sm['last_reg'], errors='coerce')
    mm = meta.rename(columns={'year': 'tournament_year'})
    cols = ['family', 'tournament_year', 'start_date', 'end_date']
    joined = sm.merge(mm[cols], on=['family', 'tournament_year'], how='left')

    joined['window_len'] = (
        joined['end_date'] - pd.Timedelta(days=1) - joined['start_date']
    ).dt.days

    ok = joined[
        (joined['window_len'] > 0)
        & (joined['final_count'] >= MIN_FINAL_COUNT)
        & (joined['has_timestamps'])
        & (~joined['is_online'].fillna(False))
        & (~joined['is_covid'].fillna(False))
    ]
    if year is not None:
        ok = ok[ok['tournament_year'] == year]
    return ok


def grade_fold(year, summary, daily_post, meta, ratios, hist_lookup,
               predict_fn, gradeable_fn=None):
    """Score the window engine on one year's events, one row per window day."""
    records = []
    clamp_fired = 0
    frozen_skipped = []
    for _, ev in eligible_events(summary, meta, year).iterrows():
        tid_daily = daily_post[daily_post['tid'] == ev['tid']]
        if tid_daily.empty:
            continue
        final = int(ev['final_count'])
        # Same frozen-curve gate the main grade uses (v3 T1). Without it this
        # scored the export gap as model error: 2022's curves are frozen far
        # below their reconciled finals, and grading them produced 17% MAE at
        # 0.0% coverage across 68 predictions — a number the model did not
        # earn. The main grade reports 2022 as N/A for the same reason, so a
        # window grade that included it would not be comparable to it.
        if gradeable_fn is not None:
            ok, ratio = gradeable_fn(tid_daily, final)
            if not ok:
                frozen_skipped.append({'tid': ev['tid'], 'year': int(year),
                                       'peak_ratio': round(ratio, 3)})
                continue
        window_len = int(ev['window_len'])
        hist_counts = hist_lookup.get(ev['family'], [])

        for d in range(0, window_len):
            current = count_at_window_day(tid_daily, d)
            if current is None or current <= 0:
                continue
            # Exactly the production chain in 04d's window branch.
            p0, lo0, hi0 = predict_fn(current, 0, ev['family'], ratios)
            point, lo, hi = window_decayed_estimate(
                current, p0, lo0, hi0, d, window_len)
            days_remaining = window_len - d
            clamped = apply_plausibility_clamp(
                point, lo, hi, current, hist_counts, days_remaining)
            if clamped[0] != point:
                clamp_fired += 1
            point, lo, hi = clamped

            records.append({
                'tid': ev['tid'], 'family': ev['family'], 'year': int(year),
                'day_into_window': d, 'window_len': window_len,
                'current_count': current, 'predicted': int(point),
                'final': final,
                'abs_error_pct': abs(point - final) / final * 100,
                'in_ci': bool(lo <= final <= hi),
            })
    return records, clamp_fired, frozen_skipped


def summarize(records):
    """MAE and CI coverage overall and by day into the window."""
    if not records:
        return {'n': 0}
    errs = [r['abs_error_pct'] for r in records]
    hits = [r['in_ci'] for r in records]
    out = {
        'n': len(records),
        'n_events': len({r['tid'] for r in records}),
        'mae_pct': round(float(np.mean(errs)), 2),
        'median_error_pct': round(float(np.median(errs)), 2),
        'ci_coverage': round(float(np.mean(hits)) * 100, 1),
        'by_day': {},
        'by_year': {},
    }
    for key, field in (('by_day', 'day_into_window'), ('by_year', 'year')):
        groups = {}
        for r in records:
            groups.setdefault(r[field], []).append(r)
        for g, rs in sorted(groups.items()):
            out[key][str(g)] = {
                'n': len(rs),
                'mae_pct': round(float(np.mean([x['abs_error_pct'] for x in rs])), 2),
                'ci_coverage': round(float(np.mean([x['in_ci'] for x in rs])) * 100, 1),
            }
    return out


# Below this many observations a day's letter grade is noise. Window day 2 has
# 9 records, where a single event moves the rubric two steps.
MIN_DAY_SAMPLE = 25


def grade_from_by_day(by_day, compute_grade_fn, grade_order):
    """Worst letter across the window days, mirroring grade_from_aggregate.

    The main grade takes the worst of T-14/7/3 so a headline cannot advertise
    the model's best horizon. The same rule applies here for the same reason:
    day 0 of the window is the easiest prediction on the board (the count is
    nearly final) and reporting it alone would flatter the engine.

    Days with fewer than MIN_DAY_SAMPLE observations are excluded from the
    letter — with n=9, one event swings the grade two steps, and a rubric
    applied to that is noise, not measurement.
    """
    scored = []
    for day, m in by_day.items():
        if m['n'] < MIN_DAY_SAMPLE:
            continue
        scored.append((compute_grade_fn(m['mae_pct'], m['ci_coverage']), day, m))
    if not scored:
        return "N/A", "No window day has enough observations to grade"
    grade, day, m = max(
        scored,
        key=lambda s: grade_order.index(s[0]) if s[0] in grade_order else len(grade_order),
    )
    return grade, (f"worst of window days 0-{max(int(d) for _, d, _ in scored)} "
                   f"→ day {day}: MAE {m['mae_pct']}%, "
                   f"CI coverage {m['ci_coverage']}% (n={m['n']})")


def grade_window_engine(summary, daily_raw, meta, eval_years, hist_lookup_fn,
                        gradeable_fn=None, train_summary=None, verbose=True):
    """Expanding-window backtest of the window engine.

    Same protocol as the main grade: for each year Y, the ratio model is built
    from data strictly before Y, so no event is scored by a model that saw it.
    Production additionally folds completed current-year tids into its ratio
    model (build_ratio_model completed_tids, v5 Cat L); the folds here do not,
    so the graded window engine is slightly weaker than the published one —
    the same documented direction as the main engine's 31-vs-23-tid mismatch.

    train_summary vs summary is a fidelity distinction, not a convenience.
    04d builds its ratio model from a summary filtered only for online and COVID
    seasons — blitz families and World Open sub-events are IN it. The evaluation
    frame drops both, so training on that would grade a model production never
    runs. Blitz ratios in particular are legitimately high at short T and their
    absence visibly moves the result. Pass the production-shaped frame as
    train_summary; `summary` still decides which events get scored.
    """
    if train_summary is None:
        train_summary = summary
    daily_post = m04c.reanchor_daily_to_event_start(
        train_summary, daily_raw.copy(), meta, keep_post_start=True)

    # reanchor only shifts T for tids it finds in the frame it is given. An
    # event scored from `summary` but absent from `train_summary` would keep
    # last_reg-anchored T and be read at the wrong window day — wrong numbers,
    # no error. The two frames currently cannot diverge that way (eligible
    # events exclude online/COVID, which is the only thing train_summary drops),
    # but that is an invariant of today's filters, not a guarantee, so check it
    # instead of relying on it.
    scored_tids = set(eligible_events(summary, meta)['tid'])
    unanchored = scored_tids - set(train_summary['tid'])
    if unanchored:
        raise ValueError(
            f"{len(unanchored)} event(s) would be graded without being "
            f"reanchored, so their window days would be read at the wrong "
            f"offset: {sorted(unanchored)[:5]}. Pass a train_summary that "
            f"covers every event `summary` can score.")

    all_records = []
    total_clamped = 0
    all_frozen = []
    skipped_years = []
    for year in eval_years:
        train = train_summary[train_summary['tournament_year'] < year].copy()
        if train.empty:
            continue
        train_daily = daily_post[
            daily_post['tid'].isin(set(train['tid']))
        ]
        ratios = build_ratio_model(train, train_daily)
        # A fold with no usable training history is not a fold. Everything
        # before 2022 is COVID- or online-flagged, so the 2022 ratio model comes
        # back empty and predict_with_lognormal_ci degenerates to "return
        # current_count with a zero-width CI". Scored naively that reads as 17%
        # MAE at 0.0% coverage across 68 predictions, which looks like a broken
        # engine and is actually an absent one. The main grade reports 2022 as
        # N/A for the same reason; a window grade that quietly included it would
        # not be comparable to the number it sits beside.
        if ratio_observation_count(ratios) == 0:
            if verbose:
                print(f"  window engine {year}: N/A — no usable training "
                      f"history before {year} (all COVID/online-flagged)")
            skipped_years.append(int(year))
            continue
        recs, clamped, frozen = grade_fold(
            year, summary, daily_post, meta, ratios,
            hist_lookup_fn(train), predict_with_lognormal_ci,
            gradeable_fn=gradeable_fn)
        all_records.extend(recs)
        total_clamped += clamped
        all_frozen.extend(frozen)
        if verbose and frozen:
            print(f"  window engine {year}: excluded {len(frozen)} frozen "
                  f"curve(s) from grading")
        if verbose and recs:
            mae = np.mean([r['abs_error_pct'] for r in recs])
            cov = np.mean([r['in_ci'] for r in recs]) * 100
            print(f"  window engine {year}: n={len(recs):3d} "
                  f"MAE {mae:5.2f}%  coverage {cov:5.1f}%")

    out = summarize(all_records)
    out['clamp_activations'] = total_clamped
    out['frozen_curves_excluded'] = len(all_frozen)
    out['years_not_graded'] = skipped_years
    out['engine'] = 'model_online_window'
    out['description'] = (
        'T=0 lognormal ratio decayed toward the live count through the '
        'post-start online-registration window, then plausibility-clamped — '
        'the chain 04d uses once a multi-schedule event has begun.')
    # The horizon is NOT the same as the main grade's, and the two letters must
    # never be presented as though they were. This engine predicts 0-2 days from
    # registration close with most of the field already registered; the nowcast
    # grade covers T-14/7/3 before the event even starts. A better letter here
    # reflects an easier question, not a better model.
    out['horizon_note'] = (
        'Graded 0-2 days into the post-start registration window, a shorter '
        'and easier horizon than the T-14/7/3 the overall grade uses. Not '
        'comparable to it.')
    return out, all_records
