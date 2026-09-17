"""Which earlier editions count as a card's history.

An edition is (family, year). Until 2026-09-17 every card was a current-season
card and its history was simply `tournament_year < 2026`. With next season's
events open early, a 2027 card's history has to reach the 2026 edition too —
but only once that edition is over.
"""
from shared.season import CURRENT_SEASON

FIRST_HISTORY_YEAR = 2019


def prior_editions(summary, families, before_year, is_settled, current_season=None):
    """Finished in-person editions of `families` from before `before_year`.

    Rows of `summary`, sorted by year, from FIRST_HISTORY_YEAR on, with online
    and COVID editions left out. Editions of a past season are settled by
    definition. An edition of an open season (possible only when the card is
    for a later season) counts once `is_settled(family, year)` says its event
    is over; until then its final_count is still climbing and is not history.
    """
    current_season = CURRENT_SEASON if current_season is None else current_season
    rows = summary[
        (summary['family'].isin(families)) &
        (~summary['is_online'].fillna(False).astype(bool)) &
        (~summary['is_covid'].fillna(False).astype(bool)) &
        (summary['tournament_year'] < before_year) &
        (summary['tournament_year'] >= FIRST_HISTORY_YEAR)
    ]
    open_rows = rows[rows['tournament_year'] >= current_season]
    unsettled = [idx for idx, r in open_rows.iterrows()
                 if not is_settled(r['family'], int(r['tournament_year']))]
    return rows.drop(index=unsettled).sort_values('tournament_year')
