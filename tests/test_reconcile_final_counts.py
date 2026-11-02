"""Regression tests for reconcile_final_counts.

Covers the two jobs the module does when the manual CCA export is absent (every
CI run):
  1. Bump an existing event's final_count up to the live daily_scrape peak so the
     04e freshness guard doesn't abort on stale early-registration truth labels.
  2. (H2) Append a roster-pending skeleton for a *scraped* event that has no
     summary row yet, so a 2026 tournament whose registration opened after the
     last export is no longer invisible to the whole pipeline. The skeleton
     carries has_timestamps=False so every 04c/04e training/grading filter
     excludes it until a real export supplies per-registration timestamps.
"""
import os
from pathlib import Path

import pytest

import pandas as pd


from reconcile_final_counts import reconcile_final_counts  # noqa: E402


def _summary(out):
    return pd.read_csv(os.path.join(out, "tournament_summary.csv"))


def test_bumps_existing_final_count_to_scrape_peak(tmp_output):
    """Atlantic City Open is in both summary and scrape; if the scrape peak
    exceeds the frozen final_count it is raised to the peak (gross semantics)."""
    before = _summary(tmp_output)
    ac_before = int(before.loc[before["tournament_name"] == "2026 Atlantic City Open",
                               "final_count"].iloc[0])
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    ac_after = int(after.loc[after["tournament_name"] == "2026 Atlantic City Open",
                             "final_count"].iloc[0])
    # scrape peak for Atlantic City is 225; final_count is raised to at least that
    # (never lowered below the frozen snapshot).
    assert ac_after >= ac_before
    assert ac_after == max(ac_before, 225)


def test_appends_roster_pending_for_unknown_scrape_event(tmp_output):
    """H2: DC International and Hartford are scraped but absent from summary.
    Reconcile must append skeleton rows for them, not silently drop them."""
    before = set(_summary(tmp_output)["tournament_name"])
    assert "2026 Hartford Open" not in before
    assert "2026 DC International" not in before

    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    names = set(after["tournament_name"])
    assert "2026 Hartford Open" in names
    assert "2026 DC International" in names

    hartford = after.loc[after["tournament_name"] == "2026 Hartford Open"].iloc[0]
    # final_count is the gross scrape peak (5 in the fixture)
    assert int(hartford["final_count"]) == 5
    assert int(hartford["tournament_year"]) == 2026
    assert hartford["family"] == "Hartford Open"
    # The load-bearing safety flag: no timestamps => excluded from every
    # 04c/04e training and grading filter until a real export arrives.
    assert bool(hartford["has_timestamps"]) is False
    assert bool(hartford["roster_pending"]) is True


def test_appended_tids_are_unique(tmp_output):
    """Skeleton rows get fresh tids above the existing max so nothing collides."""
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert after["tid"].is_unique


def test_existing_rows_marked_not_roster_pending(tmp_output):
    """When the roster_pending column is introduced, pre-existing rows default to
    False, never NaN/True — they are real roster entries."""
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    real = after.loc[after["tournament_name"] == "2026 Atlantic City Open"].iloc[0]
    assert bool(real["roster_pending"]) is False


def test_no_scrape_file_is_noop(tmp_output):
    """Missing daily_scrape.csv => return 0, summary untouched (safe to call
    blindly in the export-present branch)."""
    os.remove(os.path.join(tmp_output, "daily_scrape.csv"))
    before = _summary(tmp_output)
    n = reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert n == 0
    pd.testing.assert_frame_equal(before, after)


def test_return_counts_bumped_plus_appended(tmp_output):
    """Return value is the total number of tournaments changed (raised OR
    appended), not just the bumped ones."""
    n = reconcile_final_counts(tmp_output, verbose=False)
    # At least the 2 appended (Hartford, DC International); Atlantic City may also
    # bump depending on the frozen snapshot, so assert the appended floor.
    assert n >= 2


# ── v5 Cat R: canonical identity — the exact-name join created duplicate rows
# (export "World Open  top 6 sections" vs scraper "World Open, top 6 sections",
# tid 4248 vs 4434) and the skeleton family string didn't match the training
# rows' canonical form. ──────────────────────────────────────────────────────

def _append_summary_row(out, **kw):
    path = os.path.join(out, "tournament_summary.csv")
    df = pd.read_csv(path)
    row = {c: pd.NA for c in df.columns}
    row.update(kw)
    # Drop all-NA columns pre-concat (same dance as the module) so pandas'
    # empty-entry concat deprecation stays quiet; the column union restores them.
    new_df = pd.DataFrame([row]).dropna(axis=1, how="all")
    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(path, index=False)


