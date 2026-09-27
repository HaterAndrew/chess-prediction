"""The model can be fitted and run as of a date other than today.

The walk-forward backtest fits the model as each past season's production
run would have: training on earlier seasons, calibrating relative to that
season, joining only the standings known then, and dating the feature
adjustments at the forecast date. Defaults leave today's run unchanged.
"""
from datetime import datetime

import pandas as pd

import model.nowcast as nowcast
import ratio_model
from model.core import N5v4_Final
from shared.season import CURRENT_SEASON


def _fit(summary_df, daily_df, **kw):
    model = N5v4_Final()
    model.fit(summary_df, daily_df, verbose_standings_join=False, **kw)
    return model


def test_fit_trains_only_on_seasons_before_the_one_predicted(summary_df, daily_df):
    assert 2021 in _fit(summary_df, daily_df, season=2026)._fit_tids
    assert 2021 not in _fit(summary_df, daily_df, season=2025)._fit_tids, "a 2025 run never saw 2025"
    assert _fit(summary_df, daily_df)._fit_tids == _fit(summary_df, daily_df, season=CURRENT_SEASON)._fit_tids


def test_completed_events_of_the_season_still_train(summary_df, daily_df):
    assert 3001 in _fit(summary_df, daily_df, season=2026, completed_tids={3001})._fit_tids


def test_interval_calibration_window_moves_with_the_season(summary_df, daily_df, monkeypatch):
    seen = []
    monkeypatch.setattr(N5v4_Final, "_calibrate",
                        lambda self, valid, daily, cal_max_year=None: seen.append(cal_max_year))
    _fit(summary_df, daily_df, season=2026)
    _fit(summary_df, daily_df, season=2026, completed_tids={3001})
    _fit(summary_df, daily_df, season=2027, completed_tids={3001})
    assert seen == [2024, 2025, 2026]


def test_standings_passed_in_replace_the_file(summary_df, daily_df):
    standings = pd.DataFrame({"tournament_name": ["Harbor Open", "Harbor Open"],
                              "year": [2023, 2024], "total_players": [120, 140]})
    model = _fit(summary_df, daily_df, standings=standings)
    assert model.family_mean_final["Harbor Open"] == 130
    empty = standings.iloc[0:0]
    assert "Harbor Open" not in _fit(summary_df, daily_df, standings=empty).family_mean_final


def test_features_are_dated_at_the_forecast_date(summary_df, daily_df, monkeypatch):
    model = _fit(summary_df, daily_df)
    dates = []

    def spy(as_of, event_start, eb_deadline):
        dates.append(as_of)
        return {}
    monkeypatch.setattr(nowcast, "compute_all_features", spy)
    monkeypatch.setattr(nowcast, "compute_adjustment_factor", lambda features, T: 1.0)
    as_of = datetime(2025, 3, 1)
    model.predict_nowcast(300, 28, "Chicago Open", event_start_date="2025-05-22", as_of=as_of)
    model.predict_nowcast(300, 28, "Chicago Open", event_start_date="2025-05-22")
    assert dates == [as_of, nowcast.TODAY]


def test_ratio_model_trains_only_on_seasons_before_the_one_predicted(summary_df, daily_df):
    with_2025 = ratio_model.build_ratio_model(summary_df, daily_df, season=2026)
    without = ratio_model.build_ratio_model(summary_df, daily_df, season=2025)
    n = lambda r: sum(len(v) for v in r["Chicago Open"].values())  # noqa: E731
    assert n(with_2025) > n(without)
