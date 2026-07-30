// pickers.js — tab-bar dropdowns (virtual-scroll historical list), mobile
// tournament picker and renderTabs, split verbatim from app.js (C7).

// ══════════════════════════════════════════════════════════
// TABS — Virtual-scroll for historical dropdown (500+ items)
// ══════════════════════════════════════════════════════════
const _vs = {
  flatItems: [],   // [{type:'header'|'item'|'footer', html:string, h:number}]
  totalH: 0,
  container: null,
  spacer: null,
  content: null,
  ITEM_H: 35,
  HDR_H: 28,
  FOOTER_H: 30,
  OVERSCAN: 5,
  rafId: 0,
};

// ── Keyboard navigation state for dropdowns ──
let _kbHighlightIdx = -1;      // index into current item list (-1 = nothing highlighted)
let _kbTypeBuffer = '';         // type-ahead keystroke buffer (live/complete only)
let _kbTypeTimer = null;        // reset timer for type-ahead

function _vsBuildFlat(ql) {
  const ts = TOURNAMENT_DATA.tournaments;
  const hist = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'historical');
  const filtered = ql ? hist.filter(x => (x.t.family + ' ' + x.t.year).toLowerCase().includes(ql)) : hist;

  const byFamily = {};
  filtered.forEach(({t, i}) => {
    const key = t.family;
    if (!byFamily[key]) byFamily[key] = [];
    byFamily[key].push({t, i});
  });

  const families = Object.keys(byFamily).sort((a, b) => {
    if (ql) return a.localeCompare(b);
    return byFamily[b].length - byFamily[a].length || a.localeCompare(b);
  });

  const flat = [];
  families.forEach(fam => {
    const editions = byFamily[fam].sort((a, b) => b.t.year - a.t.year);
    flat.push({
      type: 'header', h: _vs.HDR_H,
      html: `<div style="height:${_vs.HDR_H}px;padding:5px 14px 3px;font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:1.2px;font-weight:700;background:var(--surface2);border-bottom:1px solid var(--border-light);box-sizing:border-box;display:flex;align-items:center">${esc(fam)} <span style="font-weight:400;opacity:.7;margin-left:4px">(${editions.length})</span></div>`
    });
    editions.forEach(({t, i}) => {
      flat.push({
        type: 'item', h: _vs.ITEM_H, idx: i,
        html: `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" style="height:${_vs.ITEM_H}px;box-sizing:border-box" data-act="select-from-drop" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" role="option"><span class="cat-item-name" style="padding-left:6px">${t.year}</span><span class="cat-item-meta">${fmt(t.current_count)} entries</span></div>`
      });
    });
  });

  // Footer summary
  const footerText = filtered.length === 0
    ? 'No matches'
    : `${filtered.length} editions across ${families.length} families`;
  flat.push({
    type: 'footer', h: _vs.FOOTER_H,
    html: `<div style="height:${_vs.FOOTER_H}px;padding:6px 14px;font-size:var(--fs-1);color:var(--muted);border-top:1px solid var(--border-light);display:flex;align-items:center;box-sizing:border-box">${footerText}</div>`
  });

  return flat;
}

function _vsRenderVisible() {
  const {flatItems, spacer, content, container, OVERSCAN} = _vs;
  if (!container || !flatItems.length) return;

  const scrollTop = container.scrollTop;
  const viewH = container.clientHeight;

  // Find visible range via cumulative heights
  let cumH = 0, startIdx = -1, endIdx = flatItems.length - 1;
  for (let i = 0; i < flatItems.length; i++) {
    const top = cumH;
    cumH += flatItems[i].h;
    if (startIdx === -1 && cumH > scrollTop) startIdx = i;
    if (top > scrollTop + viewH && endIdx === flatItems.length - 1) { endIdx = i; break; }
  }
  if (startIdx === -1) startIdx = 0;

  startIdx = Math.max(0, startIdx - OVERSCAN);
  endIdx = Math.min(flatItems.length - 1, endIdx + OVERSCAN);

  // Pixel offset to startIdx
  let offsetY = 0;
  for (let i = 0; i < startIdx; i++) offsetY += flatItems[i].h;

  let html = '';
  for (let i = startIdx; i <= endIdx; i++) {
    let itemHtml = flatItems[i].html;
    // Inject highlighted class for keyboard-navigated item
    if (openDrop === 'hist' && i === _kbHighlightIdx && flatItems[i].type === 'item') {
      itemHtml = itemHtml.replace('class="cat-item', 'class="cat-item highlighted');
    }
    html += itemHtml;
  }
  content.style.transform = `translateY(${offsetY}px)`;
  content.innerHTML = html;
}

