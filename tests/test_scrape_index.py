"""
Regression tests for scrape_entries.scrape_index parsing.

Pins the CCA index parse against a real captured response from the
ajaxFrontGetTourListNew.php endpoint (the AJAX tournament-list source the
chessaction.com homepage uses). The 2026-06-03 daily run failed because the
old /CCA/index.php?vendor=... URL started 302-redirecting to the generic
homepage, so the Selenium page load returned no tournament rows and the
regex matched zero tournaments. The fix fetches the AJAX endpoint directly;
this test locks the parser to the real response shape so a future site
change fails here loudly instead of silently in the cron run.

The fixture is a static HTML capture in tests/fixtures/ so the test never
hits the live CCA site.
"""

import os


from scrape_entries import _parse_index

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cca_tourlist.html")


def _load():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def test_parses_all_2026_tournaments():
    tournaments = _parse_index(_load())
    # The captured response holds 34 fully-formed 2026 tournament cards.
    assert len(tournaments) == 34, f"expected 34, got {len(tournaments)}"
    # Every row must carry a full, non-empty record.
    for t in tournaments:
        assert t["name"]
        assert t["url"].startswith("https://")
        assert t["start_date"] <= t["end_date"]
        assert t["state"]
        assert isinstance(t["entry_count"], int) and t["entry_count"] >= 0


def test_known_tournament_fields():
    by_name = {t["name"]: t for t in _parse_index(_load())}
    hartford = by_name["2026 Hartford Open"]
    assert hartford["start_date"] == "2026-06-05"
    assert hartford["end_date"] == "2026-06-07"
    assert hartford["state"] == "Connecticut"
    assert hartford["entry_count"] == 178
    # ISO date conversion and state capture for a second, unrelated row.
    nyso = by_name["2026 New York State Open"]
    assert nyso["start_date"] == "2026-06-19"
    assert nyso["state"] == "New York"


def test_empty_html_returns_no_rows():
    # The failure mode that crashed the cron: a page with no tournament cards
    # parses to zero rows (scrape_index turns this into a retryable error).
    assert _parse_index("<html><body>nothing here</body></html>") == []
