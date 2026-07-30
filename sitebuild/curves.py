"""Template-curve builder (04d variant, verbatim; distinct from
model/curves.py -- parked behavior question, see the decomposition ledger).
"""
import numpy as np
from scipy.interpolate import interp1d

from sitebuild.helpers import T_GRID


def build_template_curves(train_summary, train_daily):
    """Build median cumulative curves per family."""
    valid = train_summary[
        (train_summary['has_timestamps']) &
        (~train_summary['is_online'].fillna(False)) &
        (~train_summary['is_covid'].fillna(False)) &
        # H15: exclude in-progress 2026 editions — their injected scrape rows carry
        # cum_pct=1.0, which drags the "typical timeline" template toward 1.0 too
        # early (worst for 2-3 edition families). Parity with build_ratio_model.
        (train_summary['tournament_year'] < 2026)
    ]

    curves = {}
    for family in valid['family'].unique():
        ftids = valid[valid['family'] == family]['tid'].values
        if len(ftids) < 2:
            continue
        curves_at_T = {}
        for tid in ftids:
            ed = train_daily[train_daily['tid'] == tid].sort_values('T')
            if len(ed) < 5:
                continue
            try:
                fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                             bounds_error=False, fill_value=(1.0, 0.0))
                for t in T_GRID:
                    curves_at_T.setdefault(t, []).append(float(fi(t)))
            except Exception:
                continue
        if curves_at_T:
            curves[family] = {t: np.median(curves_at_T.get(t, [0])) for t in T_GRID}

    # Global fallback
    all_at_T = {}
    for tid in valid['tid'].values:
        ed = train_daily[train_daily['tid'] == tid].sort_values('T')
        if len(ed) < 5:
            continue
        try:
            fi = interp1d(ed['T'].values, ed['cum_pct'].values, kind='linear',
                         bounds_error=False, fill_value=(1.0, 0.0))
            for t in T_GRID:
                all_at_T.setdefault(t, []).append(float(fi(t)))
        except Exception:
            continue
    curves['__global__'] = {t: np.median(all_at_T.get(t, [0])) for t in T_GRID}

    return curves
