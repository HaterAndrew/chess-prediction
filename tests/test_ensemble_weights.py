"""The ensemble weight table must resolve lead times the way the old ladder did.

_ensemble_weight replaced a hardcoded if/elif chain (audit v3 T9) so the
weight-fitting script can try candidate tables. A refactor that shifted a bucket
boundary by a day would change predictions for every event at that lead time
without failing anything, so the boundaries are pinned here explicitly.
"""
from importlib import import_module


m04c = import_module("04c_final_model")


def test_default_table_matches_the_ladder_it_replaced():
    model = m04c.N5v4_Final()
    # Exactly the branches of the pre-T9 if/elif chain, boundaries included.
    expected = {
        0: 0.80, 1: 0.80, 3: 0.80,      # days_remaining <= 3
        4: 0.55, 7: 0.55,               # <= 7
        8: 0.30, 14: 0.30, 28: 0.30,    # <= 28
        29: 0.15, 60: 0.15, 365: 0.15,  # else
    }
    for T, w in expected.items():
        assert model._ensemble_weight(T) == w, f"T={T}"


def test_instance_override_beats_the_class_default():
    model = m04c.N5v4_Final()
    model.ensemble_weights = ((3, 0.10), (7, 0.20), (28, 0.30), (None, 0.40))
    assert model._ensemble_weight(1) == 0.10
    assert model._ensemble_weight(90) == 0.40
    # The class default is untouched, so one fitting run cannot leak into the
    # next model built in the same process.
    assert m04c.N5v4_Final()._ensemble_weight(1) == 0.80


def test_open_ended_bucket_catches_everything_above_the_last_bound():
    model = m04c.N5v4_Final()
    assert model._ensemble_weight(10_000) == 0.15


def test_class_default_is_unchanged():
    """T9 measured these; they should not drift without re-running the fitter."""
    assert m04c.N5v4_Final.ENSEMBLE_WEIGHTS == (
        (3, 0.80), (7, 0.55), (28, 0.30), (None, 0.15))
