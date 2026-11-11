"""Organizer-linked US Chess announcements retain edition and fee provenance."""
from pathlib import Path

import pandas as pd
import pytest

from fees.parse import parse_flyer
from fees.urls import ANNOUNCEMENT_SOURCES, fee_source_parts
from fees.discover import generate_candidate_urls
import merge_fees
from registry.resolve import resolve_source
from registry.sources import SOURCES


@pytest.mark.parametrize("code,regular,early,onsite", [
    ("nyssc-highschool", 146, 126, ""), ("nyssc-k8", 160, 120, 250),
    ("wcc", 160, 140, 180), ("scc", 130, 120, 140),
    ("aco", 250, 230, 270), ("mao", 140, 125, 155),
    ("nyssc", 118, 108, 130), ("nytoa", 98, 88, 110),
])
def test_announcement_fee_schedule(code, regular, early, onsite):
    url = next(u for u, edition in ANNOUNCEMENT_SOURCES.items() if edition == (code, 2027))
    fixture = Path(__file__).parent / "fixtures" / "flyers" / f"uschess-{code}27.html"
    out = parse_flyer(fixture.read_text(), url)
    assert out["year"] == 2027
    assert out["regular_fee"] == regular
    assert out["early_bird_fee"] == early
    assert out["onsite_fee"] == onsite
    assert out["url"] == url
    assert url in generate_candidate_urls([url])
    assert fee_source_parts(url + "?other=edition") is None
    assert parse_flyer(fixture.read_text().replace("2027</p>", "2026</p>"), url) is None
    assert parse_flyer(fixture.read_text().replace("<article>", "<div>").replace("</article>", "</div>"), url) is None


def test_valid_announcement_replaces_only_missing_fees_after_stale_flyer(tmp_path, monkeypatch):
    url = next(u for u, edition in ANNOUNCEMENT_SOURCES.items() if edition == ("nyssc-highschool", 2027))
    fees = pd.DataFrame([
        dict(year=2027, url="https://www.chesstour.com/nyssc27-HighSchool.htm", event_start="2026-02-28", regular_fee=999),
        dict(year=2027, url=url, event_start="2027-02-27", regular_fee=146),
    ])
    meta = pd.DataFrame([dict(family="TestFam", year=2027, start_date="2027-02-27",
        regular_fee="", onsite_fee=210, early_bird_fee="", early_bird_deadline="")])
    fp, mp = tmp_path / "fees.csv", tmp_path / "metadata.csv"
    fees.to_csv(fp, index=False)
    meta.to_csv(mp, index=False)
    monkeypatch.setattr(merge_fees, "FEES_CSV", str(fp))
    monkeypatch.setattr(merge_fees, "META_CSV", str(mp))
    monkeypatch.setattr(merge_fees, "FAMILY_TO_CODE", {"TestFam": "nyssc-highschool"})
    assert merge_fees.merge_fees(first_season=2027) == 1
    row = pd.read_csv(mp).iloc[0]
    assert row.regular_fee == 146
    assert row.onsite_fee == 210


def test_registry_allows_one_flyer_and_one_verified_announcement_per_edition():
    source = next(s for s in SOURCES if s.file == "tournament_fees.csv")
    url = next(u for u, edition in ANNOUNCEMENT_SOURCES.items() if edition == ("nyssc-highschool", 2027))
    flyer = "https://www.chesstour.com/nyssc27-HighSchool.htm"
    frame = pd.DataFrame([dict(url=flyer, year=2027), dict(url=url, year=2027)])
    families = {"New York State High School Championship"}
    assert resolve_source(source, frame, families).duplicates == []
    assert resolve_source(source, pd.concat([frame, frame.iloc[[0]]]), families).duplicates
    assert resolve_source(source, pd.concat([frame, frame.iloc[[1]]]), families).duplicates