function filterHistResults(q) {
  const list = document.getElementById('histSearchResults');
  if (!list) return;
  const ql = q.toLowerCase().trim();
  _kbHighlightIdx = -1; // Reset highlight when search changes

  // Build flat virtual-scroll item list
  _vs.flatItems = _vsBuildFlat(ql);
  _vs.totalH = _vs.flatItems.reduce((s, r) => s + r.h, 0);

  // Bootstrap virtual-scroll DOM on first call
  if (!list.querySelector('.vs-spacer')) {
    list.innerHTML = '<div class="vs-spacer" style="position:relative;width:100%"></div>';
    const spacer = list.querySelector('.vs-spacer');
    const content = document.createElement('div');
    content.className = 'vs-content';
    content.style.cssText = 'position:absolute;top:0;left:0;right:0;will-change:transform';
    spacer.appendChild(content);
    _vs.spacer = spacer;
    _vs.content = content;
    _vs.container = list;
    list.addEventListener('scroll', () => {
      if (_vs.rafId) cancelAnimationFrame(_vs.rafId);
      _vs.rafId = requestAnimationFrame(_vsRenderVisible);
    }, {passive: true});
  }

  _vs.spacer.style.height = _vs.totalH + 'px';
  list.scrollTop = 0;
  _vsRenderVisible();
}

let openDrop = null; // which dropdown is open: 'live','complete','hist'

function toggleDrop(which, e) {
  e && e.stopPropagation();
  if (openDrop === which) { closeDrop(); return; }
  closeDrop();
  if (_mobileVP()) _haptic(15);
  openDrop = which;
  _kbHighlightIdx = -1;
  _kbTypeBuffer = '';
  const btn = document.getElementById('dropBtn_' + which);
  btn.classList.add('open');
  btn.setAttribute('aria-expanded', 'true');
  const menu = document.getElementById('dropMenu_' + which);
  menu.style.display = 'block';
  document.body.classList.add('drawer-open');
  if (which === 'hist') {
    const inp = document.getElementById('histSearchInput');
    inp.value = '';
    filterHistResults('');
    setTimeout(() => inp.focus(), 30);
  } else {
    // Focus first item in live/complete dropdown
    setTimeout(() => {
      const first = menu.querySelector('.cat-item');
      if (first) first.focus();
    }, 30);
  }
}

