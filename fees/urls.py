"""Flyer filenames shared by discovery, parsing and edition lookup."""
import re
from urllib.parse import urlsplit

FLYER_RE = re.compile(r"([a-z][a-z0-9]*?)(\d{2})(?:-([a-z][a-z0-9]*))?\.html?$", re.I)


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
