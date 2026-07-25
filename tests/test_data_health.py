"""Tests for data_health.py — the prediction-output health scanner.

Each test drives the pure `scan(data, ctx)` function with a synthetic
website_data.json payload and a lightweight context stub, asserting that each
degradation mode fires at the right severity and that a healthy card stays
clean. Mirrors the failure shapes from the June 2026 World Open U13 / Eastern
incident.
"""
import os
import sys
from types import SimpleNamespace

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from data_health import scan  # noqa: E402


def ctx(scrape_latest=None, log_hist=None):
    return SimpleNamespace(
        scrape_latest=scrape_latest or {},
        log_hist=log_hist or {},
        summary_2026=set(),
        metadata_2026=set(),
    )


def card(**kw):
    """A healthy, fully-populated live 2026 card. Override fields per test."""
    base = dict(
        family="Healthy Open", year=2026, status="live",
        prediction_source="model", prediction_tier="family-direct",
        point_estimate=200, ci_lower=150, ci_upper=250, ci_level=0.8,
        current_count=50, gross_count=50, withdrawal_count=0, days_remaining=40,
        regular_fee=100.0, early_bird_fee=80.0, onsite_fee=120.0,
        event_start="2026-08-01", event_end="2026-08-03",
        registration_close="2026-08-01",
        low_confidence=False, n_historical_editions=6,
        historical=[{"year": y, "count": 200} for y in range(2019, 2025)],
        daily_data=[[0, 10], [1, 30], [2, 50]],
        walkin_source="family",
    )
    base.update(kw)
    return base


def run(cards, **ctx_kw):
    report = scan({"generated": "2026-06-06", "tournaments": cards}, ctx(**ctx_kw))
    return {(f["severity"], f["mode"]) for f in report.findings}, report


def test_healthy_card_is_clean():
    keys, report = run([card()])
    assert report.counts()["CRITICAL"] == 0
    assert report.counts()["HIGH"] == 0
    assert report.counts()["MEDIUM"] == 0


def test_critical_count_exceeds_estimate():
    keys, _ = run([card(current_count=300, point_estimate=200)])
    assert ("CRITICAL", "count-exceeds-estimate") in keys


def test_critical_frozen_main_path_estimate():
    keys, _ = run(
        [card(family="Frozen Open")],
        log_hist={"Frozen Open": [(110, 18), (110, 25), (110, 31)]},
    )
    assert ("CRITICAL", "frozen-estimate") in keys


def test_frozen_check_ignores_roster_pending():
    # roster-pending interim cards are EXPECTED to sit on the historical mean.
    keys, _ = run(
        [card(family="Pending Open", prediction_tier="roster-pending")],
        log_hist={"Pending Open": [(110, 18), (110, 25), (110, 31)]},
    )
    assert ("CRITICAL", "frozen-estimate") not in keys


def test_critical_dropped_event():
    # Scraped 50 entries but no card carries that family.
    keys, _ = run([card()], scrape_latest={"Ghost Open": {"net": 50, "gross": 50, "date": "2026-06-05"}})
    assert ("CRITICAL", "dropped-event") in keys


def test_high_alias_n_editions_mislabel():
    keys, _ = run([card(prediction_tier="family-alias", n_historical_editions=0)])
    assert ("HIGH", "alias-n-editions-mislabel") in keys


def test_high_stale_count():
    keys, _ = run(
        [card(family="Stale Open", current_count=10)],
        scrape_latest={"Stale Open": {"net": 42, "gross": 42, "date": "2026-06-05"}},
    )
    assert ("HIGH", "stale-count") in keys


def test_high_name_variant_split():
    # "Foo Open" and "Foo Open (in Ohio)" canonicalize to the same family.
    keys, _ = run([card(family="Foo Open"), card(family="Foo Open (in Ohio)")])
    assert ("HIGH", "name-variant-split") in keys


def test_medium_null_fee_near_event():
    keys, _ = run([card(regular_fee=None, days_remaining=10)])
    assert ("MEDIUM", "null-fee-near-event") in keys


