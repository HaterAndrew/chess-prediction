// ══════════════════════════════════════════════════════════
// PAGE TABS
// ══════════════════════════════════════════════════════════
let _currentTab = 'predictions';
const MORE_MENU_TABS = ['compare', 'email', 'about', 'puzzles'];
function switchPageTab(tab, skipHash) {
  if (_mobileVP() && _currentTab !== tab) _haptic(8);
  _currentTab = tab;
  // Reset active + aria-selected across both the visible strip and the overflow
  // disclosure (its items are role="tab"); only touch aria-selected where present
  // so the "Other" disclosure trigger keeps aria-expanded semantics instead.
  document.querySelectorAll('.page-tab, .page-tab-drop .cat-item').forEach(t => {
    t.classList.remove('active');
    if (t.hasAttribute('aria-selected')) t.setAttribute('aria-selected', 'false');
  });
  document.querySelectorAll('.page-tab-panel').forEach(p => p.classList.remove('active'));
  const tabBtn = document.getElementById('ptab-' + tab);
  if (tabBtn) {
    tabBtn.classList.add('active');
    tabBtn.setAttribute('aria-selected', 'true');
    // Scroll active tab into view only when the strip actually overflows
    const tabsContainer = tabBtn.closest('.page-tabs');
    if (tabsContainer && tabsContainer.scrollWidth > tabsContainer.clientWidth + 1) {
      tabBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }
  // Mirror active underline onto the "Menu" page-tab when current tab is in the dropdown
  if (MORE_MENU_TABS.includes(tab)) {
    const moreBtn = document.getElementById('ptab-more');
    if (moreBtn) { moreBtn.classList.add('active'); moreBtn.removeAttribute('aria-selected'); }
  }
  closeMoreMenu();
  const panel = document.getElementById('panel-' + tab);
  panel.classList.add('active');
  if (tab === 'puzzles') initPuzzles();
  if (tab === 'email') initEmailTab();
  if (tab === 'performance') initPerformanceTab();
  if (tab === 'compare') renderCompareTab();
  if (tab === 'ask') initAskTab();
  if (tab === 'audit') initAuditTab();
  // Focus management: move focus to new panel for screen readers
  panel.setAttribute('tabindex', '-1');
  panel.focus({ preventScroll: true });
  if (!skipHash) updateHash();
}

// Mobile swipe-between-tabs navigation
const PAGE_TAB_ORDER = ['predictions', 'compare', 'email', 'performance', 'audit', 'about', 'puzzles', 'ask'];
(function setupSwipeNav() {
  if (typeof window === 'undefined' || !('ontouchstart' in window)) return;
  let startX = 0, startY = 0, startT = 0;
  const SWIPE_THRESHOLD = 60, VERTICAL_LIMIT = 50, TIME_LIMIT = 500, EDGE_GUARD = 28;
  const ignoreIn = el => !!(el && el.closest && el.closest('canvas, .tourney-table-wrap, .compare-chart-wrap, .drop-menu, .tab-search-panel, .email-output, .email-preview, iframe, .chess-board, .de-table input'));
  document.addEventListener('touchstart', e => {
    if (!_mobileVP() || e.touches.length !== 1) return;
    const t = e.touches[0];
    if (t.clientX < EDGE_GUARD || t.clientX > window.innerWidth - EDGE_GUARD) return;
    if (ignoreIn(e.target)) { startX = 0; return; }
    startX = t.clientX; startY = t.clientY; startT = Date.now();
  }, { passive: true });
  document.addEventListener('touchend', e => {
    if (!startX) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - startX, dy = t.clientY - startY, dt = Date.now() - startT;
    startX = 0;
    if (dt > TIME_LIMIT || Math.abs(dy) > VERTICAL_LIMIT || Math.abs(dx) < SWIPE_THRESHOLD) return;
    const idx = PAGE_TAB_ORDER.indexOf(_currentTab);
    if (idx < 0) return;
    if (dx < 0 && idx < PAGE_TAB_ORDER.length - 1) switchPageTab(PAGE_TAB_ORDER[idx + 1]);
    else if (dx > 0 && idx > 0) switchPageTab(PAGE_TAB_ORDER[idx - 1]);
  }, { passive: true });
})();

// ── "Other" overflow: a disclosure (button + aria-expanded region) holding the
//    less-used tabs. Not a role=menu — the items navigate to tabpanels. ──
function _moreMenuItems() {
  const drop = document.getElementById('moreMenuDrop');
  return drop ? Array.from(drop.querySelectorAll('.cat-item')) : [];
}
function openMoreMenuDrop() {
  const drop = document.getElementById('moreMenuDrop');
  const btn = document.getElementById('ptab-more');
  if (!drop || !btn) return;
  const r = btn.getBoundingClientRect();
  const desiredLeft = r.left;                     // anchor below the button
  drop.style.top = (r.bottom + 6) + 'px';
  drop.style.left = '0px';
  drop.classList.add('open');
  const dw = drop.offsetWidth;                    // clamp horizontally once rendered
  const maxLeft = Math.max(8, window.innerWidth - dw - 8);
  drop.style.left = Math.min(desiredLeft, maxLeft) + 'px';
  btn.setAttribute('aria-expanded', 'true');
}
function toggleMoreMenu(e) {
  if (e) e.stopPropagation();
  const drop = document.getElementById('moreMenuDrop');
  if (!drop) return;
  if (drop.classList.contains('open')) closeMoreMenu();
  else openMoreMenuDrop();
}
function closeMoreMenu() {
  const drop = document.getElementById('moreMenuDrop');
  const btn = document.getElementById('ptab-more');
  if (!drop) return;
  drop.classList.remove('open');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}
function pickMoreTab(tab) {
  closeMoreMenu();
  switchPageTab(tab);
}
document.addEventListener('click', (e) => {
  const wrap = document.getElementById('moreMenuWrap');
  if (!wrap) return;
  if (!wrap.contains(e.target)) closeMoreMenu();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeMoreMenu();
});
window.addEventListener('resize', closeMoreMenu);
window.addEventListener('scroll', closeMoreMenu, { passive: true });

// Disclosure keyboard support: ArrowUp/Down from the trigger opens and enters
// the panel; inside, arrows rove (with wrap), Home/End jump, Escape closes and
// restores focus to the trigger, Tab closes.
(function moreMenuKeys() {
  const btn = document.getElementById('ptab-more');
  const drop = document.getElementById('moreMenuDrop');
  if (!btn || !drop) return;
  btn.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      openMoreMenuDrop();
      const items = _moreMenuItems();
      if (items.length) (e.key === 'ArrowUp' ? items[items.length - 1] : items[0]).focus();
    }
  });
  drop.addEventListener('keydown', e => {
    const items = _moreMenuItems();
    if (!items.length) return;
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); closeMoreMenu(); btn.focus(); }
    else if (e.key === 'Tab') { closeMoreMenu(); }
  });
})();

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

// ══════════════════════════════════════════════════════════
// DELTA BANNER
// ══════════════════════════════════════════════════════════
function renderDelta(t) {
  const banner = document.getElementById('deltaBanner');
  const icon = document.getElementById('deltaIcon');
  const main = document.getElementById('deltaMain');
  const sub = document.getElementById('deltaSub');
  const ctx = document.getElementById('deltaContext');
  const val = document.getElementById('deltaValue');

  // Multi-year at-T context — stakeholder-requested sub-line under the YoY
  // headline. Verdict-first phrasing ("Tracking [ahead/behind/on pace] with
  // N-year pace") so the eye lands on the direction before parsing the %.
  if (ctx) {
    const alert = getPaceAlert(t);
    if (alert && alert.status) {
      const verdict = alert.status === 'above_pace' ? 'ahead of'
                    : alert.status === 'below_pace' ? 'behind'
                    : 'on pace with';
      // Prefer the explicit n_years field (pipeline 2026-05-17+); fall back
      // to regex on the older message string for any stale website_data.json.
      const n = alert.n_years || ((alert.message || '').match(/(\d+)-year/) || [])[1];
      const yrs = n ? `${n}-year aggregate` : 'multi-year aggregate';
      const dev = alert.deviation_pct;
      const devStr = (dev > 0 ? `+${dev}` : `${dev}`) + '%';
      ctx.textContent = `Tracking ${verdict} ${yrs} pace (${devStr})`;
    } else {
      ctx.textContent = '';
    }
  }

  if (isDone(t)) {
    // Compare to historical average
    if (t.historical && t.historical.length > 0) {
      const avg = t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length;
      const diff = ((t.current_count - avg) / avg * 100);
      const absDiff = Math.abs(diff).toFixed(1);
      if (diff > 5) {
        banner.className = 'delta-banner green';
        icon.innerHTML = '&#9650;';
        main.textContent = `${t.family} ${t.year}: Above Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% above historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `+${absDiff}%`;
        val.className = 'delta-value green';
      } else if (diff < -5) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `${t.family} ${t.year}: Below Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% below historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `-${absDiff}%`;
        val.className = 'delta-value red';
      } else {
        banner.className = 'delta-banner gold';
        icon.innerHTML = '&#9654;';
        main.textContent = `${t.family} ${t.year}: On Par`;
        sub.textContent = `${fmt(t.current_count)} entries · In line with historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`;
        val.className = 'delta-value gold';
      }
    } else {
      banner.className = 'delta-banner muted';
      icon.innerHTML = '&#10003;';
      main.textContent = `${t.family} ${t.year}: Complete`;
      sub.textContent = `Final count: ${fmt(t.current_count)} entries`;
      val.textContent = '';
      val.className = 'delta-value';
    }
    return;
  }

  // Live tournament — compare to historical pace
  if (t.historical && t.historical.length > 0) {
    const lastYr = t.historical[t.historical.length - 1];
    // Prefer the explicit prior_year_pace.count_at_same_point — it's derived
    // from last year's actual daily registrations on this calendar day.
    // Fall back to the family-average curve only when the explicit field is
    // missing (no 2025 daily data for this family). Curve-derived estimates
    // can drift wildly from reality when the prior year's curve was unusual.
    const priorPace = t.prior_year_pace;
    const lastYrAtT = (priorPace && priorPace.count_at_same_point != null)
      ? priorPace.count_at_same_point
      : (t.registration_curve
          ? Math.round(lastYr.count * interpCurve(t.registration_curve, t.days_remaining))
          : null);
    const lastYrLabel = priorPace?.year ?? lastYr.year;

    if (lastYrAtT && lastYrAtT > 0) {
      const diff = t.current_count - lastYrAtT;
      const pctVal = ((diff / lastYrAtT) * 100);
      const pct = pctVal.toFixed(1);
      const absPct = Math.abs(pctVal).toFixed(1);

      // Compute recent daily pace
      let paceSuffix = '';
      if (t.daily_data && t.daily_data.length >= 3) {
        const recent = t.daily_data.slice(-7);
        if (recent.length >= 2) {
          const daySpan = recent[recent.length-1][0] - recent[0][0];
          const regSpan = recent[recent.length-1][1] - recent[0][1];
          if (daySpan > 0) {
            paceSuffix = ` · ${(regSpan / daySpan).toFixed(1)}/day recent pace`;
          }
        }
      }

      if (diff > 0) {
        banner.className = 'delta-banner green';
        icon.innerHTML = '&#9650;';
        main.textContent = `Tracking ahead of ${lastYrLabel} pace`;
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at the same days-to-event mark in ${lastYrLabel}${paceSuffix}`;
        val.textContent = `+${absPct}%`;
        val.className = 'delta-value green';
      } else if (diff < 0) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `Tracking behind ${lastYrLabel} pace`;
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at the same days-to-event mark in ${lastYrLabel}${paceSuffix}`;
        val.textContent = `-${absPct}%`;
        val.className = 'delta-value red';
      } else {
        banner.className = 'delta-banner gold';
        icon.innerHTML = '&#9654;';
        main.textContent = `Tracking on pace with ${lastYrLabel}`;
        sub.textContent = `${fmt(t.current_count)} registered${paceSuffix}`;
        val.textContent = '0%';
        val.className = 'delta-value gold';
      }
      return;
    }
  }

  // Fallback — no historical comparison available
  banner.className = 'delta-banner gold';
  icon.innerHTML = '&#9654;';
  main.textContent = `${t.family}: Registration in progress`;
  const _evStarted = t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const _countdown = _evStarted
    ? `${t.days_remaining} days of online registration left`
    : `${t.days_remaining} days until event`;
  sub.textContent = `${fmt(t.current_count)} entries registered · ${_countdown} · predicted final: ${fmt(t.point_estimate)}`;
  val.textContent = `T-${t.days_remaining}`;
  val.className = 'delta-value gold';
}

// ══════════════════════════════════════════════════════════
// HERO + KPI
// ══════════════════════════════════════════════════════════

// Build the prediction-tile tooltip from live PERFORMANCE_DATA so every
// pipeline run (daily auto_update + monthly recalibration) refreshes the
// numbers automatically. No hardcoded counts/biases.
function _calibrationTooltip() {
  const fallback = 'Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted.';
  if (typeof PERFORMANCE_DATA === 'undefined' || !PERFORMANCE_DATA) return fallback;
  const yr = String(new Date().getFullYear());
  const yearData = (PERFORMANCE_DATA.years || {})[yr] || PERFORMANCE_DATA;
  const agg = yearData.aggregate || PERFORMANCE_DATA.aggregate || [];
  if (!agg.length) return fallback;
  // n-weighted mean of |bias_pct| across T-points: how much the model
  // typically over- or under-shoots in the current year.
  let nSum = 0, biasNum = 0;
  for (const a of agg) {
    if (typeof a.bias_pct === 'number' && typeof a.n === 'number') {
      biasNum += a.bias_pct * a.n;
      nSum += a.n;
    }
  }
  const meanBias = nSum > 0 ? biasNum / nSum : null;
  const nEvents = yearData.n_tournaments ?? PERFORMANCE_DATA.n_tournaments ?? null;
  const asof = PERFORMANCE_DATA.generated || '';
  if (meanBias == null || nEvents == null) return fallback;
  const dir = meanBias > 0 ? 'over-predicting' : 'under-predicting';
  const absBias = Math.abs(meanBias).toFixed(1);
  return `Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted. ${yr} backtest (${nEvents} events, asof ${asof}) shows the model has been ${dir} by ${absBias}% on avg; kept conservative on purpose. See Performance tab for full breakdown.`;
}

