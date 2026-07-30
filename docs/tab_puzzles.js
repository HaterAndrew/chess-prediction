// tab_puzzles.js — chess puzzle engine, split verbatim from app.js (C6).

// ══════════════════════════════════════════════════════════
// CHESS PUZZLE ENGINE
// ══════════════════════════════════════════════════════════
const PIECE_UNICODE = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟'
};

let puzzleState = {
  puzzles: [],
  currentIdx: 0,
  board: null, // 8x8 array
  selected: null, // [row, col]
  turn: 'w',
  moveIdx: 0, // which solution move we're on (player moves are even indices after setup)
  solved: [], // 'solved'|'failed'|null per puzzle
  hintShown: false,
  flipped: false, // flip board for black
  lastMove: null, // [fromR, fromC, toR, toC]
  animating: false,
  initialized: false
};

function parseFEN(fen) {
  const board = [];
  const parts = fen.split(' ');
  const rows = parts[0].split('/');
  for (const row of rows) {
    const r = [];
    for (const ch of row) {
      if (ch >= '1' && ch <= '8') { for (let i = 0; i < parseInt(ch); i++) r.push(null); }
      else r.push(ch);
    }
    board.push(r);
  }
  return { board, turn: parts[1] || 'w' };
}

function boardToFEN(board) {
  return board.map(row => {
    let s = '', empty = 0;
    for (const sq of row) {
      if (sq === null) { empty++; }
      else { if (empty > 0) { s += empty; empty = 0; } s += sq; }
    }
    if (empty > 0) s += empty;
    return s;
  }).join('/');
}

function uciToCoords(uci) {
  const fc = uci.charCodeAt(0) - 97, fr = 8 - parseInt(uci[1]);
  const tc = uci.charCodeAt(2) - 97, tr = 8 - parseInt(uci[3]);
  const promo = uci.length > 4 ? uci[4] : null;
  return { fr, fc, tr, tc, promo };
}

function applyUCIMove(board, uci, turn) {
  const { fr, fc, tr, tc, promo } = uciToCoords(uci);
  const b = board.map(r => [...r]);
  const piece = b[fr][fc];
  b[tr][tc] = promo ? (turn === 'w' ? promo.toUpperCase() : promo.toLowerCase()) : piece;
  b[fr][fc] = null;
  // En passant
  if (piece && piece.toLowerCase() === 'p' && fc !== tc && board[tr][tc] === null) {
    b[fr][tc] = null;
  }
  // Castling
  if (piece && piece.toLowerCase() === 'k' && Math.abs(fc - tc) === 2) {
    if (tc > fc) { b[fr][5] = b[fr][7]; b[fr][7] = null; } // kingside
    else { b[fr][3] = b[fr][0]; b[fr][0] = null; } // queenside
  }
  return b;
}

// Piece name lookup for aria-labels
const PIECE_NAMES = {
  K: 'white king', Q: 'white queen', R: 'white rook', B: 'white bishop', N: 'white knight', P: 'white pawn',
  k: 'black king', q: 'black queen', r: 'black rook', b: 'black bishop', n: 'black knight', p: 'black pawn'
};

function renderBoard() {
  const el = document.getElementById('chessBoard');
  if (!el || !puzzleState.board) return;
  const brd = puzzleState.board;
  const flip = puzzleState.flipped;
  const FILES = 'abcdefgh';
  let html = '';
  for (let ri = 0; ri < 8; ri++) {
    for (let ci = 0; ci < 8; ci++) {
      const r = flip ? 7 - ri : ri;
      const c = flip ? 7 - ci : ci;
      const isLight = (r + c) % 2 === 0;
      let cls = 'chess-sq ' + (isLight ? 'light' : 'dark');
      if (puzzleState.selected && puzzleState.selected[0] === r && puzzleState.selected[1] === c) cls += ' selected';
      if (puzzleState.lastMove) {
        const [lfr, lfc, ltr, ltc] = puzzleState.lastMove;
        if ((r === lfr && c === lfc) || (r === ltr && c === ltc)) cls += ' last-move';
      }
      const piece = brd[r][c];
      const sqName = FILES[c] + (8 - r);
      const pieceName = piece ? PIECE_NAMES[piece] : 'empty';
      const ariaLabel = sqName + ', ' + pieceName;
      const pieceHtml = piece ? `<span class="piece">${PIECE_UNICODE[piece]}</span>` : '';
      html += `<div class="${cls}" data-r="${r}" data-c="${c}" data-ri="${ri}" data-ci="${ci}" tabindex="0" role="gridcell" aria-label="${ariaLabel}" data-act="puzzle-square" data-keyact="puzzle-board">${pieceHtml}</div>`;
    }
  }
  el.setAttribute('role', 'grid');
  el.setAttribute('aria-label', 'Chess puzzle board');
  el.innerHTML = html;
}

