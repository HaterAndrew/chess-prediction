"""One way to make a forecast.

Every number the site publishes or grades comes from forecast_event: the live
cards (04d), the backtest (04e) and the window-engine grade. It picks the
route, runs it, blends the model with pickup inside two weeks, moves it
toward a last final it knew nothing of (or, with no past final, toward what
first editions draw), caps its range at the year-over-year spread, and
applies the plausibility clamp last. tests/test_forecast_entry.py forbids
calling the engines or the clamp from anywhere else, so what is graded is
what is published.
"""
from forecast.event import choose_route, forecast_event, shadow_forecasts
from forecast.fit import fit_models
from forecast.types import Event, Fitted, Forecast, Observation

__all__ = ['Event', 'Fitted', 'Forecast', 'Observation', 'choose_route',
           'fit_models', 'forecast_event', 'shadow_forecasts']