function renderHero(t) {
  const statusPrefix = t.status === 'historical' ? `${t.year} ` : '';
  const heroLabel = document.getElementById('heroLabel');
  if (isDone(t)) {
    heroLabel.textContent = `${statusPrefix}Final Entries`;
    heroLabel.removeAttribute('title');
    heroLabel.style.cursor = '';
  } else {
    heroLabel.innerHTML = `Predicted Final Entries <span style="opacity:.55;font-weight:400;cursor:help" title="${esc(_calibrationTooltip())}">ⓘ</span>`;
    heroLabel.style.cursor = 'default';
  }
  const heroNum = document.getElementById('heroNumber');
  // Animate number count-up (skip the tween under prefers-reduced-motion)
  const target = t.point_estimate;
  if (_reduceMotion()) {
    heroNum.textContent = fmt(Math.round(target));
  } else {
    const duration = 600;
    const start = performance.now();
    (function animHero(now) {
      const p = Math.min(((now || performance.now()) - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      heroNum.textContent = fmt(Math.round(target * ease));
      if (p < 1) requestAnimationFrame(animHero);
    })(performance.now());
  }
  // Solid color: gold for live predictions, blue for completed totals.
  // Prior gradient-text + background-clip path was killed in iter 1 of
  // this UX pass (banned anti-pattern, mushy at small sizes). Re-applying
  // the gradient inline here would have undone that fix.
  heroNum.style.background = '';
  heroNum.style.backgroundClip = '';
  heroNum.style.webkitBackgroundClip = '';
  heroNum.style.webkitTextFillColor = '';
  heroNum.style.color = isDone(t) ? 'var(--blue-bright)' : 'var(--gold)';

  // Audit telemetry: prefer explicit low_confidence flag over derived nHist count.
  // n_historical_editions is the audit-canonical count (excludes COVID/online); fall back
  // to the historical array length only when the audit fields aren't present.
  const nHist = (typeof t.n_historical_editions === 'number')
    ? t.n_historical_editions
    : (t.historical ? t.historical.length : 0);
  const isLowConfidence = (typeof t.low_confidence === 'boolean')
    ? t.low_confidence
    : (nHist < 4);
  const confLabel = isLowConfidence
    ? (nHist >= 2 ? 'Low Confidence' : 'Very Low Confidence')
    : (nHist >= 8 ? 'High Confidence' : 'Medium Confidence');
  const confColor = isLowConfidence
    ? (nHist >= 2 ? 'var(--orange)' : 'var(--red)')
    : (nHist >= 8 ? 'var(--green)' : 'var(--gold)');
  const confBadge = !isDone(t) && t.ci_lower !== t.ci_upper
    ? ` <span title="${nHist} qualifying historical edition${nHist===1?'':'s'} for this family. Below 4 editions, the model marks the prediction low-confidence." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:var(--fs-1);font-weight:700;background:rgba(0,0,0,.3);border:1px solid ${confColor};color:${confColor};margin-left:6px;vertical-align:middle;cursor:help">${confLabel} · ${nHist} edition${nHist===1?'':'s'}</span>`
    : '';

  // Audit telemetry: surface fallback tier when prediction didn't use direct family ratios.
  // Expand tier badge text so the meaning is visible without a tooltip dive.
  const tierLabelMap = {
    'family-direct': 'direct · 5+ yr history',
    'family-alias':  'family alias · pooled history',
    'size-matched':  'size matched · no family history',
    'roster-pending': 'interim · not in roster yet',
  };
  const tierBadge = (!isDone(t) && t.prediction_tier && t.prediction_tier !== 'family-direct')
    ? ` <span title="Prediction used the '${t.prediction_tier}' fallback path. 'family-alias' pools history from related families; 'size-matched' uses families with comparable historical size when this family has no direct history." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:var(--fs-1);font-weight:700;background:rgba(0,0,0,.3);border:1px solid var(--blue);color:var(--blue);margin-left:6px;vertical-align:middle;cursor:help">${tierLabelMap[t.prediction_tier] || t.prediction_tier.replace('-',' ')}</span>`
    : '';

  // Confidence interval visualization. For completed tournaments we still
  // just show the final count (no CI to visualize). For live tournaments
  // with a real CI range, render a horizontal bar with the point estimate
  // marker positioned by where it sits inside [ci_lower, ci_upper].
  const ciLevel = Math.round((t.ci_level || .8) * 100);
  let ciHtml;
  if (t.ci_lower === t.ci_upper) {
    ciHtml = `<span class="ci-final">${fmt(t.current_count)} total entries</span>${confBadge}${tierBadge}`;
  } else {
    const lo = t.ci_lower, hi = t.ci_upper, pe = t.point_estimate;
    // Position 0-100% along the CI span. Clamp so off-band point estimates
    // (rare model edge cases) still render visibly inside the bar.
    const pct = Math.max(0, Math.min(100, ((pe - lo) / (hi - lo)) * 100));
    // Inline confidence rationale: surface WHY the model is N% confident.
    // Maps the qualitative confidence label + tier to a one-sentence reason.
    const conf = (t.confidence_label || '').toLowerCase();
    const tier = (t.prediction_tier || 'family-direct').toLowerCase();
    let reason;
    if (tier === 'family-direct' && conf.includes('high')) reason = 'Strong prior data: 5+ years of same-month history for this family.';
    else if (tier === 'family-direct' && conf.includes('medium')) reason = 'Moderate prior data: 3–4 years of comparable history.';
    else if (tier === 'family-direct' && conf.includes('low') && !conf.includes('very')) reason = 'Sparse prior data: under 3 comparable years.';
    else if (conf.includes('very')) reason = 'Limited or no comparable history; estimate falls back to family average.';
    else if (tier === 'family-alias') reason = 'No direct history: pooled from related families for this prediction.';
    else if (tier === 'size-matched') reason = 'No family history: drawn from families with comparable historical size.';
    else reason = `${t.confidence_label || 'Confidence'} based on ${tier.replace('-',' ')} history.`;
    ciHtml = `
      <div class="ci-bar" role="img" aria-label="${ciLevel}% confidence interval from ${fmt(lo)} to ${fmt(hi)}, point estimate ${fmt(pe)}. ${reason}" title="${reason}">
        <span class="ci-bound ci-bound-lo">${fmt(lo)}</span>
        <div class="ci-track">
          <div class="ci-track-fill"></div>
          <div class="ci-marker" style="left:${pct.toFixed(2)}%" title="Point estimate: ${fmt(pe)}. ${reason}"></div>
        </div>
        <span class="ci-bound ci-bound-hi">${fmt(hi)}</span>
      </div>
      <div class="ci-caption" style="font-size:var(--fs-1);color:var(--muted);margin-top:2px">Estimated final entries &middot; ${ciLevel}% range</div>
      <div class="ci-meta">${ciLevel}% CI${confBadge}${tierBadge}</div>
    `;
  }
  document.getElementById('heroCi').innerHTML = ciHtml;

  // Hero narrative removed — the pace verdict is already in the delta banner
  // above and the daily-pace KPI shows the 7-day pace, so the
  // paragraph here just duplicated info and threw the hero row out of
  // vertical balance with the week bars + KPI strip.
  document.getElementById('heroNarrative').innerHTML = '';

  // Festival cluster — renders inline if this tournament is part of a
  // multi-sub-event festival (e.g. World Open). No-op otherwise.
  renderFestivalCluster(t);

  // Side KPI cards
  document.getElementById('kpiCurrent').innerHTML = `
    <div class="kpi-label">Registered</div>
    <div class="kpi-value v-blue">${fmt(t.current_count)}</div>
    <div class="kpi-sub">${isDone(t) ? 'Final' : 'as of today'}</div>
  `;

  const daysColor = isDone(t) ? '' : t.days_remaining <= 7 ? 'v-red' : t.days_remaining <= 28 ? 'v-orange' : t.days_remaining <= 60 ? 'v-gold' : '';
  // Once the event has started, the live countdown is to online-registration
  // close (the 2-day schedule), not to an event start that already passed.
  const evStarted = !isDone(t) && t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  let daysLabel, daysValue, daysSub;
  if (isDone(t)) {
    daysLabel = 'Event Date';
    daysValue = fmtDate(t.event_start);
    daysSub = t.event_end ? fmtDate(t.event_start) + ' – ' + fmtDate(t.event_end) : '';
  } else if (evStarted) {
    daysLabel = 'Days to Reg. Close';
    daysValue = t.days_remaining;
    daysSub = t.registration_close ? fmtDate(t.registration_close) : 'event underway';
  } else {
    daysLabel = 'Days to Event';
    daysValue = t.days_remaining;
    daysSub = fmtDate(t.event_start);
  }
  document.getElementById('kpiDays').innerHTML = `
    <div class="kpi-label">${daysLabel}</div>
    <div class="kpi-value ${daysColor}">${daysValue}</div>
    <div class="kpi-sub">${daysSub}</div>
  `;

  // Pace/velocity card
  let paceHtml = '';
  if (!isDone(t) && t.daily_data && t.daily_data.length >= 3) {
    const recent = t.daily_data.slice(-7);
    if (recent.length >= 2) {
      const daySpan = recent[recent.length-1][0] - recent[0][0];
      const regSpan = recent[recent.length-1][1] - recent[0][1];
      const rateNum = daySpan > 0 ? regSpan / daySpan : 0;
      const rate = rateNum.toFixed(1);
      paceHtml = `
        <div class="kpi-label">7-Day Pace</div>
        <div class="kpi-value">${rate}</div>
        <div class="kpi-sub">entries / day</div>
      `;
    }
  } else if (isDone(t) && t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length);
    const diff = t.current_count - avg;
    const pct = ((diff / avg) * 100).toFixed(0);
    paceHtml = `
      <div class="kpi-label">vs Average</div>
      <div class="kpi-value ${diff >= 0 ? 'v-green' : 'v-red'}">${diff >= 0 ? '+' : ''}${pct}%</div>
      <div class="kpi-sub">hist avg: ${fmt(avg)}</div>
    `;
  }
  document.getElementById('kpiPace').innerHTML = paceHtml || `
    <div class="kpi-label">Historical</div>
    <div class="kpi-value" style="font-size:var(--fs-5);color:var(--muted)">–</div>
    <div class="kpi-sub">No pace data</div>
  `;

  // 4th card — Progress to predicted final (mobile fills 2x2 grid cleanly)
  const kpiProg = document.getElementById('kpiProgress');
  if (kpiProg) {
    if (isDone(t)) {
      // For complete tournaments, show YoY change vs last year
      const lastYr = emailLastYear ? emailLastYear(t) : null;
      if (lastYr && lastYr.count) {
        const diff = t.current_count - lastYr.count;
        const pct = ((diff / lastYr.count) * 100).toFixed(0);
        kpiProg.innerHTML = `
          <div class="kpi-label">vs ${lastYr.year}</div>
          <div class="kpi-value ${diff >= 0 ? 'v-green' : 'v-red'}">${diff >= 0 ? '+' : ''}${pct}%</div>
          <div class="kpi-sub">${fmt(lastYr.count)} prior</div>
        `;
      } else {
        kpiProg.innerHTML = `
          <div class="kpi-label">Status</div>
          <div class="kpi-value v-green" style="font-size:var(--fs-5)">Final</div>
          <div class="kpi-sub">${fmtDate(t.event_start)}</div>
        `;
      }
    } else if (t.point_estimate > 0) {
      const pct = Math.min(100, Math.round(t.current_count / t.point_estimate * 100));
      const color = pct >= 80 ? 'v-green' : pct >= 40 ? 'v-gold' : 'v-blue';
      kpiProg.innerHTML = `
        <div class="kpi-label">Progress</div>
        <div class="kpi-value ${color}">${pct}%</div>
        <div class="kpi-sub">of predicted</div>
      `;
    } else {
      kpiProg.innerHTML = `
        <div class="kpi-label">Progress</div>
        <div class="kpi-value" style="font-size:var(--fs-5);color:var(--muted)">–</div>
        <div class="kpi-sub">No prediction</div>
      `;
    }
  }

  // ── Last 7 days breakdown ──
  const weekEl = document.getElementById('weekBreakdown');
  const barsEl = document.getElementById('weekBars');
  if (!isDone(t) && t.daily_data && t.daily_data.length >= 2) {
    // Build one bar per real calendar day (v3 P1). Each bar carries its own
    // date, derived from the point's day_from_start against the exported
    // daily_start_date anchor — never from its position in the array. Days
    // covered by a scrape gap are spread across the gap and marked, so a
    // multi-day jump can no longer be drawn as a single day's registrations.
    const ivs = (typeof DailySeries !== 'undefined')
      ? DailySeries.intervals(t, { isLive: !isDone(t) })
      : [];
    const days = [];      // {n, date, estimated}
    for (const iv of ivs) {
      const perDay = iv.added / iv.span;
      for (let g = 0; g < iv.span; g++) {
        // Date of each covered day, counting forward from the interval start.
        const d = (typeof DailySeries !== 'undefined')
          ? DailySeries.pointDate(t, iv.fromDay + g + 1) : null;
        days.push({ n: Math.round(perDay), date: d, estimated: iv.isGap });
      }
    }
    while (days.length > 7) days.shift();
    if (days.length === 0 || days.every(o => o.n === 0)) {
      // No recent activity — render a quiet placeholder instead of nothing
      // so the hero-week column doesn't suddenly collapse to zero height.
      barsEl.innerHTML = `<div class="hero-week-empty">No registrations in the last 7 days</div>`;
      weekEl.style.display = '';
    } else if (days.length >= 2) {
      // Bar scale uses every day, but the "busiest day" highlight only considers
      // observed ones — an average spread across a scrape gap is not evidence
      // that that day was the peak.
      const maxNew = Math.max(...days.map(o => o.n), 1);
      const observed = days.filter(o => !o.estimated).map(o => o.n);
      const maxObserved = observed.length ? Math.max(...observed) : null;
      const anyEstimated = days.some(o => o.estimated);
      barsEl.innerHTML = days.map(o => {
        const label = (o.date && typeof DailySeries !== 'undefined')
          ? DailySeries.fmtPointDate(o.date) : '';
        const pct = Math.max((o.n / maxNew) * 100, 2);
        const isPeak = !o.estimated && maxObserved !== null && o.n === maxObserved;
        const color = isPeak ? 'var(--gold)' : 'var(--blue)';
        // A bar covering a scrape gap is an average, not an observation. Mark it
        // rather than presenting a spread-out figure as a measured daily count.
        // The dimming has to live in this one style attribute — a second style=
        // on the same element is discarded by the parser, which drops the flex
        // layout and stacks the row.
        const rowStyle = `display:flex;align-items:center;gap:6px${o.estimated ? ';opacity:.55' : ''}`;
        const tip = o.estimated ? ' title="Estimated: this day was covered by a gap in scraping"' : '';
        return `<div${tip} style="${rowStyle}">
          <span style="font-size:var(--fs-1);color:var(--muted);width:62px;text-align:right;white-space:nowrap">${label}</span>
          <div style="flex:1;height:11px;background:var(--surface2);border-radius:2px;overflow:hidden">
            <div style="width:${pct}%;height:100%;background:${color};border-radius:2px;transition:width .35s cubic-bezier(.22,1,.36,1)"></div>
          </div>
          <span style="font-size:var(--fs-1);color:var(--text2);width:30px;font-weight:${isPeak ? '700' : '400'}">${o.estimated ? '~' : '+'}${o.n}</span>
        </div>`;
      }).join('');
      if (anyEstimated) {
        barsEl.innerHTML += `<div style="font-size:var(--fs-1);color:var(--muted);margin-top:4px">~ estimated across a gap in scraping</div>`;
      }
      weekEl.style.display = '';
    } else {
      weekEl.style.display = 'none';
    }
  } else {
    weekEl.style.display = 'none';
  }
}

// ── KPI Row ──
function renderKPIRow(t) {
  const el = document.getElementById('kpiRow');
  const cards = [];

  // % registered (only for upcoming tournaments)
  if (!isDone(t)) {
    const regPct = t.point_estimate > 0 ? (t.current_count / t.point_estimate * 100).toFixed(1) : '–';
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">% Registered</div>
      <div class="kpi-value v-green">${regPct}%</div>
      <div class="kpi-sub">of predicted final</div>
    </div>`);
  }

  // Early bird info
  if (hasValidEarlyBird(t)) {
    const ebDate = new Date(t.early_bird_deadline + 'T00:00:00');
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    const ebPassed = ebDate <= today;
    const daysToEB = Math.ceil((ebDate - today) / 86400000);
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Early Bird</div>
      <div class="kpi-value ${ebPassed ? 'v-red' : 'v-green'}">${ebPassed ? 'Ended' : daysToEB + 'd'}</div>
      <div class="kpi-sub">${fmtDate(t.early_bird_deadline)}${t.early_bird_fee ? ' · $' + t.early_bird_fee : ''}</div>
    </div>`);
  }

  // Historical avg
  if (t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length);
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Past Average</div>
      <div class="kpi-value v-purple">${fmt(avg)}</div>
      <div class="kpi-sub">${t.historical.length} editions</div>
    </div>`);

    // Historical rank (for completed tournaments)
    if (isDone(t)) {
      const allCounts = [...t.historical.map(h => h.count), t.current_count].sort((a,b) => b - a);
      const rank = allCounts.indexOf(t.current_count) + 1;
      const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th';
      cards.push(`<div class="kpi-card">
        <div class="kpi-label">All-Time Rank</div>
        <div class="kpi-value ${rank <= 3 ? 'v-gold' : ''}">${rank}${suffix}</div>
        <div class="kpi-sub">of ${allCounts.length} editions</div>
      </div>`);
    }
  }

  // CI width
  if (t.ci_lower !== t.ci_upper) {
    const width = t.ci_upper - t.ci_lower;
    const widthPct = (width / t.point_estimate * 100).toFixed(0);
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">CI Width</div>
      <div class="kpi-value v-orange">&plusmn;${widthPct}%</div>
      <div class="kpi-sub">${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}</div>
    </div>`);
  }

  // Regular fee
  if (t.regular_fee) {
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Regular Fee</div>
      <div class="kpi-value" style="color:var(--text2)">$${t.regular_fee}</div>
      <div class="kpi-sub">${t.onsite_fee ? 'Onsite: $' + t.onsite_fee : ''}</div>
    </div>`);
  }

  el.innerHTML = cards.join('');
}

// ══════════════════════════════════════════════════════════
// PROGRESS BARS
// ══════════════════════════════════════════════════════════
function renderProgress(t) {
  const el = document.getElementById('progressRow');
  if (isDone(t) || !t.daily_data || t.daily_data.length === 0) { el.innerHTML = ''; return; }

  // v3 P3: span the registration window from its real start date to the event,
  // not from the tail of the data array. The old form (last point's day index
  // plus days_remaining) silently assumed the last scrape happened today, so a
  // stale or gappy tail shortened the window and this bar contradicted the pace
  // banner rendered from the same card.
  let totalDays;
  if (t.daily_start_date && t.event_start) {
    totalDays = daysBetween(t.daily_start_date, t.event_start);
  }
  if (!totalDays || totalDays <= 0) {
    totalDays = t.daily_data[t.daily_data.length - 1][0] + t.days_remaining || 120;
  }
  const elapsed = Math.max(0, totalDays - t.days_remaining);
  const timePct = Math.min(100, (elapsed / totalDays * 100)).toFixed(0);
  const regPct = Math.min(100, (t.current_count / t.point_estimate * 100)).toFixed(0);

  el.innerHTML = `
    <div class="progress-block">
      <div class="progress-header"><span>Time Elapsed <span style="opacity:.5">(${elapsed} of ${totalDays} days)</span></span><span>${timePct}%</span></div>
      <div class="progress-bar"><div class="progress-fill pf-blue" style="width:${timePct}%"></div></div>
    </div>
    <div class="progress-block">
      <div class="progress-header"><span>Entries Received <span style="opacity:.5">(${fmt(t.current_count)} of ~${fmt(t.point_estimate)})</span></span><span>${regPct}%</span></div>
      <div class="progress-bar"><div class="progress-fill pf-gold" style="width:${regPct}%"></div></div>
    </div>
  `;
}

function renderChart(t) {
  const ctx = document.getElementById('mainChart');
  if (chart) { chart.destroy(); chart = null; }

  if (!t.daily_data || t.daily_data.length === 0 || !t.event_start) {
    // No registration timeline data or missing event date — show placeholder
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = `${t.family} ${t.year}: No registration timeline available`;
    document.getElementById('chartCard').classList.remove('live-glow');
    return;
  }

  const eventStart = t.event_start;
  const datasets = [];

  // v3 P1: draw the sanitised series, not the raw array. Points that exceed the
  // scraped entry total are impossible and used to be plotted as-is — that is
  // how a 625-entry curve was drawn for a 197-entry event.
  const series = (typeof DailySeries !== 'undefined')
    ? DailySeries.sanitizeSeries(t.daily_data, {
        currentCount: t.current_count, isLive: !isDone(t) }).points
    : t.daily_data;
  if (!series.length) {
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = `${t.family} ${t.year}: No registration timeline available`;
    document.getElementById('chartCard').classList.remove('live-glow');
    return;
  }

  const lastDay = series[series.length - 1];
  const totalSpan = lastDay[0] + t.days_remaining;

  // Date each point from its own day index against the exported anchor. The old
  // math (event_start minus (totalSpan - day)) assumed the final point was
  // exactly days_remaining from the event, i.e. that no scrape day was ever
  // missed. When one was, every x-date on the chart shifted.
  // Built with addDays (local midnight) rather than DailySeries.pointDate (UTC
  // midnight): every other series on this axis — projected, CI arms, historical
  // overlays — is local-anchored, and mixing the two conventions would offset
  // the actual line against them by the viewer's UTC offset.
  const dayToDate = (dayFromStart) => (
    t.daily_start_date
      ? addDays(t.daily_start_date, dayFromStart)
      : addDays(eventStart, -(totalSpan - dayFromStart))
  );
  const regOpenDate = dayToDate(0);

  // Actual data
  const actualData = series.map(d => ({ x: dayToDate(d[0]), y: d[1] }));

  // Visible x-window (range control) + right headroom; remember the inputs so
  // setChartRange can recompute without a full re-render.
  const cw = _chartWindow(t, series, dayToDate);
  _chartWindowState = { t, series, dayToDate };

  // Only show point for first, last, and every 7th day to avoid clutter
  const pointRadii = actualData.map((_, i) => {
    if (i === actualData.length-1 && !isDone(t)) return 6; // today - prominent
    if (i === actualData.length-1 && isDone(t)) return 4;  // final point
    if (i === 0) return 3;  // first point
    return 0;  // hide intermediate points
  });

  // Gradient fill under actual data. The old version hardcoded a 380px
  // gradient height (wrong whenever CSS resizes the plot) and allocated a
  // fresh CanvasGradient on every scriptable pass — areaGradient fixes both.
  const _actualGrad = {};

  datasets.push({
    label: 'Actual Entries',
    data: actualData,
    borderColor: PALETTE.blue,
    backgroundColor: (context) => areaGradient(context.chart, _actualGrad, [
      [0, themeRgba(PALETTE.blue, 0.22)],
      [1, themeRgba(PALETTE.blue, 0)]
    ]),
    fill: true,
    borderWidth: 2.5,
    pointRadius: pointRadii,
    pointHoverRadius: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? 8 : 6),
    pointHoverBackgroundColor: PALETTE.blue,
    pointHoverBorderColor: PALETTE.text,
    pointHoverBorderWidth: 2,
    pointBackgroundColor: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? PALETTE.text : PALETTE.blue),
    pointBorderColor: PALETTE.blue,
    pointBorderWidth: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? 3 : 0),
    tension: 0.3,
    order: 2
  });

  // Build (year -> historical edition with daily_data) lookup once for the
  // historical-line overlay block below. Only years with multi-point daily
  // series qualify.
  const histLookup = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(other => {
    if (other.family === t.family && other.status === 'historical' &&
        Array.isArray(other.daily_data) && other.daily_data.length > 1) {
      histLookup[other.year] = other;
    }
  });

  // Projection + CI band for live
  if (!isDone(t) && t.registration_curve) {
    const projData = [];
    const todayDB = t.days_remaining;
    const todayPct = interpCurve(t.registration_curve, todayDB);

    // Project to the full point_estimate. The label says "Projected" and
    // the user reads it as "where will this finish" — silently discounting
    // it to a scrape-equivalent value is the wrong contract.
    const scaleFactor = todayPct > 0 ? t.point_estimate / interpCurve(t.registration_curve, 0) : t.point_estimate;

    // Start projection from the last actual data point to avoid a gap
    const lastActual = actualData.length > 0 ? actualData[actualData.length - 1] : null;
    if (lastActual) {
      projData.push({ x: lastActual.x, y: lastActual.y });
    }

    for (let db = todayDB; db >= 0; db--) {
      const pct = interpCurve(t.registration_curve, db);
      const projDate = addDays(eventStart, -db);
      // Skip points at or before the last actual data point
      if (lastActual && projDate <= lastActual.x) continue;
      projData.push({ x: projDate, y: Math.round(scaleFactor * pct) });
    }

    datasets.push({
      label: 'Projected',
      data: projData,
      borderColor: PALETTE.gold,
      borderWidth: 2,
      borderDash: [6, 4],
      pointRadius: 0,
      pointHoverRadius: 6,
      pointHoverBackgroundColor: PALETTE.gold,
      pointHoverBorderColor: PALETTE.text,
      pointHoverBorderWidth: 2,
      tension: 0.3,
      order: 3
    });

    // CI band — full ci_upper/ci_lower from the model, anchored to event day.
    const ciUp = [], ciLo = [];
    const pctAt0 = interpCurve(t.registration_curve, 0);
    const ciUpperScale = pctAt0 > 0 ? t.ci_upper / pctAt0 : t.ci_upper;
    const ciLowerScale = pctAt0 > 0 ? t.ci_lower / pctAt0 : t.ci_lower;
    for (let db = todayDB; db >= 0; db--) {
      const date = addDays(eventStart, -db);
      const pctAtDb = interpCurve(t.registration_curve, db);
      ciUp.push({ x: date, y: Math.round(ciUpperScale * pctAtDb) });
      ciLo.push({ x: date, y: Math.max(0, Math.round(ciLowerScale * pctAtDb)) });
    }
    // Band paint comes from CI Upper's fill('+1') alone; a vertical fade keeps
    // the band readable near the projection line without muddying the bottom.
    const _ciGrad = {};
    datasets.push({
      label: 'CI Upper', data: ciUp,
      borderColor: themeRgba(PALETTE.gold, 0.22), borderWidth: 1,
      backgroundColor: (context) => areaGradient(context.chart, _ciGrad, [
        [0, themeRgba(PALETTE.gold, 0.16)],
        [1, themeRgba(PALETTE.gold, 0.03)]
      ]),
      fill: '+1', pointRadius: 0, tension: 0.3, order: 5
    });
    datasets.push({
      label: 'CI Lower', data: ciLo,
      borderColor: themeRgba(PALETTE.gold, 0.22), borderWidth: 1,
      backgroundColor: themeRgba(PALETTE.gold, 0.12),
      pointRadius: 0, tension: 0.3, order: 5
    });
  }

  // Historical traces — dashed lines, no points, for past year curves of this family
  if (t.historical && t.registration_curve) {
    const histColors = [
      themeRgba(PALETTE.muted, 0.45),  // most recent — brightest
      themeRgba(PALETTE.muted, 0.32),
      themeRgba(PALETTE.muted, 0.22),
      themeRgba(PALETTE.muted, 0.14),
      themeRgba(PALETTE.muted, 0.10),
    ];
    // histLookup is built once at the top of renderChart (above the
    // projection block) so the scrape-ratio computation and the historical
    // line overlays share one source of truth. Cap to most recent N years
    // that HAVE real daily data: 1 on mobile, 5 on desktop.
    const realYears = t.historical.filter(h => histLookup[h.year]);
    const recent = realYears.slice(_mobileVP() ? -1 : -5);
    recent.forEach((h, i) => {
      const real = histLookup[h.year];
      const hData = [];
      // v4 U2 (audit/AUDIT_2026-07-26.md): same contract as the actual line and
      // the compare traces — draw the sanitised series, never the raw array.
      // Historical editions get no currentCount cap (isLive: false), but they
      // still need the duplicate-day and monotonicity cleaning: the server-side
      // historical path only sorts.
      const dd = (typeof DailySeries !== 'undefined')
        ? DailySeries.sanitizeSeries(real.daily_data, { isLive: false }).points
        : real.daily_data;
      if (!dd.length) return;
      const maxDay = dd[dd.length - 1][0];
      // v3 P4: anchor each historical curve to ITS OWN event date, not to the
      // tail of its data. The tail is wherever scraping happened to stop — the
      // code's own comment notes it misses ~10% of entries — so aligning on it
      // slid a year whose scraping ended early against the years around it, and
      // against the live curve it is meant to be compared with. When that year
      // exports a daily_start_date and an event_start, days-before-event is
      // computable exactly; otherwise fall back to the old tail anchor.
      const canAnchor = real.daily_start_date && real.event_start;
      // v4 U1 (audit/AUDIT_2026-07-26.md): pure day arithmetic, no Date
      // round-trip. The old form built a local-midnight Date and reprojected it
      // through toISOString()'s UTC, which lands on the previous calendar day
      // east of Greenwich and shifted every overlay one day left there.
      const spanToEvent = canAnchor
        ? daysBetween(real.daily_start_date, real.event_start)
        : null;
      dd.forEach(p => {
        // Distance of this point from its own year's event, in whole days.
        const T = canAnchor ? spanToEvent - p[0] : maxDay - p[0];
        if (T >= 0 && T <= 120) {
          hData.push({ x: addDays(eventStart, -T), y: p[1] });
        }
      });
      // Don't connect scrape-end to final with a line — the few remaining
      // entries (~10% gap, typically) get logged in the days after event day
      // when we're no longer scraping, so we don't know their exact timing.
      // The final-count marker dot below shows where the year ended.
      hData.sort((a, b) => a.x - b.x);
      const colorIdx = recent.length - 1 - i;
      datasets.push({
        label: `${h.year}`,
        data: hData,
        borderColor: histColors[colorIdx] || histColors[histColors.length - 1],
        borderWidth: 1.25,
        borderDash: [5, 4],
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: histColors[colorIdx] || histColors[histColors.length - 1],
        pointHoverBorderColor: PALETTE.text,
        pointHoverBorderWidth: 1.5,
        tension: 0.3,
        order: 6
      });
      // Final-count marker, plotted as a single point (no line) at event day
      // in the same color as the year line. Shows the small gap between
      // scrape-end and the eventual final after post-event reconciliation.
      const markerColor = histColors[colorIdx] || histColors[histColors.length - 1];
      datasets.push({
        label: `${h.year} final`,
        data: [{ x: addDays(eventStart, 0), y: h.count }],
        showLine: false,
        backgroundColor: markerColor,
        borderColor: markerColor,
        pointStyle: 'circle',
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBorderColor: PALETTE.text,
        pointBorderWidth: 1.5,
        order: 4
      });
    });
  }

  // Vertical lines plugin
  const vertLinePlugin = makeVertMarkersPlugin('vertLines', () => {
    const lines = [];
    const _isM = _mobileVP();
    // On mobile, only the Today line — Early Bird and Event labels overlap on
    // narrow screens (the days-to-event KPI card tells the user already).
    if (!_isM && hasValidEarlyBird(t)) lines.push({ value: new Date(t.early_bird_deadline + 'T00:00:00'), label: 'Early Bird', color: PALETTE.green });
    if (!isDone(t)) lines.push({ value: new Date(TOURNAMENT_DATA.generated + 'T00:00:00'), label: 'Today', color: PALETTE.blue });
    if (!_isM && t.event_start) lines.push({ value: new Date(t.event_start + 'T00:00:00'), label: 'Event', color: PALETTE.red });
    return lines;
  });

  // Crosshair plugin — vertical line that follows mouse x position
  const crosshairPlugin = {
    id: 'crosshair',
    _mouseX: null,
    afterEvent(chartInstance, args) {
      const evt = args.event;
      // Mouse events power desktop crosshair; touch events power mobile.
      // Without the touch branches, tapping the chart on a phone tooltips
      // but never shows the helpful vertical crosshair line.
      if (evt.type === 'mousemove' || evt.type === 'click' ||
          evt.type === 'touchmove' || evt.type === 'touchstart') {
        this._mouseX = evt.x;
      } else if (evt.type === 'mouseout' || evt.type === 'touchend' ||
                 evt.type === 'touchcancel') {
        this._mouseX = null;
      }
    },
    afterDraw(chartInstance) {
      if (this._mouseX == null) return;
      if (!chartInstance.tooltip?._active?.length) return;
      const ctx2 = chartInstance.ctx;
      const x = this._mouseX;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      if (x < xScale.left || x > xScale.right) return;

      ctx2.save();
      ctx2.beginPath();
      ctx2.setLineDash([3, 3]);
      ctx2.strokeStyle = themeRgba(PALETTE.muted, 0.35);
      ctx2.lineWidth = 1;
      ctx2.moveTo(x, yScale.top);
      ctx2.lineTo(x, yScale.bottom);
      ctx2.stroke();
      ctx2.restore();
    }
  };

  // Soft glow under the Actual line (dataset 0). Desktop only: shadowed
  // strokes cost a full extra raster pass per frame, and small screens get
  // no benefit at their line weight. The built-in filler runs before inline
  // plugins, so the area fill underneath stays un-shadowed.
  const lineGlowPlugin = {
    id: 'lineGlow',
    beforeDatasetDraw(chartInstance, args) {
      if (args.index !== 0 || _mobileVP()) return;
      chartInstance.ctx.save();
      chartInstance.ctx.shadowColor = themeRgba(PALETTE.blue, 0.55);
      chartInstance.ctx.shadowBlur = 6;
    },
    afterDatasetDraw(chartInstance, args) {
      if (args.index !== 0 || _mobileVP()) return;
      chartInstance.ctx.restore();
    }
  };

  // Projection endpoint: gold dot + "approx N" label at (event day, predicted
  // final). Desktop + live only; mobile keeps the hero number as the source.
  const endpointLabelPlugin = {
    id: 'endpointLabel',
    afterDraw(c) {
      if (isDone(t) || !t.point_estimate || !t.event_start || _mobileVP()) return;
      const xS = c.scales.x, yS = c.scales.y;
      const px = xS.getPixelForValue(new Date(t.event_start + 'T00:00:00').getTime());
      const py = yS.getPixelForValue(t.point_estimate);
      if (px < xS.left || px > xS.right || py < yS.top || py > yS.bottom) return;
      const g = c.ctx;
      g.save();
      // dot, visual twin of the year-final markers
      g.beginPath();
      g.arc(px, py, 4, 0, Math.PI * 2);
      g.fillStyle = PALETTE.gold;
      g.fill();
      g.lineWidth = 1.5;
      g.strokeStyle = PALETTE.text;
      g.stroke();
      // label with a surface halo; right of the dot, flip left at the edge
      const txt = '\u2248 ' + fmt(t.point_estimate);
      g.font = 'bold 11px ' + getComputedStyle(document.body).fontFamily;
      const tw = g.measureText(txt).width;
      const padX = 5, boxH = 18, gap = 8;
      let bx = px + gap;
      if (bx + tw + padX * 2 > xS.right) bx = px - gap - tw - padX * 2;
      let by = py - boxH / 2;
      // dodge the year-final dot cluster (same x pixel) if one lands in the box
      const finalYs = [];
      c.data.datasets.forEach(ds => {
        if (/ final$/.test(ds.label || '') && ds.data[0]) {
          finalYs.push(yS.getPixelForValue(ds.data[0].y));
        }
      });
      if (finalYs.some(fy => fy > by - 4 && fy < by + boxH + 4)) {
        const below = finalYs.every(fy => fy < py);
        by = below ? by + 12 : by - 12;
      }
      g.fillStyle = themeRgba(PALETTE.surface, 0.85);
      g.beginPath();
      g.roundRect(bx, by, tw + padX * 2, boxH, 4);
      g.fill();
      g.fillStyle = PALETTE.gold;
      g.textAlign = 'left';
      g.textBaseline = 'middle';
      g.fillText(txt, bx + padX, by + boxH / 2 + 0.5);
      g.restore();
    }
  };

  // Custom interaction mode: find nearest point by x-pixel in EACH dataset
  // independently, so datasets with different date ranges align correctly.
  // Only includes a dataset if the hovered x falls within its data range
  // (with a small pixel margin), preventing stale endpoint matches.
  // Chart.js ignores prefers-reduced-motion on its own; disable animation for
  // every chart in the page (reload-only, no matchMedia listener).
  if (!Chart.Interaction.modes.xAligned) {
    Chart.Interaction.modes.xAligned = function(chart2, e, options, useFinalPosition) {
      const items = [];
      const mouseX = e.x;
      chart2.data.datasets.forEach((ds, dsIdx) => {
        const meta = chart2.getDatasetMeta(dsIdx);
        if (!meta.visible || !meta.data.length) return;
        // Projection's index-0 point is a visual duplicate of Actual's last point
        // (glued together so the lines connect). Skip it for hit-testing so the
        // tooltip title doesn't get hijacked by Projected when the user is
        // actually hovering the Actual line near today/yesterday.
        const skipFirst = ds.label === 'Projected' && meta.data.length > 1;
        const firstHitIdx = skipFirst ? 1 : 0;
        if (firstHitIdx >= meta.data.length) return;
        const firstPx = meta.data[firstHitIdx].x;
        const lastPx = meta.data[meta.data.length - 1].x;
        // Registered once globally, so viewport class is checked per call.
        // Coarse pointers get a wider capture band: 15px is a comfortable
        // mouse margin but under a fingertip it makes edge points untappable.
        const _isM = _mobileVP();
        const margin = _isM ? 28 : 15;
        if (mouseX < firstPx - margin || mouseX > lastPx + margin) return;
        let bestIdx = -1, bestDist = Infinity;
        for (let idx = firstHitIdx; idx < meta.data.length; idx++) {
          const dist = Math.abs(meta.data[idx].x - mouseX);
          if (dist < bestDist) { bestDist = dist; bestIdx = idx; }
        }
        if (bestIdx >= 0 && bestDist < (_isM ? 60 : 50)) {
          items.push({ datasetIndex: dsIdx, index: bestIdx, element: meta.data[bestIdx] });
        }
      });
      return items;
    };
  }

  // Custom tooltip positioner: pin to the chart corner OPPOSITE the cursor's
  // x-position so the tooltip never occludes the line you're inspecting.
  // Stakeholder feedback: default 'average' position floated on top of the
  // data, blocking the chart while reading values.
  if (!Chart.Tooltip.positioners.cornerAway) {
    Chart.Tooltip.positioners.cornerAway = function(elements, eventPos) {
      const chartArea = this.chart.chartArea;
      if (!chartArea) return false;
      const midX = (chartArea.left + chartArea.right) / 2;
      const onRight = eventPos.x > midX;
      // Anchor to top-left when cursor is on the right half, and vice versa.
      // y stays high so the tooltip lives in the chart's top band.
      return {
        x: onRight ? chartArea.left + 8 : chartArea.right - 8,
        y: chartArea.top + 8,
      };
    };
  }

  // Progressive left-to-right draw-in on first render. Per-chart animation
  // config OVERRIDES the global Chart.defaults.animation kill, so reduced
  // motion must be handled explicitly here. The xStarted/yStarted flags live
  // on each element's $context and stop the stagger from replaying on later
  // updates; range clicks additionally use update('none').
  const _drawN = actualData.length || 1;
  const _drawPer = Math.min(700 / _drawN, 12);
  const drawInAnimation = _reduceMotion() ? false : {
    x: {
      type: 'number', easing: 'linear', duration: _drawPer, from: NaN,
      delay(c) {
        if (c.type !== 'data' || c.xStarted) return 0;
        c.xStarted = true;
        return c.index * _drawPer;
      }
    },
    y: {
      type: 'number', easing: 'linear', duration: _drawPer,
      from(c) {
        if (c.index === 0) return c.chart.scales.y.getPixelForValue(0);
        const prev = c.chart.getDatasetMeta(c.datasetIndex).data[c.index - 1];
        return prev ? prev.getProps(['y'], true).y : undefined;
      },
      delay(c) {
        if (c.type !== 'data' || c.yStarted) return 0;
        c.yStarted = true;
        return c.index * _drawPer;
      }
    }
  };

  // Hover emphasis for historical year traces. xAligned returns the nearest
  // point of EVERY dataset regardless of pointer y, so proximity to the trace
  // is checked here; without it the first year line would light up wherever
  // the cursor sat. Restore-then-set with a change guard keeps this at one
  // update('none') per trace change instead of one per mousemove.
  let _emphIdx = -1;
  function _emphasizeYearTrace(evt, elements, chart2) {
    if (_mobileVP()) return;
    let best = -1, bestDy = 14;
    for (const el of elements) {
      const lbl = chart2.data.datasets[el.datasetIndex]?.label || '';
      if (!/^\d{4}$/.test(lbl)) continue;
      const dy = Math.abs(el.element.y - evt.y);
      if (dy < bestDy) { bestDy = dy; best = el.datasetIndex; }
    }
    if (best === _emphIdx) return;
    if (_emphIdx >= 0) {
      const prev = chart2.data.datasets[_emphIdx];
      if (prev && prev._origBorder) {
        prev.borderColor = prev._origBorder.color;
        prev.borderWidth = prev._origBorder.width;
      }
    }
    if (best >= 0) {
      const ds = chart2.data.datasets[best];
      if (!ds._origBorder) ds._origBorder = { color: ds.borderColor, width: ds.borderWidth };
      ds.borderColor = themeRgba(PALETTE.muted, 0.8);
      ds.borderWidth = 2;
    }
    _emphIdx = best;
    chart2.update('none');
  }

  chart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    plugins: [vertLinePlugin, crosshairPlugin, endpointLabelPlugin, lineGlowPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: drawInAnimation,
      interaction: { mode: 'xAligned', intersect: false },
      hover: { mode: 'xAligned', intersect: false },
      onHover: _emphasizeYearTrace,
      plugins: {
        legend: { display: false },
        tooltip: {
          position: 'cornerAway',
          xAlign: undefined, yAlign: 'top',
          caretSize: 0,
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: _mobileVP() ? 9 : 12, cornerRadius: 8,
          // Mobile tooltip: tighter padding, smaller text, smaller point swatches,
          // capped width so a long historical comparison list can't overflow the
          // chart area or the viewport. Desktop unchanged.
          boxPadding: 4,
          boxWidth: _mobileVP() ? 6 : 10,
          displayColors: true,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
          bodyFont: { size: 12 },
          footerFont: { size: 11, style: 'italic' },
          titleMarginBottom: 8, bodySpacing: _mobileVP() ? 4 : 5,
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              // Pick date from the most relevant dataset present in the tooltip.
              // Prefer Projected (in future) or Actual (in past) over historical years.
              const primary = items.find(i => i.dataset.label === 'Projected')
                           || items.find(i => i.dataset.label === 'Actual Entries')
                           || items[0];
              const d = primary.raw.x;
              const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
              // Calculate days before event
              if (t.event_start) {
                const evDate = new Date(t.event_start + 'T00:00:00');
                const diff = Math.round((evDate - d) / 86400000);
                if (diff > 0) return `${dateStr}  ·  T-${diff}`;
                if (diff === 0) return `${dateStr}  ·  Event Day`;
                return `${dateStr}  ·  T+${Math.abs(diff)}`;
              }
              return dateStr;
            },
            label(item) {
              if (item.dataset.label === 'CI Upper' || item.dataset.label === 'CI Lower') return null;
              const val = fmt(item.raw.y);
              const hoveredDate = item.raw.x;
              const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
              const isHistorical = isDone(t);
              const isPastOrToday = hoveredDate <= today;

              // Per-year "final" marker is consolidated into the year line below;
              // suppress its own row so the tooltip doesn't double up.
              if (/^\d{4} final$/.test(item.dataset.label)) return null;

              if (item.dataset.label === 'Actual Entries') {
                // Only show actual line when hovering over real data (past/today),
                // not when hovering over future projected points
                if (!isHistorical && !isPastOrToday) return null;
                if (item.dataIndex > 0) {
                  const prevPt = item.dataset.data[item.dataIndex - 1];
                  const delta = item.raw.y - prevPt.y;
                  // v3 P7: label the real span. Adjacent chart points are not
                  // always one day apart — the current data holds 29 gaps wider
                  // than a day — and calling a multi-day total "/day" overstates
                  // the rate by exactly the size of the gap.
                  const spanDays = Math.max(1, Math.round(
                    (item.raw.x - prevPt.x) / 86400000));
                  const unit = spanDays === 1 ? '/day' : ` over ${spanDays} days`;
                  if (delta > 0) return ` Actual: ${val}  (+${fmt(delta)}${unit})`;
                  if (delta === 0) return ` Actual: ${val}  (no change)`;
                  return ` Actual: ${val}  (${fmt(delta)}${unit})`;
                }
                return ` Actual: ${val}`;
              }

              if (item.dataset.label === 'Projected') {
                // Only show projection when hovering over future dates
                if (isPastOrToday) return null;
                return ` Projected: ${val}`;
              }

              // Historical year row — pair the at-this-T value with the final
              // count if the matching "YYYY final" dataset exists. Reads off
              // chart.data.datasets so we don't depend on hover proximity to
              // the final-day marker dot.
              const yearMatch = item.dataset.label.match(/^(\d{4})( \(est\))?$/);
              if (yearMatch) {
                const finalDs = item.chart.data.datasets.find(
                  d => d.label === `${yearMatch[1]} final`);
                if (finalDs && finalDs.data.length > 0) {
                  return ` ${item.dataset.label}: ${val} → ${fmt(finalDs.data[0].y)}`;
                }
                return ` ${item.dataset.label}: ${val}`;
              }

              // Anything else
              return ` ${item.dataset.label}: ${val}`;
            },
            afterBody(items) {
              const lines = [];
              if (!items.length) return lines;
              const hoveredDate = items[0].raw.x;
              const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
              // Show CI when hovering future (projection) area
              if (hoveredDate > today) {
                const ciUp = items.find(i => i.dataset.label === 'CI Upper');
                const ciLo = items.find(i => i.dataset.label === 'CI Lower');
                if (ciUp && ciLo) {
                  lines.push('');
                  lines.push(`  Likely range: ${fmt(ciLo.raw.y)} – ${fmt(ciUp.raw.y)}`);
                }
              }
              // Pace vs. historical average AT THE SAME T (not vs final).
              // Comparing today's 32 to final-avg 203 read "-84%" even when
              // current is genuinely ahead of every historical year at this T.
              // Use the items already in the tooltip — each historical year
              // dataset reports its y at the hovered date.
              const yearItems = items.filter(i => /^\d{4}( \(est\))?$/.test(i.dataset.label));
              if (yearItems.length > 0) {
                const hAvgAtT = Math.round(yearItems.reduce((s, i) => s + i.raw.y, 0) / yearItems.length);
                const actual = items.find(i => i.dataset.label === 'Actual Entries');
                const projected = items.find(i => i.dataset.label === 'Projected');
                const ref = actual || projected;
                if (ref && ref.raw.y > 0 && hAvgAtT > 0) {
                  const pct = ((ref.raw.y - hAvgAtT) / hAvgAtT * 100).toFixed(1);
                  const sign = pct > 0 ? '+' : '';
                  lines.push(`  vs ${yearItems.length}-yr avg @ this T (${fmt(hAvgAtT)}): ${sign}${pct}%`);
                }
              }
              return lines;
            },
            footer(items) {
              if (!items.length) return '';
              if (t.point_estimate && !isDone(t)) {
                return `Predicted final: ${fmt(t.point_estimate)}`;
              }
              return '';
            }
          },
          filter(item) { return item.dataset.label !== 'CI Upper' && item.dataset.label !== 'CI Lower'; }
        }
      },
      onClick(evt, elements) {
        // Click a chart point to scroll to the tournament row in the data table
        if (!elements.length) return;
        const rows = document.querySelectorAll('.tourney-table tbody tr');
        const idx = TOURNAMENT_DATA.tournaments.indexOf(t);
        if (idx < 0) return;
        for (const row of rows) {
          row.classList.remove('chart-highlight');
          if (row.dataset.idx === String(idx)) {
            row.classList.add('chart-highlight');
            const wrap = row.closest('details.sect');
            if (wrap && !wrap.open) wrap.open = true;
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => row.classList.remove('chart-highlight'), 2500);
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          // Mobile: month-level labels (Mar/Apr/May) so the time axis isn't crowded.
          // Chart.js's time scale ignores maxTicksLimit on weekly units; switching
          // to monthly is the documented way to sparsen X labels.
          time: _chartTimeUnit(cw, t),
          min: cw.min,
          // Extend the axis 5 days past event day so the finals-marker dot for
          // each historical year has visible space and is clearly separate
          // from the chart's data region (the day-of / post-event surge).
          max: cw.max,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0 }
        },
        y: {
          beginAtZero: true,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8, callback: v => v >= 1000 ? (v/1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k' : v }
        }
      },
      // Desktop top padding fits two rows of annotation pills so when
      // Early Bird and Event lines overlap horizontally they can stack
      // vertically. Mobile only renders the "Today" pill (Early Bird +
      // Event are gated by !_isM in vertLinePlugin), so 14px is plenty —
      // any more steals plot area on phones.
      layout: { padding: { top: _mobileVP() ? 14 : 40 } }
    }
  });

  // Chart glow for live tournaments
  document.getElementById('chartCard').classList.toggle('live-glow', t.status === 'live');

  // Legend
  let legendHtml = '<div class="legend-item"><div class="legend-swatch" style="background:#58a6ff"></div>Actual</div>';
  if (!isDone(t)) {
    legendHtml += '<div class="legend-item"><div class="legend-swatch dashed"></div>Projected</div>';
    legendHtml += '<div class="legend-item"><div class="legend-swatch band" style="background:#f0c040"></div>Likely range</div>';
  }
  if (t.historical) {
    legendHtml += `<div class="legend-item"><div class="legend-swatch dashed" style="background:repeating-linear-gradient(90deg,${themeRgba(PALETTE.muted,0.5)} 0 4px,transparent 4px 8px)"></div>Historical</div>`;
  }
  document.getElementById('chartLegend').innerHTML = legendHtml;

  // Subtitle
  let sub = `${t.family} ${t.year} · Registration Trajectory`;
  if (!isDone(t) && hasValidEarlyBird(t)) {
    const ebD = new Date(t.early_bird_deadline + 'T00:00:00');
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    if (ebD < today) {
      sub += ` · Early bird ended ${fmtDate(t.early_bird_deadline)}`;
    } else {
      sub += ` · Early bird in ${Math.ceil((ebD - today) / 86400000)}d`;
    }
  }
  const subEl = document.getElementById('chartSubtitle');
  subEl.textContent = sub;
  // Mobile truncates the subtitle with ellipsis (long family names eat
  // plot area). Mirror full text in the title attribute so long-press
  // / hover reveals it.
  subEl.setAttribute('title', sub);

  // Mobile date strip: shows the EB + Event dates inline below the chart since
  // the pill annotations for those are hidden on phones. Desktop CSS hides
  // this element so it does not duplicate the pills.
  _syncChartRangeSeg(cw);

  const datesEl = document.getElementById('chartMobileDates');
  if (datesEl) {
    const parts = [];
    if (hasValidEarlyBird(t)) parts.push(`<span class="cmd-eb">EB · ${fmtDate(t.early_bird_deadline)}</span>`);
    if (t.event_start) parts.push(`<span class="cmd-event">Event · ${fmtDate(t.event_start)}</span>`);
    datesEl.innerHTML = parts.join(' &middot; ');
  }
}

// (What-If panel removed)

// ══════════════════════════════════════════════════════════
// TIMELINE
// ══════════════════════════════════════════════════════════
function renderTimeline(t) {
  const el = document.getElementById('timeline');
  if (isDone(t)) {
    // Show historical context — how this edition compared
    const avg = t.historical && t.historical.length > 0
      ? Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length) : null;
    el.innerHTML = `
      <div class="timeline-node"><div class="timeline-dot past"></div><div class="timeline-label">Event Date</div><div class="timeline-date">${fmtDate(t.event_start)}</div></div>
      <div class="timeline-node"><div class="timeline-dot past"></div><div class="timeline-label">Final Count</div><div class="timeline-date" style="color:var(--gold);font-size:var(--fs-4)">${fmt(t.current_count)}</div></div>
      ${avg ? `<div class="timeline-node"><div class="timeline-dot future"></div><div class="timeline-label">Past Average</div><div class="timeline-date">${fmt(avg)}</div></div>` : ''}
    `;
    return;
  }

  const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const nodes = [];

  if (hasValidEarlyBird(t)) {
    const d = new Date(t.early_bird_deadline + 'T00:00:00');
    const status = d < today ? 'past' : 'future';
    const estCount = t.registration_curve
      ? Math.round(t.point_estimate * interpCurve(t.registration_curve, daysBetween(t.early_bird_deadline, t.event_start)))
      : null;
    nodes.push({ label: 'Early Bird', date: fmtDate(t.early_bird_deadline), status, count: estCount ? `~${fmt(estCount)}` : null });
  }

  nodes.push({ label: 'Today', date: fmtDate(TOURNAMENT_DATA.generated), status: 'now', count: fmt(t.current_count) });
  nodes.push({ label: 'Event Start', date: fmtDate(t.event_start), status: 'future', count: `~${fmt(t.point_estimate)}` });

  el.innerHTML = nodes.map(n => `
    <div class="timeline-node">
      <div class="timeline-dot ${n.status}"></div>
      <div class="timeline-label">${n.label}</div>
      <div class="timeline-date">${n.date}</div>
      ${n.count ? `<div class="timeline-count">${n.count}</div>` : ''}
    </div>
  `).join('');
}

// ══════════════════════════════════════════════════════════
// MILESTONE TABLE
// ══════════════════════════════════════════════════════════
function renderMilestones(t) {
  const el = document.getElementById('milestoneTable');
  if (isDone(t)) { el.innerHTML = ''; return; }

  const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const milestones = [];

  // Predicted counts at key dates
  const checkpoints = [
    { db: 60, label: 'T-60 days' },
    { db: 42, label: 'T-42 days' },
    { db: 28, label: '1 month out' },
    { db: 14, label: '2 weeks out' },
    { db: 7, label: '1 week out' },
    { db: 3, label: '3 days out' },
    { db: 1, label: 'Day before' },
    { db: 0, label: 'Event day' },
  ];

  // Add early bird if present
  if (hasValidEarlyBird(t)) {
    const ebDB = daysBetween(t.early_bird_deadline, t.event_start);
    const ebD = new Date(t.early_bird_deadline + 'T00:00:00');
    const status = ebD < today ? 'past' : 'future';
    const estPct = interpCurve(t.registration_curve, ebDB);
    const est = Math.round(t.point_estimate * estPct);
    milestones.push({
      date: fmtDate(t.early_bird_deadline),
      label: 'Early Bird Deadline',
      est: status === 'past' ? null : est,
      actual: status === 'past' ? '(passed)' : null,
      status
    });
  }

  checkpoints.forEach(cp => {
    if (cp.db >= t.days_remaining) return; // Skip past checkpoints
    if (cp.db < 0) return;
    const cpDate = addDays(t.event_start, -cp.db);
    const status = cpDate <= today ? 'past' : cp.db === t.days_remaining ? 'now' : 'future';
    const pct = interpCurve(t.registration_curve, cp.db);
    const est = Math.round(t.point_estimate * pct);
    milestones.push({
      date: fmtDate(t.event_start.substring(0, 10)),
      dateObj: cpDate,
      label: cp.label,
      est,
      status
    });
  });

  // Fix dates
  milestones.forEach(m => {
    if (m.dateObj) {
      m.date = m.dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
  });

  if (milestones.length === 0) { el.innerHTML = ''; return; }

  // Show the most relevant milestones — keep early bird (if any) + 5 nearest
  // upcoming checkpoints. The full table view (replaced by this strip) used
  // .slice(0, 6) which was already the same shape, so no change in density.
  const shown = milestones.slice(0, 6);

  // Horizontal timeline. Each milestone is a node with a status-colored dot,
  // a label, the date, and the predicted entry count at that point. A
  // continuous gradient line runs behind the nodes; the gradient stop matches
  // the boundary between "past" and "now/future" nodes so the user sees
  // visually where the present is on the journey.
  const firstNonPast = shown.findIndex(m => m.status !== 'past');
  const pastPct = firstNonPast === -1
    ? 100
    : Math.max(0, Math.min(100, (firstNonPast / (shown.length - 1)) * 100));

  let html = `<div class="ms-strip" role="list" aria-label="Tournament milestones">
    <div class="ms-line"><div class="ms-line-past" style="width:${pastPct}%"></div></div>`;
  shown.forEach(m => {
    const count = m.actual || (m.est ? `~${fmt(m.est)}` : '');
    html += `<div class="ms-node ms-${m.status}" role="listitem">
      <div class="ms-dot" aria-hidden="true"></div>
      <div class="ms-node-label">${m.label}</div>
      <div class="ms-node-date">${m.date}</div>
      ${count ? `<div class="ms-node-count">${count}</div>` : ''}
    </div>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

// ══════════════════════════════════════════════════════════
// HISTORICAL CHART + TABLE
// ══════════════════════════════════════════════════════════
function renderHistorical(t) {
  // Bar chart
  const ctx = document.getElementById('histChart');
  if (histChartObj) { histChartObj.destroy(); histChartObj = null; }
  const wrap = document.getElementById('compTableWrap');
  if (!t.historical || t.historical.length === 0) {
    wrap.innerHTML = `<div style="text-align:center;padding:20px 0;color:var(--muted);font-size:var(--fs-2);opacity:.6">No historical editions on record</div>`;
    return;
  }

  const hist = t.historical.slice(-6);
  const histFlags = hist.map(h => h.adjusted ? { kind: h.adjusted, raw: h.count_raw } : null);
  const hasAdjusted = histFlags.some(Boolean);
  const labels = [...hist.map(h => h.adjusted ? `${h.year}*` : String(h.year)), String(t.year)];
  const counts = [...hist.map(h => h.count), isDone(t) ? t.current_count : t.point_estimate];
  // Gradient bars: current year in gold, history in blue, both fading toward
  // the baseline. One cache per bucket; scriptable by dataIndex.
  const _goldBarGrad = {}, _blueBarGrad = {};
  const colors = (context) => {
    const isCurrent = context.dataIndex === counts.length - 1;
    return isCurrent
      ? areaGradient(context.chart, _goldBarGrad, [
          [0, themeRgba(PALETTE.goldBright, 0.85)],
          [1, themeRgba(PALETTE.gold, 0.45)]
        ])
      : areaGradient(context.chart, _blueBarGrad, [
          [0, themeRgba(PALETTE.blue, 0.55)],
          [1, themeRgba(PALETTE.blue, 0.18)]
        ]);
  };
  const hoverColors = counts.map((_, i) => i === counts.length-1
    ? themeRgba(PALETTE.goldBright, 0.95) : themeRgba(PALETTE.blue, 0.7));
  const borders = counts.map((_, i) => i === counts.length-1 ? PALETTE.gold : PALETTE.blue);
  const hoverBorders = counts.map((_, i) => i === counts.length-1 ? PALETTE.goldBright : PALETTE.blueBright);

  // Average line plugin
  const histAvg = Math.round(hist.reduce((s, h) => s + h.count, 0) / hist.length);
  const avgLinePlugin = {
    id: 'avgLine',
    afterDraw(chartInstance) {
      const yScale = chartInstance.scales.y;
      const ctx2 = chartInstance.ctx;
      const y = yScale.getPixelForValue(histAvg);
      ctx2.save();
      ctx2.beginPath();
      ctx2.setLineDash([6, 4]);
      ctx2.strokeStyle = 'rgba(188,140,255,0.5)';
      ctx2.lineWidth = 1;
      ctx2.moveTo(yScale.left, y);
      ctx2.lineTo(chartInstance.scales.x.right, y);
      ctx2.stroke();
      ctx2.fillStyle = 'rgba(188,140,255,0.7)';
      ctx2.font = '9px -apple-system, system-ui, sans-serif';
      ctx2.textAlign = 'right';
      ctx2.fillText(`avg ${fmt(histAvg)}`, chartInstance.scales.x.right, y - 4);
      ctx2.restore();
    }
  };

  histChartObj = new Chart(ctx, {
    type: 'bar',
    data: {
      labels, datasets: [{
        data: counts, backgroundColor: colors, borderColor: borders,
        hoverBackgroundColor: hoverColors, hoverBorderColor: hoverBorders,
        borderWidth: 1.5, borderRadius: 6, borderSkipped: 'bottom',
        categoryPercentage: 0.72, barPercentage: 0.85
      }]
    },
    plugins: [avgLinePlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: 14, weight: 'bold' }, bodyFont: { size: 12 }, footerFont: { size: 11, style: 'italic' },
          displayColors: true,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              return labels[items[0].dataIndex] + ' Edition';
            },
            label(item) {
              return ` Entries: ${fmt(item.raw)}`;
            },
            afterBody(items) {
              if (!items.length) return [];
              const lines = [];
              const idx = items[0].dataIndex;
              const val = counts[idx];
              // Year-over-year change
              if (idx > 0) {
                const prev = counts[idx - 1];
                const diff = val - prev;
                const pct = ((diff / prev) * 100).toFixed(1);
                const sign = diff > 0 ? '+' : '';
                lines.push(`  YoY: ${sign}${fmt(diff)} (${sign}${pct}%)`);
              }
              // vs historical average
              lines.push(`  Hist avg: ${fmt(histAvg)}`);
              const diffAvg = ((val - histAvg) / histAvg * 100).toFixed(1);
              const signA = diffAvg > 0 ? '+' : '';
              lines.push(`  vs avg: ${signA}${diffAvg}%`);
              // Flag pre-split top-6 adjustment (idx into hist array, exclude current year)
              if (idx < histFlags.length && histFlags[idx]) {
                const flag = histFlags[idx];
                lines.push(`  * adjusted from ${fmt(flag.raw)} (excludes lower sections)`);
              }
              return lines;
            },
            footer(items) {
              if (!items.length) return '';
              const idx = items[0].dataIndex;
              if (idx === counts.length - 1 && !isDone(t)) return 'Predicted (not final)';
              return '';
            }
          }
        }
      },
      onClick(evt, elements) {
        if (!elements.length) return;
        const clickedYear = labels[elements[0].index];
        // Highlight the corresponding row in the comp-table
        const compRows = document.querySelectorAll('.comp-table tbody tr');
        compRows.forEach(row => {
          row.classList.remove('chart-highlight');
          if (row.cells[0] && row.cells[0].textContent.trim().startsWith(clickedYear)) {
            row.classList.add('chart-highlight');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => row.classList.remove('chart-highlight'), 2500);
          }
        });
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0 } },
        y: { beginAtZero: true, grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false }, ticks: { color: PALETTE.muted, font: { size: 11 }, maxTicksLimit: _mobileVP() ? 4 : 6, callback: v => v >= 1000 ? (v/1000).toFixed(0) + 'k' : v } }
      }
    }
  });

  // Table — show year-over-year change
  const allYears = [...hist, { year: t.year, count: isDone(t) ? t.current_count : t.point_estimate, isCurrent: true }];
  const rows = allYears.map((h, idx) => {
    const prev = idx > 0 ? allYears[idx - 1].count : null;
    const diff = prev ? h.count - prev : null;
    const pct = prev ? ((diff / prev) * 100).toFixed(1) : null;
    const cls = diff > 0 ? 'delta-pos' : diff < 0 ? 'delta-neg' : '';
    const star = h.adjusted ? '*' : '';
    const yearLabel = h.isCurrent ? `${h.year} ${isDone(t) ? '(final)' : '(est)'}` : `${h.year}${star}`;
    const rowClass = h.isCurrent ? ' class="current-year"' : '';
    const countCell = h.adjusted
      ? `${fmt(h.count)} <span style="color:var(--muted);font-size:var(--fs-2)">(was ${fmt(h.count_raw)})</span>`
      : fmt(h.count);
    return `<tr${rowClass}><td data-label="Year">${yearLabel}</td><td data-label="Count">${countCell}</td><td data-label="YoY" class="${cls}">${diff != null ? (diff > 0 ? '+' : '') + fmt(diff) : '–'}</td><td data-label="Change" class="${cls}">${pct != null ? (diff > 0 ? '+' : '') + pct + '%' : '–'}</td></tr>`;
  }).join('');

  const footnote = hasAdjusted
    ? `<div style="margin-top:8px;color:var(--muted);font-size:var(--fs-2);line-height:1.45">* 2019 and 2022 World Open were a single combined registration page (9 sections). Counts adjusted to top-6 only for apples-to-apples vs the 2023+ split. Estimates use chessevents.com final-standings ratios.</div>`
    : '';

  wrap.innerHTML = `
    <div class="comp-table-wrap">
    <table class="comp-table">
      <thead><tr><th>Year</th><th>Count</th><th title="Year-over-Year">YoY</th><th>Change</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
    ${footnote}
  `;
}

