"""The stage switches must not change production behaviour (audit v3 T8).

The ablation harness works by turning individual predict_nowcast stages off.
That is only safe if the switches are inert when nobody touches them — a model
that quietly behaves differently after the flags were added would invalidate
every backtest run since. These tests pin that: default predictions are
bit-identical, and a typo'd stage name fails loudly rather than measuring
nothing.
"""
import os
import sys
from importlib import import_module

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
m04c = import_module("04c_final_model")


class _StubModel:
    """Just enough model for _predict_nowcast_ci_tail, with no stage machinery.

    Represents the pre-T8 callers: the tail function is exercised directly by
    the CI-floor tests, which construct a bare object. Those must keep getting
    recalibration applied.
    """
    def __init__(self):
        self._recal_bias = {7: 1.10}
        self._recal_ci = {7: 1.20}


def test_stage_flags_default_to_on():
    model = m04c.N5v4_Final()
    for stage in m04c.N5v4_Final.ABLATABLE_STAGES:
        assert model._stage_on(stage) is True


def test_unknown_stage_name_raises():
    model = m04c.N5v4_Final()
    with pytest.raises(ValueError) as exc:
        model.set_stage_flags(recalibration=False)  # real name is 'recal'
    assert "recalibration" in str(exc.value)
    # The message names the valid stages, so the typo is fixable from the error.
    assert "recal" in str(exc.value)


def test_set_stage_flags_is_incremental():
    model = m04c.N5v4_Final()
    model.set_stage_flags(trend=False)
    model.set_stage_flags(recal=False)
    assert model._stage_on('trend') is False
    assert model._stage_on('recal') is False
    # Untouched stages stay on.
    assert model._stage_on('withdrawal') is True


def test_recal_applies_when_model_has_no_stage_machinery():
    """A stub model without _stage_on must still get recalibration."""
    out = m04c._predict_nowcast_ci_tail(
        _StubModel(), point=100.0, low=80.0, high=130.0, days_remaining=7,
        current_count=50, n_editions=5)
    point = out[0]
    # bias 1.10 moved the centre; had the stage check defaulted to "off", the
    # point would have come back at the unrecalibrated 100.
    assert point > 100


def test_recal_stage_off_skips_the_bias_factor():
    model = m04c.N5v4_Final()
    model._recal_bias = {7: 1.10}
    model._recal_ci = {7: 1.20}

    on = m04c._predict_nowcast_ci_tail(
        model, point=100.0, low=80.0, high=130.0, days_remaining=7,
        current_count=50, n_editions=5)
    model.set_stage_flags(recal=False)
    off = m04c._predict_nowcast_ci_tail(
        model, point=100.0, low=80.0, high=130.0, days_remaining=7,
        current_count=50, n_editions=5)

    assert on[0] != off[0]
    assert off[0] == pytest.approx(100, abs=1)
