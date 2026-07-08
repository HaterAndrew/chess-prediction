"""Guard against re-hardcoding public accuracy claims in the About tab.

The 2026-07 audit (J1/J6) corrected an eval leak that had inflated the published
grade to A+/91%-coverage. The honest headline numbers now flow from
PERFORMANCE_DATA into id'd spans (populated by renderModelHealth). This test
fails if someone re-bakes a stale literal claim back into the prose, or removes
the spans that keep the numbers single-sourced.

Scope: the *prose* claims. The "What We Tried and Rejected" ablation table keeps
its pre-leak-fix figures on purpose (a labelled relative model-selection record),
so this test does not scan table cells.
"""
import os
import re

INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs", "index.html")


def _html():
    with open(INDEX, encoding="utf-8") as f:
        return f.read()


def test_stale_leaky_claims_absent():
    """The specific inflated claims the leak produced must not reappear in prose."""
    html = _html()
    banned = [
        "91% of the time",          # inflated cumulative coverage
        "88 tournament-years",      # stale eval-set size (now sourced)
        "captured the true result\n        91%",
        "9 out of 10 times",        # inflated (90%) coverage in the sanity-check prose
        "81.9%",                    # stale backtest CI-coverage stat / footer
        "intentionally conservative",  # false framing — the CI is overconfident, not conservative
    ]
    for phrase in banned:
        assert phrase not in html, f"stale hardcoded claim re-introduced: {phrase!r}"


def test_claim_spans_present():
    """The single-source spans must stay wired so the numbers can't silently drift."""
    html = _html()
    for span_id in ("about-n", "about-median", "about-cov", "about-cov-close",
                    "about-prior-n", "about-prior-cov", "about-prior-median",
                    "mc-ci-cover", "mc-ci-cover-inline", "mc-ci-cover-footer"):
        assert f'id="{span_id}"' in html, f"claim span removed: {span_id}"


def test_coverage_claim_discloses_collapse():
    """The prose must still disclose that CI coverage degrades close to the event
    (the honest fact the leak hid), not just quote a single flattering number."""
    html = _html()
    assert "three days out" in html
    assert re.search(r"overconfident", html), "coverage-collapse disclosure removed"