// Keyboard navigation for puzzle board
function puzzleBoardKeydown(e, r, c, ri, ci) {
  const board = document.getElementById('chessBoard');
  if (!board) return;
  let newRi = ri, newCi = ci;
  switch (e.key) {
    case 'ArrowUp':    newRi = Math.max(0, ri - 1); e.preventDefault(); break;
    case 'ArrowDown':  newRi = Math.min(7, ri + 1); e.preventDefault(); break;
    case 'ArrowLeft':  newCi = Math.max(0, ci - 1); e.preventDefault(); break;
    case 'ArrowRight': newCi = Math.min(7, ci + 1); e.preventDefault(); break;
    case 'Enter':
    case ' ':
      e.preventDefault();
      puzzleSquareClick(r, c);
      return;
    default: return;
  }
  const idx = newRi * 8 + newCi;
  const squares = board.querySelectorAll('.chess-sq');
  if (squares[idx]) squares[idx].focus();
}

function puzzleSquareClick(r, c) {
  if (puzzleState.animating) return;
  const ps = puzzleState;
  const puzzle = ps.puzzles[ps.currentIdx];
  if (!puzzle) return;
  const moves = puzzle.moves.split(' ');
  // Player moves on even moveIdx (0-indexed after setup move is applied)
  if (ps.moveIdx >= moves.length) return; // puzzle done

  const piece = ps.board[r][c];
  const isMyPiece = piece && ((ps.turn === 'w' && piece === piece.toUpperCase()) || (ps.turn === 'b' && piece === piece.toLowerCase()));

  if (ps.selected) {
    // Trying to make a move
    const [sr, sc] = ps.selected;
    if (r === sr && c === sc) { ps.selected = null; renderBoard(); return; }
    if (isMyPiece) { ps.selected = [r, c]; renderBoard(); return; }
    // Build UCI from selected -> clicked
    const fromUci = String.fromCharCode(97 + sc) + (8 - sr);
    const toUci = String.fromCharCode(97 + c) + (8 - r);
    let uci = fromUci + toUci;
    // Check promotion
    const srcPiece = ps.board[sr][sc];
    if (srcPiece && srcPiece.toLowerCase() === 'p' && (r === 0 || r === 7)) uci += 'q'; // auto-queen
    const expected = moves[ps.moveIdx];
    if (uci === expected) {
      // Correct move!
      ps.board = applyUCIMove(ps.board, uci, ps.turn);
      ps.lastMove = [sr, sc, r, c];
      ps.selected = null;
      ps.turn = ps.turn === 'w' ? 'b' : 'w';
      ps.moveIdx++;
      renderBoard();
      if (ps.moveIdx >= moves.length) {
        puzzleSolved();
      } else {
        // Play opponent's response after a brief delay
        puzzleStatus('&#10003; Correct! Keep going...', 'var(--green)');
        ps.animating = true;
        setTimeout(() => {
          const opMove = moves[ps.moveIdx];
          const { fr, fc: fcc, tr, tc: tcc } = uciToCoords(opMove);
          ps.board = applyUCIMove(ps.board, opMove, ps.turn);
          ps.lastMove = [fr, fcc, tr, tcc];
          ps.turn = ps.turn === 'w' ? 'b' : 'w';
          ps.moveIdx++;
          ps.animating = false;
          renderBoard();
          if (ps.moveIdx >= moves.length) puzzleSolved();
          else puzzleStatus('Find the best move for ' + (ps.turn === 'w' ? 'White' : 'Black'), 'var(--muted)');
        }, 500);
      }
    } else {
      // Wrong move
      const sq = document.querySelector(`.chess-sq[data-r="${r}"][data-c="${c}"]`);
      if (sq) { sq.classList.add('wrong'); setTimeout(() => sq.classList.remove('wrong'), 600); }
      ps.selected = null;
      puzzleFailed();
    }
  } else {
    if (isMyPiece) { ps.selected = [r, c]; renderBoard(); }
  }
}

