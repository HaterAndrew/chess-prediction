// pickers.js — the tournament picker: one sheet on every width (a bottom
// sheet on a phone, a popover under the top bar's subject above it), with
// the Upcoming, Complete and Historical segments, a search field on
// Historical, and the keyboard navigation the old dropdowns had: the arrows
// walk the rows, Home and End jump, Enter picks, and a letter jumps to the
// first tournament that starts with it. openTourneyPicker(segment) is the
// API; the subject in the top bar and the status chips call it. sheet.js
// owns opening, closing, the focus trap and the anchoring; picker.css draws
// what is inside.

const PICKER_SHEET = 'tourneySheet';
const PICKER_SEGMENTS = [['live', 'Upcoming'], ['complete', 'Complete'], ['hist', 'Historical']];
let _pickerSeg = 'live';
let _pickerQuery = '';
let _pickerTypeBuffer = '';
let _pickerTypeTimer = null;

function _pickerSegFor(status) {
  return status === 'live' ? 'live' : status === 'complete' ? 'complete' : 'hist';
}

// The tournaments a segment lists, as [{t, i}] in list order: upcoming
// soonest first, complete most recent first, historical grouped by family
// (the busiest family first, alphabetical under a search) with the newest
// edition first inside each.
function _pickerEntries(seg, query) {
  const all = TOURNAMENT_DATA.tournaments.map((t, i) => ({ t, i }));
  if (seg === 'live') {
    return all.filter(x => x.t.status === 'live').sort((a, b) => a.t.days_remaining - b.t.days_remaining);
  }
  if (seg === 'complete') {
    return all.filter(x => x.t.status === 'complete')
      .sort((a, b) => String(b.t.event_start).localeCompare(String(a.t.event_start)));
  }
  const q = (query || '').toLowerCase().trim();
  const byFamily = new Map();
  all.filter(x => x.t.status === 'historical').forEach(x => {
    if (q && !(x.t.family + ' ' + x.t.year).toLowerCase().includes(q)) return;
    if (!byFamily.has(x.t.family)) byFamily.set(x.t.family, []);
    byFamily.get(x.t.family).push(x);
  });
  const families = Array.from(byFamily.keys()).sort((a, b) =>
    q ? a.localeCompare(b) : (byFamily.get(b).length - byFamily.get(a).length || a.localeCompare(b)));
  return families.flatMap(f => byFamily.get(f)
    .sort((a, b) => b.t.year - a.t.year)
    .map(x => ({ t: x.t, i: x.i, family: f, editions: byFamily.get(f).length })));
}

function _pickerRow(x, seg) {
  const t = x.t;
  const active = x.i === selectedIndex;
  const name = seg === 'hist' ? String(t.year) : esc(t.family);
  const meta = seg === 'live'
    ? `${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg · T-${t.days_remaining}`
    : seg === 'complete'
      ? `${fmtDate(t.event_start)} · ${fmt(t.current_count)}`
      : `${fmt(t.current_count)} entries`;
  return `<button type="button" class="pick-row pick-row-${seg}${active ? ' active' : ''}" role="option" ` +
    `aria-selected="${active}" data-act="select-tourney-picker" data-idx="${x.i}" ` +
    `data-name="${esc(String(t.family).toLowerCase())}">` +
    `<span class="pick-name">${seg === 'live' ? '<span class="live-dot"></span>' : ''}<span class="pick-title">${name}</span></span>` +
    `<span class="pick-meta">${meta}</span></button>`;
}

function _pickerListHTML() {
  const entries = _pickerEntries(_pickerSeg, _pickerQuery);
  if (!entries.length) {
    return `<div class="picker-empty">${_pickerSeg === 'hist' ? 'No tournament matches.' : 'Nothing listed yet.'}</div>`;
  }
  if (_pickerSeg !== 'hist') return entries.map(x => _pickerRow(x, _pickerSeg)).join('');
  let html = '';
  let last = null;
  entries.forEach(x => {
    if (x.family !== last) {
      html += `<div class="picker-group">${esc(x.family)} <i>(${x.editions})</i></div>`;
      last = x.family;
    }
    html += _pickerRow(x, 'hist');
  });
  const families = new Set(entries.map(x => x.family)).size;
  return html + `<div class="picker-foot">${entries.length} editions across ${families} families</div>`;
}

function renderTourneyPicker() {
  const segments = document.getElementById('pickerSegments');
  const list = document.getElementById('pickerList');
  if (!segments || !list) return;
  const counts = { live: 0, complete: 0, hist: 0 };
  TOURNAMENT_DATA.tournaments.forEach(t => { counts[_pickerSegFor(t.status)]++; });
  segments.innerHTML = PICKER_SEGMENTS.map(([k, label]) =>
    `<button type="button" role="tab" aria-selected="${_pickerSeg === k}" class="${_pickerSeg === k ? 'active' : ''}" ` +
    `data-act="tourney-tab" data-tab="${k}">${label}<span class="seg-count">${counts[k]}</span></button>`).join('');
  const search = document.getElementById('pickerSearch');
  const input = document.getElementById('pickerSearchInput');
  if (search) search.hidden = _pickerSeg !== 'hist';
  if (input) input.value = _pickerSeg === 'hist' ? _pickerQuery : '';
  list.innerHTML = _pickerListHTML();
}

function _pickerFocusInput() {
  const input = document.getElementById('pickerSearchInput');
  if (input && _pickerSeg === 'hist') input.focus();
}

// Open on the selected tournament's own segment, or the one asked for.
function openTourneyPicker(initialSeg) {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  _pickerSeg = initialSeg || (t ? _pickerSegFor(t.status) : 'live');
  _pickerQuery = '';
  renderTourneyPicker();
  openSheet(PICKER_SHEET, document.getElementById('headerTournLabel'));
  // openSheet focuses the first segment on the next frame; on Historical the
  // search field is where the visitor starts, so it takes over after that.
  requestAnimationFrame(_pickerFocusInput);
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
  if (seg === 'hist') _pickerFocusInput();
  else if (tab) tab.focus();
}

function filterTourneyHistResults(query) {
  _pickerQuery = query || '';
  const list = document.getElementById('pickerList');
  if (list) list.innerHTML = _pickerListHTML();
}

function selectFromTourneyPicker(idx) {
  _haptic(10);
  closeTourneyPicker();
  selectTournament(idx);
}

// ── Keyboard: the rows are buttons, so Enter and Space pick natively; this
// moves focus between them and jumps by letter. ──
function _pickerRows() {
  return Array.from(document.querySelectorAll('#pickerList .pick-row'));
}

function _pickerFocusRow(row) {
  if (!row) return;
  row.focus({ preventScroll: true });
  row.scrollIntoView({ block: 'nearest' });
}

function _pickerTypeAhead(key, rows) {
  clearTimeout(_pickerTypeTimer);
  _pickerTypeBuffer += key.toLowerCase();
  _pickerTypeTimer = setTimeout(() => { _pickerTypeBuffer = ''; }, 500);
  const match = rows.find(r => (r.dataset.name || '').startsWith(_pickerTypeBuffer));
  if (match) _pickerFocusRow(match);
}

document.addEventListener('keydown', e => {
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
    if (at <= 0 && _pickerSeg === 'hist' && !inInput) _pickerFocusInput();
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
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey && !inInput) {
    // A letter typed over the Historical list belongs in its search field;
    // over Upcoming and Complete it jumps to the matching tournament.
    if (_pickerSeg === 'hist') _pickerFocusInput();
    else _pickerTypeAhead(e.key, rows);
  }
});
