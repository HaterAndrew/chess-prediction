"""The edition registry resolves every file's rows to one (family, year) and
fails loud on a row it cannot place or on two rows for one edition. Six key
schemes name the same events; the registry is where they must agree."""
import os

import pandas as pd
import pytest

from registry import keys
from registry.checks import build_registry, check_integrity, exemption_lines
from registry.io import load_frames
from registry.resolve import resolve

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _frames(**over):
    frames = {
        "tournament_summary.csv": pd.DataFrame({
            "tid": [10, 4100], "family": ["42nd annual Continental Open", "Chicago Open"],
            "tournament_year": [None, 2026.0], "final_count": [300, 900]}),
        "tournament_metadata.csv": pd.DataFrame({
            "family": ["Chicago Open", "World Open top 6 sections"], "year": [2026, 2026],
            "start_date": ["2026-05-21", "2026-07-01"], "end_date": ["2026-05-25", "2026-07-05"]}),
        "daily_scrape.csv": pd.DataFrame({
            "date": ["2026-05-01", "2026-05-02"],
            "tournament_name": ["2026 Chicago Open", "2026 World Open, top 6 sections"],
            "entry_count": [500, 900], "url": ["u", "u"]}),
        "tournament_fees.csv": pd.DataFrame({
            "tournament_name": ["Chicago Open", "blitz"], "year": [2026, 2026],
            "url": ["https://www.chesstour.com/chio26.htm", "https://www.chesstour.com/eob26.htm"]}),
        "historical_standings.csv": pd.DataFrame({
            "tournament_name": ["Chicago Open"], "year": [2025], "total_players": [850]}),
        "historical_tournaments.csv": pd.DataFrame({
            "tournament_name": ["2025 Chicago Open", "2025 Chicago Open Blitz", "2020 CCA July Open on ICC"],
            "year": [2025, 2025, 2020], "total_entries": [850, 60, 40]}),
        "walk_in_multipliers.csv": pd.DataFrame({
            "family": ["Chicago Open"], "year": [2025], "walk_in_ratio": [1.1]}),
        "forecast_ledger.csv": pd.DataFrame({"family": ["Chicago Open"] * 2, "year": [2026, 2026]}),
        "forecast_ledger_backfill.csv": pd.DataFrame({"family": ["Chicago Open"], "year": [2026]}),
    }
    frames.update(over)
    return frames


def test_clean_frames_resolve_with_every_exemption_counted():
    report, resolutions = check_integrity(_frames())
    assert report.errors == []
    assert exemption_lines(resolutions) == [
        "tournament_summary.csv: 1 row(s) exempt as legacy tid 10-75",
        "tournament_fees.csv: 1 row(s) exempt as side-event flyer",
        "historical_tournaments.csv: 1 row(s) exempt as outside the tracked families",
        "historical_tournaments.csv: 1 row(s) exempt as side event",
    ]


def test_the_registry_lists_each_files_own_key_per_edition():
    _, resolutions = check_integrity(_frames())
    reg = build_registry(resolutions).set_index(["family", "year"])
    row = reg.loc[("Chicago Open", 2026)]
    assert row["tids"] == "4100"
    assert row["fee_urls"] == "https://www.chesstour.com/chio26.htm"
    assert reg.loc[("World Open top 6 sections", 2026), "scrape_names"] == "2026 World Open, top 6 sections"
    assert reg.loc[("Chicago Open", 2025), "standings_names"] == "Chicago Open"


def test_two_spellings_of_one_metadata_edition_fail():
    """2026-10-04: tournament_metadata.csv held 'World Open top 6 sections'
    and 'World Open, top 6 sections' for 2026, identical values."""
    meta = _frames()["tournament_metadata.csv"]
    dup = pd.concat([meta, meta.iloc[[1]].assign(family="World Open, top 6 sections")])
    report, _ = check_integrity(_frames(**{"tournament_metadata.csv": dup}))
    assert report.errors == ["tournament_metadata.csv: World Open top 6 sections 2026 has 2 rows"]


