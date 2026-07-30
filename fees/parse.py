"""chesstour.com flyer parser (scrape_fees, verbatim -- the demotion
reason strings are test contract, do not reword).
"""
import logging
import re
from datetime import datetime

from fees.patterns import (EARLY_BIRD_MIN_GAP_DAYS, _EARLY_BIRD_PHRASE_RE,
                           _EVENT_DATE_RE, _FEE_TIER_RANGE_RE, _FEE_TIER_RE,
                           _ONSITE_RE, _PRIZE_RE, _TITLE_GUESSES)

log = logging.getLogger(__name__)


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


def _guess_title(html, url):
    """Try several heuristics to extract the tournament name."""
    for pat in _TITLE_GUESSES:
        m = pat.search(html)
        if m:
            title = _clean(m.group(1))
            # Skip generic/junk titles
            if title and len(title) > 4 and 'chesstour' not in title.lower():
                return title
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


def parse_flyer(html, url):
    """Extract fee/deadline data from a chesstour.com flyer page.

    Returns a dict with the parsed fields, or None if nothing useful found.

    Guardrails (in order of application):
      1. early_bird_fee / early_bird_deadline are populated ONLY when the
         cheapest tier's deadline lands ≥EARLY_BIRD_MIN_GAP_DAYS before
         event_start. CCA's advance/onsite step (T-3 days) is NOT an early
         bird and gets demoted to the regular slot.
      2. If event_start can't be determined, EB fields stay blank — fail
         loud rather than guess.
      3. The cheapest tier must be strictly less than the next tier
         (no flat "early bird = regular" placeholders).
    """
    year = _guess_year_from_url(url)
    title = _guess_title(html, url)

    # Work with the visible text (tags stripped) for regex matching,
    # but keep original for structured tag searches
    text = _clean(html)
    event_start = _guess_event_start(html, year)

    has_eb_phrase = bool(_EARLY_BIRD_PHRASE_RE.search(text))

    # --- Fee tiers (date-bound) ---
    tiers = []
    for m in _FEE_TIER_RE.finditer(text):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        tiers.append((fee, deadline))

    # Also scan raw HTML in case tags break up the visible text
    for m in _FEE_TIER_RE.finditer(html):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        if (fee, deadline) not in tiers:
            tiers.append((fee, deadline))

    # Catch the keyword-less "$158 1/3-1/15" middle-tier pattern. We deduplicate
    # against tiers we already have.
    for m in _FEE_TIER_RANGE_RE.finditer(text):
        fee = _parse_fee(m.group(1))
        deadline = _normalise_date(m.group(2), year_hint=year)
        if (fee, deadline) not in tiers:
            tiers.append((fee, deadline))

    # Collapse per-deadline to the HIGHEST fee at that deadline. CCA pages
    # usually list "Top 5 sections $X by Y, all $Z at site" and then a
    # lower section ("Under 1200: $X-20 by Y"). Without this step, the
    # sub-section's $X-20 sorts as "cheapest" and pollutes the early-bird
    # detection. Top-section pricing is what we want to publish.
    by_deadline = {}
    for fee, deadline in tiers:
        if not isinstance(fee, int):
            continue
        if deadline not in by_deadline or fee > by_deadline[deadline]:
            by_deadline[deadline] = fee
    tiers = [(fee, dl) for dl, fee in by_deadline.items()]

    # Sort tiers by fee amount (cheapest first)
    tiers.sort(key=lambda t: t[0] if isinstance(t[0], int) else 0)

    # --- Onsite fee ---
    onsite_fee = None
    for m in _ONSITE_RE.finditer(text):
        onsite_fee = _parse_fee(m.group(1))
        break
    if onsite_fee is None:
        for m in _ONSITE_RE.finditer(html):
            onsite_fee = _parse_fee(m.group(1))
            break

    # --- Prize fund ---
    prize_fund = None
    for m in _PRIZE_RE.finditer(text):
        prize_fund = _parse_fee(m.group(1))
        break
    if prize_fund is None:
        for m in _PRIZE_RE.finditer(html):
            prize_fund = _parse_fee(m.group(1))
            break

    # If we found nothing at all, skip this page
    if not tiers and onsite_fee is None:
        log.debug("No fee data found on %s", url)
        return None

    # ── Apply early-bird guardrails ────────────────────────────────────
    # An "early bird" is a price hike WELL BEFORE the event during the
    # advance-registration window — not the 3-day-out advance/onsite step
    # that nearly every CCA event has.
    early_bird_fee = ""
    early_bird_deadline = ""
    regular_fee = ""
    regular_deadline = ""
    eb_demoted_reason = None

    if len(tiers) >= 2 and isinstance(tiers[0][0], int) and isinstance(tiers[1][0], int):
        cheapest_fee, cheapest_deadline = tiers[0]
        second_fee, second_deadline = tiers[1]
        gap = _days_gap(cheapest_deadline, event_start) if event_start else None

        if cheapest_fee >= second_fee:
            eb_demoted_reason = f"cheapest tier ${cheapest_fee} not less than next tier ${second_fee}"
        elif event_start is None:
            eb_demoted_reason = "could not parse event_start from flyer"
        elif gap is None:
            eb_demoted_reason = f"could not compute gap (deadline={cheapest_deadline}, event={event_start})"
        elif gap < EARLY_BIRD_MIN_GAP_DAYS:
            eb_demoted_reason = (
                f"deadline {cheapest_deadline} is T-{gap} (< T-{EARLY_BIRD_MIN_GAP_DAYS}) "
                f"vs event {event_start} — advance/onsite step, not early bird"
            )

        if eb_demoted_reason is None:
            early_bird_fee = cheapest_fee
            early_bird_deadline = cheapest_deadline
            regular_fee = second_fee
            regular_deadline = second_deadline
            if not has_eb_phrase:
                log.info(
                    "  EB-NOTE  %s — accepted on gap (T-%d) but flyer lacks explicit "
                    "'early bird' phrasing; double-check the source if values look off",
                    url, gap,
                )
        else:
            log.info("  EB-DEMOTE  %s — %s", url, eb_demoted_reason)
            regular_fee = cheapest_fee
            regular_deadline = cheapest_deadline
            # Promote the second tier toward onsite if we don't have one yet
            if onsite_fee is None:
                onsite_fee = second_fee
    elif len(tiers) == 1 and isinstance(tiers[0][0], int):
        # Single date-bound tier = advance fee, no early bird possible.
        # Treat as the same "advance/onsite step" we filter elsewhere so the
        # validator can flag it consistently.
        regular_fee, regular_deadline = tiers[0]
        gap = _days_gap(regular_deadline, event_start) if event_start else None
        if event_start is None:
            eb_demoted_reason = "could not parse event_start from flyer"
        elif gap is None:
            eb_demoted_reason = f"could not compute gap (deadline={regular_deadline}, event={event_start})"
        else:
            eb_demoted_reason = (
                f"only one date-bound tier (${regular_fee} by {regular_deadline}, T-{gap}) — "
                f"advance/onsite step, not early bird"
            )
        log.info("  EB-DEMOTE  %s — %s", url, eb_demoted_reason)

    if onsite_fee is None and len(tiers) >= 3:
        onsite_fee = tiers[-1][0]

    return {
        "tournament_name": title,
        "year": year or "",
        "event_start": event_start or "",
        "early_bird_fee": early_bird_fee,
        "early_bird_deadline": early_bird_deadline,
        "regular_fee": regular_fee,
        "regular_deadline": regular_deadline,
        "onsite_fee": onsite_fee or "",
        "prize_fund": prize_fund or "",
        "has_eb_phrasing": has_eb_phrase,
        "eb_demoted_reason": eb_demoted_reason or "",
        "url": url,
    }