def _append_scrape_rows(out, name, counts, start="2026-06-01"):
    path = os.path.join(out, "daily_scrape.csv")
    df = pd.read_csv(path)
    dates = pd.date_range(start, periods=len(counts))
    add = pd.DataFrame([{"date": d.strftime("%Y-%m-%d"), "tournament_name": name,
                         "entry_count": c, "url": "https://example.invalid"}
                        for d, c in zip(dates, counts)])
    pd.concat([df, add], ignore_index=True).to_csv(path, index=False)


def test_comma_variant_scrape_name_does_not_spawn_skeleton(tmp_output):
    """A scrape spelling that canonicalizes onto an existing summary row must
    bump that row (canonical fallback pass), never append a duplicate skeleton."""
    _append_summary_row(tmp_output, tid=4248,
                        tournament_name="2026 World Open  top 6 sections",
                        family="World Open top 6 sections",
                        tournament_year=2026.0, final_count=28,
                        has_timestamps=True, ts_count=28,
                        is_covid=False, is_online=False, early_bird_spike=False)
    _append_scrape_rows(tmp_output, "2026 World Open, top 6 sections",
                        [900, 1000, 1066])

    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert "2026 World Open, top 6 sections" not in set(after["tournament_name"])
    real = after.loc[after["tournament_name"] == "2026 World Open  top 6 sections"]
    assert len(real) == 1
    assert int(real.iloc[0]["final_count"]) == 1066


def test_heals_existing_skeleton_real_duplicate_pair(tmp_output):
    """A pre-existing skeleton whose canonical (family, year) collides with a
    real row is dropped; the real row inherits the group's max final_count."""
    _append_summary_row(tmp_output, tid=4248,
                        tournament_name="2026 World Open  top 6 sections",
                        family="World Open top 6 sections",
                        tournament_year=2026.0, final_count=28,
                        has_timestamps=True, ts_count=28,
                        is_covid=False, is_online=False, early_bird_spike=False,
                        roster_pending=False)
    _append_summary_row(tmp_output, tid=4434,
                        tournament_name="2026 World Open, top 6 sections",
                        family="World Open, top 6 sections",
                        tournament_year=2026.0, final_count=1066,
                        has_timestamps=False, ts_count=0,
                        is_covid=False, is_online=False, early_bird_spike=False,
                        roster_pending=True)

    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert 4434 not in set(after["tid"])
    real = after.loc[after["tid"] == 4248]
    assert len(real) == 1
    assert int(real.iloc[0]["final_count"]) == 1066
    assert bool(real.iloc[0]["has_timestamps"]) is True


def test_heal_is_idempotent(tmp_output):
    """Running reconcile twice after a heal changes nothing the second time."""
    _append_summary_row(tmp_output, tid=4248,
                        tournament_name="2026 World Open  top 6 sections",
                        family="World Open top 6 sections",
                        tournament_year=2026.0, final_count=28,
                        has_timestamps=True, ts_count=28,
                        is_covid=False, is_online=False, early_bird_spike=False,
                        roster_pending=False)
    _append_summary_row(tmp_output, tid=4434,
                        tournament_name="2026 World Open, top 6 sections",
                        family="World Open, top 6 sections",
                        tournament_year=2026.0, final_count=1066,
                        has_timestamps=False, ts_count=0,
                        is_covid=False, is_online=False, early_bird_spike=False,
                        roster_pending=True)
    reconcile_final_counts(tmp_output, verbose=False)
    first = _summary(tmp_output)
    reconcile_final_counts(tmp_output, verbose=False)
    second = _summary(tmp_output)
    pd.testing.assert_frame_equal(first, second)


def test_new_skeleton_family_is_canonical(tmp_output):
    """Skeleton rows store the canonical family form so 04d's family joins,
    history lookups and n_editions counts resolve; tournament_name stays
    scraper-exact."""
    _append_scrape_rows(tmp_output, "2026 World Open, lower sections", [40, 60, 93])

    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    row = after.loc[after["tournament_name"] == "2026 World Open, lower sections"]
    assert len(row) == 1
    assert row.iloc[0]["family"] == "World Open lower sections"
    assert bool(row.iloc[0]["roster_pending"]) is True


