"""Fold the nightly scrape into the summary counts and the daily curves.

Extracted from sitebuild/main.py. Open editions only: past-season editions
are settled, and reconcile_final_counts owns them. Pure functions over
DataFrames; the caller reads the file and supplies the clock.
"""
import pandas as pd

from shared.season import is_open_season

from sitebuild.scrape_join import annotate_editions, edition_mask


def normalize_scrape(scrape, default_year):
    """Parse dates, backfill the withdrawal columns older rows lack, and key rows by edition."""
    scrape = scrape.copy()
    scrape['date'] = pd.to_datetime(scrape['date'])
    if 'active_count' not in scrape.columns:
        scrape['active_count'] = scrape['entry_count']
    else:
        scrape['active_count'] = scrape['active_count'].fillna(scrape['entry_count'])
    if 'withdrawal_count' not in scrape.columns:
        scrape['withdrawal_count'] = 0
    else:
        scrape['withdrawal_count'] = scrape['withdrawal_count'].fillna(0)
    return annotate_editions(scrape, default_year=default_year)


def merge_scrape_counts(summary, latest_scrape):
    """Write each open edition's latest gross count into summary, in place.

    H13: one count semantic, gross (entry_count), matching
    tournament_summary.csv, the performance tab, the freshness guard, and how
    04e grades. Net and the withdrawal delta go in their own columns for
    display. Returns how many final_counts changed.
    """
    if 'active_count' not in summary.columns:
        summary['active_count'] = pd.NA
    if 'withdrawal_count' not in summary.columns:
        summary['withdrawal_count'] = pd.NA
    updated = 0
    for _, s in latest_scrape.iterrows():
        if not is_open_season(s['year']):
            continue
        mask = edition_mask(summary, s['family'], s['year'])
        gross_count = int(s['entry_count']) if s['entry_count'] > 0 else int(s['active_count'])
        net_count = int(s['active_count']) if s['active_count'] > 0 else gross_count
        if not (mask.any() and gross_count > 0):
            continue
        old_count = summary.loc[mask, 'final_count'].iloc[0]
        summary.loc[mask, 'final_count'] = gross_count
        summary.loc[mask, 'active_count'] = net_count
        summary.loc[mask, 'withdrawal_count'] = max(gross_count - net_count, 0)
        if old_count != gross_count:
            updated += 1
    return updated


def _scrape_T(s, tid_row, meta, now):
    """Days from the scrape date to event start (or last registration), else None."""
    family_name, edition_year = s['family'], s['year']
    meta_row = meta[edition_mask(meta, family_name, edition_year, year_col='year')]
    if len(meta_row) == 0:
        meta_row = meta[(meta['year'] == edition_year) & (meta['start_date'] > now)]
        meta_row = meta_row[meta_row['family'].str.contains(family_name.split()[0], case=False, na=False)]
    if len(meta_row) > 0:
        event_start = pd.to_datetime(meta_row.iloc[0]['start_date'])
        return max((event_start - pd.to_datetime(s['date'])).days, 0)
    last_reg = tid_row.get('last_reg')
    if pd.notna(last_reg):
        return max((pd.to_datetime(last_reg) - pd.to_datetime(s['date'])).days, 0)
    return None


def inject_scrape_curves(scrape, summary, daily, meta, now):
    """Add each open edition's scrape counts to its event_start-anchored daily curve.

    A scrape day with no curve row becomes one; a scrape count above the
    curve's raises it. Curve points use active_count (net). Returns daily.
    """
    for _, s in scrape.iterrows():
        if not is_open_season(s['year']):
            continue
        tid_match = summary[edition_mask(summary, s['family'], s['year'])]
        if len(tid_match) == 0:
            continue
        tid = tid_match.iloc[0]['tid']
        T = _scrape_T(s, tid_match.iloc[0], meta, now)
        if T is None:
            continue
        scrape_count = int(s['active_count']) if s['active_count'] > 0 else int(s['entry_count'])
        existing = daily[(daily['tid'] == tid) & (daily['T'] == T)]
        if len(existing) == 0 and scrape_count > 0:
            new_row = pd.DataFrame([{
                'tid': tid, 'T': T, 'daily_regs': 0,
                'cum_regs': scrape_count, 'cum_pct': 1.0
            }])
            daily = pd.concat([daily, new_row], ignore_index=True)
        elif len(existing) > 0 and scrape_count > existing.iloc[0]['cum_regs']:
            daily.loc[(daily['tid'] == tid) & (daily['T'] == T), 'cum_regs'] = scrape_count
    return daily
