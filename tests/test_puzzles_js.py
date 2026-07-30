"""Tests for docs/tab_puzzles.js — the pure FEN/board/move helpers.

C6 of the app.js split. The puzzle engine's board math (FEN parse/serialize,
UCI decoding, en passant, castling, promotion) is pure logic with no DOM, so
it runs under node via tests/js/puzzles_driver.js. Skipped when node is
unavailable, matching test_daily_series_js.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "puzzles_driver.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                          cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_fen_parse_roundtrips(res):
    assert res["parsed_turn"] == "w"
    assert res["roundtrip"] == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def test_uci_decoding(res):
    assert res["uci"] == {"fr": 6, "fc": 4, "tr": 4, "tc": 4, "promo": None}
    assert res["uci_promo"] == "q"


def test_plain_move(res):
    assert res["after_e4"] == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"


def test_promotion_auto_queens_with_movers_color(res):
    assert res["after_promo"] == "Q7/8/8/8/8/8/8/K6k"


def test_en_passant_removes_the_passed_pawn(res):
    """A diagonal pawn move onto an empty square must clear the bypassed
    pawn, or the board silently desyncs from the solution line."""
    assert res["after_ep"] == "k7/8/3P4/8/8/8/8/K7"


def test_castling_moves_the_rook_too(res):
    assert res["after_castle"] == "k7/8/8/8/8/8/8/5RK1"


def test_piece_lookup_tables(res):
    assert res["unicode_white_king"] == "♔"
    assert res["name_black_queen"] == "black queen"
