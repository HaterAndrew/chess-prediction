"""Historical-edition cards (04d main() body, verbatim).

get_event_date arrives as a parameter -- it closes over main()-scope
meta/summary. tournaments_out is mutated in place, as before.
"""
from pipeline_utils import chart_series_start_date
from tournament_aliases import canonicalize_family

from sitebuild.helpers import _apply_wo_top6_adjustment, m04c


def add_historical_editions(EXCLUDE_FAMILIES, curves, daily, get_event_date,
                            summary, tournaments_out):
    # ── Build reverse alias map for 2026 families ──
    # If "DC International" is a 2026 family with alias "Philadelphia International",
    # historical "Philadelphia International" editions should display under "DC International"
    # so the website shows one unified tournament card with full history.
    _alias_to_2026 = {}
    for t in tournaments_out:
        fam = t['family']
        if hasattr(m04c, 'FAMILY_ALIASES') and fam in m04c.FAMILY_ALIASES:
            for alias in m04c.FAMILY_ALIASES[fam]:
                _alias_to_2026[alias] = fam

    # ── Add ALL historical tournament editions ──
    # Every individual edition (non-online, non-covid, >=10 entries) gets its own entry
    existing_tids = set()
    for t in tournaments_out:
        # Track 2026 families to avoid duplicating them
        existing_tids.add(t.get('_tid'))

    historical_valid = summary[
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['final_count'] >= 10) &
        (~summary['family'].isin(EXCLUDE_FAMILIES)) &
        (summary['tournament_year'] < 2026) &
        (summary['tournament_year'] >= 2015)
    ].sort_values(['family', 'tournament_year'])

    print(f"\nAdding {len(historical_valid)} historical editions...")

    for _, row in historical_valid.iterrows():
        family = row['family']
        tid = row['tid']
        yr = int(row['tournament_year'])
        count = int(row['final_count'])
        # Remap alias families to their 2026 canonical name
        # e.g. historical "Philadelphia International" → "DC International"
        # Then canonicalize to strip comma variants (e.g. "World Open, lower
        # sections" → "World Open lower sections") so live/historical match.
        display_family = canonicalize_family(_alias_to_2026.get(family, family))

        # Get event date
        event_date = get_event_date(family, yr)

        # Same-family history (include alias families so remapped entries show full lineage)
        hist_families = [family]
        if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
            hist_families.extend(m04c.FAMILY_ALIASES[family])
        # Also check reverse: if this family is an alias of a 2026 family, include the 2026 family
        if family in _alias_to_2026:
            canonical = _alias_to_2026[family]
            if canonical not in hist_families:
                hist_families.append(canonical)
        hist = historical_valid[
            (historical_valid['family'].isin(hist_families)) &
            (historical_valid['tournament_year'] <= yr)
        ].sort_values('tournament_year')
        historical = _apply_wo_top6_adjustment(display_family, [
            {"year": int(h['tournament_year']), "count": int(h['final_count']),
             "family": h['family']}
            for _, h in hist.iterrows()
        ], strip_family=True)

        # Registration curve
        curve = curves.get(family, curves.get('__global__', {}))
        reg_curve = []
        for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
            pct = curve.get(db, 0)
            reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})

        # Daily data for this specific edition
        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) > 0:
            max_T = tid_daily['T'].max()
            daily_data = []
            for _, d in tid_daily.iterrows():
                day_from_start = int(max_T - d['T'])
                daily_data.append([day_from_start, int(d['cum_regs'])])
            daily_data.sort(key=lambda x: x[0])
        else:
            daily_data = [[0, count]]

        t_out = {
            "family": display_family,
            "year": yr,
            "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
            "event_end": None,
            "early_bird_deadline": None,
            "early_bird_fee": None,
            "regular_fee": None,
            "onsite_fee": None,
            "current_count": count,
            "days_remaining": 0,
            "point_estimate": count,
            "ci_lower": count,
            "ci_upper": count,
            "ci_level": 0.80,
            "historical": historical,
            "daily_data": daily_data,
            "daily_start_date": chart_series_start_date(tid, daily, event_date),
            "registration_curve": reg_curve,
            "status": "historical",
        }
        tournaments_out.append(t_out)
