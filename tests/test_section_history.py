"""A separated event inherits its own verified gross section history only."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from sitebuild import metadata
from sitebuild.section_history import HISTORY_FILE, SectionHistoryError, load_section_history

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)


def sources():
    return (pd.read_csv(ROOT / "output/tournament_summary.csv"),
            pd.read_csv(ROOT / "output/historical_standings.csv"))


def history():
    return load_section_history(ROOT / "output", *sources(), NOW)


def card(monkeypatch, family, supplement, summary=None, year=2027):
    monkeypatch.setattr(metadata, "TODAY", pd.Timestamp("2026-11-11"))
    meta = pd.DataFrame([dict(family=family, year=year, start_date=f"{year}-02-26", end_date=f"{year}-02-28")])
    if summary is None:
        summary = pd.DataFrame(columns=["family", "tournament_year", "final_count", "is_online", "is_covid"])
    result = []
    metadata.build_metadata_cards(set(), 3, lambda *_: 0, lambda *_: ([], None), {},
        SimpleNamespace(curve_for=lambda _: {0: 1}), set(), lambda *_: pd.Timestamp("2026-03-01"),
        meta, summary, result, supplement)
    return result[0]


def test_committed_history_reconciles_gross_and_published_section_counts():
    records = history()
    senior = [r for r in records if r["source_section"] == "Senior"]
    adult = [r for r in records if r["source_section"] == "Young Adult/Middle Age"]
    assert [r["count"] for r in senior] == [32, 49]
    assert [r["count"] for r in adult] == [25, 12]
    assert sum(r["count"] for r in records if r["year"] == 2025) == 57
    assert sum(r["count"] for r in records if r["year"] == 2026) == 61


@pytest.mark.parametrize("family,point,counts", [
    ("New York State Senior Championship", 40, [32, 49]),
    ("Saratoga Tournament Of-The-Ages Open", 18, [25, 12]),
])
def test_separate_cards_use_own_history_without_fabricating_current_entries(monkeypatch, family, point, counts):
    result = card(monkeypatch, family, history())
    assert result["history_basis"] == "transferred_sections"
    assert result["history_transfer_inferred"] is True
    assert "2027 rules differ" in result["history_note"]
    assert result["current_count"] == 0
    assert result["point_estimate"] == point
    assert [h["count"] for h in result["historical"]] == counts
    assert result["prediction_source"] == "metadata_historical_avg"
    assert result["low_confidence"] is True and result["n_historical_editions"] == 2
    assert result["ci_lower"] == min(counts) and result["ci_upper"] == max(counts)


def test_direct_edition_history_is_not_overwritten_or_double_counted(monkeypatch):
    family = "New York State Senior Championship"
    summary = pd.DataFrame([dict(family=family, tournament_year=2026, final_count=60,
                                 is_online=False, is_covid=False)])
    result = card(monkeypatch, family, history(), summary)
    assert [h["count"] for h in result["historical"]] == [32, 60]
    assert result["point_estimate"] == 46


def test_unrelated_family_does_not_inherit_age_group_counts(monkeypatch):
    result = card(monkeypatch, "Example Open", history())
    assert result["point_estimate"] is None and result["historical"] == []


@pytest.mark.parametrize("fault", ["total", "active", "withdrawn", "negative", "boolean", "section", "duplicate", "source_id", "future", "unclosed", "private_field"])
def test_unverified_section_history_never_supplies_forecasts(tmp_path, fault):
    body = json.loads((ROOT / "output" / HISTORY_FILE).read_text())
    e = body["editions"][0]
    if fault == "total": e["total"] += 1
    if fault == "active": e["sections"][0]["active"] += 1
    if fault == "withdrawn": e["sections"][0]["withdrawn"] += 1
    if fault == "negative": e["sections"][0]["active"] = -1
    if fault == "boolean": e["sections"][0]["withdrawn"] = True
    if fault == "section": e["sections"][0]["name"] = "Other"
    if fault == "duplicate": body["editions"].append(copy.deepcopy(e))
    if fault == "source_id": e["tournament_id"] = "9999"
    if fault == "future": e["source_as_of"] = "2028-01-01T00:00:00+00:00"
    if fault == "unclosed": e["source_as_of"] = "2025-03-15T00:00:00+00:00"
    if fault == "private_field": e["email"] = "synthetic invalid extra field"
    (tmp_path / HISTORY_FILE).write_text(json.dumps(body))
    with pytest.raises(SectionHistoryError):
        load_section_history(tmp_path, *sources(), NOW)


def test_missing_optional_history_retains_unavailable_behavior(tmp_path):
    assert load_section_history(tmp_path, *sources(), NOW) == []


def test_fractional_parent_total_cannot_be_truncated_to_reconcile():
    summary, standings = sources()
    summary["final_count"] = summary["final_count"].astype(float)
    selected = (summary["family"] == "New York State Senior Championship With Young Adult Mi") & (summary["tournament_year"] == 2025)
    summary.loc[selected, "final_count"] = 57.9
    with pytest.raises(SectionHistoryError):
        load_section_history(ROOT / "output", summary, standings, NOW)
