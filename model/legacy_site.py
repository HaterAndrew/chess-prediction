"""Legacy website-JSON builders (04c 2039-2248, verbatim).

Superseded by 04d/sitebuild for production, but pinned alive by
tests/test_pipeline_integration.py — do not delete without an owner call.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from model.constants import TODAY, TYPICAL_DURATION

def get_event_info(family, year, meta_lookup, summary):
    """Get or estimate event dates for a tournament."""
    key = (family, year)
    if key in meta_lookup:
        return meta_lookup[key]

    # Estimate from historical last_reg dates (pre-2026 editions)
    hist = summary[
        (summary['family'] == family) &
        (summary['has_timestamps']) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'].notna())
    ]
    last_regs = pd.to_datetime(hist['last_reg'].dropna())
    if len(last_regs) > 0:
        med_month = int(last_regs.dt.month.median())
        med_day = min(int(last_regs.dt.day.median()), 28)
        try:
            est_end = datetime(year, med_month, med_day)
        except ValueError:
            est_end = datetime(year, med_month, 28)
        est_start = est_end - timedelta(days=TYPICAL_DURATION)
        return {'start_date': est_start, 'end_date': est_end}

    # For new families, check the current year's last_reg as a proxy
    # (if last_reg is recent and close to today, the event likely already happened)
    current = summary[
        (summary['family'] == family) &
        (summary['has_timestamps']) &
        (summary['tournament_year'] == year)
    ]
    cur_last_regs = pd.to_datetime(current['last_reg'].dropna())
    if len(cur_last_regs) > 0:
        latest = cur_last_regs.max()
        est_end = datetime(latest.year, latest.month, latest.day)
        est_start = est_end - timedelta(days=TYPICAL_DURATION)
        return {'start_date': est_start, 'end_date': est_end}

    # Last resort: assume future event
    return {
        'start_date': TODAY + timedelta(days=90),
        'end_date': TODAY + timedelta(days=94),
    }


def determine_status(event_info):
    """Determine tournament status based on event dates."""
    start = event_info['start_date']
    end = event_info['end_date']
    if isinstance(start, str):
        start = pd.to_datetime(start)
    if isinstance(end, str):
        end = pd.to_datetime(end)

    if TODAY > end + timedelta(days=1):
        return 'complete'
    elif TODAY >= start:
        return 'in_progress'
    else:
        return 'live'


def build_daily_data(tid, daily):
    """Get daily data as [[days_from_first_reg, cumulative_count], ...]."""
    td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(td) == 0:
        return []
    max_T = td['T'].max()
    return [[int(max_T - r['T']), int(r['cum_regs'])] for _, r in td.iterrows()]


def build_reg_curve(family, template_curves):
    """Build registration curve for a family."""
    curve = template_curves.get(family, template_curves.get('__global__', {}))
    if not curve:
        return []
    leads = [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]
    return [{'days_before': t, 'cumulative_pct': round(curve.get(t, 0.0), 3)}
            for t in leads if curve.get(t, 0.0) > 0]


def get_historical(family, summary):
    """Historical final counts (2015+, non-online, non-covid)."""
    hist = summary[
        (summary['family'] == family) &
        (~summary.get('is_online', pd.Series(False)).fillna(False)) &
        (~summary.get('is_covid', pd.Series(False)).fillna(False)) &
        (summary['tournament_year'].notna()) &
        (summary['tournament_year'] >= 2015) &
        (summary['tournament_year'] < 2026)
    ].sort_values('tournament_year')
    return [{'year': int(r['tournament_year']), 'count': int(r['final_count'])}
            for _, r in hist.iterrows()]


def build_website_json(summary, daily, meta_lookup, model, template_curves):
    """Build final website_data.json with all 2026 tournaments."""
    t2026 = summary[summary['tournament_year'] == 2026].copy()
    tournaments = []

    for _, row in t2026.iterrows():
        family = row['family']
        tid = row['tid']
        current_count = int(row['final_count'])

        # Event info
        info = get_event_info(family, 2026, meta_lookup, summary)
        event_start = info['start_date']
        event_end = info['end_date']
        status = determine_status(info)

        # Days remaining to event start
        if isinstance(event_start, str):
            event_start = pd.to_datetime(event_start)
        if isinstance(event_end, str):
            event_end = pd.to_datetime(event_end)
        days_to_start = max((event_start - TODAY).days, 0)

        # T = days_to_start: training data is anchored to event_start after
        # reanchor_daily_to_event_start(), so pass days_to_start directly.

        # Predict with guardrails
        hist_counts = [h['count'] for h in get_historical(family, summary)]
        prediction_source = 'model'
        if status == 'live' and current_count > 0 and days_to_start > 0:
            # Guardrail: don't trust ratio-based predictions with < 10 regs
            # and > 60 days out — fall back to historical average
            if current_count < 10 and days_to_start > 60 and len(hist_counts) >= 1:
                hist_med = int(np.median(hist_counts))
                pred = hist_med
                lo = int(np.percentile(hist_counts, 10)) if len(hist_counts) >= 5 else int(hist_med * 0.7)
                hi = int(np.percentile(hist_counts, 90)) if len(hist_counts) >= 5 else int(hist_med * 1.3)
            else:
                pred, lo, hi = model.predict_nowcast(current_count, days_to_start, family)
                if pred is None:
                    pred, lo, hi = current_count, current_count, current_count

            # Plausibility check: if prediction is outside [0.3x, 3x] of
            # historical range, clamp to historical bounds
            if len(hist_counts) >= 1:
                hist_min = min(hist_counts)
                hist_max = max(hist_counts)
                if pred < hist_min * 0.3:
                    hist_med = int(np.median(hist_counts))
                    pred, lo, hi = hist_med, int(hist_med * 0.7), int(hist_med * 1.3)
                elif pred > hist_max * 3.0:
                    pred = int(hist_max * 1.5)
                    hi = min(hi, int(hist_max * 2.5))
        elif status == 'in_progress':
            # Event underway — pass through scraped count directly.
            # Does NOT include on-site/walk-up registrations.
            pred, lo, hi = current_count, current_count, current_count
            prediction_source = 'live_scrape'
        elif status == 'complete':
            pred, lo, hi = current_count, current_count, current_count
            prediction_source = 'final'
        else:
            pred, lo, hi = current_count, current_count, current_count

        entry = {
            'family': family,
            'year': 2026,
            'event_start': event_start.strftime('%Y-%m-%d') if hasattr(event_start, 'strftime') else str(event_start)[:10],
            'event_end': event_end.strftime('%Y-%m-%d') if hasattr(event_end, 'strftime') else str(event_end)[:10],
            'current_count': current_count,
            'days_remaining': days_to_start,
            'point_estimate': pred,
            'ci_lower': lo,
            'ci_upper': hi,
            'ci_level': 0.80,
            'historical': get_historical(family, summary),
            'registration_curve': build_reg_curve(family, template_curves),
            'daily_data': build_daily_data(tid, daily),
            'status': 'live' if status == 'in_progress' else status,
            'prediction_source': prediction_source,
        }

        # Fee info from metadata
        key = (family, 2026)
        if key in meta_lookup:
            m = meta_lookup[key]
            if m.get('early_bird_deadline') and not pd.isna(m['early_bird_deadline']):
                entry['early_bird_deadline'] = str(m['early_bird_deadline'])[:10]
            if m.get('early_bird_fee') and not pd.isna(m['early_bird_fee']):
                entry['early_bird_fee'] = int(m['early_bird_fee'])
            if m.get('regular_fee') and not pd.isna(m['regular_fee']):
                entry['regular_fee'] = int(m['regular_fee'])
            if m.get('onsite_fee') and not pd.isna(m['onsite_fee']):
                entry['onsite_fee'] = int(m['onsite_fee'])

        tournaments.append(entry)

    # Sort: live first, then by days_remaining
    status_order = {'live': 0, 'in_progress': 1, 'complete': 2, 'unknown': 3}
    tournaments.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

    return {
        'generated': TODAY.strftime('%Y-%m-%d'),
        'model': 'N5v4_Final',
        'model_description': (
            'Ensemble model (N5v4): historical ratio (harmonic mean) + '
            'per-family pooled Huber regression (final ~ count_at_T + T). '
            'T-dependent weights (ratio: 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). '
            '80% CI from lognormal prediction intervals, LOO-calibrated with '
            'ensemble shrinkage. Empirical Bayes sigma shrinkage, T-interpolation, '
            'expanding-window calibration, and plausibility guardrails.'
        ),
        'tournaments': tournaments,
    }

