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

init();