def test_a_modern_summary_row_without_a_year_fails():
    summary = _frames()["tournament_summary.csv"]
    summary.loc[len(summary)] = [4200, "Chicago Open", float("nan"), 5]
    report, _ = check_integrity(_frames(**{"tournament_summary.csv": summary}))
    assert report.errors == ["tournament_summary.csv row 4: '4200' names no family or year"]


def test_an_unmapped_flyer_code_fails():
    fees = _frames()["tournament_fees.csv"]
    fees.loc[len(fees)] = ["New Open", 2026, "https://www.chesstour.com/zzz26.htm"]
    report, _ = check_integrity(_frames(**{"tournament_fees.csv": fees}))
    assert len(report.errors) == 1 and "'zzz' maps to no family" in report.errors[0]


def test_an_unknown_standings_name_fails():
    st = pd.DataFrame({"tournament_name": ["Mysteryopen"], "year": [2025], "total_players": [9]})
    report, _ = check_integrity(_frames(**{"historical_standings.csv": st}))
    assert report.errors == [
        "historical_standings.csv row 2: 'Mysteryopen': no family 'Mysteryopen' in the summary or metadata"]


def test_a_broken_column_contract_fails_before_resolution():
    meta = _frames()["tournament_metadata.csv"].assign(year=["2026", "twenty"])
    report, resolutions = check_integrity(_frames(**{"tournament_metadata.csv": meta}))
    assert any(e.startswith("tournament_metadata.csv: year fails") for e in report.errors)
    assert "tournament_metadata.csv" not in {r.file for r in resolutions}


def test_a_missing_file_fails():
    frames = _frames()
    del frames["historical_standings.csv"]
    report, _ = check_integrity(frames)
    assert report.errors == ["historical_standings.csv not found"]


def test_fee_codes_resolve_through_the_canonical_family():
    assert keys.fee_edition_key("https://www.chesstour.com/wo26.htm") == ("World Open top 6 sections", 2026)
    with pytest.raises(keys.AmbiguousKey):
        keys.fee_edition_key("https://x/ab26.htm", table={"Atlantic Open": "ab", "Bradley Open": "ab"})
    with pytest.raises(keys.UnresolvedKey):
        keys.fee_edition_key("https://x/no-code-here")


def test_standings_names_go_through_the_standings_map():
    assert keys.standings_edition_key("Bostonchess Congress", 2019) == ("Boston Chess Congress", 2019)


def test_resolve_fails_loud_on_an_unknown_family_or_missing_year():
    assert resolve("scrape", ("2026 Chicago Open",), {"Chicago Open"}) == ("Chicago Open", 2026)
    with pytest.raises(keys.UnresolvedKey, match="no family"):
        resolve("scrape", ("2026 New Open",), {"Chicago Open"})
    with pytest.raises(keys.UnresolvedKey, match="carries no year"):
        resolve("summary", ("Chicago Open", None), {"Chicago Open"})


def test_the_committed_data_passes():
    """Reads the real output/ on purpose, like the fee code parity test: a
    data change that breaks an edition key fails CI, not the next nightly."""
    report, _ = check_integrity(load_frames(os.path.join(PROJECT_ROOT, "output")))
    assert report.errors == []


def _write(frames, out):
    out.mkdir()
    for name, frame in frames.items():
        frame.to_csv(out / name, index=False)


def test_the_step_writes_the_registry_when_every_key_resolves(tmp_path):
    from pipeline.registry_step import step_edition_registry
    _write(_frames(), tmp_path / "output")
    step_edition_registry(str(tmp_path / "output"))
    reg = pd.read_csv(tmp_path / "output" / "edition_registry.csv")
    assert ("Chicago Open", 2026) in set(zip(reg["family"], reg["year"]))