// ══════════════════════════════════════════════════════════
// REGISTRATION CURVE CHART
// ══════════════════════════════════════════════════════════
let regCurveObj = null;
function renderRegCurve(t) {
  const ctx = document.getElementById('regCurveChart');
  if (regCurveObj) { regCurveObj.destroy(); regCurveObj = null; }
  if (!t.registration_curve || t.registration_curve.length === 0) {
    document.getElementById('regCurveCaption').textContent = 'No curve data available';
    return;
  }

  const sorted = [...t.registration_curve].sort((a, b) => b.days_before - a.days_before);
  const labels = sorted.map(pt => pt.days_before);
  const data = sorted.map(pt => ((pt.cumulative_pct || pt.pct || 0) * 100));

  // Mark where "today" is
  const todayIdx = labels.findIndex(db => db <= t.days_remaining);
  const pointColors = labels.map((db, i) => {
    if (isDone(t)) return 'rgba(88,166,255,0.6)';
    return db >= t.days_remaining ? 'rgba(88,166,255,0.6)' : 'rgba(240,192,64,0.6)';
  });

  const _regGrad = {};

  // "You are here" annotation plugin for reg curve
  const regCurveAnnotation = makeVertMarkersPlugin('regCurveAnnotation', () => {
    if (isDone(t)) return [];
    // Find the label index closest to today
    let idx = -1;
    let minDiff = Infinity;
    labels.forEach((db, i) => {
      const d = Math.abs(db - t.days_remaining);
      if (d < minDiff) { minDiff = d; idx = i; }
    });
    if (idx < 0) return [];
    return [{ value: idx, label: 'Today', color: PALETTE.blue }];
  });

  regCurveObj = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.map(db => db === 0 ? 'Event' : db >= 7 ? `${db}d` : `${db}d`),
      datasets: [{
        data,
        borderColor: 'rgba(240,192,64,0.6)',
        backgroundColor: (context) => areaGradient(context.chart, _regGrad, [
          [0, themeRgba(PALETTE.gold, 0.16)],
          [1, themeRgba(PALETTE.gold, 0.02)]
        ]),
        fill: true,
        borderWidth: 2.25,
        // Elapsed/ahead split at today, matching pointColors and the main
        // chart: blue = behind us, gold = still to come. Done tournaments
        // keep the flat base color (no split to show).
        segment: {
          borderColor: (c) => isDone(t) ? undefined :
            (c.p1DataIndex <= todayIdx ? themeRgba(PALETTE.blue, 0.75)
                                       : themeRgba(PALETTE.gold, 0.75))
        },
        pointRadius: labels.map(db => db === 0 || db === t.days_remaining ? 5 : 0),
        pointHoverRadius: 6,
        pointHitRadius: 10,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        tension: 0.4
      }]
    },
    plugins: [regCurveAnnotation],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom for the shared marker pill (drawn 18px above the plot top).
      layout: { padding: { top: 22 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: 14, weight: 'bold' }, bodyFont: { size: 12 }, footerFont: { size: 11, style: 'italic' },
          displayColors: true,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = labels[items[0].dataIndex];
              if (db === 0) return 'Event Day';
              return `T-${db} (${db} days before event)`;
            },
            label(item) {
              return ` ${item.raw.toFixed(1)}% of final entries`;
            },
            afterBody(items) {
              if (!items.length) return [];
              const lines = [];
              const db = labels[items[0].dataIndex];
              const pct = items[0].raw / 100;
              // Estimated count at this point
              if (t.point_estimate) {
                const estCount = Math.round(t.point_estimate * pct);
                lines.push(`  Est. entries: ~${fmt(estCount)}`);
              }
              // Compare to current if live
              if (!isDone(t) && db === t.days_remaining) {
                lines.push(`  Actual now: ${fmt(t.current_count)}`);
              }
              return lines;
            },
            footer(items) {
              if (!items.length || isDone(t)) return '';
              const db = labels[items[0].dataIndex];
              if (db > t.days_remaining) return 'Already passed';
              if (db === t.days_remaining) return 'You are here';
              return '';
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0, maxTicksLimit: _mobileVP() ? 6 : 12 }
        },
        y: {
          min: 0, max: 105,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: {
            color: PALETTE.muted, font: { size: 11 },
            maxTicksLimit: _mobileVP() ? 4 : 6,
            callback: v => v + '%'
          }
        }
      }
    }
  });

  // Caption
  const todayPct = interpCurve(t.registration_curve, t.days_remaining);
  if (!isDone(t)) {
    const actualPct = (t.current_count / t.point_estimate * 100).toFixed(1);
    const expectedPct = (todayPct * 100).toFixed(1);
    const diff = (actualPct - expectedPct).toFixed(1);
    const ahead = parseFloat(diff) > 0;
    document.getElementById('regCurveCaption').textContent =
      `At T-${t.days_remaining}: expected ${expectedPct}%, actual ${actualPct}% of predicted final; ${ahead ? 'ahead' : 'behind'} typical pace by ${Math.abs(diff)} percentage points`;
  } else {
    document.getElementById('regCurveCaption').textContent =
      `Historical registration pattern for ${t.family}. Shows % of final entries at each lead time.`;
  }
}

