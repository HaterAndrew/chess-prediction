// pickers.js — the tournament picker and the one way to find a tournament:
// one sheet on every width (a bottom sheet on a phone, a popover under the
// top bar's subject above it), with the Upcoming, Complete and Historical
// segments and a search field over all three. Typing a query lists every
// matching tournament, whatever its status; clearing it returns to the
// segment. The arrows walk the rows, Home and End jump, Enter picks, a
// letter typed over the list goes to the search field, and Ctrl K (Cmd K)
// opens the picker with the field focused. openTourneyPicker(segment) is the
// API; the subject in the top bar calls it. sheet.js owns opening, closing,
// the focus trap and the anchoring; picker.css draws what is inside.

const PICKER_SHEET = 'tourneySheet';
const PICKER_SEGMENTS = [['live', 'Upcoming'], ['complete', 'Complete'], ['hist', 'Historical']];
const PICKER_STATUS_RANK = { live: 0, complete: 1, hist: 2 };
let _pickerSeg = 'live';
let _pickerQuery = '';

function _pickerSegFor(status) {
  return status === 'live' ? 'live' : status === 'complete' ? 'complete' : 'hist';
}

// The tournaments a segment lists, as [{t, i}] in list order: upcoming
// soonest first, complete most recent first, historical grouped by family
// (the busiest family first) with the newest edition first inside each.
function _pickerEntries(seg) {
  const all = TOURNAMENT_DATA.tournaments.map((t, i) => ({ t, i }));
  if (seg === 'live') {
    return all.filter(x => x.t.status === 'live').sort((a, b) => a.t.days_remaining - b.t.days_remaining);
  }
  if (seg === 'complete') {
    return all.filter(x => x.t.status === 'complete')
      .sort((a, b) => String(b.t.event_start).localeCompare(String(a.t.event_start)));
  }
  const byFamily = new Map();
  all.filter(x => x.t.status === 'historical').forEach(x => {
    if (!byFamily.has(x.t.family)) byFamily.set(x.t.family, []);
    byFamily.get(x.t.family).push(x);
  });
  const families = Array.from(byFamily.keys()).sort((a, b) =>
    byFamily.get(b).length - byFamily.get(a).length || a.localeCompare(b));
  return families.flatMap(f => byFamily.get(f)
    .sort((a, b) => b.t.year - a.t.year)
    .map(x => ({ t: x.t, i: x.i, family: f, editions: byFamily.get(f).length })));
}

// Every tournament whose name, year or city holds each word of the query:
// upcoming first (soonest first), then complete, then historical, the newest
// edition first within a status.
function _pickerMatches(query) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const rank = x => PICKER_STATUS_RANK[_pickerSegFor(x.t.status)];
  return TOURNAMENT_DATA.tournaments.map((t, i) => ({ t, i }))
    .filter(x => {
      const hay = `${x.t.family} ${x.t.year} ${x.t.venue_city || ''} ${x.t.venue_state || ''}`.toLowerCase();
      return words.every(w => hay.includes(w));
    })
    .sort((a, b) => {
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      if (a.t.status === 'live') return a.t.days_remaining - b.t.days_remaining;
      return b.t.year - a.t.year;
    });
}

function _pickerMeta(t) {
  const seg = _pickerSegFor(t.status);
  if (seg === 'live') return `${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg · T-${t.days_remaining}`;
  if (seg === 'complete') return `${fmtDate(t.event_start)} · ${fmt(t.current_count)}`;
  return `${fmt(t.current_count)} entries`;
}

// A row names the tournament: the family and year, the family alone on the
// Upcoming list (one edition each), the year alone under a family heading.
function _pickerRow(x, naming) {
  const t = x.t;
  const seg = _pickerSegFor(t.status);
  const active = x.i === selectedIndex;
  const name = naming === 'year' ? String(t.year)
    : naming === 'family' ? esc(t.family) : `${esc(t.family)} ${t.year}`;
  return `<button type="button" class="pick-row pick-row-${seg}${active ? ' active' : ''}" role="option" ` +
    `aria-selected="${active}" data-act="select-tourney-picker" data-idx="${x.i}">` +
    `<span class="pick-name">${seg === 'live' ? '<span class="live-dot"></span>' : ''}<span class="pick-title">${name}</span></span>` +
    `<span class="pick-meta">${_pickerMeta(t)}</span></button>`;
}

function _pickerListHTML() {
  const query = _pickerQuery.trim();
  if (query) {
    const matches = _pickerMatches(query);
    return matches.length ? matches.map(x => _pickerRow(x, 'full')).join('')
      : '<div class="picker-empty">No tournament matches.</div>';
  }
  const entries = _pickerEntries(_pickerSeg);
  if (!entries.length) return '<div class="picker-empty">Nothing listed yet.</div>';
  if (_pickerSeg !== 'hist') return entries.map(x => _pickerRow(x, _pickerSeg === 'live' ? 'family' : 'full')).join('');
  let html = '';
  let last = null;
  entries.forEach(x => {
    if (x.family !== last) {
      html += `<div class="picker-group">${esc(x.family)} <i>(${x.editions})</i></div>`;
      last = x.family;
    }
    html += _pickerRow(x, 'year');
  });
  const families = new Set(entries.map(x => x.family)).size;
  return html + `<div class="picker-foot">${entries.length} editions across ${families} families</div>`;
}