function puzzleStatus(msg, color) {
  const el = document.getElementById('puzzleStatus');
  if (el) el.innerHTML = `<span style="color:${color}">${msg}</span>`;
}

function puzzleSolved() {
  const ps = puzzleState;
  if (ps.solved[ps.currentIdx] !== 'failed') ps.solved[ps.currentIdx] = 'solved';
  puzzleStatus('&#9733; Puzzle solved!', 'var(--green)');
  renderPuzzleProgress();
  document.getElementById('puzzleRetry').style.display = 'none';
  // Round 32: tactile reward — short success pattern (Android only; iOS no-ops).
  _haptic([20, 40, 30]);
}

function puzzleFailed() {
  const ps = puzzleState;
  ps.solved[ps.currentIdx] = 'failed';
  puzzleStatus('&#10007; Incorrect. Try again or click Retry', 'var(--red)');
  renderPuzzleProgress();
  document.getElementById('puzzleRetry').style.display = '';
  // Round 32: tactile error — single longer buzz.
  _haptic(40);
}

function puzzleGiveHint() {
  const ps = puzzleState;
  const puzzle = ps.puzzles[ps.currentIdx];
  if (!puzzle) return;
  const moves = puzzle.moves.split(' ');
  if (ps.moveIdx >= moves.length) return;
  const move = moves[ps.moveIdx];
  const { fr, fc } = uciToCoords(move);
  // Highlight the source square
  const sq = document.querySelector(`.chess-sq[data-r="${fr}"][data-c="${fc}"]`);
  if (sq) { sq.classList.add('hint'); setTimeout(() => sq.classList.remove('hint'), 1500); }
  ps.hintShown = true;
}

function puzzleRetry() {
  loadPuzzle(puzzleState.currentIdx);
}

function puzzleNav(dir) {
  const ps = puzzleState;
  const next = ps.currentIdx + dir;
  if (next < 0 || next >= ps.puzzles.length) return;
  loadPuzzle(next);
}

function loadPuzzle(idx) {
  const ps = puzzleState;
  ps.currentIdx = idx;
  const puzzle = ps.puzzles[idx];
  if (!puzzle) return;

  // Parse FEN and apply setup move
  const { board, turn } = parseFEN(puzzle.fen);
  const moves = puzzle.moves.split(' ');
  // First move in the moves list is the "last move played" (setup) — apply it
  const setupMove = moves[0];
  ps.board = applyUCIMove(board, setupMove, turn);
  const { fr, fc, tr, tc } = uciToCoords(setupMove);
  ps.lastMove = [fr, fc, tr, tc];
  ps.turn = turn === 'w' ? 'b' : 'w'; // after setup move, it's the other side's turn
  ps.flipped = ps.turn === 'b'; // flip board so player is at bottom
  ps.moveIdx = 1; // player starts at move index 1
  ps.selected = null;
  ps.hintShown = false;
  ps.animating = false;

  // Update UI
  document.getElementById('puzzleNum').textContent = idx + 1;
  document.getElementById('puzzleRating').textContent = puzzle.rating;
  const diff = puzzle.rating >= 2500 ? 'Master' : puzzle.rating >= 2200 ? 'Expert' : puzzle.rating >= 2000 ? 'Advanced' : 'Intermediate';
  document.getElementById('puzzleDifficulty').textContent = diff;
  document.getElementById('puzzleThemes').innerHTML = (puzzle.themes || []).map(t => `<span class="puzzle-theme-tag">${esc(t.replace(/([A-Z])/g, ' $1').trim())}</span>`).join('');
  document.getElementById('puzzleLink').href = puzzle.url || '#';
  // #puzzleTurn is a span INSIDE #puzzleStatus, and puzzleStatus() on the next
  // line replaces that container's innerHTML — so the span exists only until
  // the first status write and is gone for every later loadPuzzle call. The
  // unguarded lookup threw there, and because the throw landed mid-function the
  // lines below never ran: the move list kept the previous puzzle's moves and
  // the prev/next buttons kept the previous puzzle's disabled state. Retry and
  // both nav arrows were dead after the first puzzle. The write is kept for the
  // first render and guarded for the rest; the status line below says the same
  // thing either way.
  const turnEl = document.getElementById('puzzleTurn');
  if (turnEl) turnEl.textContent = ps.turn === 'w' ? 'White' : 'Black';
  puzzleStatus('Find the best move for ' + (ps.turn === 'w' ? 'White' : 'Black'), 'var(--muted)');
  document.getElementById('puzzleMoveList').textContent = '';
  document.getElementById('puzzlePrev').disabled = idx === 0;
  document.getElementById('puzzleNext').disabled = idx === ps.puzzles.length - 1;
  document.getElementById('puzzleRetry').style.display = 'none';

  renderBoard();
  renderPuzzleProgress();
}