// ══════════════════════════════════════════════════════════
// FEE PANEL
// ══════════════════════════════════════════════════════════
function renderFees(t) {
  const el = document.getElementById('feeContent');
  if (!t.early_bird_fee && !t.regular_fee && !t.onsite_fee) {
    el.innerHTML = `<div style="text-align:center;padding:24px 0">
      <p style="color:var(--muted);font-size:var(--fs-2);opacity:.6">Fee data not available for this tournament.</p>
    </div>`;
    return;
  }

  const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  let currentFee = null;
  let feeStatus = '';
  if (hasValidEarlyBird(t)) {
    const ebD = new Date(t.early_bird_deadline + 'T00:00:00');
    if (ebD >= today) {
      currentFee = t.early_bird_fee;
      feeStatus = `Early bird rate until ${fmtDate(t.early_bird_deadline)}`;
    } else {
      currentFee = t.regular_fee;
      feeStatus = `Early bird ended ${fmtDate(t.early_bird_deadline)}`;
    }
  } else {
    currentFee = t.regular_fee;
    feeStatus = 'Standard rate';
  }

  let html = '';
  if (currentFee && !isDone(t)) {
    html += `<div style="text-align:center;padding:16px 0 20px;border-bottom:1px solid var(--border);margin-bottom:16px">
      <div style="font-size:var(--fs-2);color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Current Rate</div>
      <div style="font-size:2.2rem;font-weight:900;color:var(--gold)">$${currentFee}</div>
      <div style="font-size:var(--fs-2);color:var(--muted);margin-top:4px">${feeStatus}</div>
    </div>`;
  }

  html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;text-align:center">';
  if (t.early_bird_fee && t.regular_fee && t.early_bird_fee < t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Early Bird</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--green)">$${t.early_bird_fee}</div>
    </div>`;
  }
  if (t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Regular</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--text2)">$${t.regular_fee}</div>
    </div>`;
  }
  if (t.onsite_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">On-site</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--orange)">$${t.onsite_fee}</div>
    </div>`;
  }
  html += '</div>';

  el.innerHTML = html;
}

// ══════════════════════════════════════════════════════════
// ALL TOURNAMENTS TABLE
// ══════════════════════════════════════════════════════════
let tableSortCol = 'date';
let tableSortDir = 'asc';

function sortTable(col, ev) {
  if (tableSortCol === col) {
    tableSortDir = tableSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    tableSortCol = col;
    tableSortDir = 'asc';
  }
  // Update header classes
  document.querySelectorAll('.tourney-table th.sortable').forEach(th => th.classList.remove('asc', 'desc'));
  const header = ev && ev.target ? ev.target.closest('th') : document.querySelector(`.tourney-table th[onclick*="'${col}'"]`);
  if (header) header.classList.add(tableSortDir);
  renderAllTournaments();
}

// Filter state for the all-tournaments table. status filter is one of
// 'all' | 'live' | 'complete'; query is a free-text substring match against
// family/year/state/city. Both apply on top of the existing sort.
let _ttStatusFilter = 'all';
function filterTourneyTable(status) {
  if (status) {
    _ttStatusFilter = status;
    document.querySelectorAll('.tt-filter').forEach(b =>
      b.classList.toggle('tt-filter-active', b.dataset.filter === status));
  }
  renderAllTournaments();
}

function renderAllTournaments() {
  const body = document.getElementById('tourneyBody');
  const filterInput = document.getElementById('tourneyFilter');
  const q = filterInput ? filterInput.value.trim().toLowerCase() : '';
  // Only show upcoming + complete (not 361 historical rows)
  const active = TOURNAMENT_DATA.tournaments
    .map((t, i) => ({t, i}))
    .filter(({t}) => {
      if (t.status !== 'live' && t.status !== 'complete') return false;
      if (_ttStatusFilter !== 'all' && t.status !== _ttStatusFilter) return false;
      if (q) {
        const hay = `${t.family} ${t.year} ${t.venue_city || ''} ${t.venue_state || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

  // Sort
  const dir = tableSortDir === 'asc' ? 1 : -1;
  active.sort((a, b) => {
    const ta = a.t, tb = b.t;
    switch (tableSortCol) {
      case 'name': return dir * ta.family.localeCompare(tb.family);
      case 'status': return dir * (ta.status === 'live' ? -1 : 1);
      case 'date': return dir * ((ta.event_start || '').localeCompare(tb.event_start || ''));
      case 'current': return dir * (ta.current_count - tb.current_count);
      case 'predicted': return dir * (ta.point_estimate - tb.point_estimate);
      case 'progress': {
        const pa = ta.point_estimate > 0 ? ta.current_count / ta.point_estimate : 0;
        const pb = tb.point_estimate > 0 ? tb.current_count / tb.point_estimate : 0;
        return dir * (pa - pb);
      }
      default: return 0;
    }
  });

  body.innerHTML = active.map(({t, i}) => {
    const isLive = t.status === 'live';
    const pill = isLive
      ? '<span class="status-pill pill-live"><span class="live-dot"></span>Upcoming</span>'
      : '<span class="status-pill pill-complete">Complete</span>';

    const pct = t.point_estimate > 0 ? Math.min(100, (t.current_count / t.point_estimate * 100)).toFixed(0) : 100;
    const paceColor = isLive ? (pct > 30 ? 'var(--green)' : pct > 15 ? 'var(--gold)' : 'var(--blue)') : 'var(--muted)';

    const ci = t.ci_lower === t.ci_upper ? '–' : `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}`;

    // Compute daily pace for live tournaments
    let paceStr = '';
    if (isLive && t.daily_data && t.daily_data.length >= 3) {
      const recent = t.daily_data.slice(-7);
      if (recent.length >= 2) {
        const daySpan = recent[recent.length-1][0] - recent[0][0];
        const regSpan = recent[recent.length-1][1] - recent[0][1];
        const rate = daySpan > 0 ? (regSpan / daySpan).toFixed(1) : '0';
        paceStr = `<span style="font-size:var(--fs-2);color:var(--green)">${rate}/day</span>`;
      }
    }

    return `<tr data-act="select-tournament-top" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" style="cursor:pointer">
      <td data-label="Tournament"><div class="t-name" title="${esc(t.family)} ${t.year}">${esc(t.family)}</div><div class="t-sub">${t.year}${isLive ? ' · ' + t.days_remaining + 'd out' : ''}</div></td>
      <td data-label="Status">${pill}</td>
      <td data-label="Event Date">${fmtDate(t.event_start)}${t.event_end ? ' – ' + fmtDate(t.event_end) : ''}</td>
      <td data-label="Current" style="font-weight:600;color:var(--blue)">${fmt(t.current_count)} ${paceStr}</td>
      <td data-label="Predicted" style="font-weight:700;color:var(--gold)">${fmt(t.point_estimate)}</td>
      <td data-label="Likely Range" style="font-size:var(--fs-3);color:var(--muted)">${ci}</td>
      <td data-label="Progress">
        <span class="pace-bar-wrap"><span class="pace-bar-fill" style="width:${pct}%;background:${paceColor}"></span></span>
        <span style="font-size:var(--fs-2);color:var(--muted)">${pct}%</span>
      </td>
    </tr>`;
  }).join('');
  if (active.length === 0) {
    body.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px 0;color:var(--muted);font-size:var(--fs-3)">No tournaments match the current filter.</td></tr>`;
  }
}

// ══════════════════════════════════════════════════════════
// SUMMARY BAR
// ══════════════════════════════════════════════════════════
function renderSummaryBar() {
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.filter(t => t.status === 'live');
  const complete2026 = ts.filter(t => t.status === 'complete');
  const historical = ts.filter(t => t.status === 'historical');
  const totalRegs = ts.filter(t => t.status !== 'historical').reduce((s, t) => s + t.current_count, 0);
  const nextEvent = [...live].sort((a, b) => a.days_remaining - b.days_remaining)[0];

  const el = document.getElementById('summaryBar');
  el.innerHTML = `
    <span><strong style="color:var(--green)">${live.length}</strong> upcoming</span>
    <span><strong style="color:var(--muted)">${complete2026.length}</strong> complete '26</span>
    <span><strong style="color:var(--purple)">${historical.length}</strong> historical</span>
    <span><strong style="color:var(--blue)">${fmt(totalRegs)}</strong> YTD entries</span>
    ${nextEvent ? `<span style="cursor:pointer" data-act="select-tournament" data-idx="${TOURNAMENT_DATA.tournaments.indexOf(nextEvent)}">Next: <strong style="color:var(--gold)">${nextEvent.family}</strong> in ${nextEvent.days_remaining}d</span>` : ''}
  `;
}

// Movements widget removed in iter 24 — today's delta is already on each
// mini-card via the delta chip (iter 9). Calendar timeline still surfaces
// the portfolio view by event date.

// Confidence breakdown panel removed in iter 25 — the hero narrative +
// confidence badge already say "tracking on pace" or "low confidence
// (3 editions)" in plain English, which is the same info this 4-row
// audit panel surfaced more verbosely.

// ══════════════════════════════════════════════════════════
// FESTIVAL CLUSTER (e.g. World Open's 3 sub-events as one festival)
// ══════════════════════════════════════════════════════════
// When the selected tournament is one of several sub-events that
// share a festival lineage (currently World Open's top 6 / lower
// sections / Under 13), surface the sibling sub-events inline so
// the user can switch between them without navigating back out to
// the selector. Each sibling shows its current count + predicted
// final + days until its own event_start.
const FESTIVAL_GROUPS = [
  {
    name: 'World Open',
    families: [
      'World Open top 6 sections',
      'World Open lower sections',
      'World Open Under 13 Championship',
    ],
  },
];

function renderFestivalCluster(t) {
  const el = document.getElementById('festivalCluster');
  if (!el) return;
  if (!t || !t.family || !t.year) { el.innerHTML = ''; return; }
  const group = FESTIVAL_GROUPS.find(g =>
    g.families.includes(t.family) ||
    g.families.some(f => t.family.startsWith(f.split(' ').slice(0, 2).join(' '))));
  if (!group) { el.innerHTML = ''; return; }
  // Find sibling tournaments — same year, family in the group.
  const siblings = TOURNAMENT_DATA.tournaments
    .map((tt, idx) => ({ tt, idx }))
    .filter(({ tt }) => tt.year === t.year && group.families.includes(tt.family));
  if (siblings.length < 2) { el.innerHTML = ''; return; }

  // Sort by event_start so sub-events appear in chronological order.
  siblings.sort((a, b) => (a.tt.event_start || '').localeCompare(b.tt.event_start || ''));

  let html = `<div class="fc-head">
    <span class="fc-title">${esc(group.name)} ${t.year} festival</span>
    <span class="fc-sub">${siblings.length} sub-events</span>
  </div>
  <div class="fc-rows">`;
  siblings.forEach(({ tt, idx }) => {
    const isActive = idx === selectedIndex;
    // Short label — strip the redundant "World Open " prefix.
    const shortName = tt.family.replace(/^World Open\s*/, '').trim() || 'World Open';
    const subLabel = shortName.replace('top 6 sections', 'Top 6')
                              .replace('lower sections', 'Lower')
                              .replace('Under 13 Championship', 'Under 13');
    const current = isDone(tt) ? tt.current_count : tt.current_count;
    const pred = tt.point_estimate;
    const eventDate = tt.event_start
      ? new Date(tt.event_start + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : '—';
    html += `<button class="fc-card ${isActive ? 'fc-card-active' : ''}"
      data-act="select-tournament" data-idx="${idx}"
      aria-current="${isActive ? 'true' : 'false'}"
      aria-label="${esc(subLabel)}: predicted ${fmt(pred)}, ${fmt(current)} registered">
      <div class="fc-card-label">${esc(subLabel)}</div>
      <div class="fc-card-num">${fmt(pred)}</div>
      <div class="fc-card-sub">${fmt(current)} reg · ${eventDate}</div>
    </button>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

// Recent-finishes feed removed in iter 26 — the all-tournaments table
// at the bottom already lists completed tournaments and is sortable +
// filterable. Model accuracy summary lives in the strip just below the
// calendar; the per-tournament drilldown lives in the Performance tab.

// ══════════════════════════════════════════════════════════
// INLINE MODEL ACCURACY STRIP (Predictions tab)
// ══════════════════════════════════════════════════════════
// Compact "the model has been right X% of the time at T-14" strip that
// pulls from PERFORMANCE_DATA. Surfaces trustworthiness inline without
// making the user click into the Performance tab. Three cells: grade,
// T-14 MAE, T-14 CI coverage. Click the strip to jump to the full
// Performance tab.
function renderAccuracyStrip() {
  const el = document.getElementById('accuracyStrip');
  if (!el) return;
  const data = (typeof PERFORMANCE_DATA !== 'undefined') ? PERFORMANCE_DATA : null;
  if (!data) { el.innerHTML = ''; return; }
  const cumulative = data.cumulative || data;
  if (!cumulative || !cumulative.aggregate) { el.innerHTML = ''; return; }
  const agg = cumulative.aggregate;
  // Find the T-14 bucket if it exists; fall back to nearest under-21d.
  let t14 = agg.find(a => a.T === 14);
  if (!t14) t14 = agg.find(a => a.T >= 7 && a.T <= 21);
  const grade = cumulative.grade || data.grade || '–';
  const nEvents = cumulative.n_tournaments ?? data.n_tournaments ?? null;
  const mae = t14 ? t14.mae_pct : null;
  const cov = t14 ? t14.ci_coverage : null;

  // Grade-color mapping (matches the Performance tab letter conventions).
  function gradeCls(g) {
    if (!g) return 'flat';
    const first = g[0];
    if (first === 'A') return 'pos';
    if (first === 'B') return 'flat';
    return 'neg';
  }

  el.innerHTML = `
    <button class="acc-row" data-act="page-tab" data-tab="performance" aria-label="Open full model performance tab">
      <span class="acc-cell acc-grade">
        <span class="acc-grade-letter acc-${gradeCls(grade)}">${grade}</span>
        <span class="acc-grade-label">Model grade${nEvents ? ` · ${nEvents} tests` : ''}</span>
      </span>
      ${mae != null ? `<span class="acc-cell">
        <span class="acc-num">${mae.toFixed(1)}%</span>
        <span class="acc-lab">Avg miss at 2 weeks out</span>
      </span>` : ''}
      ${cov != null ? `<span class="acc-cell">
        <span class="acc-num">${Math.round(cov)}%</span>
        <span class="acc-lab">In range at 2 weeks out</span>
      </span>` : ''}
      <span class="acc-cta">View details &rarr;</span>
    </button>
  `;
}

// ══════════════════════════════════════════════════════════
// UPCOMING-EVENTS CALENDAR TIMELINE
// ══════════════════════════════════════════════════════════
// Horizontal timeline of all live tournaments by event date. Each dot is
// sized by predicted final and colored by pace status. Hovering the dot
// shows the tournament; clicking selects it. Gives a portfolio-wide view
// of "what's coming up and how big" that the per-card grid below doesn't
// surface at a glance.
function renderCalendar() {
  const el = document.getElementById('calendarStrip');
  if (!el) return;
  const ts = TOURNAMENT_DATA.tournaments;
  const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const events = [];
  ts.forEach((t, idx) => {
    if (t.status !== 'live' || !t.event_start) return;
    const d = new Date(t.event_start + 'T00:00:00');
    const daysOut = Math.round((d - today) / 86400000);
    if (daysOut < 0 || daysOut > 240) return; // 8-month horizon
    events.push({ idx, t, d, daysOut });
  });
  if (events.length === 0) { el.innerHTML = ''; return; }
  events.sort((a, b) => a.daysOut - b.daysOut);

  // Range for x-positioning. Always 0..maxDaysOut so the earliest event
  // sits at the left edge and the furthest at the right.
  const maxDaysOut = events[events.length - 1].daysOut || 1;

  // Predicted-final range for dot sizing.
  const preds = events.map(e => e.t.point_estimate || 0).filter(n => n > 0);
  const maxPred = Math.max(...preds, 1);

  // Pace classification matches the mini-card logic so colors agree.
  function paceClass(t) {
    const pa = t.pace_alert;
    if (!pa) return 'flat';
    if (pa.status === 'above_pace') return 'pos';
    if (pa.status === 'below_pace') return 'neg';
    return 'flat';
  }

  let html = `<div class="cal-head">
    <div class="cal-title">Upcoming events</div>
    <div class="cal-legend">
      <span class="cal-legend-item"><span class="cal-dot-mini cal-pace-pos"></span>Ahead</span>
      <span class="cal-legend-item"><span class="cal-dot-mini cal-pace-flat"></span>On pace</span>
      <span class="cal-legend-item"><span class="cal-dot-mini cal-pace-neg"></span>Behind</span>
    </div>
  </div>
  <div class="cal-track-wrap">
    <div class="cal-track">
      <div class="cal-axis-now" title="Today"></div>`;
  events.forEach(e => {
    const xPct = (e.daysOut / maxDaysOut) * 100;
    const sizePx = Math.max(10, Math.min(28, 10 + 18 * Math.sqrt((e.t.point_estimate || 0) / maxPred)));
    const pace = paceClass(e.t);
    const monthDay = e.d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const longDate = e.d.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric' });
    const paceLabel = pace === 'pos' ? 'Ahead of pace'
                    : pace === 'neg' ? 'Behind pace'
                    : 'On pace';
    const ariaLabel = `${e.t.family} on ${monthDay}, T-${e.daysOut}, predicted ${fmt(e.t.point_estimate || 0)}`;
    html += `<button class="cal-dot cal-pace-${pace}" style="left:${xPct.toFixed(2)}%;width:${sizePx}px;height:${sizePx}px"
      data-act="select-tournament" data-idx="${e.idx}"
      data-tip-name="${esc(e.t.family)} ${e.t.year}"
      data-tip-date="${esc(longDate)}"
      data-tip-days="${e.daysOut}"
      data-tip-pred="${fmt(e.t.point_estimate || 0)}"
      data-tip-pace="${esc(paceLabel)}"
      data-tip-paceclass="${pace}"
      aria-label="${esc(ariaLabel)}"></button>`;
  });
  // Month axis labels — find each month boundary in the visible range.
  const months = [];
  const start = new Date(today);
  for (let m = 0; m <= Math.ceil(maxDaysOut / 30) + 1; m++) {
    const d = new Date(start.getFullYear(), start.getMonth() + m, 1);
    const daysOut = Math.round((d - today) / 86400000);
    if (daysOut < 0 || daysOut > maxDaysOut) continue;
    const xPct = (daysOut / maxDaysOut) * 100;
    months.push({ d, xPct });
  }
  html += '</div><div class="cal-axis">';
  months.forEach(m => {
    html += `<span class="cal-axis-tick" style="left:${m.xPct.toFixed(2)}%">${m.d.toLocaleDateString('en-US', { month: 'short' })}</span>`;
  });
  html += '</div></div>';
  el.innerHTML = html;
  _bindCalendarTooltips(el);
}

// Floating premium tooltip for the upcoming-events dots. One shared
// element gets repositioned over the hovered/focused dot. Native title=
// is intentionally NOT set on the dot anymore so the browser's plain
// yellow tooltip doesn't double up with our custom one.
function _bindCalendarTooltips(scopeEl) {
  let tip = document.getElementById('calTooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'calTooltip';
    tip.className = 'cal-tooltip';
    tip.setAttribute('role', 'tooltip');
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  const dots = scopeEl.querySelectorAll('.cal-dot');
  const show = (dot) => {
    const name = dot.dataset.tipName || '';
    const date = dot.dataset.tipDate || '';
    const days = dot.dataset.tipDays || '';
    const pred = dot.dataset.tipPred || '';
    const pace = dot.dataset.tipPace || '';
    const cls  = dot.dataset.tipPaceclass || 'flat';
    tip.innerHTML = `
      <div class="cal-tip-name">${name}</div>
      <div class="cal-tip-meta">
        <span class="cal-tip-date">${date}</span>
        <span class="cal-tip-sep" aria-hidden="true">&middot;</span>
        <span class="cal-tip-days">T&minus;${days}</span>
      </div>
      <div class="cal-tip-row">
        <span class="cal-tip-label">Predicted</span>
        <span class="cal-tip-value">${pred}</span>
      </div>
      <div class="cal-tip-row">
        <span class="cal-tip-label">Pace</span>
        <span class="cal-tip-value cal-tip-pace-${cls}">${pace}</span>
      </div>
    `;
    tip.hidden = false;
    tip.classList.remove('cal-tooltip-pos', 'cal-tooltip-flat', 'cal-tooltip-neg');
    tip.classList.add(`cal-tooltip-${cls}`);
    // Position above the dot, centered. Clamp to viewport horizontally.
    const r = dot.getBoundingClientRect();
    const tr = tip.getBoundingClientRect();
    let left = r.left + r.width / 2 - tr.width / 2;
    left = Math.max(8, Math.min(window.innerWidth - tr.width - 8, left));
    const top = r.top - tr.height - 10 + window.scrollY;
    tip.style.left = `${left}px`;
    tip.style.top  = `${top}px`;
    requestAnimationFrame(() => tip.classList.add('cal-tooltip-show'));
  };
  const hide = () => {
    tip.classList.remove('cal-tooltip-show');
    setTimeout(() => { if (!tip.classList.contains('cal-tooltip-show')) tip.hidden = true; }, 160);
  };
  dots.forEach(dot => {
    dot.addEventListener('mouseenter', () => show(dot));
    dot.addEventListener('mouseleave', hide);
    dot.addEventListener('focus', () => show(dot));
    dot.addEventListener('blur', hide);
  });
}

// ══════════════════════════════════════════════════════════
// UPCOMING MINI CARDS
// ══════════════════════════════════════════════════════════
// Progressive disclosure (phase 5): the wrapped Predictions sections are
// summary-first on phones and always open on desktop and in print.
let _sectWide = null;
function syncSectionDisclosure(force) {
  const wide = window.innerWidth >= 640;
  if (!force && wide === _sectWide) return;
  _sectWide = wide;
  document.querySelectorAll('details.sect').forEach(d => { d.open = wide; });
}

function renderMiniCards() {
  const el = document.getElementById('miniGrid');
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.map((t, i) => ({t, i}))
    .filter(({t}) => t.status === 'live')
    .sort((a, b) => a.t.days_remaining - b.t.days_remaining);

  const card = ({t, i}) => {
    const isSelected = i === selectedIndex;
    const pct = t.point_estimate > 0 ? (t.current_count / t.point_estimate * 100).toFixed(0) : 0;
    // Today's delta surfaces velocity on the selector card itself instead of
    // forcing a click through. v3 P1: this used to be a raw last-minus-prior
    // with no gap check, so when a scrape day went missing it reported several
    // days of registrations — or a corrupted jump — as "today's change". That
    // is the "+125 entries" the incident put on screen. latestDailyChange
    // returns null unless the final interval really is one day; anything wider
    // gets labelled with its true span instead.
    let deltaChip = '';
    if (typeof DailySeries !== 'undefined') {
      const todayDelta = DailySeries.latestDailyChange(t, { isLive: !isDone(t) });
      if (todayDelta != null && todayDelta !== 0) {
        deltaChip = `<span class="mini-card-delta ${todayDelta > 0 ? 'pos' : 'neg'}" title="Change since the previous day's scrape">${todayDelta > 0 ? '+' : ''}${todayDelta}</span>`;
      } else {
        const iv = DailySeries.latestInterval(t, { isLive: !isDone(t) });
        if (iv && iv.isGap && iv.added > 0) {
          deltaChip = `<span class="mini-card-delta pos" title="No scrape for ${iv.span} days: the value covers the whole period, not one day">+${iv.added} / ${iv.span}d</span>`;
        }
      }
    }
    // Pace comparison — same metric as the detail-view YoY banner:
    // compare current_count to prior_year_pace.count_at_same_point. Falls
    // back to last-year × curve-pct only when 2025 daily data is missing.
    // Previously used point_estimate × curve%, which produced a third
    // disagreeing pace metric on the same screen.
    let paceIndicator = '';
    let expectedCount = null;
    if (t.prior_year_pace && t.prior_year_pace.count_at_same_point > 0) {
      expectedCount = t.prior_year_pace.count_at_same_point;
    } else if (t.registration_curve && t.historical && t.historical.length > 0) {
      const lastYr = t.historical[t.historical.length - 1];
      const expectedPct = interpCurve(t.registration_curve, t.days_remaining);
      const c = Math.round(lastYr.count * expectedPct);
      if (c > 0) expectedCount = c;
    }
    if (expectedCount != null) {
      if (t.current_count > expectedCount * 1.05) {
        paceIndicator = `<span style="color:var(--green);font-size:var(--fs-1)">&#9650; ahead</span>`;
      } else if (t.current_count < expectedCount * 0.95) {
        paceIndicator = `<span style="color:var(--orange);font-size:var(--fs-1)">&#9660; behind</span>`;
      } else {
        paceIndicator = `<span style="color:var(--muted);font-size:var(--fs-1)">&#8212; on pace</span>`;
      }
    }
    return `<div class="mini-card ${isSelected ? 'mini-card-active' : ''}" data-act="select-tournament" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" role="button" aria-label="${esc(t.family)} - ${fmt(t.point_estimate)} predicted">
      <div class="mini-card-header">
        <span class="mini-card-name" title="${esc(t.family)} ${t.year}">${esc(t.family)}</span>
        <div class="mini-card-chips">
          ${deltaChip}
          <span class="mini-badge badge-live"><span class="live-dot" style="width:5px;height:5px"></span>T-${t.days_remaining}</span>
        </div>
      </div>
      <div style="display:flex;align-items:baseline;gap:8px">
        <div class="mini-card-number">${fmt(t.point_estimate)}</div>
        ${paceIndicator}
      </div>
      <div class="mini-card-details">
        ${fmt(t.current_count)} registered · ${fmtDate(t.event_start)}
        <div style="margin-top:6px">
          <div class="pace-bar-wrap" style="width:100%;display:block"><div class="pace-bar-fill" style="width:${pct}%;background:linear-gradient(90deg,var(--blue),var(--gold))"></div></div>
        </div>
      </div>
    </div>`;
  };

  // Tiered layout: the next three events get the featured row; the rest stay
  // compact. Everything remains clickable and information-identical.
  const featured = live.slice(0, 3);
  const later = live.slice(3);
  el.classList.add('mini-grid-tiered');
  el.innerHTML =
    (featured.length ? `<div class="mini-section-label">Next up</div><div class="mini-grid-featured">${featured.map(card).join('')}</div>` : '') +
    (later.length ? `<div class="mini-section-label">Later</div><div class="mini-grid-rest">${later.map(card).join('')}</div>` : '');
}

// ══════════════════════════════════════════════════════════
// DEEP LINKING (hash routing)
// ══════════════════════════════════════════════════════════
const VALID_TABS = ['predictions', 'compare', 'email', 'performance', 'audit', 'about', 'puzzles', 'ask'];

function updateHash() {
  const tab = _currentTab || 'predictions';
  const hash = tab === 'predictions' ? '#predictions/' + selectedIndex : '#' + tab;
  history.replaceState(null, '', hash);
}

function parseHash() {
  const raw = window.location.hash.replace(/^#/, '');
  if (!raw) return null;
  const parts = raw.split('/');
  const tab = parts[0];
  if (!VALID_TABS.includes(tab)) return null;
  const idx = parts[1] !== undefined ? parseInt(parts[1], 10) : null;
  return { tab, idx: (idx !== null && !isNaN(idx)) ? idx : null };
}

function navigateToHash() {
  const route = parseHash();
  if (!route) return false;
  const maxIdx = TOURNAMENT_DATA.tournaments.length - 1;
  switchPageTab(route.tab, true);
  if (route.tab === 'predictions') {
    // Fall back to the first tournament when the index is missing or out of
    // range, which is what a fresh load does anyway.
    //
    // Without this, `#predictions` with no index — a shared link someone
    // truncated, or `#predictions/9999` after the list shortened — left every
    // panel showing its skeleton placeholder forever. Nothing threw and nothing
    // logged; the page just sat there looking like it was still loading, which
    // is the worst way for it to fail. selectTournament() is what clears the
    // skeletons, so if it never runs they never clear.
    const inRange = route.idx !== null && route.idx >= 0 && route.idx <= maxIdx;
    selectTournament(inRange ? route.idx : 0, inRange);
  }
  // Set hash without re-triggering (already at the right hash)
  return true;
}

window.addEventListener('hashchange', () => navigateToHash());

// ══════════════════════════════════════════════════════════
// MAIN ORCHESTRATOR
// ══════════════════════════════════════════════════════════
function selectTournament(index, skipHash) {
  selectedIndex = index;
  const t = TOURNAMENT_DATA.tournaments[index];
  if (!skipHash) updateHash();

  // Update header label and page title
  const dot = document.getElementById('tournDot');
  dot.style.display = t.status === 'live' ? '' : 'none';
  const tournLabel = document.getElementById('tournLabel');
  tournLabel.textContent = `${t.family} ${t.year}`;
  tournLabel.title = `${t.family} ${t.year}`;
  document.title = `${t.family} ${t.year} · CCA Entry Predictor`;

  updateFavButton(t.family);
  updateCompareBtn();

  // Staggered fade-in for visual polish
  const sections = document.querySelectorAll('.delta-banner, .chart-card, .kpi-row, .progress-row, .grid-2');
  sections.forEach(s => s.style.opacity = '0');

  setTimeout(() => {
    renderTabs();
    renderCalendar();
    // Model accuracy summary lives on the Performance tab; removed from home.
    renderMiniCards();
    renderDelta(t);
    renderHero(t);
    // KPI row removed: % Registered duplicates the CI bar, Early Bird is in
    // the chart annotations + subtitle, Past Average shows in Historical
    // Comparison, CI Width is the CI bar itself, Regular Fee has its own panel.
    renderProgress(t);
    renderChart(t);
    renderTimeline(t);
    renderMilestones(t);
    renderHistorical(t);
    renderRegCurve(t);
    renderFees(t);

    // Show/hide sections based on tournament type
    const miniGrid = document.getElementById('miniGrid');
    miniGrid.style.display = t.status === 'live' ? '' : 'none';

    // Hide fee panel for historical tournaments (no fee data)
    const feePanel = document.getElementById('feePanel');
    if (feePanel) feePanel.style.display = (!t.early_bird_fee && !t.regular_fee && !t.onsite_fee) ? 'none' : '';

    // Scroll to delta banner smoothly when switching tournaments
    document.getElementById('deltaBanner').scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Hide skeleton loaders now that content is rendered
    hideSkeletons();

    // Staggered reveal
    sections.forEach((s, i) => {
      setTimeout(() => {
        s.style.opacity = '';
        s.style.transform = 'translateY(0)';
        s.classList.add('fade-enter');
        setTimeout(() => s.classList.remove('fade-enter'), 400);
      }, i * 60);
    });
  }, 120);
}

// AUDIT.md follow-up #3 — Model Health panel populates audit telemetry on the
// About-the-Model tab. Pulls cumulative CI coverage from PERFORMANCE_DATA,
// walkin/tier/low_confidence counts from TOURNAMENT_DATA, and fetches
// audit_warnings.json for the latest pipeline-run warnings.
function renderModelHealth() {
  const grid = document.getElementById('mh-grid');
  if (!grid) return;
  const updated = document.getElementById('mh-updated');
  if (updated) {
    const ts = TOURNAMENT_DATA.last_updated || TOURNAMENT_DATA.generated;
    updated.textContent = ts ? 'Pipeline last ran ' + ts : '';
  }

  // v3 T7: say what the grade actually covers, and give the second engine its
  // own measured number rather than leaving it implied.
  //
  // Several paths reach the page. predict_nowcast produces the headline grade.
  // The online-window estimator handles multi-schedule events that have already
  // started, and it is now graded separately (04e writes performance_data
  // .window_engine). The remaining cards use interim fallbacks — pace,
  // historical average, or the raw live count — which no grade covers, and
  // those are marked low-confidence.
  //
  // The two letters are deliberately not combined. The window engine is scored
  // 0-2 days from registration close with most of the field already in; the
  // headline is scored at T-14/7/3 before the event starts. Averaging them, or
  // showing one as though it described the other, would read as a better model
  // when it is only an easier question.
  const scopeEl = document.getElementById('mh-grade-scope');
  if (scopeEl && typeof TOURNAMENT_DATA !== 'undefined') {
    const live = TOURNAMENT_DATA.tournaments.filter(t => t.status === 'live');
    const graded = live.filter(t => t.prediction_source === 'model');
    const windowed = live.filter(t => t.prediction_source === 'model_online_window');
    if (live.length) {
      const other = live.length - graded.length - windowed.length;
      const parts = [
        `Grade scope: the headline grade is measured on the main model, which `
        + `currently produces ${graded.length} of ${live.length} live predictions.`,
      ];
      const we = (typeof PERFORMANCE_DATA !== 'undefined')
        ? PERFORMANCE_DATA.window_engine : null;
      if (windowed.length && we && we.grade && we.grade !== 'N/A') {
        parts.push(
          `${windowed.length} come from the online-registration-window model, `
          + `graded ${we.grade} separately over ${we.n} predictions: a shorter, `
          + `easier horizon than the headline, so the two are not comparable.`);
      } else if (windowed.length) {
        parts.push(
          `${windowed.length} come from the online-registration-window model, `
          + `graded separately.`);
      }
      if (other > 0) {
        parts.push(
          `The other ${other} use interim fallbacks (pace, historical average, `
          + `or the live count) that no grade covers; those cards are marked `
          + `low-confidence.`);
      }
      scopeEl.textContent = parts.join(' ');
    }
  }

  // v3 T10: the footer corpus size comes from the data too. It was hardcoded as
  // "192K entry records across 778 tournaments" and had drifted from the real
  // 781 / 194.5K.
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const tc = document.getElementById('footerTournamentCount');
    if (tc && PERFORMANCE_DATA.n_corpus_tournaments) {
      tc.textContent = PERFORMANCE_DATA.n_corpus_tournaments.toLocaleString();
    }
    const er = document.getElementById('footerEntryRecords');
    if (er && PERFORMANCE_DATA.n_entry_records) {
      const n = PERFORMANCE_DATA.n_entry_records;
      er.textContent = n >= 1000 ? Math.round(n / 1000) + 'K' : String(n);
    }
  }

  // K1/L2: single-source the "How We Tested It" prose numbers from
  // PERFORMANCE_DATA so they can never drift from the graded truth. Cumulative
  // T-14 drives the headline; cumulative T-3 the close-in coverage caveat.
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const cum = PERFORMANCE_DATA.cumulative || {};
    const cagg = cum.aggregate || [];
    const at = (T) => cagg.find(a => a.T === T);
    const t14 = at(14), t3 = at(3);
    const setTxt = (id, v) => { const e = document.getElementById(id); if (e && v != null) e.textContent = v; };
    setTxt('about-n', cum.n_tournaments);
    setTxt('about-prior-n', cum.n_tournaments);
    if (t14) {
      const cov14 = Math.round(t14.ci_coverage);
      setTxt('about-median', t14.median_ape_pct + '%');
      setTxt('about-prior-median', t14.median_ape_pct + '%');
      setTxt('about-cov', cov14 + '%');
      setTxt('about-prior-cov', cov14 + '%');
      // Methodology callout / sanity-check / footer coverage stats (same source).
      setTxt('mc-ci-cover', cov14 + '%');
      setTxt('mc-ci-cover-inline', cov14 + '%');
      setTxt('mc-ci-cover-footer', cov14 + '%');
    }
    if (t3) setTxt('about-cov-close', Math.round(t3.ci_coverage) + '%');
    const yrs = Object.keys(PERFORMANCE_DATA.years || {})
      .filter(y => (PERFORMANCE_DATA.years[y].n_tournaments || 0) > 0).sort();
    if (cum.n_tournaments && yrs.length) {
      setTxt('about-span-note', `${cum.n_tournaments} tournaments across ${yrs[0]}–${yrs[yrs.length - 1]}.`);
    }
  }

  const tiles = [];

  // Tile 1: cumulative T-14 CI coverage vs nominal 80%
  let covPct = null;
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const cum = PERFORMANCE_DATA.cumulative || {};
    const cumT14 = (cum.aggregate || []).find(a => a.T === 14);
    if (cumT14) covPct = cumT14.ci_coverage;
  }
  if (covPct !== null) {
    const drift = Math.abs(covPct - 80);
    const color = drift <= 3 ? 'var(--green)' : drift <= 7 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'CI coverage (cumulative T-14)',
      value: covPct + '%',
      sub: 'target 80% / drift ' + Math.round(drift) + 'pp',
      color,
      help: 'Cumulative empirical coverage of the 80% confidence interval across years 2023-2026. Should sit near 80%.',
    });
  }

  // Tile 2: walk-in source distribution
  const walkinSrc = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(t => {
    if (t.walkin_source) walkinSrc[t.walkin_source] = (walkinSrc[t.walkin_source] || 0) + 1;
  });
  const walkinTotal = Object.values(walkinSrc).reduce((a, b) => a + b, 0);
  if (walkinTotal > 0) {
    const fam = walkinSrc.family || 0;
    const est = walkinSrc.estimate || 0;
    const famPct = Math.round(100 * fam / walkinTotal);
    const color = famPct >= 80 ? 'var(--green)' : famPct >= 50 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Walk-in family-level coverage',
      value: famPct + '%',
      sub: fam + ' family / ' + est + ' estimate (n=' + walkinTotal + ')',
      color,
      help: 'How many tournaments use family-specific walk-in multipliers vs the global 1.1x fallback.',
    });
  }

  // Tile 3: prediction tier on live cohort
  const tierCounts = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(t => {
    if (t.status === 'live' && t.prediction_tier) {
      tierCounts[t.prediction_tier] = (tierCounts[t.prediction_tier] || 0) + 1;
    }
  });
  const liveTotal = Object.values(tierCounts).reduce((a, b) => a + b, 0);
  if (liveTotal > 0) {
    const direct = tierCounts['family-direct'] || 0;
    const fallback = liveTotal - direct;
    const directPct = Math.round(100 * direct / liveTotal);
    const color = directPct >= 90 ? 'var(--green)' : directPct >= 70 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Live cohort direct family ratio',
      value: directPct + '%',
      sub: direct + ' direct / ' + fallback + ' fallback (n=' + liveTotal + ')',
      color,
      help: 'Of live-cohort predictions, how many used direct family ratios vs a fallback path.',
    });
  }

  // Tile 4: low-confidence count
  const lowConf = (TOURNAMENT_DATA.tournaments || []).filter(t => t.low_confidence).length;
  const totalTournaments = (TOURNAMENT_DATA.tournaments || []).length;
  if (totalTournaments > 0) {
    const pct = Math.round(100 * lowConf / totalTournaments);
    const color = pct <= 5 ? 'var(--green)' : pct <= 15 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Low-confidence predictions',
      value: String(lowConf),
      sub: pct + '% of ' + totalTournaments + ' tournaments / n<4 history',
      color,
      help: 'Predictions for families with <4 qualifying historical editions. Lognormal CI is unreliable below 4.',
    });
  }

  // Tile 5: 2026 backtest grade
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA && PERFORMANCE_DATA.years && PERFORMANCE_DATA.years['2026']) {
    const yr = PERFORMANCE_DATA.years['2026'];
    const grade = yr.grade || 'N/A';
    const color = grade.startsWith('A') ? 'var(--green)' : grade.startsWith('B') ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: '2026 backtest grade',
      value: grade,
      sub: yr.grade_detail || ((yr.n_tournaments || 0) + ' tournaments'),
      color,
      help: 'Letter grade from the 2026 evaluation cohort: worst of the T-14/T-7/T-3 lead times (MAE + CI coverage), leave-one-out so no tournament grades itself.',
    });
  }

  grid.innerHTML = tiles.map(t =>
    '<div title="' + t.help.replace(/"/g, '&quot;') + '" style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;cursor:help">' +
    '<div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">' + t.label + '</div>' +
    '<div style="font-size:1.6rem;font-weight:800;color:' + t.color + ';line-height:1">' + t.value + '</div>' +
    '<div style="font-size:var(--fs-1);color:var(--text2);margin-top:6px">' + t.sub + '</div>' +
    '</div>'
  ).join('');

  // Pipeline warnings — async fetch
  const warnEl = document.getElementById('mh-warnings');
  if (!warnEl) return;
  fetch('audit_warnings.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || !data.warnings) { warnEl.innerHTML = ''; return; }
      const c = data.count || 0;
      if (c === 0) {
        warnEl.innerHTML = '<div style="font-size:var(--fs-2);color:var(--green);padding:10px 12px;background:rgba(72,187,120,.08);border:1px solid rgba(72,187,120,.3);border-radius:8px">Latest pipeline run: 0 warnings (clean).</div>';
        return;
      }
      // v5 Cat V: warnings are deduped upstream and carry a per-entry count;
      // step/text pass through esc() — pipeline-controlled or not, nothing
      // lands in innerHTML unescaped.
      const rows = data.warnings.map(w =>
        '<tr><td style="padding:4px 8px;color:var(--muted);font-size:var(--fs-2);white-space:nowrap">' +
        esc(w.step.split('(')[0].trim()) + '</td><td style="padding:4px 8px;color:var(--text2);font-size:var(--fs-2)">' +
        esc(w.text) + (w.count > 1 ? ' <span style="color:var(--muted)">×' + w.count + '</span>' : '') + '</td></tr>'
      ).join('');
      warnEl.innerHTML =
        '<details style="background:rgba(214,158,46,.08);border:1px solid rgba(214,158,46,.3);border-radius:8px;padding:10px 12px">' +
        '<summary style="cursor:pointer;font-size:var(--fs-2);color:var(--gold);font-weight:600">Latest pipeline run: ' + c + ' distinct warning' + (c === 1 ? '' : 's') + ' (click to expand)</summary>' +
        '<table style="width:100%;margin-top:10px;border-collapse:collapse">' + rows + '</table></details>';
    })
    .catch(() => { warnEl.innerHTML = ''; });
}

