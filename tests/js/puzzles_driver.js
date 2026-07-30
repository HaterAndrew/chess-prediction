// Node driver for docs/tab_puzzles.js — exercised by tests/test_puzzles_js.py.
// Runs the pure FEN/board/move helpers under node and prints one JSON blob;
// the pytest side asserts on it (daily_series driver pattern).
const path = require('path');
const P = require(path.join(__dirname, '..', '..', 'docs', 'tab_puzzles.js'));

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const parsed = P.parseFEN(START);

// e2e4 from the start position.
const afterE4 = P.applyUCIMove(parsed.board, 'e2e4', 'w');

// Promotion: white pawn a7a8q auto-queens.
const promoBoard = P.parseFEN('8/P7/8/8/8/8/8/K6k w - - 0 1').board;
const afterPromo = P.applyUCIMove(promoBoard, 'a7a8q', 'w');

// En passant: e5 pawn takes d6 in passing; the d5 black pawn must vanish.
const epBoard = P.parseFEN('k7/8/8/3pP3/8/8/8/K7 w - - 0 1').board;
const afterEP = P.applyUCIMove(epBoard, 'e5d6', 'w');

// Castling kingside: e1g1 must also move the h1 rook to f1.
const castleBoard = P.parseFEN('k7/8/8/8/8/8/8/4K2R w K - 0 1').board;
const afterCastle = P.applyUCIMove(castleBoard, 'e1g1', 'w');

const out = {
  parsed_turn: parsed.turn,
  roundtrip: P.boardToFEN(parsed.board),
  uci: P.uciToCoords('e2e4'),
  uci_promo: P.uciToCoords('a7a8q').promo,
  after_e4: P.boardToFEN(afterE4),
  after_promo: P.boardToFEN(afterPromo),
  after_ep: P.boardToFEN(afterEP),
  after_castle: P.boardToFEN(afterCastle),
  unicode_white_king: P.PIECE_UNICODE.K,
  name_black_queen: P.PIECE_NAMES.q,
};
process.stdout.write(JSON.stringify(out));
