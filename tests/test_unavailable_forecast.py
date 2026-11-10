"""A metadata card with no history keeps its observed count, without an invented forecast."""
from types import SimpleNamespace

import pandas as pd
import pytest

from sitebuild import metadata


@pytest.mark.parametrize('family', ['Saratoga Tournament Of-The-Ages Open', 'New York State Senior Championship'])
def test_no_history_card_remains_with_unavailable_forecast(monkeypatch, family):
    monkeypatch.setattr(metadata, 'TODAY', pd.Timestamp('2026-11-10'))
    meta = pd.DataFrame([{'family': family, 'year': 2027, 'start_date': '2027-04-01', 'end_date': '2027-04-03'}])
    summary = pd.DataFrame(columns=['family', 'tournament_year', 'final_count', 'is_online', 'is_covid'])
    cards = []
    metadata.build_metadata_cards(set(), 7, lambda *_: 0, lambda *_: ([[0, 3]], '2026-11-09'),
                                  {(family, 2027): {'gross': 3, 'wd': 1}},
                                  SimpleNamespace(curve_for=lambda _: {0: 1}), set(), lambda *_: None,
                                  meta, summary, cards)
    assert len(cards) == 1
    card = cards[0]
    assert card['family'] == family and card['current_count'] == 3 and card['withdrawal_count'] == 1
    assert card['status'] == 'live' and card['daily_data'] == [[0, 3]]
    assert all(card[k] is None for k in ['point_estimate', 'ci_lower', 'ci_upper'])
    assert card['prediction_source'] == 'insufficient_history'


def test_supported_historical_average_remains_unchanged(monkeypatch):
    monkeypatch.setattr(metadata, 'TODAY', pd.Timestamp('2026-11-10'))
    family = 'Example Open'
    meta = pd.DataFrame([{'family': family, 'year': 2027, 'start_date': '2027-04-01', 'end_date': '2027-04-03'}])
    summary = pd.DataFrame([{'family': family, 'tournament_year': 2025, 'final_count': 240,
                             'is_online': False, 'is_covid': False}])
    cards = []
    metadata.build_metadata_cards(set(), 7, lambda *_: 0, lambda *_: ([], None), {},
                                  SimpleNamespace(curve_for=lambda _: {0: 1}), set(), lambda *_: None,
                                  meta, summary, cards)
    assert cards[0]['point_estimate'] == 240
    assert cards[0]['ci_lower'] == 168 and cards[0]['ci_upper'] == 312


def test_unavailable_forecast_browser_consumers():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if node is None:
        pytest.skip('node not available')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, str(root / 'tests/js/unavailable_forecast_driver.js')],
                            cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence['email_lengths'] == 3 and all(evidence.values())
