// cmdk.js — command palette (Cmd/Ctrl+K), split verbatim from app.js (C3).

// ══════════════════════════════════════════════════════════
// COMMAND PALETTE (Cmd/Ctrl + K)
// ══════════════════════════════════════════════════════════
// Fuzzy search across all tournaments + jump to result. Lightweight
// substring + token match scoring — no fuse.js dependency.
let _cmdkActive = -1;
let _cmdkMatches = [];
const RECENT_KEY = 'cca_recentTournaments';
const RECENT_MAX = 3;
function _getRecentTournaments() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}
function _pushRecentTournament(idx) {
  let arr = _getRecentTournaments().filter(i => i !== idx);
  arr.unshift(idx);
  arr = arr.slice(0, RECENT_MAX);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(arr)); } catch (e) {}
}

function openCmdK() {
  const root = document.getElementById('cmdkRoot');
  if (!root) return;
  root.removeAttribute('hidden');
  const input = document.getElementById('cmdkInput');
  input.value = '';
  _renderCmdK('');
  setTimeout(() => input.focus(), 0);
}
function closeCmdK() {
  const root = document.getElementById('cmdkRoot');
  if (!root) return;
  root.setAttribute('hidden', '');
}
function _cmdkScore(query, t) {
  if (!query) return 0.5; // neutral score, sort by status weight
  const q = query.toLowerCase();
  const hay = `${t.family} ${t.year} ${t.venue_city || ''} ${t.venue_state || ''}`.toLowerCase();
  // Exact prefix on family: highest
  if (t.family.toLowerCase().startsWith(q)) return 10;
  // Substring in family
  if (t.family.toLowerCase().includes(q)) return 7;
  // Substring in haystack (city/state/year)
  if (hay.includes(q)) return 4;
  // Token match — every query word appears somewhere
  const tokens = q.split(/\s+/).filter(Boolean);
  if (tokens.every(tok => hay.includes(tok))) return 2;
  return 0;
}
function _statusWeight(t) {
  if (t.status === 'live') return 3;
  if (t.status === 'complete') return 2;
  return 1; // historical
}
function _renderCmdK(query) {
  const list = document.getElementById('cmdkResults');
  if (!list) return;
  const ts = TOURNAMENT_DATA.tournaments;
  const scored = ts.map((t, idx) => ({ t, idx, score: _cmdkScore(query, t) }))
    .filter(x => x.score > 0);
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (_statusWeight(b.t) !== _statusWeight(a.t)) return _statusWeight(b.t) - _statusWeight(a.t);
    return (b.t.year || 0) - (a.t.year || 0);
  });
  _cmdkMatches = scored.slice(0, 20);
  _cmdkActive = _cmdkMatches.length > 0 ? 0 : -1;
  if (_cmdkMatches.length === 0) {
    list.innerHTML = `<div class="cmdk-empty">No tournaments match "${esc(query)}"</div>`;
    return;
  }
  // Recent strip: only when query is empty and we have prior selections.
  let recentHTML = '';
  if (!query) {
    const recents = _getRecentTournaments().filter(i => ts[i]).slice(0, RECENT_MAX);
    if (recents.length > 0) {
      const chips = recents.map(i => {
        const t = ts[i];
        return `<button class="cmdk-recent-chip" data-act="cmdk-select" data-idx="${i}">${esc(t.family)} ${t.year}</button>`;
      }).join('');
      recentHTML = `<div class="cmdk-recent"><span class="cmdk-recent-label">Recent:</span>${chips}</div>`;
    }
  }
  list.innerHTML = recentHTML + _cmdkMatches.map((m, i) => {
    const t = m.t;
    const statusCls = t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'hist';
    const statusLabel = t.status === 'live' ? `T-${t.days_remaining ?? '?'}`
                      : t.status === 'complete' ? 'final'
                      : 'past';
    const numText = t.status === 'live' ? `${fmt(t.current_count)} → ${fmt(t.point_estimate)}`
                  : `${fmt(t.current_count)}`;
    return `<button class="cmdk-row ${i === _cmdkActive ? 'cmdk-row-active' : ''}" data-idx="${m.idx}" data-pos="${i}" data-act="cmdk-select" role="option" aria-selected="${i === _cmdkActive}">
      <span class="cmdk-row-status cmdk-status-${statusCls}">${statusLabel}</span>
      <span class="cmdk-row-name">${esc(t.family)} <span class="cmdk-row-year">${t.year}</span></span>
      <span class="cmdk-row-num">${numText}</span>
    </button>`;
  }).join('');
}
function _cmdkSelect(idx) {
  _pushRecentTournament(idx);
  closeCmdK();
  // Make sure we're on the Predictions tab before scrolling/selecting.
  switchPageTab('predictions');
  selectTournament(idx);
}
function _cmdkSetActive(delta) {
  if (_cmdkMatches.length === 0) return;
  _cmdkActive = (_cmdkActive + delta + _cmdkMatches.length) % _cmdkMatches.length;
  const list = document.getElementById('cmdkResults');
  list.querySelectorAll('.cmdk-row').forEach((el, i) => {
    el.classList.toggle('cmdk-row-active', i === _cmdkActive);
    el.setAttribute('aria-selected', i === _cmdkActive ? 'true' : 'false');
    if (i === _cmdkActive) el.scrollIntoView({ block: 'nearest' });
  });
}
// Global keydown — Cmd/Ctrl + K opens; ESC closes; up/down/enter navigate.
document.addEventListener('keydown', e => {
  const isMod = e.metaKey || e.ctrlKey;
  if (isMod && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    openCmdK();
    return;
  }
  const root = document.getElementById('cmdkRoot');
  if (!root || root.hasAttribute('hidden')) return;
  if (e.key === 'Escape') { e.preventDefault(); closeCmdK(); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); _cmdkSetActive(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); _cmdkSetActive(-1); }
  else if (e.key === 'Enter' && _cmdkActive >= 0) {
    e.preventDefault();
    _cmdkSelect(_cmdkMatches[_cmdkActive].idx);
  }
});
// Re-render on input.
document.addEventListener('input', e => {
  if (e.target && e.target.id === 'cmdkInput') _renderCmdK(e.target.value);
});