function renderPuzzleProgress() {
  const ps = puzzleState;
  const el = document.getElementById('puzzleProgress');
  if (!el) return;
  el.innerHTML = ps.puzzles.map((_, i) => {
    let cls = 'puzzle-dot';
    if (ps.solved[i] === 'solved') cls += ' solved';
    else if (ps.solved[i] === 'failed') cls += ' failed';
    if (i === ps.currentIdx) cls += ' current';
    return `<div class="${cls}" data-act="load-puzzle" data-idx="${i}" style="cursor:pointer" title="Puzzle ${i+1}"></div>`;
  }).join('');
  const solved = ps.solved.filter(s => s === 'solved').length;
  document.getElementById('puzzleScore').textContent = `${solved}/${ps.puzzles.length} solved`;
}

function loadHistoryEvents() {
  const el = document.getElementById('historyEvents');
  if (!el) return;
  const today = new Date();
  const key = String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
  if (typeof CHESS_HISTORY !== 'undefined' && CHESS_HISTORY[key]) {
    const events = CHESS_HISTORY[key];
    el.innerHTML = events.map(e =>
      `<div class="history-event"><span class="history-year">${e.year}</span>${esc(e.event)}<span class="history-cat">${esc(e.category)}</span></div>`
    ).join('');
  } else {
    el.innerHTML = '<div class="history-event" style="color:var(--muted)">No historical events found for today.</div>';
  }
}

let puzzlesInitialized = false;
function initPuzzles() {
  if (puzzlesInitialized) return;
  puzzlesInitialized = true;
  const ps = puzzleState;
  if (typeof PUZZLE_DATA !== 'undefined' && PUZZLE_DATA.puzzles && PUZZLE_DATA.puzzles.length > 0) {
    ps.puzzles = PUZZLE_DATA.puzzles;
    ps.solved = new Array(ps.puzzles.length).fill(null);
    document.getElementById('puzzleTotal').textContent = ps.puzzles.length;
    loadPuzzle(0);
  } else {
    document.getElementById('chessBoard').innerHTML = '<div style="padding:40px;text-align:center;color:var(--muted);grid-column:1/-1">No puzzles available. Run the puzzle scraper to generate daily puzzles.</div>';
  }
  loadHistoryEvents();
}

// (Header dropdown removed — using tab bar dropdowns instead)

// ── node export tail (added by the C6 split; not part of the original) ──
// Lets tests/js/puzzles_driver.js require() the pure board/move helpers.
// Browsers never take this branch.
if (typeof module !== 'undefined') {
  module.exports = {
    parseFEN, boardToFEN, uciToCoords, applyUCIMove,
    PIECE_UNICODE, PIECE_NAMES,
  };
}
