"""v5 follow-up: validate_metadata_freshness must tell verified-absent from
unknown.

The old blanket WARNING counted every upcoming event with a null
early_bird_deadline as "missing" and prescribed update_metadata.py. For events
whose flyer IS scraped and simply has no early-bird tier (chesstour's modern
advance/onsite step, demoted by scrape_fees), that absence is source truth —
neutral EB features are correct, and the nightly warning was noise. Only
events with no flyer scraped yet are actionably unknown.
"""

import pandas as pd


from validate_scraped_data import validate_metadata_freshness  # noqa: E402

YEAR = 2099  # far future so start_date > today never goes stale


def _write_inputs(tmp_path, families, flyer_codes, titles=None):
    meta = pd.DataFrame({
        "family": families,
        "year": [YEAR] * len(families),
        "start_date": [f"{YEAR}-12-01"] * len(families),
        "early_bird_deadline": [None] * len(families),
    })
    meta_path = tmp_path / "tournament_metadata.csv"
    meta.to_csv(meta_path, index=False)
    # Like the real file: url always carries the <code><yy> page;
    # tournament_name is the page title when the parser found one.
    fees = pd.DataFrame({
        "tournament_name": titles or flyer_codes,
        "year": [YEAR] * len(flyer_codes),
        "early_bird_deadline": [None] * len(flyer_codes),
        "url": [f"https://www.chesstour.com/{c}.htm" for c in flyer_codes],
    })
    fees.to_csv(tmp_path / "tournament_fees.csv", index=False)
    return str(meta_path)


def test_flyer_found_by_url_when_the_row_is_named_by_its_page_title(tmp_path):
    # 2026-10-03: five events were reported as having no flyer although
    # mwcc26/eo26/... were scraped, because their rows are titled
    # "Midwest Class" etc. and the check compared codes to names.
    meta_path = _write_inputs(tmp_path, ["Eastern Open"], ["eo99"], titles=["Eastern Open"])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert report.warnings == []


def test_venue_suffix_resolves_through_the_canonical_family(tmp_path):
    meta_path = _write_inputs(
        tmp_path, ["Eastern Chess Congress (in New Jersey)"], ["ecco99"])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert report.warnings == []


def test_warning_no_longer_prescribes_spike_estimates(tmp_path):
    # update_metadata.py's spike estimates were the source of the fabricated
    # early-bird values in audit/eb-verification/2026-truth.json.
    meta_path = _write_inputs(tmp_path, ["Eastern Open"], [])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert "update_metadata" not in report.warnings[0]


def test_flyer_present_without_eb_tier_is_not_a_warning(tmp_path):
    # Atlantic Open maps to "ao"; ao99 flyer exists with no EB tier.
    meta_path = _write_inputs(tmp_path, ["Atlantic Open"], ["ao99"])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert report.warnings == []


def test_no_flyer_yet_still_warns(tmp_path):
    meta_path = _write_inputs(tmp_path, ["Eastern Open"], [])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert len(report.warnings) == 1
    assert "no flyer scraped yet" in report.warnings[0]
    assert "Eastern Open" in report.warnings[0]


def test_mixed_group_warns_only_for_the_unknown_family(tmp_path):
    meta_path = _write_inputs(
        tmp_path, ["Atlantic Open", "Eastern Open"], ["ao99"])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert len(report.warnings) == 1
    assert "Eastern Open" in report.warnings[0]
    assert "Atlantic Open" not in report.warnings[0]


def test_unmappable_family_is_named_as_missing_a_flyer_code(tmp_path):
    # A family with no FAMILY_TO_CODE entry cannot be verified against a
    # flyer, and its fees never fill: waiting for chesstour will not help, so
    # it gets its own warning rather than the "no flyer yet" one.
    meta_path = _write_inputs(tmp_path, ["Some Brand New Open", "Eastern Open"], [])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert len(report.warnings) == 2
    no_code = next(w for w in report.warnings if "no flyer code" in w)
    assert "Some Brand New Open" in no_code and "Eastern Open" not in no_code


def test_a_missing_fees_file_is_named_as_the_cause(tmp_path):
    meta_path = _write_inputs(tmp_path, ["Eastern Open"], ["eo99"])
    (tmp_path / "tournament_fees.csv").unlink()
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert any("tournament_fees.csv not found" in w for w in report.warnings)


def test_an_unparseable_start_date_is_reported_not_skipped(tmp_path):
    meta_path = _write_inputs(tmp_path, ["Eastern Open", "Atlantic Open"], ["eo99", "ao99"])
    meta = pd.read_csv(meta_path)
    meta.loc[1, "start_date"] = "TBD"
    meta.to_csv(meta_path, index=False)
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert len(report.warnings) == 1
    assert "start_date" in report.warnings[0] and "Atlantic Open" in report.warnings[0]
