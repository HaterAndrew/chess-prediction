"""The long-lead anchor blend: weight resolution, ablation, and the floor.

The anchor pulls the point estimate toward the family's most recent final count
at horizons past T-14, where the naive "last year" forecast measured better than
the ensemble (2026-09-07 review). These tests pin the parts that would otherwise
change published predictions without failing anything: the bucket boundaries,
the instance-override contract the fitting script depends on, and the guarantee
that the anchor is off inside T-14.
"""
from importlib import import_module

import numpy as np
import pytest


m04c = import_module("04c_final_model")


def test_anchor_is_off_inside_two_weeks():
    """The model beats the baseline from T-14 inward, so it must keep the wheel."""
    model = m04c.N5v4_Final()
    for T in (0, 1, 3, 4, 7, 8, 14):
        assert model._anchor_weight(T) == 0.0, f"T={T}"


def test_anchor_engages_past_two_weeks():
    model = m04c.N5v4_Final()
    assert model._anchor_weight(15) == 0.40
    assert model._anchor_weight(28) == 0.40
    assert model._anchor_weight(29) == 0.60
    assert model._anchor_weight(90) == 0.60
    assert model._anchor_weight(10_000) == 0.60


def test_instance_override_beats_the_class_default():
    model = m04c.N5v4_Final()
    model.anchor_weights = ((14, 0.1), (28, 0.3), (None, 0.4))
    assert model._anchor_weight(1) == 0.1
    assert model._anchor_weight(90) == 0.4
    assert m04c.N5v4_Final()._anchor_weight(90) == 0.60


def test_an_all_zero_override_is_honoured():
    """The `or` idiom used for ensemble_weights would silently ignore this.

    An all-zero table is falsy, and it is exactly how fit_anchor_weights.py
    measures the model without the anchor. If the override fell back to the
    class default here, every "no anchor" row in the sweep would secretly be an
    anchored run and the fitted weights would be chosen against a phantom
    baseline.
    """
    model = m04c.N5v4_Final()
    model.anchor_weights = ((14, 0.0), (28, 0.0), (None, 0.0))
    assert model._anchor_weight(90) == 0.0


def test_anchor_is_ablatable():
    model = m04c.N5v4_Final()
    assert 'anchor' in m04c.N5v4_Final.ABLATABLE_STAGES
    model.set_stage_flags(anchor=False)
    assert model._stage_on('anchor') is False


def test_class_default_is_unchanged():
    """Fitted by scripts/fit_anchor_weights.py; do not drift without re-running."""
    assert m04c.N5v4_Final.ANCHOR_WEIGHTS == (
        (14, 0.0), (28, 0.40), (None, 0.60))


# --- behaviour through predict_nowcast -------------------------------------
#
# These fit a real model on the shared fixtures rather than stubbing state.
# predict_nowcast has thirteen stages and several guard paths that return early;
# a hand-built stub reaches the anchor only by accident, and would keep passing
# if the stage moved behind one of those guards.


def _fitted(summary_df, daily_df, anchor=True):
    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)
    if not anchor:
        model.set_stage_flags(anchor=False)
    return model


def _anchored_family(model):
    """A family whose most recent final is far from the current-count scale."""
    for fam, recent in sorted(model.family_recent_final.items()):
        if recent and recent > 200 and model.family_n_editions.get(fam, 0) >= 2:
            return fam, recent
    pytest.skip("fixture corpus has no family large enough to test the anchor")


def test_anchor_moves_the_long_lead_point_toward_last_year(summary_df, daily_df):
    on = _fitted(summary_df, daily_df, anchor=True)
    off = _fitted(summary_df, daily_df, anchor=False)
    fam, recent = _anchored_family(on)
    # Current count well below last year's final, so the anchor pulls upward.
    count = int(recent * 0.2)
    p_on = on.predict_nowcast(count, 90, fam)[0]
    p_off = off.predict_nowcast(count, 90, fam)[0]
    assert p_on > p_off, f"{fam}: anchor did not raise the T-90 point estimate"
    # Deliberately not asserting p_on lands between p_off and the anchor. The
    # blend does land there, but the trend adjustment and the ratio floors run
    # after it and can carry the result past the anchor. Direction is the
    # invariant; containment would be asserting something the pipeline does not
    # promise, and it fails on the fixture corpus by 8 entries.
    assert p_on < recent * 2, f"{fam}: anchor overshot to {p_on} against {recent}"


def test_anchor_never_pulls_below_what_has_already_registered(summary_df, daily_df):
    """A family that grew sharply must not be dragged under its own floor."""
    on = _fitted(summary_df, daily_df, anchor=True)
    fam, recent = _anchored_family(on)
    count = int(recent * 2)          # already past last year's entire field
    point, low, high = on.predict_nowcast(count, 90, fam)
    assert point >= count
    assert low <= point <= high


@pytest.mark.parametrize('T', [3, 7, 14])
def test_anchor_leaves_short_lead_predictions_alone(summary_df, daily_df, T):
    """Inside T-14 the weight is zero, so no prediction may move at all."""
    on = _fitted(summary_df, daily_df, anchor=True)
    off = _fitted(summary_df, daily_df, anchor=False)
    fam, recent = _anchored_family(on)
    count = int(recent * 0.6)
    assert np.allclose(on.predict_nowcast(count, T, fam),
                       off.predict_nowcast(count, T, fam))


def test_a_family_with_no_history_is_unaffected(summary_df, daily_df):
    """No anchor value means no blend, not a blend toward zero."""
    on = _fitted(summary_df, daily_df, anchor=True)
    off = _fitted(summary_df, daily_df, anchor=False)
    unknown = 'Definitely Not A Real Family'
    assert unknown not in on.family_recent_final
    assert np.allclose(on.predict_nowcast(120, 90, unknown),
                       off.predict_nowcast(120, 90, unknown))