function closeDrop() {
  if (!openDrop) return;
  const btn = document.getElementById('dropBtn_' + openDrop);
  const menu = document.getElementById('dropMenu_' + openDrop);
  if (btn) { btn.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
  if (menu) menu.style.display = 'none';
  document.body.classList.remove('drawer-open');
  _kbHighlightIdx = -1;
  _kbTypeBuffer = '';
  openDrop = null;
}

function selectFromDrop(idx) {
  if (_mobileVP()) _haptic(10);
  closeDrop();
  selectTournament(idx);
}

// ══════════════════════════════════════════════════════════
// MOBILE UNIFIED TOURNAMENT PICKER (Material 3 modal bottom sheet
// with iOS HIG segmented control). Replaces the 3 cat-btn pills on
// phones; desktop still uses the original 3 dropdowns.
// ══════════════════════════════════════════════════════════
let _tourneyTab = 'live';
let _tourneyPickerOpen = false;
// Round 32: a11y. Save the trigger so we can restore focus on close per WAI-ARIA dialog pattern.
let _pickerLastFocus = null;

function maybeOpenTourneyPicker(e) {
  if (!_mobileVP()) return;                                     // desktop: do nothing
  if (e && e.target && e.target.closest('.compare-add-btn')) return; // compare button has its own handler
  openTourneyPicker();
}

function openTourneyPicker(initialTab) {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  if (initialTab) _tourneyTab = initialTab;
  else if (t) _tourneyTab = t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'hist';
  if (_mobileVP()) _haptic(15);
  _pickerLastFocus = document.activeElement;
  renderTourneyPicker();
  const menu = document.getElementById('dropMenu_tourney');
  if (!menu) return;
  menu.style.display = 'block';
  document.body.classList.add('drawer-open');
  // Make the background inert so nothing behind the aria-modal sheet takes
  // focus or taps (the drawer is a sibling of #mainContent, so it stays live).
  const mc = document.getElementById('mainContent');
  if (mc) mc.inert = true;
  _tourneyPickerOpen = true;
  // Move focus into drawer per WAI-ARIA dialog pattern.
  setTimeout(() => {
    if (_tourneyTab === 'hist') {
      const inp = document.getElementById('tourneyHistSearch');
      if (inp) { inp.focus(); return; }
    }
    const activeSeg = menu.querySelector('.seg-btn.active');
    if (activeSeg) { activeSeg.focus(); return; }
    const firstFocusable = menu.querySelector('button, [tabindex="0"], input');
    if (firstFocusable) firstFocusable.focus();
  }, 80);
}

function closeTourneyPicker() {
  const menu = document.getElementById('dropMenu_tourney');
  if (menu) menu.style.display = 'none';
  document.body.classList.remove('drawer-open');
  const mc = document.getElementById('mainContent');
  if (mc) mc.inert = false;   // restore background interactivity before returning focus
  _tourneyPickerOpen = false;
  // Return focus to the element that opened the drawer (WAI-ARIA dialog pattern).
  try {
    if (_pickerLastFocus && typeof _pickerLastFocus.focus === 'function' && document.contains(_pickerLastFocus)) {
      _pickerLastFocus.focus();
    }
  } catch (_) { /* element may have been re-rendered; ignore */ }
  _pickerLastFocus = null;
}

function setTourneyTab(which) {
  if (_tourneyTab !== which) _haptic(8);
  _tourneyTab = which;
  renderTourneyPicker();
  if (which === 'hist') {
    setTimeout(() => {
      const inp = document.getElementById('tourneyHistSearch');
      if (inp) inp.focus();
    }, 30);
  }
}

function renderTourneyPicker() {
  const menu = document.getElementById('dropMenu_tourney');
  if (!menu) return;
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'live').sort((a, b) => a.t.days_remaining - b.t.days_remaining);
  const complete = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'complete');
  const hist = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'historical');

  const seg = (k, label, count) =>
    `<button class="seg-btn ${_tourneyTab === k ? 'active' : ''}" role="tab" aria-selected="${_tourneyTab === k}" data-seg="${k}" data-act="tourney-tab" data-tab="${k}">${label}<span class="seg-count">${count}</span></button>`;

  let html = '';
  html += '<div class="tourney-picker-header">';
  html += `<div class="seg-control" role="tablist" aria-label="Tournament category">${seg('live', 'Upcoming', live.length)}${seg('complete', 'Complete', complete.length)}${seg('hist', 'Historical', hist.length)}</div>`;
  html += '</div>';

  html += '<div class="tourney-picker-body">';
  if (_tourneyTab === 'live') {
    html += '<div class="tourney-list">';
    live.forEach(({t, i}) => {
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-act="select-tourney-picker" data-idx="${i}" data-keyable="1" tabindex="0" role="option">`;
      html += `<span class="cat-item-name"><span class="live-dot"></span>${esc(t.family)}</span>`;
      html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg · ${t.days_remaining}d</span>`;
      html += '</div>';
    });
    html += '</div>';
  } else if (_tourneyTab === 'complete') {
    html += '<div class="tourney-list">';
    complete.forEach(({t, i}) => {
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-act="select-tourney-picker" data-idx="${i}" data-keyable="1" tabindex="0" role="option">`;
      html += `<span class="cat-item-name">${esc(t.family)}</span>`;
      html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)}</span>`;
      html += '</div>';
    });
    html += '</div>';
  } else if (_tourneyTab === 'hist') {
    html += '<div class="tab-search-bar">';
    html += '<span style="opacity:.5">&#128269;</span>';
    html += '<input class="tab-search-input" id="tourneyHistSearch" type="text" placeholder="Search tournaments..." data-inputact="filter-tourney-hist" autocomplete="off">';
    html += '</div>';
    html += '<div class="tourney-list" id="tourneyHistList">';
    hist.forEach(({t, i}) => {
      const dataName = String(t.family || '').toLowerCase();
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-name="${esc(dataName)}" data-act="select-tourney-picker" data-idx="${i}" data-keyable="1" tabindex="0" role="option">`;
      html += `<span class="cat-item-name">${esc(t.family)} ${t.year}</span>`;
      html += `<span class="cat-item-meta">${fmt(t.current_count)}</span>`;
      html += '</div>';
    });
    html += '</div>';
  }
  html += '</div>';

  menu.innerHTML = html;
}

function filterTourneyHistResults(query) {
  const q = (query || '').toLowerCase().trim();
  document.querySelectorAll('#tourneyHistList .cat-item').forEach(el => {
    const name = el.dataset.name || '';
    el.style.display = (q === '' || name.includes(q)) ? '' : 'none';
  });
}

function selectFromTourneyPicker(idx) {
  _haptic(10);
  closeTourneyPicker();
  selectTournament(idx);
}

// Close picker on outside-click (the scrim has pointer-events:none, so clicks bubble to document)
document.addEventListener('click', e => {
  if (!_tourneyPickerOpen) return;
  if (e.target.closest('.drop-menu-tourney')) return;          // click inside drawer — keep open
  if (e.target.closest('#headerTournLabel')) return;           // re-tap on trigger handled separately
  closeTourneyPicker();
});
// Esc to close + Tab focus trap inside the drawer (Round 32 a11y).
document.addEventListener('keydown', e => {
  if (!_tourneyPickerOpen) return;
  if (e.key === 'Escape') { closeTourneyPicker(); return; }
  if (e.key !== 'Tab') return;
  const menu = document.getElementById('dropMenu_tourney');
  if (!menu) return;
  // Only trap over visible candidates — hidden ones (inactive segment tab,
  // filtered-out search rows) have no offsetParent and must not receive focus.
  const focusables = Array.from(menu.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), [tabindex="0"]'
  )).filter(el => el.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;
  if (e.shiftKey) {
    if (active === first || !menu.contains(active)) { e.preventDefault(); last.focus(); }
  } else {
    if (active === last) { e.preventDefault(); first.focus(); }
  }
});

// ── Dropdown keyboard navigation helpers ──

/** Get array of {idx, name} for simple (non-virtual) dropdown items */
function _dropSimpleItems(which) {
  const ts = TOURNAMENT_DATA.tournaments;
  if (which === 'live') {
    return ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'live')
      .sort((a, b) => a.t.days_remaining - b.t.days_remaining)
      .map(({t, i}) => ({idx: i, name: t.family}));
  }
  if (which === 'complete') {
    return ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'complete')
      .map(({t, i}) => ({idx: i, name: t.family}));
  }
  return [];
}

/** Apply highlight class to the Nth .cat-item in a simple dropdown menu */
function _dropApplyHighlight(which) {
  const menu = document.getElementById('dropMenu_' + which);
  if (!menu) return;
  const items = menu.querySelectorAll('.cat-item');
  items.forEach((el, i) => {
    el.classList.toggle('highlighted', i === _kbHighlightIdx);
  });
  if (_kbHighlightIdx >= 0 && _kbHighlightIdx < items.length) {
    items[_kbHighlightIdx].scrollIntoView({block: 'nearest'});
  }
}

/** Scroll hist virtual list so that flat index is visible, then re-render */
function _vsScrollToIdx(flatIdx) {
  if (!_vs.container || !_vs.flatItems.length) return;
  let cumH = 0;
  for (let i = 0; i < flatIdx; i++) cumH += _vs.flatItems[i].h;
  const itemBot = cumH + _vs.flatItems[flatIdx].h;
  const st = _vs.container.scrollTop;
  const vh = _vs.container.clientHeight;
  if (cumH < st) _vs.container.scrollTop = cumH;
  else if (itemBot > st + vh) _vs.container.scrollTop = itemBot - vh;
  _vsRenderVisible();
}

/** Find next/prev selectable item in hist flat list (skip headers/footers) */
function _vsNextItem(from, dir) {
  const flat = _vs.flatItems;
  let i = from + dir;
  while (i >= 0 && i < flat.length) {
    if (flat[i].type === 'item') return i;
    i += dir;
  }
  return from; // stay put if nothing found
}

/** Find first/last selectable item in hist flat list */
function _vsFirstItem() {
  for (let i = 0; i < _vs.flatItems.length; i++) {
    if (_vs.flatItems[i].type === 'item') return i;
  }
  return -1;
}
function _vsLastItem() {
  for (let i = _vs.flatItems.length - 1; i >= 0; i--) {
    if (_vs.flatItems[i].type === 'item') return i;
  }
  return -1;
}

document.addEventListener('click', (e) => {
  if (openDrop && !e.target.closest('.drop-wrap')) closeDrop();
});
document.addEventListener('keydown', (e) => {
  if (!openDrop) return;
  if (e.key === 'Escape') { closeDrop(); return; }

  // ── Historical dropdown (virtual scroll) ──
  if (openDrop === 'hist') {
    const flat = _vs.flatItems;
    if (!flat.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _kbHighlightIdx = _kbHighlightIdx < 0 ? _vsFirstItem() : _vsNextItem(_kbHighlightIdx, 1);
      _vsScrollToIdx(_kbHighlightIdx);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _kbHighlightIdx = _kbHighlightIdx < 0 ? _vsLastItem() : _vsNextItem(_kbHighlightIdx, -1);
      _vsScrollToIdx(_kbHighlightIdx);
    } else if (e.key === 'Home') {
      e.preventDefault();
      _kbHighlightIdx = _vsFirstItem();
      _vsScrollToIdx(_kbHighlightIdx);
    } else if (e.key === 'End') {
      e.preventDefault();
      _kbHighlightIdx = _vsLastItem();
      _vsScrollToIdx(_kbHighlightIdx);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (_kbHighlightIdx >= 0 && flat[_kbHighlightIdx] && flat[_kbHighlightIdx].type === 'item') {
        selectFromDrop(flat[_kbHighlightIdx].idx);
      }
    }
    return;
  }

  // ── Live / Complete dropdowns (simple list) ──
  const items = _dropSimpleItems(openDrop);
  if (!items.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _kbHighlightIdx = _kbHighlightIdx < items.length - 1 ? _kbHighlightIdx + 1 : 0;
    _dropApplyHighlight(openDrop);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _kbHighlightIdx = _kbHighlightIdx > 0 ? _kbHighlightIdx - 1 : items.length - 1;
    _dropApplyHighlight(openDrop);
  } else if (e.key === 'Home') {
    e.preventDefault();
    _kbHighlightIdx = 0;
    _dropApplyHighlight(openDrop);
  } else if (e.key === 'End') {
    e.preventDefault();
    _kbHighlightIdx = items.length - 1;
    _dropApplyHighlight(openDrop);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (_kbHighlightIdx >= 0 && _kbHighlightIdx < items.length) {
      selectFromDrop(items[_kbHighlightIdx].idx);
    }
  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    // Type-ahead for live/complete dropdowns
    clearTimeout(_kbTypeTimer);
    _kbTypeBuffer += e.key.toLowerCase();
    _kbTypeTimer = setTimeout(() => { _kbTypeBuffer = ''; }, 500);
    const match = items.findIndex(it => it.name.toLowerCase().startsWith(_kbTypeBuffer));
    if (match >= 0) {
      _kbHighlightIdx = match;
      _dropApplyHighlight(openDrop);
    }
  }
});

function renderTabs() {
  const el = document.getElementById('tabBar');
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'live');
  const complete = ts.map((t, i) => ({t, i})).filter(x => x.t.status === 'complete');
  const nHist = ts.filter(t => t.status === 'historical').length;
  const sel = ts[selectedIndex];

  let html = '';

  // ── Upcoming dropdown ──
  html += `<div class="drop-wrap">`;
  html += `<div class="cat-btn cat-btn--live" id="dropBtn_live" data-act="toggle-drop" data-drop="live" data-keyable="1" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `<span class="live-dot"></span>Upcoming <span class="cat-count" style="background:var(--green-dim);color:var(--green)">${live.length}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu" id="dropMenu_live" role="listbox" aria-label="Upcoming tournaments">`;
  live.sort((a, b) => a.t.days_remaining - b.t.days_remaining).forEach(({t, i}) => {
    html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-act="select-from-drop" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" role="option">`;
    html += `<span class="cat-item-name"><span class="live-dot"></span>${esc(t.family)}${paceBadgeHTML(getPaceAlert(t))}</span>`;
    html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg</span></div>`;
  });
  html += `</div></div>`;

  // ── Complete dropdown ──
  html += `<div class="drop-wrap">`;
  html += `<div class="cat-btn cat-btn--complete" id="dropBtn_complete" data-act="toggle-drop" data-drop="complete" data-keyable="1" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `Complete <span class="cat-count">${complete.length}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu" id="dropMenu_complete" role="listbox" aria-label="Completed tournaments">`;
  complete.forEach(({t, i}) => {
    html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-act="select-from-drop" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" role="option">`;
    html += `<span class="cat-item-name">${esc(t.family)}</span>`;
    html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)}</span></div>`;
  });
  html += `</div></div>`;

  // ── Historical search dropdown ──
  html += `<div class="drop-wrap">`;
  html += `<div class="cat-btn cat-btn--hist" id="dropBtn_hist" data-act="toggle-drop" data-drop="hist" data-keyable="1" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `<span style="opacity:.6">&#128269;</span> Historical <span class="cat-count" style="background:var(--purple-dim);color:var(--purple)">${nHist}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu drop-menu-search" id="dropMenu_hist" role="listbox" aria-label="Historical tournaments">`;
  html += `<div class="tab-search-bar">`;
  html += `<span style="opacity:.5">&#128269;</span>`;
  html += `<input class="tab-search-input" id="histSearchInput" type="text" placeholder="Search tournaments..." data-inputact="filter-hist" autocomplete="off">`;
  html += `</div>`;
  html += `<div class="tab-search-results" id="histSearchResults"></div>`;
  html += `</div></div>`;

  el.innerHTML = html;
}