// While a query lists matches from every status, no segment is the open one.
function _pickerMarkSegments() {
  const searching = !!_pickerQuery.trim();
  document.querySelectorAll('#pickerSegments [data-tab]').forEach(b => {
    const on = !searching && b.dataset.tab === _pickerSeg;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', String(on));
  });
}

function renderTourneyPicker() {
  const segments = document.getElementById('pickerSegments');
  const list = document.getElementById('pickerList');
  if (!segments || !list) return;
  const counts = { live: 0, complete: 0, hist: 0 };
  TOURNAMENT_DATA.tournaments.forEach(t => { counts[_pickerSegFor(t.status)]++; });
  segments.innerHTML = PICKER_SEGMENTS.map(([k, label]) =>
    `<button type="button" role="tab" data-act="tourney-tab" data-tab="${k}">${label}<span class="seg-count">${counts[k]}</span></button>`).join('');
  _pickerMarkSegments();
  const input = document.getElementById('pickerSearchInput');
  if (input) input.value = _pickerQuery;
  list.innerHTML = _pickerListHTML();
}

function _pickerFocusInput() {
  const input = document.getElementById('pickerSearchInput');
  if (input) input.focus();
}

// Open on the selected tournament's own segment, or the one asked for.
// focusSearch puts the caret in the search field (Ctrl K); a tap on the
// subject leaves it out so a phone's keyboard does not cover the list.
function openTourneyPicker(initialSeg, focusSearch) {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  _pickerSeg = initialSeg || (t ? _pickerSegFor(t.status) : 'live');
  _pickerQuery = '';
  renderTourneyPicker();
  openSheet(PICKER_SHEET, document.getElementById('headerTournLabel'));
  // openSheet focuses the first segment on the next frame; the search field
  // takes over after that when asked for.
  if (focusSearch) requestAnimationFrame(() => requestAnimationFrame(_pickerFocusInput));
}

function closeTourneyPicker() {
  if (openSheetId() === PICKER_SHEET) closeSheet();
}

function setTourneyTab(seg) {
  if (_pickerSeg !== seg) _haptic(8);
  _pickerSeg = seg;
  _pickerQuery = '';
  renderTourneyPicker();
  const tab = document.querySelector(`#pickerSegments [data-tab="${seg}"]`);
  if (tab) tab.focus();
}

function filterTourneyPicker(query) {
  _pickerQuery = query || '';
  _pickerMarkSegments();
  const list = document.getElementById('pickerList');
  if (list) {
    list.innerHTML = _pickerListHTML();
    list.scrollTop = 0;
  }
}

function selectFromTourneyPicker(idx) {
  _haptic(10);
  closeTourneyPicker();
  selectTournament(idx);
}

// ── Keyboard: the rows are buttons, so Enter and Space pick natively; this
// moves focus between them and sends typing to the search field. ──
function _pickerRows() {
  return Array.from(document.querySelectorAll('#pickerList .pick-row'));
}

function _pickerFocusRow(row) {
  if (!row) return;
  row.focus({ preventScroll: true });
  row.scrollIntoView({ block: 'nearest' });
}

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    if (openSheetId() === PICKER_SHEET) _pickerFocusInput();
    else openTourneyPicker(null, true);
    return;
  }
  if (openSheetId() !== PICKER_SHEET) return;
  const rows = _pickerRows();
  const active = document.activeElement;
  const inInput = !!active && active.id === 'pickerSearchInput';
  const at = rows.indexOf(active);
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _pickerFocusRow(rows[at < 0 ? 0 : Math.min(at + 1, rows.length - 1)]);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (at <= 0 && !inInput) _pickerFocusInput();
    else _pickerFocusRow(rows[at < 0 ? rows.length - 1 : Math.max(at - 1, 0)]);
  } else if (e.key === 'Home' && !inInput) {
    e.preventDefault();
    _pickerFocusRow(rows[0]);
  } else if (e.key === 'End' && !inInput) {
    e.preventDefault();
    _pickerFocusRow(rows[rows.length - 1]);
  } else if (e.key === 'Enter' && inInput) {
    // Enter in the search field picks the first match.
    e.preventDefault();
    if (rows[0]) rows[0].click();
  } else if (e.key.length === 1 && e.key !== ' ' && !e.ctrlKey && !e.metaKey && !e.altKey && !inInput) {
    // A letter typed over the list belongs in the search field; moving focus
    // before the key lands lets the browser type it there. Space stays with
    // the focused row, which it picks.
    _pickerFocusInput();
  }
});
