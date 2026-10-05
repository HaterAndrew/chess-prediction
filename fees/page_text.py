"""Fields read off a chesstour.com flyer page: title, year, event start,
fee amounts and dates. parse_flyer (fees/parse.py) combines them."""
import re
from datetime import datetime

from fees.patterns import _EVENT_DATE_RE, _TITLE_GUESSES


def _clean(text):
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _parse_fee(s):
    """Convert '$1,234' -> 1234 as int, or return the raw string."""
    s = s.strip().lstrip('$').replace(',', '')
    try:
        return int(s)
    except ValueError:
        return s


def _normalise_date(raw, year_hint=None):
    """Best-effort parse of a messy date string into YYYY-MM-DD.

    year_hint is the tournament year (from URL or page).  If the raw date
    has no year component we attach year_hint.
    """
    raw = raw.strip().rstrip('.')
    # Try common formats
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
        "%m/%d", "%m-%d",
        "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
        "%B %d", "%b %d", "%b. %d",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            # If year came from format and is reasonable, keep it
            if '%Y' in fmt or '%y' in fmt:
                return dt.strftime("%Y-%m-%d")
            # Otherwise attach year_hint
            if year_hint:
                dt = dt.replace(year=int(year_hint))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: return as-is
    return raw


def _guess_year_from_url(url):
    """Extract a 2-digit year suffix from a chesstour.com filename."""
    m = re.search(r'(\d{2})\.htm', url)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy < 50 else 1900 + yy
    return None


def _drop_stale_year(title, url):
    """The eo24, eo25 and eo26 pages kept the <title> "2023 Eastern Open
    chess tournament". A leading year that is not the URL's year is dropped."""
    m = re.match(r"((?:19|20)\d{2})\s+(.+)", title)
    if m and int(m.group(1)) != _guess_year_from_url(url):
        return m.group(2)
    return title


def _guess_title(html, url):
    """Try several heuristics to extract the tournament name."""
    for pat in _TITLE_GUESSES:
        m = pat.search(html)
        if m:
            title = _clean(m.group(1))
            # Skip generic/junk titles
            if title and len(title) > 4 and 'chesstour' not in title.lower():
                return _drop_stale_year(title, url)
    # Fallback: derive from filename
    fname = url.rsplit('/', 1)[-1].replace('.htm', '')
    return fname


def _guess_event_start(html, year_hint):
    """Pull the event start date out of a CCA flyer.

    CCA flyers consistently lead with a header like 'May 21-25, 2026' or
    'July 17-19 or 18-19, 2026'. We take the FIRST date hit on the page.
    Returns YYYY-MM-DD or None.
    """
    text = _clean(html)
    m = _EVENT_DATE_RE.search(text)
    if not m:
        return None
    raw = f"{m.group('month').strip('.')} {m.group('day')} {m.group('year')}"
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _days_gap(deadline_iso, event_iso):
    """Days between deadline and event_start. None if either is unparseable."""
    try:
        d = datetime.strptime(deadline_iso, "%Y-%m-%d")
        e = datetime.strptime(event_iso, "%Y-%m-%d")
        return (e - d).days
    except (TypeError, ValueError):
        return None
