"""chesstour.com flyer parser (scrape_fees, verbatim -- the demotion
reason strings are test contract, do not reword).
"""
import logging

from fees.page_text import (  # noqa: F401  (re-exported for callers of fees.parse)
    _clean, _days_gap, _drop_stale_year, _guess_event_start, _guess_title,
    _guess_year_from_url, _normalise_date, _parse_fee)
from fees.patterns import (EARLY_BIRD_MIN_GAP_DAYS, _EARLY_BIRD_PHRASE_RE,
                           _FEE_TIER_RANGE_RE, _FEE_TIER_RE, _ONSITE_RE,
                           _PRIZE_RE)

log = logging.getLogger(__name__)


def _plausible_onsite(onsite_fee, regular_fee, url):
    """None for an on-site fee below the advance fee. CCA charges more at the
    site, so a lower figure is some other line read as the on-site fee: the
    chio22 blitz entry, lbo22's US Chess youth dues, dci26's titled-player fee."""
    if isinstance(onsite_fee, int) and isinstance(regular_fee, int) and onsite_fee < regular_fee:
        log.info("  ONSITE-DROP  %s — $%d is below the advance fee $%d, not an on-site fee",
                 url, onsite_fee, regular_fee)
        return None
    return onsite_fee


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
    onsite_fee = _plausible_onsite(onsite_fee, regular_fee, url)

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
