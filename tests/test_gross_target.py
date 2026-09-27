"""The forecast is of gross entries: the count the site shows and every
final since 2010 records, withdrawals included. Nothing in the model may
quietly turn it into a net forecast."""
from model.core import N5v4_Final


def test_withdrawal_data_does_not_move_the_forecast(summary_df, daily_df):
    model = N5v4_Final()
    model.fit(summary_df, daily_df, verbose_standings_join=False)
    before = model.predict_nowcast(300, 28, "Chicago Open")
    model.family_withdrawal_rates = {"Chicago Open": 0.10}
    assert model.predict_nowcast(300, 28, "Chicago Open") == before


def test_there_is_no_withdrawal_stage_to_switch_on():
    assert "withdrawal" not in N5v4_Final.ABLATABLE_STAGES