function init() {
  // --- Stale data warning banner ---
  const freshness = assessDataFreshness(TOURNAMENT_DATA, new Date());
  if (freshness.stale) {
    const banner = document.getElementById('staleBanner');
    const bannerText = document.getElementById('staleBannerText');
    if (banner && bannerText) {
      const ts = TOURNAMENT_DATA.last_updated || TOURNAMENT_DATA.generated;
      let msg;
      if (freshness.degraded) {
        // The pipeline told us it failed partway. Say so plainly rather than
        // implying a transient upstream outage.
        msg = '\u26A0 The update pipeline failed on its last run. Showing the last '
            + 'complete data, from ' + ts + '. Counts and predictions below may be out of date.';
      } else if (freshness.reason === 'age' && !TOURNAMENT_DATA.is_stale) {
        // Nothing flagged this, but the browser clock says the data is old \u2014
        // the case a mid-run crash used to hide entirely.
        const days = Math.floor(freshness.ageHours / 24);
        msg = '\u26A0 This data is ' + (days >= 1 ? days + ' day' + (days === 1 ? '' : 's') : Math.round(freshness.ageHours) + ' hours')
            + ' old (generated ' + ts + '). The nightly update has not completed since then.';
      } else {
        msg = '\u26A0 Predictions last updated ' + ts + '. Live data temporarily unavailable.';
      }
      bannerText.textContent = msg;
      banner.style.display = 'block';
      // Push page content down so banner doesn't overlap
      document.body.style.paddingTop = banner.offsetHeight + 'px';
    }
  }

  renderModelHealth();
  document.getElementById('lastUpdated').textContent = fmtDateTimeLong(TOURNAMENT_DATA.generated_time || TOURNAMENT_DATA.generated);
  // First-run hint: shown once to genuinely new visitors. Anyone who already
  // saw the old splash gate (cep:splash:seen) counts as a returning user.
  try {
    if (!localStorage.getItem('cep:splash:seen') && !localStorage.getItem('cep:hint:seen')) {
      const hint = document.getElementById('firstRunHint');
      if (hint) hint.hidden = false;
    }
  } catch (_) {}

  renderAllTournaments();
  renderSummaryBar();

  syncSectionDisclosure();
  window.addEventListener('resize', () => syncSectionDisclosure());
  window.addEventListener('beforeprint', () => {
    document.querySelectorAll('details.sect').forEach(d => { d.open = true; });
  });
  window.addEventListener('afterprint', () => syncSectionDisclosure(true));

  // Set default sort indicator on the date column
  const defaultSortTh = document.querySelector('.tourney-table th[data-act="sort-table"][data-col="date"]');
  if (defaultSortTh) defaultSortTh.classList.add('asc');

  // Part B: Deep link from hash, or default to Chicago Open / first live
  if (!navigateToHash()) {
    const chiIdx = TOURNAMENT_DATA.tournaments.findIndex(t => t.status === 'live' && t.family.includes('Chicago Open'));
    const liveIdx = chiIdx >= 0 ? chiIdx : TOURNAMENT_DATA.tournaments.findIndex(t => t.status === 'live');
    selectTournament(liveIdx >= 0 ? liveIdx : 0);
  }
}