def test_the_step_raises_and_writes_nothing_on_a_failed_check(tmp_path):
    from pipeline.registry_step import step_edition_registry
    frames = _frames()
    meta = frames["tournament_metadata.csv"]
    frames["tournament_metadata.csv"] = pd.concat([meta, meta.iloc[[0]]])
    _write(frames, tmp_path / "output")
    with pytest.raises(RuntimeError, match="Chicago Open 2026 has 2 rows"):
        step_edition_registry(str(tmp_path / "output"))
    assert not (tmp_path / "output" / "edition_registry.csv").exists()


def test_both_writers_run_the_step_and_both_workflows_commit_the_registry():
    def read(*parts):
        with open(os.path.join(PROJECT_ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()
    auto = read("auto_update.py")
    assert auto.index("step_edition_registry()\n") < auto.index("generate_manifest(OUTPUT_DIR)")
    enrich = read("run_enrichment.py")
    assert enrich.index("step_edition_registry()") < enrich.index("generate_manifest()")
    for workflow in ("daily_update.yml", "enrichment_scrapers.yml"):
        assert "output/edition_registry.csv" in read(".github", "workflows", workflow)


def test_an_empty_file_fails_instead_of_passing_vacuously():
    empty = _frames()["historical_standings.csv"].iloc[0:0]
    report, _ = check_integrity(_frames(**{"historical_standings.csv": empty}))
    assert report.errors == ["historical_standings.csv has no rows"]


def test_a_legacy_tid_with_a_year_is_resolved_not_exempted():
    summary = _frames()["tournament_summary.csv"].assign(tournament_year=[2012.0, 2026.0])
    report, resolutions = check_integrity(_frames(**{"tournament_summary.csv": summary}))
    assert report.errors == []
    assert "tournament_summary.csv: 1 row(s) exempt as legacy tid 10-75" not in exemption_lines(resolutions)
    assert ("42nd annual Continental Open", 2012) in set(build_registry(resolutions)
                                                        .set_index(["family", "year"]).index)


def test_a_fractional_year_breaks_the_contract():
    summary = _frames()["tournament_summary.csv"].assign(tournament_year=[None, 2026.5])
    report, _ = check_integrity(_frames(**{"tournament_summary.csv": summary}))
    assert any("whole_number" in e for e in report.errors)


def test_year_columns_that_disagree_with_the_key_are_warned():
    fees = _frames()["tournament_fees.csv"].assign(year=[2025, 2026])
    hist = _frames()["historical_tournaments.csv"].assign(year=[2024, 2025, 2020])
    report, _ = check_integrity(_frames(**{"tournament_fees.csv": fees,
                                           "historical_tournaments.csv": hist}))
    assert report.errors == []
    assert report.warnings == [
        "tournament_fees.csv row 2: year column 2025 disagrees with the URL's 2026",
        "historical_tournaments.csv row 2: '2025 Chicago Open' is filed under 2024, "
        "the year of its start_date",
    ]


def test_append_only_files_count_yearless_rows_instead_of_failing_forever():
    scrape = _frames()["daily_scrape.csv"]
    scrape.loc[len(scrape)] = ["2026-05-03", "Chicago Open", 510, "u"]
    ledger = pd.DataFrame({"family": ["Chicago Open", "Chicago Open"], "year": [2026, None]})
    report, resolutions = check_integrity(_frames(**{"daily_scrape.csv": scrape,
                                                    "forecast_ledger.csv": ledger}))
    assert report.errors == []
    lines = exemption_lines(resolutions)
    assert "daily_scrape.csv: 1 row(s) exempt as name carries no year" in lines
    assert "forecast_ledger.csv: 1 row(s) exempt as no year" in lines


def test_an_all_integer_summary_year_still_passes():
    summary = _frames()["tournament_summary.csv"].iloc[[1]].assign(tournament_year=[2026])
    report, _ = check_integrity(_frames(**{"tournament_summary.csv": summary}))
    assert report.errors == []