def test_medium_sparse_history_hidden():
    keys, _ = run([card(low_confidence=False, n_historical_editions=2,
                        historical=[{"year": 2024, "count": 100}, {"year": 2025, "count": 110}])])
    assert ("MEDIUM", "sparse-history-hidden") in keys


def test_medium_no_history_default():
    keys, _ = run([card(point_estimate=100, ci_lower=70, ci_upper=130, historical=[],
                        n_historical_editions=0, low_confidence=True)])
    assert ("MEDIUM", "no-history-default") in keys


def test_info_roster_pending():
    keys, _ = run([card(family="Pending Open", prediction_tier="roster-pending")])
    assert ("INFO", "roster-pending") in keys


def test_warning_lines_cover_critical_and_high_only():
    _, report = run(
        [card(prediction_tier="family-alias", n_historical_editions=0),  # HIGH
         card(family="X2", regular_fee=None, days_remaining=5)],          # MEDIUM
    )
    lines = report.warning_lines()
    assert any("alias-n-editions-mislabel" in ln for ln in lines)
    assert all("null-fee-near-event" not in ln for ln in lines)  # MEDIUM not harvested


# ---------------------------------------------------------------------------
# v3 Q1/Q3 (audit/AUDIT_2026-07-25.md): daily_data integrity rules. Before
# these, the only daily_data check was a single-point INFO stub, so the
# 2026-07-25 incident (Bradley Open shipping a curve topping out at 625 against
# a real count of 197) passed data_health clean and reached production.
# ---------------------------------------------------------------------------


def test_daily_max_exceeding_current_count_is_critical():
    """The incident shape: a live card whose chart tops out above the entries
    actually scraped. Cumulative registrations cannot exceed the current count."""
    modes, _ = run([card(current_count=197,
                         daily_data=[[0, 50], [1, 300], [2, 625]])])
    assert ("CRITICAL", "daily-max-exceeds-count") in modes


def test_daily_max_equal_to_current_count_is_clean():
    """Boundary: the chart tail legitimately equals the current count."""
    modes, _ = run([card(current_count=197,
                         daily_data=[[0, 50], [1, 120], [2, 197]])])
    assert ("CRITICAL", "daily-max-exceeds-count") not in modes


def test_historical_card_daily_max_not_flagged():
    """A completed edition's final_count lives in current_count differently;
    the max-vs-count rule targets live cards only."""
    modes, _ = run([card(status="historical", current_count=100,
                         daily_data=[[0, 50], [1, 300]])])
    assert ("CRITICAL", "daily-max-exceeds-count") not in modes


def test_non_monotone_daily_data_is_high():
    """A cumulative series that falls means the curve was mis-assembled."""
    modes, _ = run([card(current_count=500,
                         daily_data=[[0, 50], [1, 300], [2, 120]])])
    assert ("HIGH", "daily-non-monotone") in modes


def test_duplicate_day_index_is_high():
    modes, _ = run([card(current_count=500,
                         daily_data=[[0, 50], [1, 100], [1, 140]])])
    assert ("HIGH", "daily-dup-neg-index") in modes


def test_negative_day_index_is_high():
    modes, _ = run([card(current_count=500,
                         daily_data=[[-3, 50], [1, 100]])])
    assert ("HIGH", "daily-dup-neg-index") in modes


def test_large_recent_gap_is_medium():
    """Q3: a big day-gap just before the tail is the exact precondition that let
    the A4 rescale fire. Warn before it turns into a corrupted curve."""
    modes, _ = run([card(current_count=500,
                         daily_data=[[0, 50], [1, 60], [2, 70], [20, 400]])])
    assert ("MEDIUM", "daily-large-recent-gap") in modes


def test_contiguous_daily_data_has_no_gap_finding():
    modes, _ = run([card(current_count=500,
                         daily_data=[[0, 50], [1, 60], [2, 70], [3, 80]])])
    assert ("MEDIUM", "daily-large-recent-gap") not in modes


def test_healthy_card_triggers_no_daily_findings():
    modes, _ = run([card()])
    daily_modes = {m for sev, m in modes if m.startswith("daily-")}
    assert daily_modes == set(), f"healthy card raised {daily_modes}"
