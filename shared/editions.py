"""An edition is one running of a tournament family: (family, year).

CCA names every card "<year> <family>" ("2027 Atlantic City Open"), and the
scraper stores that name verbatim in daily_scrape.csv. Consumers used to peel
the year off with a literal `'2026 '` prefix check, each in its own copy. That
made the family the whole identity, which holds only while one season is open.
CCA opens next season's registration months before the current season ends, so
two editions of one family are live in the data at once: the finished 2026
Atlantic City Open and the 2027 one taking entries.

One parser, so every join can key on the edition rather than the family.
"""
import re

_YEAR_PREFIX_RE = re.compile(r"^\s*(\d{4})\s+(.*?)\s*$")


def split_edition_name(name):
    """('Atlantic City Open', 2027) for '2027 Atlantic City Open'.

    A name with no year prefix comes back as (name, None): the caller decides
    what an unlabelled edition means, this function does not guess a season.
    Non-strings (NaN from a CSV) come back as (None, None).
    """
    if not isinstance(name, str):
        return None, None
    m = _YEAR_PREFIX_RE.match(name)
    if not m:
        return name.strip(), None
    return m.group(2), int(m.group(1))
