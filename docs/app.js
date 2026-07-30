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
