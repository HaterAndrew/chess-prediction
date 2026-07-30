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


def _write_inputs(tmp_path, families, flyer_codes):
    meta = pd.DataFrame({
        "family": families,
        "year": [YEAR] * len(families),
        "start_date": [f"{YEAR}-12-01"] * len(families),
        "early_bird_deadline": [None] * len(families),
    })
    meta_path = tmp_path / "tournament_metadata.csv"
    meta.to_csv(meta_path, index=False)
    fees = pd.DataFrame({
        "tournament_name": flyer_codes,
        "year": [YEAR] * len(flyer_codes),
        "early_bird_deadline": [None] * len(flyer_codes),
    })
    fees.to_csv(tmp_path / "tournament_fees.csv", index=False)
    return str(meta_path)


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


def test_unmappable_family_counts_as_unknown(tmp_path):
    # A family with no FAMILY_TO_CODE entry cannot be verified against a
    # flyer — it must stay in the WARNING group, not silently vanish.
    meta_path = _write_inputs(tmp_path, ["Some Brand New Open"], [])
    report = validate_metadata_freshness(csv_path=meta_path, year=YEAR)
    assert len(report.warnings) == 1
    assert "Some Brand New Open" in report.warnings[0]