// Back to top visibility
const bttBtn = document.getElementById('backToTop');
let bttTick = false;
window.addEventListener('scroll', () => {
  if (!bttTick) {
    requestAnimationFrame(() => {
      bttBtn.classList.toggle('visible', window.scrollY > 500);
      bttTick = false;
    });
    bttTick = true;
  }
}, { passive: true });

// Keyboard navigation
document.addEventListener('keydown', (e) => {
  if (openDrop) return;
  // L5: never hijack arrows while typing (INPUT/TEXTAREA/contenteditable) or on
  // any tab other than Predictions — otherwise arrows in the Ask box or on the
  // puzzle board silently switch tournaments and rewrite the hash.
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
  if (typeof _currentTab !== 'undefined' && _currentTab !== 'predictions') return;
  const n = TOURNAMENT_DATA.tournaments.length;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    selectTournament((selectedIndex + 1) % n);
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    selectTournament((selectedIndex - 1 + n) % n);
  }
});

function saveDataEntry() {
  const inputs = document.querySelectorAll('#deBody input');
  const overrides = JSON.parse(localStorage.getItem('cca_overrides') || '{}');

  // Pre-flight validation: type="date" / type="number" + min="0" enforce format
  // at the browser level. Collect any input that fails checkValidity() and
  // abort the save with a visible banner before touching localStorage.
  const invalid = [];
  inputs.forEach(inp => {
    inp.classList.remove('de-input-invalid');
    if (inp.value !== '' && !inp.checkValidity()) {
      inp.classList.add('de-input-invalid');
      invalid.push(`${inp.dataset.family} · ${inp.dataset.field}`);
    }
  });
  if (invalid.length > 0) {
    showDataEntryBanner(`${invalid.length} field${invalid.length === 1 ? '' : 's'} need fixing; see highlighted rows.`, 'error');
    return;
  }

  inputs.forEach(inp => {
    const family = inp.dataset.family;
    const field = inp.dataset.field;
    const val = inp.value;
    const pristine = inp.dataset.pristine || '';
    const saved = inp.dataset.saved || '';
    // Skip fields the user didn't touch: if the input still matches the pipeline
    // value AND no override was previously saved for this field, do nothing.
    // If an override WAS saved and the user reverted to the pipeline value, drop it.
    const isPipelineValue = val === pristine;
    const hadSavedOverride = saved !== '';
    if (isPipelineValue && !hadSavedOverride) return;
    if (isPipelineValue && hadSavedOverride) {
      if (overrides[family]) {
        delete overrides[family][field];
        if (Object.keys(overrides[family]).length === 0) delete overrides[family];
      }
      return;
    }
    if (!overrides[family]) overrides[family] = {};
    if (field === 'current_count' || field.includes('fee')) {
      overrides[family][field] = val !== '' ? Number(val) : undefined;
    } else {
      overrides[family][field] = val || undefined;
    }
  });

  localStorage.setItem('cca_overrides', JSON.stringify(overrides));

  // Apply overrides to TOURNAMENT_DATA in memory
  applyOverrides();

  // Re-render the current tournament view
  selectTournament(selectedIndex);

  // Show saved message (legacy inline + new toast)
  const msg = document.getElementById('deSavedMsg');
  msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
  showDataEntryBanner('Saved.', 'success');
}

