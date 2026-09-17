"""A card's history is the editions that ran before it and are over.

2026-09-17. History was every edition `< 2026`. A 2027 card needs the 2026
edition in its history, but only once that edition is finished: an open 2026
event's count is still climbing, and publishing it as "last year's final"
would anchor the 2027 estimate on a number that is not final.
"""
import pandas as pd

from sitebuild.editions import prior_editions


def _summary():
    return pd.DataFrame({
        "family": ["Atlantic City Open"] * 3 + ["Eastern Open"] * 3 + ["Boston Online"],
        "tournament_year": [2025, 2026, 2027, 2018, 2025, 2026, 2025],
        "final_count": [300, 424, 3, 150, 210, 1, 80],
        "is_online": [False] * 6 + [True],
        "is_covid": [False] * 7,
    })


def _never(_family, _year):
    raise AssertionError("past-season editions are settled without asking")


def test_current_season_card_sees_only_earlier_seasons():
    got = prior_editions(_summary(), ["Atlantic City Open"], 2026, _never, current_season=2026)
    assert list(got["tournament_year"]) == [2025]


def test_next_season_card_includes_the_finished_current_edition():
    got = prior_editions(_summary(), ["Atlantic City Open"], 2027,
                         lambda f, y: True, current_season=2026)
    assert list(got["tournament_year"]) == [2025, 2026]
    assert list(got["final_count"]) == [300, 424]


def test_next_season_card_excludes_an_unfinished_current_edition():
    asked = []

    def is_settled(family, year):
        asked.append((family, year))
        return False

    got = prior_editions(_summary(), ["Eastern Open"], 2027, is_settled, current_season=2026)
    assert list(got["tournament_year"]) == [2025]
    assert asked == [("Eastern Open", 2026)]


def test_excludes_pre_2019_online_and_covid():
    summary = _summary()
    summary.loc[summary["tournament_year"] == 2025, "is_covid"] = True
    got = prior_editions(summary, ["Eastern Open", "Boston Online"], 2026, _never,
                         current_season=2026)
    assert got.empty


def test_tolerates_missing_flags():
    summary = _summary()
    summary["is_online"] = summary["is_online"].astype(object)
    summary.loc[0, "is_online"] = None
    got = prior_editions(summary, ["Atlantic City Open"], 2026, _never, current_season=2026)
    assert list(got["tournament_year"]) == [2025]
