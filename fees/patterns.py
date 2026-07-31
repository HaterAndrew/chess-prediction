"""Flyer-parsing regex library (scrape_fees, verbatim)."""
import re

# ---------------------------------------------------------------------------
# Step 3 — parse a chesstour.com flyer page
# ---------------------------------------------------------------------------

# Money amounts: $NNN or $N,NNN
_MONEY = r'\$[\d,]+'
# Date-like strings: month/day, month-day, "March 21", "3/21/25", etc.
_DATE_LOOSE = (
    r'(?:\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{2,4})?)'
)

# Regex for a fee tier line. CCA flyers vary wildly in spacing/markup:
#   "$207 by 3/19"
#   "$118 online at chessaction.com by 6/2"
#   "$148 if rec'd by 1/2"
# We allow up to 40 chars of letters / commas / periods / dots between the
# money and the deadline keyword, but no other dollar signs or digits in
# that gap (so we don't accidentally span two prize lines).
_FEE_TIER_RE = re.compile(
    rf'({_MONEY})'
    rf'(?:[A-Za-z\s,.\'"]{{0,40}})?\s*'
    rf'(?:if\s+(?:rec[\x27\u2019]?d?|postmarked|received)[\s,]*(?:by\s+)?|by|before|until|through|thru|b4)\s*'
    rf'({_DATE_LOOSE})',
    re.IGNORECASE,
)

# Fallback for the "$158 1/3-1/15" middle-tier pattern CCA uses when there's
# no "by" keyword \u2014 a bare date range right after the dollar amount. We
# capture the END of the range as the tier's deadline ($158 applies through
# 1/15, then prices step up). Requires the range form to limit false hits
# from prize lists like "$1000-600-400".
_FEE_TIER_RANGE_RE = re.compile(
    rf'({_MONEY})\s+'
    r'\d{1,2}/\d{1,2}\s*[\-\u2013to ]+\s*'
    r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)',
    re.IGNORECASE,
)

_ONSITE_RE = re.compile(
    rf'({_MONEY})'
    rf'(?:[A-Za-z\s,.\'"]{{0,30}})?\s*'
    rf'(?:on\s*-?\s*site|at\s+(?:the\s+)?door|after|at\s+site|walk[\s-]*in)',
    re.IGNORECASE,
)

_PRIZE_RE = re.compile(
    rf'(?:prize\s+fund|prizes?|guaranteed|based\s+on)[:\s]*({_MONEY})',
    re.IGNORECASE,
)

# Phrasing that signals an actual early-bird marketing structure (not just
# advance vs onsite). Combined with the 14-day gap rule below, this lets us
# distinguish Chicago Open ("early bird ends 3/19", T-63) from Cleveland
# ("online by 6/2", T-3 — just an advance/onsite step).
_EARLY_BIRD_PHRASE_RE = re.compile(
    r'\b(early[\s\-]?bird|early\s+registration|early\s+entry|advance\s+registration\s+discount)\b',
    re.IGNORECASE,
)

# Event date heuristic. Tolerates CCA's multi-schedule headers, e.g.
# "May 21-25, 22-25, 23-25, or 24-25, 2026" or "July 17-19 or 18-19, 2026"
# or the simple "May 5, 2026". We capture month + FIRST day, then accept
# glue (digits, dashes, commas, "or", whitespace, one short parenthetical
# like "(Thanksgiving Weekend)") before the 4-digit year. The dash class
# includes \x96/\x97: cp1252 en/em-dash bytes survive as those control
# chars when a flyer is decoded as latin-1 (ncc26 was the first to hit
# this). The non-greedy gap stops at the first plausible year.
_EVENT_DATE_RE = re.compile(
    r'(?P<month>'
    r'January|February|March|April|May|June|July|August|September|October|November|December'
    r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec'
    r')\.?'
    r'\s+(?P<day>\d{1,2})'
    r'(?:[\s\-–—,\x96\x97]|\d|or|\([^()]{0,40}\))*?'
    r'(?P<year>20\d{2})',
    re.IGNORECASE,
)

# An early bird is only real when the deadline is at least this many days
# before the event. Mirrors EARLY_BIRD_MIN_GAP_DAYS in 04d_website_data_v2.py
# and the JS gate in docs/app.js. 14 days = "well before the event."
EARLY_BIRD_MIN_GAP_DAYS = 14

_TITLE_GUESSES = [
    re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<h[12][^>]*>(.*?)</h[12]>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<font[^>]*size=["\']?[5-7]["\']?[^>]*>(.*?)</font>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<b>((?:20\d{2}\s+)?\w[\w\s]{5,40}(?:Open|Congress|Classic|Championship)s?)</b>', re.IGNORECASE),
]