function showDataEntryBanner(text, kind) {
  let toast = document.getElementById('deToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'deToast';
    toast.className = 'de-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = text;
  toast.className = `de-toast de-toast-${kind} show`;
  clearTimeout(showDataEntryBanner._t);
  showDataEntryBanner._t = setTimeout(() => { toast.className = 'de-toast'; }, 2500);
}

function clearDataEntry() {
  if (!confirm('Reset all manual overrides to default values?')) return;
  localStorage.removeItem('cca_overrides');
  // Reload page to reset TOURNAMENT_DATA
  location.reload();
}

function applyOverrides() {
  let overrides;
  try {
    overrides = JSON.parse(localStorage.getItem('cca_overrides') || '{}');
    if (typeof overrides !== 'object' || overrides === null || Array.isArray(overrides)) {
      overrides = {};
    }
  } catch (e) {
    console.warn('Invalid overrides in localStorage, ignoring');
    return;
  }
  if (Object.keys(overrides).length === 0) {
    _renderOverrideBanner([]);
    return;
  }

  const applied = [];
  TOURNAMENT_DATA.tournaments.forEach(t => {
    const o = overrides[t.family];
    if (!o || typeof o !== 'object' || t.status !== 'live') return;
    const before = { current_count: t.current_count };
    if (typeof o.current_count === 'number' && o.current_count >= 0 && o.current_count < 100000) t.current_count = o.current_count;
    if (typeof o.event_start === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(o.event_start)) {
      t.event_start = o.event_start;
      const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
      const evt = new Date(o.event_start + 'T00:00:00');
      t.days_remaining = Math.max(0, Math.ceil((evt - today) / 86400000));
    }
    if (typeof o.early_bird_deadline === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(o.early_bird_deadline)) t.early_bird_deadline = o.early_bird_deadline;
    if (typeof o.early_bird_fee === 'number' && o.early_bird_fee >= 0) t.early_bird_fee = o.early_bird_fee;
    if (typeof o.regular_fee === 'number' && o.regular_fee >= 0) t.regular_fee = o.regular_fee;
    if (typeof o.onsite_fee === 'number' && o.onsite_fee >= 0) t.onsite_fee = o.onsite_fee;
    // Track families where the override actually changed current_count vs the
    // pipeline-generated value (other overrides like fee/date are less likely
    // to mislead the dashboard's pace banners).
    if (t.current_count !== before.current_count) {
      applied.push({ family: t.family, was: before.current_count, now: t.current_count });
    }
  });
  _renderOverrideBanner(applied);
}

function _renderOverrideBanner(applied) {
  const banner = document.getElementById('overrideBanner');
  if (!banner) return;
  if (!applied || applied.length === 0) {
    banner.style.display = 'none';
    return;
  }
  const detail = document.getElementById('overrideBannerDetail');
  if (detail) {
    const lines = applied.map(a =>
      `${a.family}: showing <strong>${fmt(a.now)}</strong> instead of pipeline value <strong>${fmt(a.was)}</strong>`
    );
    detail.innerHTML = lines.join('<br>') + '<br><span style="opacity:.75">Pace + KPIs reflect the override, not live registrations.</span>';
  }
  banner.style.display = 'block';
}

// Apply any saved overrides on load
// ══════════════════════════════════════════════════════════
// FAVORITES (My Tournaments)
// ══════════════════════════════════════════════════════════
const FAV_KEY = 'cca_favorites';

function getFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function saveFavorites(favs) {
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
}

function isFavorite(family) {
  return getFavorites().includes(family);
}

function toggleFavorite(family) {
  const favs = getFavorites();
  const idx = favs.indexOf(family);
  if (idx >= 0) favs.splice(idx, 1);
  else favs.push(family);
  saveFavorites(favs);
  updateFavButton(family);
}

function toggleFavoriteSelected() {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  if (t) toggleFavorite(t.family);
}

function updateFavButton(family) {
  const btn = document.getElementById('favToggle');
  if (!btn) return;
  const fav = isFavorite(family);
  btn.innerHTML = fav ? '&#9733;' : '&#9734;';
  btn.classList.toggle('fav-active', fav);
  btn.title = fav ? 'Remove from My Tournaments' : 'Add to My Tournaments';
}

// ══════════════════════════════════════════════════════════
// COMPARE (side-by-side tournament comparison)
// ══════════════════════════════════════════════════════════
const COMPARE_KEY = 'cca_compare';
const COMPARE_COLORS = [PALETTE.blue, PALETTE.gold, PALETTE.green];
const COMPARE_COLORS_DIM = ['rgba(88,166,255,0.15)', 'rgba(240,192,64,0.15)', 'rgba(63,185,80,0.15)'];
let _compareSlots = [];
let _compareChart = null;

function getCompareSlots() {
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}
function saveCompareSlots(slots) {
  localStorage.setItem(COMPARE_KEY, JSON.stringify(slots));
}

function addToCompare(idx) {
  _compareSlots = getCompareSlots();
  if (_compareSlots.includes(idx)) return;
  if (_compareSlots.length >= 3) {
    alert('Compare supports up to 3 tournaments. Remove one first.');
    return;
  }
  _compareSlots.push(idx);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  if (_compareSlots.length >= 2) {
    switchPageTab('compare');
  }
}

function removeFromCompare(idx) {
  _compareSlots = getCompareSlots();
  const pos = _compareSlots.indexOf(idx);
  if (pos >= 0) _compareSlots.splice(pos, 1);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  if (_currentTab === 'compare') renderCompareTab();
}

function addToCompareSelected() {
  if (selectedIndex != null) addToCompare(selectedIndex);
}

function updateCompareBtn() {
  const btn = document.getElementById('compareAddBtn');
  if (!btn) return;
  _compareSlots = getCompareSlots();
  const inCompare = selectedIndex != null && _compareSlots.includes(selectedIndex);
  btn.classList.toggle('compare-active', inCompare);
  btn.title = inCompare ? 'Remove from Compare' : 'Add to Compare';
  if (inCompare) {
    btn.onclick = function() { removeFromCompare(selectedIndex); };
  } else {
    btn.onclick = function() { addToCompareSelected(); };
  }
}

function renderCompareTab() {
  const el = document.getElementById('compareContent');
  if (!el) return;
  _compareSlots = getCompareSlots();
  const tournaments = TOURNAMENT_DATA.tournaments;

  // Empty state: pre-fill with active tournament + same family last year so
  // the panel opens with a useful default view. User can still pick others;
  // we only seed in-memory, don't persist to localStorage until user adds.
  if (_compareSlots.length === 0 && typeof selectedIndex === 'number' && tournaments[selectedIndex]) {
    const active = tournaments[selectedIndex];
    _compareSlots = [selectedIndex];
    const priorIdx = tournaments.findIndex((t, i) =>
      i !== selectedIndex && t.family === active.family && Number(t.year) === Number(active.year) - 1
    );
    if (priorIdx >= 0) _compareSlots.push(priorIdx);
  }

  // One-line caption above the selectors
  let captionHTML = '<div class="compare-caption" style="font-size:var(--fs-2);color:var(--muted);margin:0 0 10px">Pick up to 3 tournaments to compare entry trajectories side-by-side.</div>';

  // Build selector UI
  let selectorHTML = captionHTML + '<div class="compare-selectors">';
  for (let s = 0; s < 3; s++) {
    const currentIdx = _compareSlots[s];
    const colorDot = `<span class="compare-color-dot" style="background:${COMPARE_COLORS[s]}"></span>`;
    selectorHTML += `<div class="compare-selector">
      ${colorDot}
      <select class="compare-dropdown" data-inputact="compare-slot-changed" data-slot="${s}">
        <option value="">Select tournament...</option>
        ${tournaments.map((t, i) => {
          const sel = i === currentIdx ? 'selected' : '';
          const label = esc(t.family) + ' ' + t.year;
          return `<option value="${i}" ${sel}>${label}</option>`;
        }).join('')}
      </select>
      ${currentIdx != null ? `<button class="compare-remove-btn" data-act="compare-slot-remove" data-slot="${s}" title="Remove">&#10005;</button>` : ''}
    </div>`;
  }
  selectorHTML += '</div>';

  // Build stat table if 2+ selected
  const selected = _compareSlots.map(i => ({ idx: i, t: tournaments[i] })).filter(x => x.t);
  let statsHTML = '';
  let chartHTML = '';
  let insightHTML = '';

  if (selected.length >= 2) {
    statsHTML = '<div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Stat</th>';
    selected.forEach((s, ci) => {
      statsHTML += `<th style="color:${COMPARE_COLORS[ci]}">${esc(s.t.family)} ${s.t.year}</th>`;
    });
    statsHTML += '</tr></thead><tbody>';

    const rows = [
      { label: 'Status', fn: t => {
        const s = t.status === 'live' ? 'Live' : t.status === 'complete' ? 'Complete' : 'Upcoming';
        return `<span class="mini-badge badge-${t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'upcoming'}">${s}</span>`;
      }},
      { label: 'Current Count', fn: t => fmt(t.current_count) },
      { label: 'Predicted Final', fn: t => fmt(t.point_estimate) },
      { label: 'CI Range', fn: t => t.ci_lower && t.ci_upper ? `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}` : '—' },
      { label: 'Days Remaining', fn: t => t.days_remaining != null ? t.days_remaining : '—' },
      { label: 'Historical Avg', fn: t => t.historical && t.historical.length > 0 ? fmt(Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length)) : '—' },
      { label: 'Event Date', fn: t => t.event_date ? fmtDate(t.event_date) : '—' },
    ];

    rows.forEach(row => {
      statsHTML += `<tr><td class="compare-stat-label" data-stat="${esc(row.label)}">${row.label}</td>`;
      selected.forEach(s => { statsHTML += `<td data-label="${esc(s.t.family)} ${s.t.year}">${row.fn(s.t)}</td>`; });
      statsHTML += '</tr>';
    });
    statsHTML += '</tbody></table></div>';

    // Insight: compare predicted finals
    const preds = selected.map(s => ({ name: s.t.family, pred: s.t.point_estimate || 0 }));
    const maxPred = preds.reduce((a, b) => a.pred > b.pred ? a : b);
    const insights = [];
    preds.forEach(p => {
      if (p.name !== maxPred.name && maxPred.pred > 0 && p.pred > 0) {
        const pctAhead = ((maxPred.pred - p.pred) / p.pred * 100).toFixed(0);
        insights.push(`<strong>${esc(maxPred.name)}</strong> is predicted ${pctAhead}% higher than <strong>${esc(p.name)}</strong>`);
      }
    });
    if (insights.length > 0) {
      insightHTML = `<div class="compare-insights">${insights.map(i => `<div class="compare-insight">${i}</div>`).join('')}</div>`;
    }

    // Chart container
    chartHTML = `<div class="compare-chart-wrap"><canvas id="compareChart"></canvas></div>`;
  } else if (selected.length < 2) {
    statsHTML = `<div class="compare-empty">
      <div style="font-size:2.5rem;margin-bottom:12px">&#9878;</div>
      <div style="font-size:1rem;font-weight:600;margin-bottom:6px">Select at least 2 tournaments to compare</div>
      <div style="font-size:var(--fs-3);color:var(--muted)">Use the dropdowns above or click &#9878; on any tournament in the Predictions tab</div>
    </div>`;
  }

  // v4 U3 (audit/AUDIT_2026-07-26.md): the <2-selected path re-renders without
  // a canvas, so destroy before the innerHTML write detaches it — otherwise the
  // instance and its ResizeObserver stay live on the orphaned canvas.
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  el.innerHTML = selectorHTML + insightHTML + statsHTML + chartHTML;

  // Render chart if 2+
  if (selected.length >= 2) renderCompareChart(selected);
}

function compareSlotChanged(slotIdx, val) {
  _compareSlots = getCompareSlots();
  const idx = val !== '' ? parseInt(val, 10) : null;
  // Remove if already in another slot
  if (idx != null) _compareSlots = _compareSlots.filter(i => i !== idx);
  // Set or clear the slot
  while (_compareSlots.length <= slotIdx) _compareSlots.push(null);
  _compareSlots[slotIdx] = idx;
  // Compact: remove trailing nulls
  _compareSlots = _compareSlots.filter(i => i != null);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  renderCompareTab();
}

function compareSlotRemove(slotIdx) {
  _compareSlots = getCompareSlots();
  if (slotIdx < _compareSlots.length) _compareSlots.splice(slotIdx, 1);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  renderCompareTab();
}

function renderCompareChart(selected) {
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  const canvas = document.getElementById('compareChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // Build datasets from each tournament's ACTUAL daily_data (current edition's
  // real trajectory), not the smoothed prediction curve. y-axis is normalized
  // to % of predicted final, so different-sized tournaments compare cleanly
  // on the same scale. Each live tournament gets:
  //   - A solid line of its actual trajectory so far (this year's daily_data)
  //   - A dashed line of its prior year at T-N (where available) for context
  //   - A "today" dot at the latest data point
  // Completed tournaments get a single solid trace of their full daily_data.
  const datasets = [];
  selected.forEach((s, ci) => {
    const t = s.t;
    const color = COMPARE_COLORS[ci];
    const dimColor = COMPARE_COLORS_DIM[ci];
    // The y scaling target — predicted for live, actual final for completed.
    const target = (t.status === 'live')
      ? (t.point_estimate || 1)
      : (t.current_count || 1);
    if (target <= 0) return;

    // Current edition trajectory (solid line).
    if (t.daily_data && t.daily_data.length > 0 && t.event_start) {
      // Same contract as the main chart (v3 P1): draw the sanitised series,
      // never the raw array — raw points above the scraped total are
      // impossible and skew the normalized %.
      const dd = (typeof DailySeries !== 'undefined')
        ? DailySeries.sanitizeSeries(t.daily_data, {
            currentCount: t.current_count, isLive: t.status === 'live' }).points
        : t.daily_data;
      // Guard block (not an early return): an empty sanitised series must not
      // silently drop this tournament's prior-year trace below.
      if (dd.length) {
        // Convert daily_data ([day_idx, cumulative]) to (days_before, %).
        const lastDay = dd[dd.length - 1][0];
        const data = dd.map(p => ({
          x: lastDay - p[0] + (t.days_remaining || 0),
          y: (p[1] / target) * 100,
        }));
        datasets.push({
          label: `${t.family} ${t.year}`,
          data,
          borderColor: color,
          backgroundColor: dimColor,
          fill: ci === 0,
          borderWidth: 2.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 5,
          tension: 0.25,
        });
        // Today dot — the very last actual data point.
        if (t.status === 'live') {
          const last = data[data.length - 1];
          datasets.push({
            label: `${t.family} · Today`,
            data: [last],
            borderColor: color,
            backgroundColor: color,
            pointRadius: 7,
            pointStyle: 'circle',
            pointBorderWidth: 2,
            // Canvas cannot resolve CSS custom properties; 'var(--bg)' here
            // silently painted the ring black on every theme.
            pointBorderColor: PALETTE.bg,
            showLine: false,
          });
        }
      }
    }

    // Prior-year context — dashed line of the most recent historical edition
    // (model uses this as part of its training). Surfaces "is this year
    // tracking ahead/behind last year at the same T?" visually.
    if (t.status === 'live' && t.historical && t.historical.length > 0) {
      const prior = t.historical[t.historical.length - 1];
      if (prior && prior.daily_data && prior.daily_data.length > 0
          && prior.count && prior.count > 0) {
        const priorTarget = prior.count;
        const pdd = (typeof DailySeries !== 'undefined')
          ? DailySeries.sanitizeSeries(prior.daily_data, {
              currentCount: prior.count, isLive: false }).points
          : prior.daily_data;
        const priorLast = pdd.length ? pdd[pdd.length - 1][0] : 0;
        const priorData = pdd.map(p => ({
          x: priorLast - p[0],
          y: (p[1] / priorTarget) * 100,
        }));
        datasets.push({
          label: `${t.family} · ${prior.year} (prior)`,
          data: priorData,
          borderColor: color,
          borderDash: [4, 4],
          borderWidth: 1.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 3,
          tension: 0.25,
          fill: false,
        });
      }
    }

    // Final-count fallback: if we couldn't build a daily line (e.g. no
    // daily_data for a completed tournament), at least render a single
    // marker at x=0 (event day) at 100%.
    if (!t.daily_data || t.daily_data.length === 0) {
      datasets.push({
        label: `${t.family} ${t.year}`,
        data: [{ x: 0, y: 100 }],
        borderColor: color, backgroundColor: color,
        pointRadius: 8, pointStyle: 'circle', showLine: false,
      });
    }
  });

  if (datasets.length === 0) return;

  // Direct end labels for the primary traces (desktop only; mobile keeps the
  // legend). The x scale is reverse:true, so a trace's "now" endpoint (lowest
  // days-before value) renders at the RIGHT edge — labels sit left of the
  // endpoint and clamp inside the chart area. Vertical collisions stack the
  // same way the marker pills do.
  const compareEndLabels = {
    id: 'compareEndLabels',
    afterDraw(chartInstance) {
      if (_mobileVP()) return;
      const area = chartInstance.chartArea;
      const ctx2 = chartInstance.ctx;
      const drawn = [];
      chartInstance.data.datasets.forEach((ds, i) => {
        if (!ds.label || ds.label.includes('· Today') || ds.label.includes('(prior)')) return;
        const meta = chartInstance.getDatasetMeta(i);
        if (!meta.visible || !meta.data.length) return;
        const end = meta.data[meta.data.length - 1];
        ctx2.save();
        ctx2.font = 'bold 11px -apple-system, system-ui, sans-serif';
        ctx2.textAlign = 'left';
        const textW = ctx2.measureText(ds.label).width;
        const pillW = textW + 12;
        const pillH = 16;
        let px = end.x - 10 - pillW;
        if (px < area.left) px = Math.min(end.x + 10, area.right - pillW);
        let py = end.y - pillH / 2;
        if (py < area.top) py = area.top;
        if (py + pillH > area.bottom) py = area.bottom - pillH;
        // Dodge vertically past any already-drawn label rect.
        let guard = 0;
        while (guard++ < 6 && drawn.some(d =>
            !(px + pillW < d.x || px > d.x + d.w || py + pillH < d.y || py > d.y + d.h))) {
          py += pillH + 3;
          if (py + pillH > area.bottom) { py = area.top; break; }
        }
        drawn.push({ x: px, y: py, w: pillW, h: pillH });
        ctx2.fillStyle = themeRgba(PALETTE.surface, 0.85);
        ctx2.beginPath();
        ctx2.roundRect(px, py, pillW, pillH, 4);
        ctx2.fill();
        ctx2.strokeStyle = ds.borderColor;
        ctx2.globalAlpha = 0.6;
        ctx2.lineWidth = 1;
        ctx2.stroke();
        ctx2.globalAlpha = 1;
        ctx2.fillStyle = ds.borderColor;
        ctx2.fillText(ds.label, px + 6, py + pillH - 5);
        ctx2.restore();
      });
    }
  };

  _compareChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    plugins: [compareEndLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // v4 U6: without this the chart falls back to nearest+intersect:true and a
      // fingertip has to land on the 2.5px line itself. Same contract as the
      // scatter and timeline charts.
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: {
          type: 'linear',
          reverse: true,
          title: { display: !_mobileVP(), text: 'Days Before Event', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8, maxRotation: 0,
            callback(v) { return v === 0 ? 'Event' : v + 'd'; }
          },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        },
        y: {
          title: { display: !_mobileVP(), text: '% of Final Entries', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8,
            callback(v) { return v + '%'; }
          },
          grid: { color: themeRgba(PALETTE.border, 0.4) },
          min: 0
        }
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: PALETTE.text2,
            font: { size: 11 },
            boxWidth: _mobileVP() ? 8 : 12,
            padding: _mobileVP() ? 6 : 10,
            filter(item) { return !item.text.includes('· Today'); },
            usePointStyle: true, pointStyle: 'line'
          }
        },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95),
          borderColor: themeRgba(PALETTE.border, 0.8),
          borderWidth: 1,
          titleColor: PALETTE.text,
          bodyColor: PALETTE.text2,
          footerColor: PALETTE.muted,
          padding: 12,
          cornerRadius: 8,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
          bodyFont: { size: 12 },
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = items[0].parsed.x;
              return db === 0 ? 'Event Day' : `T-${db} (${db} days before)`;
            },
            label(item) {
              return ` ${item.dataset.label}: ${item.parsed.y.toFixed(1)}%`;
            }
          }
        }
      }
    }
  });
}

// One-shot migration: the previous saveDataEntry() iterated every input and
// persisted every visible field as an override, freezing pipeline values for
// tournaments the user never intended to override. Wipe legacy overrides once
// per client (flagged in localStorage so it runs exactly once).
(function purgeLegacyOverrides() {
  const FLAG = 'cca_overrides_purged_v35';
  if (localStorage.getItem(FLAG)) return;
  try {
    const existing = JSON.parse(localStorage.getItem('cca_overrides') || '{}');
    if (existing && typeof existing === 'object' && Object.keys(existing).length > 0) {
      localStorage.removeItem('cca_overrides');
      console.info('[CCA] Cleared stale overrides on upgrade. Re-set any deliberate overrides in Data Entry.');
    }
  } catch (e) {}
  localStorage.setItem(FLAG, '1');
})();

applyOverrides();

// ══════════════════════════════════════════════════════════
// ASK TAB — chatbot UI
// (declarations must precede init() — init() may invoke initAskTab via
//  navigateToHash if the URL contains #ask, which would TDZ-throw on these
//  consts/lets if they're declared after init().)
// ══════════════════════════════════════════════════════════
const ASK_ENDPOINT = (function() {
  const h = (typeof location !== 'undefined') ? location.hostname : '';
  if (h === 'localhost' || h === '127.0.0.1' || h === '') return 'http://localhost:8787/ask';
  return 'https://chess-ask.hater-andrewd.workers.dev/ask';
})();
const ASK_SUGGESTIONS = [
  'When does Liberty Bell start?',
  'How big will Continental get?',
  'Top 5 biggest tournaments right now',
  'Did North American Open grow last year?',
  "What's the early bird fee for World Open?",
  'Which live tournament has the most entries?',
];
const ASK_HISTORY_KEY = 'cep:ask:history';
const ASK_MAX_HISTORY_PAIRS = 4;        // last N Q/A pairs sent as history[] (worker caps at 8 msgs)
const ASK_REQUEST_TIMEOUT_MS = 60000;   // client-side abort so a stuck request can't hang forever
// Query words that carry no signal for name matching in the keyword fallback.
const ASK_STOPWORDS = new Set(['the', 'a', 'an', 'of', 'in', 'on', 'at', 'for', 'to', 'is', 'are',
  'was', 'were', 'how', 'what', 'when', 'which', 'who', 'did', 'does', 'do', 'will', 'get', 'got',
  'and', 'or', 'vs', 'right', 'now', 'this', 'that', 'many', 'much', 'tournament', 'tournaments']);
let askInited = false;
let askInFlight = false;
let askController = null;                // AbortController for the in-flight request
const askTurns = [];                     // in-memory conversation ({q, a}) for multi-turn context

init();

function initAskTab() {
  if (askInited) return;
  askInited = true;
  const info = document.getElementById('askDataInfo');
  if (info && typeof TOURNAMENT_DATA !== 'undefined' && TOURNAMENT_DATA && TOURNAMENT_DATA.generated) {
    info.textContent = `Plain English works. Data is current as of ${TOURNAMENT_DATA.generated}.`;
  }
  const chipsHost = document.getElementById('askChips');
  if (chipsHost) {
    chipsHost.innerHTML = '';
    ASK_SUGGESTIONS.forEach(q => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'ask-chip';
      b.textContent = q;
      b.addEventListener('click', () => askRun(q));
      chipsHost.appendChild(b);
    });
  }
  const input = document.getElementById('askInput');
  if (input) {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        askSubmit();
      }
    });
  }
  const btn = document.getElementById('askSubmit');
  if (btn) {
    btn.addEventListener('click', askSubmit);
  }
  renderAskRecent();
}

function askSubmit() {
  if (askSubmit._busy) return;
  askSubmit._busy = true;
  setTimeout(() => { askSubmit._busy = false; }, 250);
  const input = document.getElementById('askInput');
  if (!input) return;
  let q = input.value.trim();
  if (!q) {
    q = ASK_SUGGESTIONS[0];
    input.value = q;
    showAskBanner('warn', 'Empty input: running the first suggestion. Type your own question and press Ask.');
  }
  askRun(q);
}

// Flatten the in-memory conversation into the worker's history[] shape (last N pairs).
function buildAskHistory() {
  const msgs = [];
  askTurns.slice(-ASK_MAX_HISTORY_PAIRS).forEach(p => {
    msgs.push({ role: 'user', content: p.q });
    msgs.push({ role: 'assistant', content: p.a });
  });
  return msgs;
}

async function askRun(question) {
  if (askInFlight) return;
  askInFlight = true;
  const input = document.getElementById('askInput');
  const btn = document.getElementById('askSubmit');
  const banner = document.getElementById('askBanner');
  if (input) input.value = '';
  if (btn) { btn.disabled = true; btn.textContent = 'Thinking…'; }
  if (banner) { banner.hidden = true; banner.textContent = ''; banner.className = 'ask-banner'; }

  appendUserTurn(question);
  const pending = appendAssistantPending();
  scrollAskThread();

  askController = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; askController.abort(); }, ASK_REQUEST_TIMEOUT_MS);

  try {
    const resp = await fetch(ASK_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: buildAskHistory() }),
      signal: askController.signal,
    });
    const data = await resp.json().catch(() => ({}));
    pending.stop();

    if (!resp.ok) {
      const isRateLimit = resp.status === 429;
      const isBudget = resp.status === 503 && data.error === 'daily_budget_exhausted';
      const msg = data.message || `Error ${resp.status}.`;
      if (isRateLimit || isBudget) {
        showAskBanner('warn', msg);
        fillAssistantText(pending.bubble, '(No answer: ' + msg + ')');
      } else {
        showAskBanner('error', msg + ' Showing keyword matches instead.');
        fillAssistantFallback(pending.bubble, question);
      }
      return;
    }

    const answer = data.answer || '(no answer returned)';
    fillAssistantText(pending.bubble, answer, {
      model: data.model,
      latency_ms: data.latency_ms,
      data_generated: data.data_generated,
      tools_used: data.tools_used,
    });
    rememberAskTurn(question, answer);
    pushAskHistory(question);
  } catch (e) {
    pending.stop();
    if (e && e.name === 'AbortError') {
      if (timedOut) {
        fillAssistantText(pending.bubble, 'That took over a minute and was stopped. Try a simpler question, or these keyword matches:');
        fillAssistantFallback(pending.bubble, question, true);
      } else {
        fillAssistantText(pending.bubble, 'Stopped.');
      }
    } else {
      showAskBanner('error', 'AI is unavailable right now; here are keyword matches instead:');
      fillAssistantFallback(pending.bubble, question);
    }
  } finally {
    clearTimeout(timer);
    askController = null;
    askInFlight = false;
    if (btn) { btn.disabled = false; btn.textContent = 'Ask'; }
    scrollAskThread();
  }
}

function rememberAskTurn(q, a) {
  askTurns.push({ q, a });
  if (askTurns.length > 12) askTurns.shift();
}

function scrollAskThread() {
  const el = document.getElementById('askAnswer');
  if (!el) return;
  const last = el.lastElementChild;
  if (last && typeof last.scrollIntoView === 'function') {
    last.scrollIntoView({ block: 'nearest' });
  }
}

function appendUserTurn(text) {
  const host = document.getElementById('askAnswer');
  if (!host) return;
  const turn = document.createElement('div');
  turn.className = 'ask-turn ask-turn-user';
  const bubble = document.createElement('div');
  bubble.className = 'ask-bubble';
  bubble.textContent = text;
  turn.appendChild(bubble);
  host.appendChild(turn);
}

// Append an assistant bubble in the "thinking" state with an elapsed counter,
// a one-time SR announcement, and a Cancel button. Returns { bubble, stop() }.
function appendAssistantPending() {
  const host = document.getElementById('askAnswer');
  const turn = document.createElement('div');
  turn.className = 'ask-turn ask-turn-assistant';
  const bubble = document.createElement('div');
  bubble.className = 'ask-bubble ask-bubble-pending';

  const row = document.createElement('div');
  row.className = 'ask-pending';

  const spinner = document.createElement('span');
  spinner.className = 'ask-spinner';
  spinner.setAttribute('aria-hidden', 'true');

  // Constant text — announced once by the live region, not re-announced.
  const msg = document.createElement('span');
  msg.className = 'ask-pending-msg';
  msg.textContent = 'Working on your answer; this can take up to a minute.';

  // Per-second counter — hidden from the accessibility tree so it doesn't spam SR.
  const label = document.createElement('span');
  label.className = 'ask-pending-label';
  label.setAttribute('aria-hidden', 'true');

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'ask-cancel';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', () => { if (askController) askController.abort(); });

  const started = Date.now();
  const tick = () => { label.textContent = Math.round((Date.now() - started) / 1000) + 's'; };
  tick();

  row.appendChild(spinner);
  row.appendChild(msg);
  row.appendChild(label);
  row.appendChild(cancelBtn);
  bubble.appendChild(row);
  turn.appendChild(bubble);
  host.appendChild(turn);

  const iv = setInterval(tick, 1000);
  return { bubble, stop() { clearInterval(iv); } };
}

function fillAssistantText(bubble, text, meta) {
  if (!bubble) return;
  bubble.classList.remove('ask-bubble-pending');
  bubble.innerHTML = '';
  const body = document.createElement('div');
  body.textContent = text;
  bubble.appendChild(body);
  if (meta) {
    const m = document.createElement('div');
    m.className = 'ask-answer-meta';
    const parts = [];
    if (meta.model) parts.push(esc(meta.model));
    if (typeof meta.latency_ms === 'number') parts.push((meta.latency_ms / 1000).toFixed(1) + 's');
    if (meta.data_generated) parts.push('data: ' + esc(meta.data_generated));
    if (Array.isArray(meta.tools_used) && meta.tools_used.length) {
      parts.push('tools: ' + meta.tools_used.map(esc).join(', '));
    }
    m.innerHTML = parts.join(' &middot; ');
    bubble.appendChild(m);
  }
}

function showAskBanner(kind, message) {
  const banner = document.getElementById('askBanner');
  if (!banner) return;
  banner.hidden = false;
  banner.className = 'ask-banner is-' + kind;
  banner.textContent = message;
}

// Rank tournaments by keyword overlap with the query. Any-token match (not
// all-tokens) so a multi-word question still surfaces the relevant families;
// stopwords are dropped, exact and substring hits rank highest.
function fallbackMatches(query) {
  if (!TOURNAMENT_DATA || !TOURNAMENT_DATA.tournaments) return [];
  const q = query.toLowerCase().trim();
  const rawTokens = q.split(/[^a-z0-9]+/).filter(Boolean);
  const tokens = rawTokens.filter(t => t.length > 1 && !ASK_STOPWORDS.has(t));
  const useTokens = tokens.length ? tokens : rawTokens;   // stopword-only query still matches on rawTokens
  return TOURNAMENT_DATA.tournaments
    .map(t => {
      const name = (t.family + ' ' + t.year).toLowerCase();
      let s = 0;
      if (name === q) s = 1000;
      else if (q && name.includes(q)) s += 100;
      let hits = 0;
      useTokens.forEach(tok => { if (name.includes(tok)) { s += 12; hits++; } });
      if (hits && hits === useTokens.length) s += 20;     // bonus when every query token lands
      return { t, s };
    })
    .filter(x => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, 8)
    .map(x => x.t);
}

// Render keyword matches into an assistant bubble. `append` keeps any text
// already placed above (used when a timeout message precedes the matches).
function fillAssistantFallback(bubble, query, append) {
  if (!bubble) return;
  bubble.classList.remove('ask-bubble-pending');
  if (!append) bubble.innerHTML = '';
  const matches = fallbackMatches(query);
  if (matches.length === 0) {
    const none = document.createElement('div');
    none.textContent = 'No keyword matches in the local data.';
    bubble.appendChild(none);
    return;
  }
  const head = document.createElement('div');
  head.textContent = 'Keyword matches:';
  bubble.appendChild(head);
  const list = document.createElement('div');
  list.className = 'ask-fallback-results';
  matches.forEach(t => {
    const row = document.createElement('div');
    row.className = 'ask-fallback-item';
    const name = document.createElement('div');
    name.innerHTML = '<strong>' + esc(t.family + ' ' + t.year) + '</strong>';
    const meta = document.createElement('div');
    meta.className = 'meta';
    const bits = [];
    if (t.status) bits.push(esc(t.status));
    if (t.event_start) bits.push(esc(t.event_start));
    if (typeof t.current_count === 'number') bits.push(t.current_count.toLocaleString() + ' entries');
    else if (typeof t.point_estimate === 'number') bits.push('predicted ' + t.point_estimate.toLocaleString());
    meta.textContent = bits.join(' · ');
    row.appendChild(name);
    row.appendChild(meta);
    list.appendChild(row);
  });
  bubble.appendChild(list);
}

function loadAskHistory() {
  try {
    const raw = localStorage.getItem(ASK_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}
function pushAskHistory(q) {
  let h = loadAskHistory().filter(x => x !== q);
  h.unshift(q);
  h = h.slice(0, 5);
  try { localStorage.setItem(ASK_HISTORY_KEY, JSON.stringify(h)); } catch {}
  renderAskRecent();
}
function renderAskRecent() {
  const host = document.getElementById('askRecent');
  if (!host) return;
  const h = loadAskHistory();
  host.innerHTML = '';
  if (!h.length) return;
  const title = document.createElement('div');
  title.className = 'ask-recent-title';
  title.textContent = 'Recent';
  host.appendChild(title);
  const list = document.createElement('div');
  list.className = 'ask-recent-list';
  h.forEach(q => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ask-recent-item';
    b.textContent = q;
    b.onclick = () => askRun(q);
    list.appendChild(b);
  });
  host.appendChild(list);
}