def test_two_spellings_of_one_new_edition_spawn_one_skeleton(tmp_output):
    """Two scrape names for one edition with no summary row (CCA respelled the
    card) used to append a skeleton each: the summary then held two rows for
    one edition, which the edition registry rejects every night."""
    _append_scrape_rows(tmp_output, "2026 World Open, lower sections", [40, 60])
    _append_scrape_rows(tmp_output, "2026 World Open lower sections", [70, 80])
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    lower = after.loc[after["family"] == "World Open lower sections"]
    assert len(lower) == 1
    assert int(lower.iloc[0]["final_count"]) == 80


# Reviewed outcomes contain aggregates only, never player rows or fake scrape days.
def _correction(out, **changes):
    row = dict(family="Atlantic City Open", year=2026, end_date="2026-04-05",
               verified_on="2026-11-02", last_registration="2026-04-03",
               active=401, withdrawn=23,
               source_url="https://www.chessaction.com/tournaments/advance_entry_list.php?tid=aco26")
    row.update(changes)
    pd.DataFrame([row]).to_csv(Path(out) / "final_count_corrections.csv", index=False)
    pd.DataFrame([dict(family="Atlantic City Open", year=2026, end_date="2026-04-05")]).to_csv(
        Path(out) / "tournament_metadata.csv", index=False)


def test_verified_final_corrects_label_without_rewriting_observations(tmp_output):
    _correction(tmp_output)
    scrape = (Path(tmp_output) / "daily_scrape.csv").read_bytes()
    before = _summary(tmp_output)
    reconcile_final_counts(tmp_output, verbose=False, as_of="2026-11-02")
    after = _summary(tmp_output)
    row = after.loc[after.family == "Atlantic City Open"].iloc[0]
    assert row.final_count == 424
    old = before.loc[before.family == "Atlantic City Open"].iloc[0]
    assert row.ts_count == old.ts_count
    assert row.last_reg == old.last_reg
    assert (Path(tmp_output) / "daily_scrape.csv").read_bytes() == scrape
    first = (Path(tmp_output) / "tournament_summary.csv").read_bytes()
    assert reconcile_final_counts(tmp_output, verbose=False, as_of="2026-11-02") == 0
    assert (Path(tmp_output) / "tournament_summary.csv").read_bytes() == first


def test_verified_final_is_not_available_before_verification(tmp_output):
    _correction(tmp_output)
    reconcile_final_counts(tmp_output, verbose=False, as_of="2026-11-01")
    assert _summary(tmp_output).loc[lambda d: d.family == "Atlantic City Open", "final_count"].iloc[0] < 424


def test_verified_final_does_not_lower_a_newer_peak(tmp_output):
    _correction(tmp_output)
    _append_scrape_rows(tmp_output, "2026 Atlantic City Open", [450])
    reconcile_final_counts(tmp_output, verbose=False)
    assert _summary(tmp_output).loc[lambda d: d.family == "Atlantic City Open", "final_count"].iloc[0] == 450


@pytest.mark.parametrize("changes", [
    {"active": -1}, {"withdrawn": "2.5"}, {"year": "2026.0"},
    {"verified_on": "2026-04-05"}, {"last_registration": "2026-04-06"},
    {"end_date": "2026-04-04"}, {"family": "Unknown Open"},
    {"source_url": "https://outside.invalid/tournaments/list"},
])
def test_invalid_verified_final_fails_before_writing(tmp_output, changes):
    _correction(tmp_output, **changes)
    before = (Path(tmp_output) / "tournament_summary.csv").read_bytes()
    with pytest.raises(ValueError):
        reconcile_final_counts(tmp_output, verbose=False)
    assert (Path(tmp_output) / "tournament_summary.csv").read_bytes() == before


def test_duplicate_verified_final_is_rejected(tmp_output):
    _correction(tmp_output)
    path = Path(tmp_output) / "final_count_corrections.csv"
    frame = pd.read_csv(path)
    pd.concat([frame, frame]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_final_counts(tmp_output, verbose=False)


def test_scrape_and_verified_bumps_count_an_edition_once(tmp_output):
    _correction(tmp_output)
    # First create unrelated pending rows so this run changes only ACO.
    (Path(tmp_output) / "final_count_corrections.csv").unlink()
    reconcile_final_counts(tmp_output, verbose=False)
    _correction(tmp_output)
    frame = _summary(tmp_output)
    frame.loc[frame.family == "Atlantic City Open", "final_count"] = 100
    frame.to_csv(Path(tmp_output) / "tournament_summary.csv", index=False)
    assert reconcile_final_counts(tmp_output, verbose=False) == 1
