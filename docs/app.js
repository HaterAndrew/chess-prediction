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
