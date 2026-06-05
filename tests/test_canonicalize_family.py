"""Regression tests for venue-suffix folding in canonicalize_family.

A relocated tournament edition ("Eastern Class Championships (in Connecticut)")
must canonicalize onto its historical series ("Eastern Class Championships") so
the model finds prior editions instead of treating it as a brand-new family
with zero history. That zero-history path is what pinned the 2026 Eastern
events to the flat 100 / CI 70-130 default and froze the World Open U13 card on
a historical average (stale-roster bug, June 2026).
"""
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from tournament_aliases import canonicalize_family, strip_venue_suffix


def test_strip_venue_suffix_removes_in_state_qualifier():
    assert strip_venue_suffix(
        "Eastern Class Championships (in Connecticut)"
    ) == "Eastern Class Championships"
    assert strip_venue_suffix(
        "Eastern Chess Congress (in New Jersey)"
    ) == "Eastern Chess Congress"


def test_strip_venue_suffix_is_case_insensitive_and_tolerates_spacing():
    assert strip_venue_suffix("Foo Open (in  Ohio)") == "Foo Open"
    assert strip_venue_suffix("Foo Open (In Texas)") == "Foo Open"


def test_strip_venue_suffix_preserves_plain_names():
    assert strip_venue_suffix("World Open Under 13") == "World Open Under 13"
    assert strip_venue_suffix("Chicago Open") == "Chicago Open"


def test_strip_venue_suffix_leaves_non_venue_parentheticals():
    # Only "(in <location>)" venue qualifiers are stripped; other trailing
    # parentheticals stay so we don't silently merge genuinely distinct events.
    assert strip_venue_suffix("Some Open (Open Section)") == "Some Open (Open Section)"


def test_canonicalize_folds_relocated_eastern_class_onto_history():
    # Folds onto the FAMILY_GROUPS canonical so historical editions match.
    assert canonicalize_family(
        "Eastern Class Championships (in Connecticut)"
    ) == "Eastern Class Championships"


def test_canonicalize_folds_relocated_eastern_congress():
    # No FAMILY_GROUP entry for Eastern Chess Congress, but the venue suffix
    # must still be stripped so it matches its own historical editions.
    assert canonicalize_family(
        "Eastern Chess Congress (in New Jersey)"
    ) == "Eastern Chess Congress"


def test_canonicalize_u13_unchanged_by_venue_strip():
    # U13 has no venue suffix; canonicalization (to the FAMILY_GROUPS head)
    # must be unaffected by the new strip.
    assert canonicalize_family(
        "World Open Under 13 Championship"
    ) == "World Open Under 13 Championship"
