"""fees/codes.py is the single home for the CCA code tables.

The three consumer modules re-import the tables under their legacy names, so
drift between "copies" is structurally impossible — these tests pin the
re-import identity and the documented probe-list discrepancies so a future
edit that reintroduces a private literal (or silently "fixes" a probe code)
fails loudly instead of drifting.
"""
import importlib.util
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from fees import codes  # noqa: E402


def test_validate_fees_views_are_the_canonical_objects():
    import validate_fees
    assert validate_fees.FAMILY_TO_CODE is codes.FAMILY_TO_CODE
    assert validate_fees.UNMAPPED_CODES is codes.UNMAPPED_CODES


def test_scrape_fees_probe_list_is_the_canonical_object():
    import scrape_fees
    assert scrape_fees.TOURNAMENT_CODES is codes.FLYER_PROBE_CODES


def test_scrape_entries_view_is_the_canonical_object():
    spec = importlib.util.spec_from_file_location(
        "scrape_entries_mod", os.path.join(PROJECT_ROOT, "scrape_entries.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ENTRY_LIST_CODES is codes.ENTRY_LIST_CODES


def test_probe_list_extras_are_exactly_the_documented_set():
    # Probe codes with no FAMILY_TO_CODE family are a recorded heuristic
    # surface. Growing or shrinking this set is a deliberate decision, not
    # drift: update fees/codes.py's discrepancy notes together with this set.
    mapped = set(codes.FAMILY_TO_CODE.values())
    extras = {c for c in codes.FLYER_PROBE_CODES if c not in mapped}
    assert extras == {"lib", "pho", "uso", "lvo", "dc"}


def test_documented_lib_lbo_discrepancy_still_stands():
    # FAMILY_TO_CODE says Liberty Bell Open = "lbo" while the probe list tries
    # "lib". Parked behavior question (ledger); if either side changes, the
    # notes in fees/codes.py must be resolved, not silently updated.
    assert codes.FAMILY_TO_CODE["Liberty Bell Open"] == "lbo"
    assert "lib" in codes.FLYER_PROBE_CODES
