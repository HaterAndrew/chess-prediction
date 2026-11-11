"""Flyer filenames shared by discovery, parsing and edition lookup."""
import re
from urllib.parse import urlsplit

FLYER_RE = re.compile(r"([a-z][a-z0-9]*?)(\d{2})(?:-([a-z][a-z0-9]*))?\.html?$", re.I)

# Exact editions linked from the organizer's current tournament settings.
# These URLs have no year suffix; never infer their edition from the slug.
ANNOUNCEMENT_SOURCES = {
    "https://new.uschess.org/14th-annual-new-york-state-senior-championship": ("nyssc", 2027),
    "https://new.uschess.org/saratoga-tournament-ages-open-additional-college-bonus-prizes": ("nytoa", 2027),
    "https://new.uschess.org/59th-annual-new-york-state-high-school-championship": ("nyssc-highschool", 2027),
    "https://new.uschess.org/59th-annual-new-york-state-k-8-scholastic-championships-open-grades-k-8-only": ("nyssc-k8", 2027),
    "https://new.uschess.org/34th-annual-western-class-championships": ("wcc", 2027),
    "https://new.uschess.org/24th-annual-southern-class-championships": ("scc", 2027),
    "https://new.uschess.org/2nd-annual-atlantic-city-open": ("aco", 2027),
    "https://new.uschess.org/31st-annual-mid-america-open": ("mao", 2027),
}


def fee_source_parts(url):
    """A flyer or explicitly verified announcement's (code, year)."""
    return ANNOUNCEMENT_SOURCES.get(str(url)) or flyer_parts(url)


def flyer_parts(url):
    """(code, year), including a section suffix in the code, or None."""
    match = FLYER_RE.fullmatch(urlsplit(str(url)).path.rsplit("/", 1)[-1])
    if not match:
        return None
    code, yy, suffix = match.groups()
    code = code.lower() + ("-" + suffix.lower() if suffix else "")
    return code, 2000 + int(yy)


def flyer_filename(code, year):
    """The year precedes a section suffix: nyssc27-HighSchool.htm."""
    stem, _, suffix = code.partition("-")
    suffix = "HighSchool" if suffix.lower() == "highschool" else suffix
    return f"{stem}{year}" + (f"-{suffix}" if suffix else "") + ".htm"
