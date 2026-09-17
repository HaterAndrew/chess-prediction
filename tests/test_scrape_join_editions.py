"""The site builder joins scrape rows to cards on the edition, not the family.

2026-09-17. With the 2027 Atlantic City Open taking entries while the 2026
edition sits finished in the same files, a family-only join hands one edition
the other's numbers: the 2027 card would inherit the 2026 final count of 424,
or the finished 2026 card would be overwritten with the single 2027 entry.
"""
import pandas as pd
import pytest

from sitebuild import scrape_join as sj


def _scrape(rows):
    df = pd.DataFrame(rows, columns=["date", "tournament_name", "entry_count",
                                     "active_count", "withdrawal_count"])
    df["date"] = pd.to_datetime(df["date"])
    return sj.annotate_editions(df, default_year=2026)


@pytest.fixture
def scrape():
    return _scrape([
        ("2026-03-20", "2026 Atlantic City Open", 400, 390, 10),
        ("2026-03-24", "2026 Atlantic City Open", 424, 401, 23),
        ("2026-09-15", "2027 Atlantic City Open", 0, 0, 0),
        ("2026-09-16", "2027 Atlantic City Open", 1, 1, 0),
        ("2026-09-17", "2027 Atlantic City Open", 3, 2, 1),
        ("2026-09-17", "2027 Golden State Open", 0, 0, 0),
    ])


def test_annotate_splits_name_into_family_and_year(scrape):
    got = set(zip(scrape["family"], scrape["year"]))
    assert got == {("Atlantic City Open", 2026), ("Atlantic City Open", 2027),
                   ("Golden State Open", 2027)}


def test_annotate_gives_unlabelled_names_the_default_year():
    df = _scrape([("2026-09-17", "Boston Chess Congress", 5, 5, 0)])
    assert list(df["year"]) == [2026]
    assert list(df["family"]) == ["Boston Chess Congress"]


def test_latest_by_edition_keeps_both_editions_of_a_family(scrape):
    latest = sj.latest_by_edition(scrape)
    by = {(r["family"], r["year"]): r for _, r in latest.iterrows()}
    assert by[("Atlantic City Open", 2026)]["entry_count"] == 424
    assert by[("Atlantic City Open", 2027)]["entry_count"] == 3
    assert len(latest) == 3


def test_counts_lookup_is_keyed_on_the_edition(scrape):
    lookup = sj.counts_by_edition(sj.latest_by_edition(scrape))
    assert lookup[("Atlantic City Open", 2027)] == {"net": 2, "gross": 3, "wd": 1}
    assert lookup[("Atlantic City Open", 2026)] == {"net": 401, "gross": 424, "wd": 23}
    assert lookup[("Golden State Open", 2027)] == {"net": 0, "gross": 0, "wd": 0}


def test_daily_series_reads_one_edition_only(scrape):
    series, start = sj.scrape_daily_series(scrape, "Atlantic City Open", 2027, 3)
    assert series == [[0, 0], [1, 1], [2, 2]]
    assert start == "2026-09-15"
    series_26, start_26 = sj.scrape_daily_series(scrape, "Atlantic City Open", 2026, 424)
    assert series_26 == [[0, 390], [4, 401]]
    assert start_26 == "2026-03-20"


def test_daily_series_falls_back_to_a_single_point(scrape):
    series, start = sj.scrape_daily_series(scrape, "Golden State Open", 2027, 0)
    assert series == [[0, 0]]
    assert start is None


def test_zero_streak_counts_one_edition_only(scrape):
    # The 2026 edition's hundreds of entries must not mask a 2027 zero streak,
    # and the 2027 zeros must not leak into the 2026 edition.
    assert sj.consecutive_zero_scrape_days(scrape, "Golden State Open", 2027, 3) == 1
    assert sj.consecutive_zero_scrape_days(scrape, "Atlantic City Open", 2027, 3) == 0
    assert sj.consecutive_zero_scrape_days(scrape, "Atlantic City Open", 2026, 3) == 0


def test_zero_streak_of_a_never_scraped_edition_is_the_threshold(scrape):
    assert sj.consecutive_zero_scrape_days(scrape, "Liberty Bell Open", 2027, 3) == 3


def test_edition_mask_selects_the_matching_year_only():
    summary = pd.DataFrame({
        "family": ["Atlantic City Open", "Atlantic City Open", "World Open top 6 sections"],
        "tournament_year": [2026, 2027, 2027],
    })
    mask = sj.edition_mask(summary, "Atlantic City Open", 2027)
    assert list(mask) == [False, True, False]
    # comma/whitespace variants still fold through canonicalize_family
    mask_wo = sj.edition_mask(summary, "World Open, top 6 sections", 2027)
    assert list(mask_wo) == [False, False, True]
