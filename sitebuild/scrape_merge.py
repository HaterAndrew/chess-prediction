"""Fold the nightly scrape into the summary counts.

Extracted from sitebuild/main.py. Open editions only: past-season editions
are settled, and reconcile_final_counts owns them. Pure functions over
DataFrames; the caller reads the file. The curves of editions the export never
saw come from the scrape at load time (corpus.scrape_curves), gross like the
counts here.
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
