"""Join daily_scrape.csv rows to cards on the edition, (family, year).

Extracted from sitebuild/main.py on 2026-09-17. Every join here used to strip a
literal `'2026 '` prefix and match on the family under CURRENT_SEASON. That
holds only while one season is open. CCA opens next season's registration
months early, so the finished 2026 Atlantic City Open and the 2027 one taking
entries sit in the same file, and a family-only join hands one the other's
numbers.

Pure functions over DataFrames: no file reads, no clock.
"""
import pandas as pd

from shared.editions import split_edition_name
from tournament_aliases import canonicalize_family, cca_family


def annotate_editions(scrape, default_year):
    """Return `scrape` with `family` and `year` columns parsed from the name.

    The family comes from cca_family, the same function the scraper's metadata
    sync uses, so a scrape row and its metadata row always agree on the family.
    A name with no year prefix takes `default_year`. The scraper has always
    written the prefix, so this only keeps a hand-edited row joinable.
    """
    scrape = scrape.copy()
    years = scrape['tournament_name'].map(lambda n: split_edition_name(n)[1])
    scrape['family'] = scrape['tournament_name'].map(cca_family)
    scrape['year'] = [y if y is not None else int(default_year) for y in years]
    return scrape


def latest_by_edition(scrape):
    """The most recent scrape row of each edition."""
    return (scrape.sort_values('date')
                  .groupby(['family', 'year'], as_index=False)
                  .last())


def edition_mask(frame, family, year, family_col='family', year_col='tournament_year'):
    """Rows of `frame` that are this edition. Family equality goes through
    canonicalize_family so comma/whitespace/venue variants still match."""
    canon = canonicalize_family(family)
    return (frame[family_col].map(canonicalize_family) == canon) & (frame[year_col] == year)


def _net(row):
    """Net (active) count of a scrape row, falling back to gross."""
    active = row.get('active_count')
    if pd.notna(active) and active > 0:
        return int(active)
    return int(row['entry_count'])


def counts_by_edition(latest_scrape):
    """(family, year) -> {'net', 'gross', 'wd'} from the latest scrape rows.

    Keyed on the scraper's family spelling; callers that need comma/venue
    folding canonicalize the key themselves.
    """
    lookup = {}
    for _, s in latest_scrape.iterrows():
        wd = s.get('withdrawal_count')
        lookup[(s['family'], int(s['year']))] = {
            'net': _net(s),
            'gross': int(s['entry_count']),
            'wd': int(wd) if pd.notna(wd) else 0,
        }
    return lookup


def _edition_rows(scrape, family, year):
    return scrape[(scrape['family'] == family) & (scrape['year'] == year)]


def _peak_by_day(rows, day_of):
    by_day = {}
    for _, r in rows.iterrows():
        day = day_of(r['date'])
        by_day[day] = max(by_day.get(day, 0), _net(r))
    return by_day


def consecutive_zero_scrape_days(scrape, family, year, never_scraped):
    """How many of the most recent consecutive scrape days show 0 entries.

    Returns `never_scraped` when the edition has no scrape rows at all, since
    "no scrape rows ever" is genuinely untracked rather than a transient miss.
    """
    rows = _edition_rows(scrape, family, year)
    if len(rows) == 0:
        return never_scraped
    by_day = _peak_by_day(rows, lambda d: pd.to_datetime(d).normalize())
    streak = 0
    for day in sorted(by_day, reverse=True):
        if by_day[day] != 0:
            break
        streak += 1
    return streak


def scrape_daily_series(scrape, family, year, fallback_count):
    """Real [day_index, cumulative_count] entry-bar history for one edition.

    Mirrors the main path's cummax cleaning. Falls back to a single point only
    when fewer than two scrapes exist — the chart needs >=3 points to draw
    bars, so the old hardcoded [[0, count]] rendered nothing for these events.

    Returns (series, start_date) where start_date is the 'YYYY-MM-DD' calendar
    date of day 0, or None when unknown. v3 P1: the front end dates every chart
    point from this anchor plus the point's own day index, so a gap in scraping
    can no longer shift the labels. v3 N9: this path runs the same max-vs-count
    invariant as build_chart_series instead of going unchecked.
    """
    rows = _edition_rows(scrape, family, year).sort_values('date')
    if len(rows) < 2:
        return [[0, int(fallback_count)]], None
    min_date = rows['date'].min()
    by_day = _peak_by_day(rows, lambda d: int((d - min_date).days))
    peak, series = 0, []
    for day in sorted(by_day):
        peak = max(peak, by_day[day])
        series.append([day, peak])

    # v3 N9: this series is built from the scrape itself so it should never
    # exceed the scraped count; if it does, the edition match pulled in another
    # event's rows.
    if fallback_count and peak > int(fallback_count):
        print(f"WARNING: roster-pending series max ({peak}) exceeds count "
              f"({int(fallback_count)}) for {family} {year}; check the edition match.")

    return series, pd.to_datetime(min_date).strftime('%Y-%m-%d')
