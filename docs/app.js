
// ══════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════
// Opt out of browser scroll-restoration. With the mobile reorientation
// (round Path A) doing CSS-order shuffling, restored scroll positions from
// prior visits land users mid-page on reload. Always start fresh at top.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
let selectedIndex = 0;
let chart = null;
let histChartObj = null;
// (dropdownOpen removed — using openDrop from tab bar system)

// ══════════════════════════════════════════════════════════
// HELPERS
// ══════════════════════════════════════════════════════════
function _mobileVP() { return window.matchMedia('(max-width: 639px)').matches; }
// Progressive-enhancement haptic. Android Chrome/Firefox supported; iOS Safari
// no-ops. Respects prefers-reduced-motion. Round 31.
function _haptic(ms) {
  if (typeof navigator === 'undefined' || !navigator.vibrate) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  try { navigator.vibrate(ms || 12); } catch (_) {}
}
function hideSkeletons() {
  document.querySelectorAll('.skeleton').forEach(el => el.style.display = 'none');
  const loader = document.getElementById('skeletonLoader');
  if (loader) loader.style.display = 'none';
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}
function fmt(n) { return n == null ? '–' : n.toLocaleString(); }
function isDone(t) { return t.status === 'complete' || t.status === 'historical'; }

// ══════════════════════════════════════════════════════════
// COMMAND PALETTE (Cmd/Ctrl + K)
// ══════════════════════════════════════════════════════════
// Fuzzy search across all tournaments + jump to result. Lightweight
// substring + token match scoring — no fuse.js dependency.
let _cmdkActive = -1;
let _cmdkMatches = [];
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
  list.innerHTML = _cmdkMatches.map((m, i) => {
    const t = m.t;
    const statusCls = t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'hist';
    const statusLabel = t.status === 'live' ? `T-${t.days_remaining ?? '?'}`
                      : t.status === 'complete' ? 'final'
                      : 'past';
    const numText = t.status === 'live' ? `${fmt(t.current_count)} → ${fmt(t.point_estimate)}`
                  : `${fmt(t.current_count)}`;
    return `<button class="cmdk-row ${i === _cmdkActive ? 'cmdk-row-active' : ''}" data-idx="${m.idx}" data-pos="${i}" onclick="_cmdkSelect(${m.idx})" role="option" aria-selected="${i === _cmdkActive}">
      <span class="cmdk-row-status cmdk-status-${statusCls}">${statusLabel}</span>
      <span class="cmdk-row-name">${esc(t.family)} <span class="cmdk-row-year">${t.year}</span></span>
      <span class="cmdk-row-num">${numText}</span>
    </button>`;
  }).join('');
}
function _cmdkSelect(idx) {
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

// An "early bird" only exists when there's an actual price hike BETWEEN an
// early-bird window and a regular window, AND the deadline lands well before
// the event. Just having a deadline isn't enough — many CCA events publish a
// $X advance / $X+ onsite step 2-3 days out (Cleveland Open 2026: $93→$110
// with 3d gap), which is a late-registration penalty, not an early bird.
// Threshold: at least 14 days between early_bird_deadline and event_start.
// CCA metadata also occasionally carries impossible deadlines (e.g. Chicago
// Class 2026 had EB=Nov 10 with event=Jul 17), which the gap check excludes.
const EARLY_BIRD_MIN_GAP_DAYS = 14;
function hasValidEarlyBird(t) {
  if (!t.early_bird_deadline || !t.event_start) return false;
  if (t.early_bird_fee == null || t.regular_fee == null) return false;
  if (t.early_bird_fee >= t.regular_fee) return false;
  return daysBetween(t.early_bird_deadline, t.event_start) >= EARLY_BIRD_MIN_GAP_DAYS;
}
function fmtDate(s) {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
function fmtDateLong(s) {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}
function fmtDateTimeLong(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '–';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit'
  });
}
function addDays(dateStr, days) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return d;
}
function daysBetween(a, b) {
  return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000);
}
function interpCurve(curve, daysBefore) {
  if (!curve || curve.length === 0) return 1;
  const sorted = [...curve].sort((a, b) => b.days_before - a.days_before);
  const pct = (pt) => pt.cumulative_pct !== undefined ? pt.cumulative_pct : (pt.pct || 0);
  if (daysBefore >= sorted[0].days_before) return pct(sorted[0]);
  if (daysBefore <= sorted[sorted.length-1].days_before) return pct(sorted[sorted.length-1]);
  for (let i = 0; i < sorted.length - 1; i++) {
    if (daysBefore <= sorted[i].days_before && daysBefore >= sorted[i+1].days_before) {
      const frac = (sorted[i].days_before - daysBefore) / (sorted[i].days_before - sorted[i+1].days_before);
      return pct(sorted[i]) + frac * (pct(sorted[i+1]) - pct(sorted[i]));
    }
  }
  return 1;
}

// ══════════════════════════════════════════════════════════
// PACE ALERT HELPERS
// ══════════════════════════════════════════════════════════
function getPaceAlert(t) {
  return t && t.pace_alert ? t.pace_alert : null;
}

// Builds the hero narrative — a 1-2 sentence plain-English summary that ties
// the headline numbers together. Returns HTML (not text) so we can highlight
// the specific phrase that's load-bearing (the comparison verdict) with
// color. Handles three states: completed (compare to historical avg),
// live with pace_alert (compare to N-yr at-T avg + name the next milestone),
// and live without pace_alert (still-loading or insufficient history).
function buildHeroNarrative(t) {
  if (!t) return '';
  // Completed: name what happened vs history.
  if (isDone(t)) {
    if (!t.historical || t.historical.length === 0) {
      return `<p>Final count: <strong>${fmt(t.current_count)}</strong> entries.</p>`;
    }
    const avg = Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length);
    const diff = t.current_count - avg;
    const pct = avg > 0 ? Math.round((diff / avg) * 100) : 0;
    let verdict, cls;
    if (pct >= 5) { verdict = `${Math.abs(pct)}% above`; cls = 'pos'; }
    else if (pct <= -5) { verdict = `${Math.abs(pct)}% below`; cls = 'neg'; }
    else { verdict = 'in line with'; cls = 'flat'; }
    return `<p><strong>${fmt(t.current_count)}</strong> entries — <span class="hn-verdict hn-${cls}">${verdict}</span> the ${t.historical.length}-year average of ${fmt(avg)}.</p>`;
  }

  // Live state — combine pace verdict + countdown + next milestone.
  const parts = [];
  const pa = t.pace_alert;
  if (pa && pa.expected != null) {
    const cls = pa.status === 'above_pace' ? 'pos'
              : pa.status === 'below_pace' ? 'neg' : 'flat';
    const dev = Math.round(pa.deviation_pct || 0);
    const devText = dev > 0 ? `+${dev}%` : `${dev}%`;
    const phrase = pa.status === 'on_pace'
      ? 'tracking on pace'
      : pa.status === 'above_pace'
        ? 'tracking ahead of pace'
        : 'tracking behind pace';
    parts.push(`<strong>${fmt(t.current_count)}</strong> of a predicted <strong>${fmt(t.point_estimate)}</strong> — <span class="hn-verdict hn-${cls}">${phrase} (${devText} vs prior years at this point)</span>.`);
  } else {
    // No pace_alert (typically: not enough historical daily data).
    parts.push(`<strong>${fmt(t.current_count)}</strong> registered so far of a predicted <strong>${fmt(t.point_estimate)}</strong>.`);
  }

  // Daily pace + needed pace context.
  if (t.daily_data && t.daily_data.length >= 3 && t.days_remaining > 0) {
    const recent = t.daily_data.slice(-7);
    const daySpan = recent[recent.length-1][0] - recent[0][0];
    const regSpan = recent[recent.length-1][1] - recent[0][1];
    const rate = daySpan > 0 ? regSpan / daySpan : 0;
    const remaining = t.point_estimate - t.current_count;
    const needed = remaining / t.days_remaining;
    if (rate >= 0.5 && needed >= 0.5) {
      const verdict = rate >= needed * 0.95
        ? 'on track to land in the predicted range'
        : `needs ${needed.toFixed(1)}/day to hit the prediction (currently ${rate.toFixed(1)}/day)`;
      parts.push(verdict.charAt(0).toUpperCase() + verdict.slice(1) + '.');
    }
  }

  // Next milestone — the closest upcoming reference point.
  if (hasValidEarlyBird(t)) {
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    const ebDate = new Date(t.early_bird_deadline + 'T00:00:00');
    const ebDays = Math.ceil((ebDate - today) / 86400000);
    if (ebDays > 0 && ebDays <= 21) {
      parts.push(`Early bird closes in ${ebDays} day${ebDays === 1 ? '' : 's'}.`);
    }
  } else if (t.days_remaining != null && t.days_remaining <= 14 && t.days_remaining > 0) {
    parts.push(`Event opens in ${t.days_remaining} day${t.days_remaining === 1 ? '' : 's'}.`);
  }

  return `<p>${parts.join(' ')}</p>`;
}
function paceBadgeHTML(alert) {
  if (!alert) return '';
  const cls = alert.status === 'above_pace' ? 'above' : alert.status === 'below_pace' ? 'below' : 'on';
  const icon = alert.status === 'above_pace' ? '\uD83D\uDFE2' : alert.status === 'below_pace' ? '\uD83D\uDD34' : '\uD83D\uDFE1';
  return `<span class="pace-badge ${cls}">${icon}</span>`;
}
// The multi-year at-T context (alert.message from alerts.py) used to render
// as its own separate banner below the YoY delta banner. Two stacked
// indicators competing for attention; the lightning-bolt one duplicated
// the parenthetical pct already inside the message ("(-1%)" + "-0.8%").
// Now it ships as a sub-line inside the delta banner via renderDelta().

// ══════════════════════════════════════════════════════════
// PAGE TABS
// ══════════════════════════════════════════════════════════
let _currentTab = 'predictions';
function switchPageTab(tab, skipHash) {
  if (_mobileVP() && _currentTab !== tab) _haptic(8);
  _currentTab = tab;
  document.querySelectorAll('.page-tab').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
  document.querySelectorAll('.page-tab-panel').forEach(p => p.classList.remove('active'));
  const tabBtn = document.getElementById('ptab-' + tab);
  tabBtn.classList.add('active');
  tabBtn.setAttribute('aria-selected', 'true');
  // Scroll active tab into view only when the strip actually overflows
  const tabsContainer = tabBtn.closest('.page-tabs');
  if (tabsContainer && tabsContainer.scrollWidth > tabsContainer.clientWidth + 1) {
    tabBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }
  const panel = document.getElementById('panel-' + tab);
  panel.classList.add('active');
  if (tab === 'puzzles') initPuzzles();
  if (tab === 'dataentry') renderDataEntry();
  if (tab === 'email') initEmailTab();
  if (tab === 'performance') initPerformanceTab();
  if (tab === 'favorites') renderFavoritesTab();
  if (tab === 'compare') renderCompareTab();
  // Focus management: move focus to new panel for screen readers
  panel.setAttribute('tabindex', '-1');
  panel.focus({ preventScroll: true });
  if (!skipHash) updateHash();
}

// Mobile swipe-between-tabs navigation
const PAGE_TAB_ORDER = ['predictions', 'dataentry', 'compare', 'email', 'performance', 'about', 'puzzles'];
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

// ══════════════════════════════════════════════════════════
// EMAIL GENERATOR
// ══════════════════════════════════════════════════════════
let emailLength = 'medium';
let emailFormat = 'plain';
let emailLive = [];
let emailInited = false;

function initEmailTab() {
  if (emailInited) return;
  emailInited = true;
  emailLive = TOURNAMENT_DATA.tournaments
    .filter(t => t.status === 'live')
    .sort((a, b) => a.days_remaining - b.days_remaining);
  const grid = document.getElementById('emailGrid');
  grid.innerHTML = '';
  emailLive.forEach((t, i) => {
    const lbl = document.createElement('label');
    const defaultOn = t.days_remaining <= 60;
    lbl.innerHTML = `<input type="checkbox" data-eidx="${i}" ${defaultOn ? 'checked' : ''}>
      <span>${esc(t.family)}</span>
      <span class="email-tourn-days">${t.days_remaining}d</span>`;
    grid.appendChild(lbl);
  });
  // Auto-suggest subject line on first init
  const subj = document.getElementById('emailSubject');
  if (subj && !subj.value) subj.placeholder = emailAutoSubject(emailGetSelected());
}

function emailGetSelected() {
  const sel = [];
  document.querySelectorAll('#emailGrid input[type="checkbox"]').forEach(cb => {
    if (cb.checked) sel.push(emailLive[parseInt(cb.dataset.eidx)]);
  });
  return sel;
}
function emailSelectAll() { document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = true); }
function emailSelectNone() { document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = false); }
function emailSelectClose() {
  document.querySelectorAll('#emailGrid input').forEach(cb => {
    cb.checked = emailLive[parseInt(cb.dataset.eidx)].days_remaining <= 60;
  });
}
function emailSelectLiveOnly() {
  // All emailLive are already live; this just re-checks all (alias for All within live set)
  document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = true);
}

function setEmailLength(len) {
  emailLength = len;
  document.querySelectorAll('#emailLenToggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.len === len);
  });
}

function setEmailFormat(fmt) {
  emailFormat = fmt;
  document.querySelectorAll('#emailFormatToggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.fmt === fmt);
  });
  applyEmailViewState();
}

function setEmailSplitTab(tab) {
  const split = document.getElementById('emailSplit');
  if (!split) return;
  split.dataset.tab = tab;
  document.querySelectorAll('#emailSplitTabs .email-split-tab').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  applyEmailViewState();
}

function applyEmailViewState() {
  const out = document.getElementById('emailOutput');
  const pv = document.getElementById('emailPreview');
  const split = document.getElementById('emailSplit');
  const tabs = document.getElementById('emailSplitTabs');
  const copyHtmlBtn = document.getElementById('emailCopyHtmlBtn');
  if (!out || !pv) return;
  const tab = (split && split.dataset.tab) || 'source';
  const isMobile = window.matchMedia('(max-width: 639px)').matches;

  if (emailFormat === 'html') {
    out.classList.add('mode-html');
    if (copyHtmlBtn) copyHtmlBtn.style.display = '';
    if (isMobile) {
      if (tabs) tabs.style.display = '';
      out.style.display = (tab === 'source') ? '' : 'none';
      pv.style.display = (tab === 'preview') ? '' : 'none';
    } else {
      if (tabs) tabs.style.display = 'none';
      out.style.display = '';
      pv.style.display = '';
    }
  } else {
    out.classList.remove('mode-html');
    if (copyHtmlBtn) copyHtmlBtn.style.display = 'none';
    if (tabs) tabs.style.display = 'none';
    out.style.display = '';
    pv.style.display = 'none';
  }
}

window.addEventListener('resize', () => {
  if (typeof emailFormat !== 'undefined') applyEmailViewState();
});

// Re-apply mobile-aware chart options on viewport change (orientation flip,
// devtools emulation toggle, browser resize). Without this, charts initialized
// at one viewport keep their original tick density / time unit even after
// the layout crosses the 640px breakpoint.
let _chartResizeT;
window.addEventListener('resize', () => {
  clearTimeout(_chartResizeT);
  _chartResizeT = setTimeout(() => {
    const isM = _mobileVP();
    if (chart && chart.options && chart.options.scales) {
      const xs = chart.options.scales.x;
      const ys = chart.options.scales.y;
      if (xs && xs.time) {
        xs.time.unit = isM ? 'month' : 'week';
        xs.time.displayFormats = isM ? { month: 'MMM' } : { week: 'MMM d' };
      }
      if (xs && xs.ticks) xs.ticks.font = { size: isM ? 10 : 11 };
      if (ys && ys.ticks) {
        ys.ticks.font = { size: isM ? 10 : 11 };
        ys.ticks.maxTicksLimit = isM ? 4 : 8;
      }
      chart.update('none');
    }
  }, 200);
});

function emailLastYear(t) {
  if (!t.historical || !t.historical.length) return null;
  return [...t.historical].sort((a, b) => b.year - a.year)[0];
}
function emailHistAvg(t) {
  if (!t.historical || !t.historical.length) return null;
  const c = t.historical.map(h => h.count);
  return Math.round(c.reduce((a, b) => a + b, 0) / c.length);
}

// Tab-separated table — tabs align natively in every email client
function emailTable(headers, rows) {
  const cell = c => (c !== '' && c != null) ? String(c) : '';
  const line = cols => cols.map(cell).join('\t');
  return line(headers) + '\n' + rows.map(r => line(r)).join('\n');
}

function emailFormatTournament(t, len) {
  const ly = emailLastYear(t);
  const avg = emailHistAvg(t);
  const pace = t.prior_year_pace;
  const name = t.family.toUpperCase();
  const sorted = t.historical ? [...t.historical].sort((a, b) => b.year - a.year) : [];
  const parts = [];

  // ── SHORT ──
  if (len === 'short') {
    let s = `${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`;
    if (ly) s += `  Last year was ${ly.count}.`;
    parts.push(s);
    if (pace) {
      const d = t.current_count - pace.count_at_same_point;
      if (d > 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are ahead of pace.`);
      else if (d < 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are a bit behind.`);
      else parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}.`);
    }
    return parts.join('  ');
  }

  // ── MEDIUM ──
  if (len === 'medium') {
    let main = `${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`;
    if (ly) {
      const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
      if (pct > 10) main += `  Last year was ${ly.count}, so we are ahead.`;
      else if (pct < -10) main += `  Last year was ${ly.count}, so we are still behind.`;
      else if (pct < -3) main += `  Last year was ${ly.count}, so we are a little behind.`;
      else main += `  Last year was ${ly.count}.`;
    }
    parts.push(main);
    if (pace) {
      const d = t.current_count - pace.count_at_same_point;
      if (d > 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are ahead of pace.`);
      else if (d < 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are a bit behind.`);
      else parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}.`);
    }
    if (sorted.length >= 2) {
      const rows = [[2026, t.current_count, t.point_estimate, '']];
      sorted.forEach(h => rows.push([h.year, '', '', h.count]));
      parts.push(emailTable(['YEAR', 'ENTRIES', 'PROJECTION', 'FINAL'], rows));
    }
    return parts.join('\n');
  }

  // ── LONG ──
  parts.push(`${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`);

  if (ly) {
    const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
    if (pct > 15) parts.push(`Last year was ${ly.count}, so the projection has us well ahead.`);
    else if (pct > 5) parts.push(`Last year was ${ly.count}, so we are tracking ahead.`);
    else if (pct > -5) parts.push(`Last year was ${ly.count}, so we are in the same neighborhood.`);
    else if (pct > -15) parts.push(`Last year was ${ly.count}, so we are still a bit behind.`);
    else parts.push(`Last year was ${ly.count}, so we are lagging.`);
  }

  if (avg && sorted.length >= 3) {
    const pct = Math.round((t.point_estimate - avg) / avg * 100);
    if (pct < -10) parts.push(`The historical average is ${avg}, so we are still below the norm.`);
    else if (pct > 10) parts.push(`The historical average is ${avg}, so we are trending above average.`);
  }

  if (pace) {
    const d = t.current_count - pace.count_at_same_point;
    parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}` +
      (d > 0 ? `, so we are ahead of pace.` : d < 0 ? `, so we are behind.` : `.`));
  }

  if (sorted.length >= 3) {
    const counts = sorted.map(h => h.count);
    const worst = Math.min(...counts);
    const best = Math.max(...counts);
    const worstYr = sorted.find(h => h.count === worst).year;
    const bestYr = sorted.find(h => h.count === best).year;
    if (t.point_estimate < worst) parts.push(`The last time we were this low was ${worstYr} when we got ${worst}.`);
    else if (t.point_estimate > best) parts.push(`If we hit the projection, it would be the best year since at least ${bestYr} (${best}).`);
  }

  if (sorted.length >= 2) {
    const rows = [[2026, t.current_count, t.point_estimate, `${t.ci_lower}-${t.ci_upper}`, '']];
    sorted.forEach(h => rows.push([h.year, '', '', '', h.count]));
    parts.push(emailTable(['YEAR', 'ENTRIES', 'PROJECTION', 'RANGE', 'FINAL'], rows));
  }

  return parts.join('\n');
}

function emailOverallTheme(selected) {
  let ahead = 0, behind = 0;
  selected.forEach(t => {
    const ly = emailLastYear(t);
    if (!ly) return;
    const pct = (t.point_estimate - ly.count) / ly.count;
    if (pct > 0.05) ahead++;
    else if (pct < -0.05) behind++;
  });
  const total = ahead + behind;
  if (total === 0) return 'Things are holding steady across the board.';
  if (behind === 0) return 'The overall theme is improvement across the board.';
  if (ahead === 0) return 'The overall theme is we are still lagging across the board.';
  if (ahead >= behind) return 'The overall theme is a mixed bag \u2014 some improvement, but we are still behind on a few events.';
  return 'The overall theme today is there has been some improvement, but we are still lagging.';
}

// ── Highlights: biggest mover, fastest pace, behind-pace flags ──
function emailComputeHighlights(selected) {
  const h = { biggestUp: null, biggestDown: null, fastestPace: null, behindPace: [] };
  selected.forEach(t => {
    const ly = emailLastYear(t);
    if (ly && ly.count > 0 && t.point_estimate) {
      const pct = (t.point_estimate - ly.count) / ly.count;
      if (!h.biggestUp || pct > h.biggestUp.pct) h.biggestUp = { t, pct };
      if (!h.biggestDown || pct < h.biggestDown.pct) h.biggestDown = { t, pct };
    }
    const pa = getPaceAlert(t);
    if (pa) {
      if (pa.status === 'above_pace' && (!h.fastestPace || pa.deviation_pct > h.fastestPace.pct)) {
        h.fastestPace = { t, pct: pa.deviation_pct };
      }
      if (pa.status === 'below_pace') h.behindPace.push({ t, pct: pa.deviation_pct });
    }
  });
  return h;
}

function emailHighlightBullets(h) {
  const lines = [];
  if (h.biggestUp && h.biggestUp.pct > 0.05) {
    lines.push(`${h.biggestUp.t.family} is the biggest mover — projecting +${Math.round(h.biggestUp.pct * 100)}% vs last year.`);
  }
  if (h.biggestDown && h.biggestDown.pct < -0.05 && (!h.biggestUp || h.biggestDown.t.family !== h.biggestUp.t.family)) {
    lines.push(`${h.biggestDown.t.family} is tracking lowest — projecting ${Math.round(h.biggestDown.pct * 100)}% vs last year.`);
  }
  if (h.fastestPace) {
    lines.push(`${h.fastestPace.t.family} is running ${h.fastestPace.pct > 0 ? '+' : ''}${h.fastestPace.pct}% vs historical pace.`);
  }
  if (h.behindPace.length) {
    const names = h.behindPace.map(x => x.t.family).join(', ');
    lines.push(`Behind pace: ${names}.`);
  }
  return lines;
}

// ── Auto subject line ──
function emailAutoSubject(selected) {
  const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const n = selected.length;
  if (n === 0) return `CCA Entries Update — ${today}`;
  if (n === 1) return `CCA Entries Update — ${selected[0].family} (${today})`;
  return `CCA Entries Update — ${n} events (${today})`;
}

// ── HTML email formatter (email-client-safe: tables + inline styles, no flex/grid) ──
const EM = {
  bg: '#ffffff', text: '#1a1a1a', muted: '#6a6a6a',
  border: '#d9d9d9', accent: '#c99000',
  green: '#2ca444', red: '#c44646', blue: '#1a6fbc',
  surface: '#f9f7f0',
};

function emailHTMLTable(headers, rows) {
  const th = headers.map(h => `<th style="text-align:left;padding:6px 12px;border-bottom:1px solid ${EM.border};text-transform:uppercase;font-size:11px;letter-spacing:.05em;color:${EM.muted};font-weight:700">${esc(String(h))}</th>`).join('');
  const tr = rows.map(r => {
    const tds = r.map(c => `<td style="padding:6px 12px;border-bottom:1px solid ${EM.border};font-size:14px">${c === '' || c == null ? '&nbsp;' : esc(String(c))}</td>`).join('');
    return `<tr>${tds}</tr>`;
  }).join('');
  return `<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:8px 0 14px;font-family:Arial,Helvetica,sans-serif;border:1px solid ${EM.border}"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

function emailHTMLTournament(t, len) {
  const ly = emailLastYear(t);
  const avg = emailHistAvg(t);
  const pace = t.prior_year_pace;
  const sorted = t.historical ? [...t.historical].sort((a, b) => b.year - a.year) : [];
  const parts = [];
  const name = esc(t.family);
  const B = v => `<strong style="color:${EM.text}">${esc(String(v))}</strong>`;
  const colorFor = pct => pct > 0 ? EM.green : pct < 0 ? EM.red : EM.text;

  parts.push(`<h3 style="margin:22px 0 6px;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:${EM.text}">${name}</h3>`);
  parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">We are at ${B(t.current_count)} entries which projects to ${B(t.point_estimate)} with a range of ${B(t.ci_lower)}&ndash;${B(t.ci_upper)}.</p>`);

  if (ly) {
    const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
    let verdict;
    if (len === 'short') verdict = '';
    else if (pct > 15) verdict = ', so the projection has us well ahead.';
    else if (pct > 5) verdict = ', so we are tracking ahead.';
    else if (pct > -5) verdict = ', so we are in the same neighborhood.';
    else if (pct > -15) verdict = ', so we are still a bit behind.';
    else verdict = ', so we are lagging.';
    parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">Last year was ${B(ly.count)}${verdict}</p>`);
  }

  if (pace) {
    const d = t.current_count - pace.count_at_same_point;
    const col = d > 0 ? EM.green : d < 0 ? EM.red : EM.text;
    const suffix = d > 0 ? `, so we are <span style="color:${col};font-weight:600">ahead of pace</span>.`
                 : d < 0 ? `, so we are <span style="color:${col};font-weight:600">a bit behind</span>.`
                 : '.';
    parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">At this point last year we were at ${B(pace.count_at_same_point)} and finished at ${B(pace.final)}${suffix}</p>`);
  }

  if (len === 'long' && avg && sorted.length >= 3) {
    const pct = Math.round((t.point_estimate - avg) / avg * 100);
    if (pct < -10) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The historical average is ${B(avg)}, so we are still below the norm.</p>`);
    else if (pct > 10) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The historical average is ${B(avg)}, so we are trending above average.</p>`);
  }

  if (len === 'long' && sorted.length >= 3) {
    const counts = sorted.map(h => h.count);
    const worst = Math.min(...counts);
    const best = Math.max(...counts);
    const worstYr = sorted.find(h => h.count === worst).year;
    const bestYr = sorted.find(h => h.count === best).year;
    if (t.point_estimate < worst) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The last time we were this low was ${worstYr} when we got ${B(worst)}.</p>`);
    else if (t.point_estimate > best) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">If we hit the projection, it would be the best year since at least ${bestYr} (${B(best)}).</p>`);
  }

  if (len !== 'short' && sorted.length >= 2) {
    const hdrs = len === 'long' ? ['Year', 'Entries', 'Projection', 'Range', 'Final'] : ['Year', 'Entries', 'Projection', 'Final'];
    const rows = [];
    if (len === 'long') {
      rows.push([2026, t.current_count, t.point_estimate, `${t.ci_lower}\u2013${t.ci_upper}`, '']);
      sorted.forEach(h => rows.push([h.year, '', '', '', h.count]));
    } else {
      rows.push([2026, t.current_count, t.point_estimate, '']);
      sorted.forEach(h => rows.push([h.year, '', '', h.count]));
    }
    parts.push(emailHTMLTable(hdrs, rows));
  }

  return parts.join('\n');
}

function emailBuildHTML(subject, intro, selected, len, highlights) {
  const theme = selected.length > 1 ? emailOverallTheme(selected) : '';
  const bullets = emailHighlightBullets(highlights);
  const greeting = intro && intro.trim() ? esc(intro.trim()) : 'Team,';

  const highlightBlock = bullets.length
    ? `<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;background:${EM.surface};border-left:4px solid ${EM.accent};margin:14px 0;width:100%"><tr><td style="padding:12px 16px;font-family:Arial,Helvetica,sans-serif">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:${EM.muted};font-weight:700;margin-bottom:6px">Highlights</div>
        ${bullets.map(b => `<div style="font-size:14px;line-height:1.5;color:${EM.text};margin:2px 0">&bull; ${esc(b)}</div>`).join('')}
      </td></tr></table>`
    : '';

  const themeBlock = (len !== 'short' && theme)
    ? `<p style="margin:10px 0;font-size:14px;line-height:1.55;color:${EM.text}">${esc(theme)}</p>`
    : '';

  const body = selected.map(t => emailHTMLTournament(t, len)).join('\n');

  return `<div style="font-family:Arial,Helvetica,sans-serif;color:${EM.text};background:${EM.bg};padding:16px 18px;max-width:720px;margin:0 auto">
  <p style="margin:0 0 10px;font-size:14px;color:${EM.text}">${greeting}</p>
  ${highlightBlock}
  ${themeBlock}
  ${body}
  <p style="margin:20px 0 0;font-size:14px;color:${EM.text}">Dave</p>
</div>`;
}

function generateEmail() {
  const selected = emailGetSelected();
  const out = document.getElementById('emailOutput');
  const pv = document.getElementById('emailPreview');
  const subjField = document.getElementById('emailSubject');
  const introField = document.getElementById('emailIntro');

  if (!selected.length) { out.textContent = 'No tournaments selected.'; if (pv) { pv.srcdoc = ''; } return; }

  // Auto-fill subject placeholder so user sees what it'll default to if empty
  if (subjField) subjField.placeholder = emailAutoSubject(selected);

  const len = emailLength;
  const highlights = emailComputeHighlights(selected);

  if (emailFormat === 'html') {
    const subject = (subjField && subjField.value) || emailAutoSubject(selected);
    const intro = introField ? introField.value : '';
    const html = emailBuildHTML(subject, intro, selected, len, highlights);
    out.textContent = html;
    if (pv) pv.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(subject)}</title></head><body style="margin:0;background:#f1f1f1">${html}</body></html>`;
  } else {
    // Plain text (original behavior + optional intro + highlight lines)
    const sections = [];
    const intro = introField && introField.value.trim() ? introField.value.trim() : 'Team';
    sections.push(intro + (intro.endsWith(',') ? '' : ''));

    const bullets = emailHighlightBullets(highlights);
    if (bullets.length && len !== 'short') {
      sections.push('HIGHLIGHTS\n' + bullets.map(b => `  \u2022 ${b}`).join('\n'));
    }

    if (len !== 'short' && selected.length > 1) {
      sections.push(emailOverallTheme(selected));
    }
    selected.forEach(t => { sections.push(emailFormatTournament(t, len)); });
    sections.push('Dave');
    out.textContent = sections.join('\n\n');
  }

  const btn = document.getElementById('emailCopyBtn');
  btn.textContent = 'Copy';
  btn.classList.remove('copied');
}

function _emailCopyFeedback(btn, label = 'Copy') {
  const orig = label;
  btn.textContent = 'Copied!';
  btn.classList.add('copied');
  setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
}

function copyEmail() {
  const text = document.getElementById('emailOutput').textContent;
  if (!text) return;
  const btn = document.getElementById('emailCopyBtn');
  navigator.clipboard.writeText(text).then(() => _emailCopyFeedback(btn, 'Copy'));
}

function copyEmailHTML() {
  // Copy the rendered HTML as rich text (text/html) so pasting into Outlook keeps formatting
  const html = document.getElementById('emailOutput').textContent;
  if (!html) return;
  const btn = document.getElementById('emailCopyHtmlBtn');
  const plain = document.getElementById('emailPreview')?.contentDocument?.body?.innerText || html.replace(/<[^>]+>/g, '');
  if (window.ClipboardItem && navigator.clipboard.write) {
    const item = new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }),
      'text/plain': new Blob([plain], { type: 'text/plain' }),
    });
    navigator.clipboard.write([item]).then(() => _emailCopyFeedback(btn, 'Copy HTML'));
  } else {
    navigator.clipboard.writeText(html).then(() => _emailCopyFeedback(btn, 'Copy HTML'));
  }
}

// ══════════════════════════════════════════════════════════
// MODEL PERFORMANCE TAB
// ══════════════════════════════════════════════════════════
let perfInited = false;
let perfSelectedKey = null;

function initPerformanceTab() {
  if (perfInited) return;
  perfInited = true;

  const data = typeof PERFORMANCE_DATA !== 'undefined' ? PERFORMANCE_DATA : {};
  const hasYears = data.years && Object.values(data.years).some(y => y && y.n_tournaments > 0);
  const hasCumulative = data.cumulative && data.cumulative.n_tournaments > 0;
  const hasFlat = data.aggregate && data.aggregate.length > 0;

  if (!hasYears && !hasCumulative && !hasFlat) {
    document.getElementById('perfGradeLetter').textContent = '--';
    document.getElementById('perfGradeLabel').textContent = 'NO DATA';
    document.getElementById('perfGradeDetail').textContent = 'Performance data will appear once tournaments complete.';
    return;
  }

  const selector = document.getElementById('perfYearSelector');
  if (selector && (hasYears || hasCumulative)) {
    const buttons = [];
    const nowYear = new Date().getFullYear();
    const years = data.years
      ? Object.keys(data.years).map(Number).filter(y => data.years[y] && data.years[y].n_tournaments > 0).sort()
      : [];
    years.forEach(y => buttons.push({key: String(y), label: y === nowYear ? `${y} YTD` : String(y)}));
    if (hasCumulative) buttons.push({key: 'cumulative', label: 'Cumulative'});

    selector.innerHTML = '<span style="font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-right:6px">View:</span>' +
      buttons.map(b => `<button onclick="perfSelectYear('${b.key}')" id="perfYearBtn_${b.key}" style="padding:6px 14px;border-radius:8px;font-size:.76rem;font-weight:600;border:1px solid var(--border);background:var(--surface2);color:var(--text);cursor:pointer;transition:all .15s">${b.label}</button>`).join('');

    const defaultKey = years.includes(nowYear) ? String(nowYear) : (years.length ? String(years[years.length - 1]) : 'cumulative');
    perfSelectYear(defaultKey);
  } else {
    if (selector) selector.style.display = 'none';
    perfRenderFlat(data);
  }
}

function perfSelectYear(key) {
  perfSelectedKey = key;
  document.querySelectorAll('[id^="perfYearBtn_"]').forEach(btn => {
    const isActive = btn.id === 'perfYearBtn_' + key;
    btn.style.background = isActive ? 'var(--gold)' : 'var(--surface2)';
    btn.style.color = isActive ? '#0d1117' : 'var(--text)';
    btn.style.borderColor = isActive ? 'var(--gold)' : 'var(--border)';
  });
  perfRender();
}

function perfRender() {
  const data = PERFORMANCE_DATA;
  const key = perfSelectedKey;
  const baseData = key === 'cumulative' ? data.cumulative : (data.years && data.years[key]);
  if (!baseData) return perfRenderFlat(data);

  const nowYear = new Date().getFullYear();
  const isYTD = key === String(nowYear);
  const desc = key === 'cumulative'
    ? `Blind-tested across ${baseData.n_tournaments} tournaments (all years)`
    : `Blind-tested on ${baseData.n_tournaments} ${key} tournaments${isYTD ? ' (YTD)' : ''}`;

  perfPaint({
    aggregate: baseData.aggregate,
    tournaments: baseData.tournaments || [],
    grade: baseData.grade,
    n_tournaments: baseData.n_tournaments,
    detail: desc,
    generated: data.generated,
  });
}

function perfRenderFlat(data) {
  perfPaint({
    aggregate: data.aggregate || [],
    tournaments: data.tournaments || [],
    grade: data.grade,
    n_tournaments: data.n_tournaments,
    detail: data.grade_detail || `Blind-tested on ${data.n_tournaments} completed tournaments`,
    generated: data.generated,
  });
}

function perfPaint(view) {
  const agg = view.aggregate || [];
  const gc = {'A+':'#22c55e','A':'#22c55e','A-':'#4ade80','B+':'#86efac','B':'var(--gold)','B-':'var(--gold)','C+':'#fb923c','C':'#f97316','C-':'#ea580c','D':'#ef4444','F':'#dc2626'};
  document.getElementById('perfGradeLetter').textContent = view.grade || '--';
  document.getElementById('perfGradeLetter').style.color = gc[view.grade] || 'var(--muted)';
  document.getElementById('perfGradeLabel').textContent = 'MODEL GRADE';
  document.getElementById('perfGradeDetail').textContent = view.detail;
  document.getElementById('perfGradeMeta').textContent = `N5v4_Final Ensemble \u00b7 Rolling retrain + auto-recalibration \u00b7 Updated ${view.generated || ''}`;

  if (!agg.length) {
    document.getElementById('perfKPIs').innerHTML = '';
    document.getElementById('perfHorizonStrip').innerHTML = '';
    document.getElementById('perfTable').innerHTML = '<div style="color:var(--muted);padding:12px 0;font-size:.78rem">No completed tournaments for this selection.</div>';
    return;
  }

  const t14 = agg.find(a => a.T === 14) || agg[0];
  const t1 = agg.find(a => a.T === 1);
  const avgCov = Math.round(agg.reduce((s, a) => s + a.ci_coverage, 0) / agg.length);
  const avgBias = +(agg.reduce((s, a) => s + a.bias_pct, 0) / agg.length).toFixed(1);

  const kpis = [
    {v: t14.mae_pct.toFixed(1) + '%', l: '2-Week Error', s: 'MAE at T-14', c: t14.mae_pct <= 8 ? '#22c55e' : t14.mae_pct <= 15 ? 'var(--gold)' : '#ef4444'},
    {v: t1 ? t1.mae_pct.toFixed(1) + '%' : '--', l: 'Day-Before', s: 'MAE at T-1', c: t1 && t1.mae_pct <= 5 ? '#22c55e' : '#4ade80'},
    {v: avgCov + '%', l: 'CI Coverage', s: 'Target 80%', c: avgCov >= 75 ? '#22c55e' : avgCov >= 60 ? 'var(--gold)' : '#ef4444'},
    {v: (avgBias > 0 ? '+' : '') + avgBias + '%', l: 'Bias', s: avgBias > 2 ? 'Over-predicts' : avgBias < -2 ? 'Under-predicts' : 'Well-centered', c: Math.abs(avgBias) <= 5 ? '#22c55e' : 'var(--gold)'},
  ];
  document.getElementById('perfKPIs').innerHTML = kpis.map(k => `
    <div style="padding:12px 14px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;text-align:center">
      <div style="font-size:1.4rem;font-weight:800;color:${k.c};line-height:1;font-variant-numeric:tabular-nums">${k.v}</div>
      <div style="font-size:.65rem;font-weight:600;color:var(--text);margin-top:5px;letter-spacing:.03em">${k.l}</div>
      <div style="font-size:.58rem;color:var(--muted);margin-top:1px">${k.s}</div>
    </div>`).join('');

  requestAnimationFrame(() => {
    perfDrawScatter(view);
    perfDrawTimeline(view);
  });

  const strip = document.getElementById('perfHorizonStrip');
  strip.innerHTML = agg.map(a => {
    const bg = a.mae_pct <= 8 ? 'rgba(34,197,94,.12)' : a.mae_pct <= 12 ? 'rgba(240,192,64,.10)' : 'rgba(239,68,68,.10)';
    const bc = a.mae_pct <= 8 ? 'rgba(34,197,94,.25)' : a.mae_pct <= 12 ? 'rgba(240,192,64,.2)' : 'rgba(239,68,68,.2)';
    const tc = a.mae_pct <= 8 ? '#22c55e' : a.mae_pct <= 12 ? 'var(--gold)' : '#ef4444';
    return `<div style="flex:1;min-width:80px;padding:10px 8px;background:${bg};border:1px solid ${bc};border-radius:10px;text-align:center" title="n=${a.n}, bias ${a.bias_pct > 0 ? '+' : ''}${a.bias_pct}%">
      <div style="font-size:.6rem;font-weight:700;letter-spacing:.06em;color:var(--muted);text-transform:uppercase">T-${a.T}</div>
      <div style="font-size:1.1rem;font-weight:800;color:${tc};margin:3px 0 2px">${a.mae_pct.toFixed(1)}%</div>
      <div style="font-size:.55rem;color:var(--muted)">CI ${a.ci_coverage}%</div>
    </div>`;
  }).join('');

  perfDrawTable(view);
}

function perfDrawScatter(data) {
  const canvas = document.getElementById('perfScatterCanvas');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth; const H = canvas.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const isM = _mobileVP();
  const pad = {t:8, r:12, b:28, l: isM ? 36 : 44};
  const tickFont = isM ? '10px system-ui' : '9px system-ui';
  const noteFont = isM ? '9px system-ui' : '8px system-ui';
  const axisFont = isM ? '10px system-ui' : '9px system-ui';
  const pw = W - pad.l - pad.r; const ph = H - pad.t - pad.b;

  const pts = [];
  data.tournaments.forEach(t => {
    const p = t.predictions.find(p => p.T === 14) || t.predictions.find(p => p.T === 28) || t.predictions[0];
    if (p) pts.push({f: t.family, a: t.final_count, p: p.predicted, lo: p.ci_lower, hi: p.ci_upper, ok: p.in_ci});
  });
  if (!pts.length) return;

  const maxV = Math.max(...pts.map(p => Math.max(p.a, p.p, p.hi))) * 1.12;
  const x = v => pad.l + (v / maxV) * pw;
  const y = v => pad.t + ph - (v / maxV) * ph;

  // Grid
  ctx.strokeStyle = '#30363d'; ctx.lineWidth = 0.5; ctx.setLineDash([3, 3]);
  for (let i = 1; i <= 4; i++) {
    const v = Math.round(maxV / 4 * i);
    ctx.beginPath(); ctx.moveTo(pad.l, y(v)); ctx.lineTo(pad.l + pw, y(v)); ctx.stroke();
    ctx.fillStyle = '#8b949e'; ctx.font = tickFont; ctx.textAlign = 'right';
    ctx.fillText(v.toLocaleString(), pad.l - 5, y(v) + 3);
  }
  ctx.setLineDash([]);

  // Perfect line
  ctx.strokeStyle = 'rgba(240,192,64,.2)'; ctx.lineWidth = 1.5;
  ctx.setLineDash([8, 5]);
  ctx.beginPath(); ctx.moveTo(pad.l, pad.t + ph); ctx.lineTo(pad.l + pw, pad.t); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = 'rgba(240,192,64,.35)'; ctx.font = noteFont; ctx.textAlign = 'right';
  ctx.fillText('Perfect prediction', pad.l + pw - 2, pad.t + 10);

  // CI whiskers + dots
  pts.forEach(p => {
    const px = x(p.a); const py = y(p.p);
    const col = p.ok ? '#22c55e' : '#ef4444';
    // Whisker
    ctx.strokeStyle = col; ctx.globalAlpha = 0.25; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(px, y(p.lo)); ctx.lineTo(px, y(p.hi)); ctx.stroke();
    ctx.globalAlpha = 1;
    // Dot with glow
    ctx.shadowColor = col; ctx.shadowBlur = 8;
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(px, py, 4.5, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    // Outline
    ctx.strokeStyle = '#0d1117'; ctx.lineWidth = 1.2; ctx.stroke();
  });

  // Axis labels
  ctx.fillStyle = '#8b949e'; ctx.font = axisFont; ctx.textAlign = 'center';
  ctx.fillText('Actual Entries', pad.l + pw / 2, H - 6);
  ctx.save(); ctx.translate(10, pad.t + ph / 2); ctx.rotate(-Math.PI / 2);
  ctx.fillText('Predicted', 0, 0); ctx.restore();
}

function perfDrawTimeline(data) {
  const canvas = document.getElementById('perfTimelineCanvas');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth; const H = canvas.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const isM = _mobileVP();
  const pad = {t:20, r:14, b:28, l: isM ? 30 : 36};
  const tickFont = isM ? '9px system-ui' : '8px system-ui';
  const valFont = isM ? 'bold 10px system-ui' : 'bold 9px system-ui';
  const tFont = isM ? '10px system-ui' : '9px system-ui';
  const axisFont = isM ? '10px system-ui' : '9px system-ui';
  const pw = W - pad.l - pad.r; const ph = H - pad.t - pad.b;
  const agg = [...data.aggregate].sort((a, b) => b.T - a.T);
  if (!agg.length) return;

  const maxMAE = Math.max(15, ...agg.map(a => a.mae_pct)) * 1.2;
  const xp = i => pad.l + (i / Math.max(agg.length - 1, 1)) * pw;
  const yp = v => pad.t + ph - (v / maxMAE) * ph;

  // Good zone
  const gy = yp(10);
  ctx.fillStyle = 'rgba(34,197,94,.05)';
  ctx.fillRect(pad.l, gy, pw, pad.t + ph - gy);

  // Grid
  ctx.strokeStyle = '#30363d'; ctx.lineWidth = 0.5; ctx.setLineDash([3, 3]);
  [5, 10, 15].filter(v => v < maxMAE).forEach(v => {
    ctx.beginPath(); ctx.moveTo(pad.l, yp(v)); ctx.lineTo(pad.l + pw, yp(v)); ctx.stroke();
    ctx.fillStyle = '#8b949e'; ctx.font = tickFont; ctx.textAlign = 'right';
    ctx.fillText(v + '%', pad.l - 4, yp(v) + 3);
  });
  ctx.setLineDash([]);

  // Area fill
  ctx.beginPath(); ctx.moveTo(xp(0), pad.t + ph);
  agg.forEach((a, i) => ctx.lineTo(xp(i), yp(a.mae_pct)));
  ctx.lineTo(xp(agg.length - 1), pad.t + ph); ctx.closePath();
  const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ph);
  grad.addColorStop(0, 'rgba(240,192,64,.18)'); grad.addColorStop(1, 'rgba(240,192,64,.02)');
  ctx.fillStyle = grad; ctx.fill();

  // Line
  ctx.beginPath();
  agg.forEach((a, i) => { i === 0 ? ctx.moveTo(xp(i), yp(a.mae_pct)) : ctx.lineTo(xp(i), yp(a.mae_pct)); });
  ctx.strokeStyle = 'var(--gold)'; ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.stroke();

  // Dots + labels
  agg.forEach((a, i) => {
    const cx = xp(i); const cy = yp(a.mae_pct);
    const c = a.mae_pct <= 8 ? '#22c55e' : a.mae_pct <= 12 ? '#4ade80' : '#f0c040';
    ctx.shadowColor = c; ctx.shadowBlur = 6;
    ctx.fillStyle = c; ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = '#161b22'; ctx.lineWidth = 1.5; ctx.stroke();
    // Value
    ctx.fillStyle = '#e6edf3'; ctx.font = valFont; ctx.textAlign = 'center';
    ctx.fillText(a.mae_pct.toFixed(1) + '%', cx, cy - 10);
    // T label
    ctx.fillStyle = '#8b949e'; ctx.font = tFont;
    ctx.fillText('T-' + a.T, cx, pad.t + ph + 14);
  });

  // Axis
  ctx.fillStyle = '#8b949e'; ctx.font = axisFont; ctx.textAlign = 'center';
  ctx.fillText('Days Before Event', pad.l + pw / 2, H - 5);
}

function perfDrawTable(data) {
  const table = document.getElementById('perfTable');
  const agg = data.aggregate;
  const tPoints = agg.map(a => a.T);

  let html = `<table style="width:100%;border-collapse:collapse;font-size:.76rem">
    <thead><tr style="border-bottom:2px solid var(--border)">
      <th style="padding:8px 10px;text-align:left;white-space:nowrap">Tournament</th>
      <th style="padding:8px 8px;text-align:right;white-space:nowrap">Final</th>`;
  tPoints.forEach(T => { html += `<th style="padding:8px 4px;text-align:center;font-size:.68rem;white-space:nowrap">T-${T}</th>`; });
  html += `</tr></thead><tbody>`;

  data.tournaments.forEach((t, idx) => {
    const bg = idx % 2 ? 'background:var(--surface2)' : '';
    html += `<tr style="border-bottom:1px solid rgba(48,54,61,.4);${bg}">
      <td data-label="Tournament" style="padding:5px 10px;white-space:nowrap;font-weight:500">${esc(t.family)}</td>
      <td data-label="Final" style="padding:5px 8px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums">${t.final_count.toLocaleString()}</td>`;
    tPoints.forEach(T => {
      const p = t.predictions.find(p => p.T === T);
      if (p) {
        const ec = Math.abs(p.error_pct) <= 5 ? '#22c55e' : Math.abs(p.error_pct) <= 15 ? 'var(--gold)' : '#ef4444';
        const ci = p.in_ci ? '\u2713' : '\u2717';
        const cic = p.in_ci ? '#22c55e' : '#ef4444';
        html += `<td data-label="T-${T}" style="padding:5px 4px;text-align:center;font-size:.7rem" title="Pred ${p.predicted} from ${p.count_at_T} reg, CI [${p.ci_lower}-${p.ci_upper}]">
          <span style="color:${ec};font-weight:600;font-variant-numeric:tabular-nums">${p.error_pct > 0 ? '+' : ''}${p.error_pct}%</span><span style="color:${cic};font-size:.58rem;margin-left:2px">${ci}</span></td>`;
      } else {
        html += `<td data-label="T-${T}" style="padding:5px 4px;text-align:center;color:var(--muted)">\u2014</td>`;
      }
    });
    html += '</tr>';
  });

  // Aggregate
  html += `<tr style="border-top:2px solid var(--border);font-weight:700;background:rgba(240,192,64,.04)">
    <td data-label="Average" style="padding:8px 10px" colspan="2">Average (${data.n_tournaments})</td>`;
  tPoints.forEach(T => {
    const a = agg.find(x => x.T === T);
    if (a) {
      html += `<td data-label="T-${T}" style="padding:8px 4px;text-align:center;font-size:.68rem">
        <div style="color:var(--text)">${a.mae_pct}%</div>
        <div style="font-size:.56rem;color:var(--muted);font-weight:400">CI ${a.ci_coverage}%</div></td>`;
    } else html += `<td data-label="T-${T}">\u2014</td>`;
  });
  html += '</tr></tbody></table>';
  table.innerHTML = html;
}

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
      html += `<div class="${cls}" data-r="${r}" data-c="${c}" data-ri="${ri}" data-ci="${ci}" tabindex="0" role="gridcell" aria-label="${ariaLabel}" onclick="puzzleSquareClick(${r},${c})" onkeydown="puzzleBoardKeydown(event,${r},${c},${ri},${ci})">${pieceHtml}</div>`;
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
  puzzleStatus('&#10007; Incorrect — try again or click Retry', 'var(--red)');
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
  document.getElementById('puzzleTurn').textContent = ps.turn === 'w' ? 'White' : 'Black';
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
    return `<div class="${cls}" onclick="loadPuzzle(${i})" style="cursor:pointer" title="Puzzle ${i+1}"></div>`;
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

// ══════════════════════════════════════════════════════════
// SPLASH
// ══════════════════════════════════════════════════════════
function dismissSplash() {
  document.getElementById('splash').classList.add('hidden');
  setTimeout(() => document.getElementById('mainContent').classList.add('visible'), 100);
  // Always land at the top of the dashboard, regardless of browser scroll-restoration.
  window.scrollTo(0, 0);
}

function showSplash() {
  document.getElementById('mainContent').classList.remove('visible');
  document.getElementById('splash').classList.remove('hidden');
}

function initSplash() {
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.filter(t => t.status === 'live').length;
  const years = new Set(ts.map(t => t.year));
  const yearSpan = Math.max(...years) - Math.min(...years) + 1;
  document.getElementById('ss-live').textContent = live;
  document.getElementById('ss-total').textContent = ts.length;
  document.getElementById('ss-years').textContent = yearSpan;
  document.getElementById('splashScrapeDate').textContent = 'Last scrape: ' + fmtDateTimeLong(TOURNAMENT_DATA.generated_time || TOURNAMENT_DATA.generated);

  // Auto-animate numbers
  animateNum('ss-live', 0, live, 800);
  animateNum('ss-total', 0, ts.length, 1000);
  animateNum('ss-years', 0, yearSpan, 700);
  initChessboard();
}

// Chessboard canvas + knight animation
function initChessboard() {
  const splash = document.getElementById('splash');
  const canvas = document.getElementById('splashCanvas');
  if (!canvas || !splash) return;

  let _sq = 60, _ox = 0, _oy = 0, _cols = 16, _rows = 12;

  function drawBoard() {
    const W = canvas.width  = canvas.offsetWidth  || window.innerWidth;
    const H = canvas.height = canvas.offsetHeight || window.innerHeight;
    const ctx = canvas.getContext('2d');
    _sq   = Math.max(40, Math.round(Math.min(W, H) / 16));
    _cols = Math.ceil(W / _sq) + 1;
    _rows = Math.ceil(H / _sq) + 1;
    _ox   = ((W % _sq) / 2) | 0;
    _oy   = ((H % _sq) / 2) | 0;
    ctx.clearRect(0, 0, W, H);
    for (let r = 0; r < _rows; r++) {
      for (let c = 0; c < _cols; c++) {
        const light = (r + c) % 2 === 0;
        ctx.fillStyle = light ? 'rgba(240,192,64,.55)' : 'rgba(56,100,180,.18)';
        ctx.fillRect(_ox + c * _sq, _oy + r * _sq, _sq, _sq);
      }
    }
    const grad = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W, H) * .75);
    grad.addColorStop(0,   'rgba(5,8,16,0)');
    grad.addColorStop(.55, 'rgba(5,8,16,.6)');
    grad.addColorStop(1,   'rgba(5,8,16,1)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
  }
  drawBoard();
  let resizeRaf;
  window.addEventListener('resize', () => { cancelAnimationFrame(resizeRaf); resizeRaf = requestAnimationFrame(drawBoard); });

  // Knight that hops across the board
  const knight = document.createElement('div');
  knight.id = 'splash-knight-orbit';
  knight.textContent = '\u265E';
  splash.appendChild(knight);

  let kCol = Math.round(_cols / 2);
  let kRow = Math.round(_rows / 2);
  let kTimer = null;

  const KNIGHT_OFFSETS = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]];

  function knightNextSquare() {
    const cx = _cols / 2, cy = _rows / 2;
    const moves = KNIGHT_OFFSETS
      .map(([dc, dr]) => ({ col: kCol + dc, row: kRow + dr }))
      .filter(({ col, row }) => col >= 1 && col < _cols - 1 && row >= 1 && row < _rows - 1);
    if (!moves.length) { kCol = Math.round(_cols/2); kRow = Math.round(_rows/2); return; }
    const weights = moves.map(({ col, row }) => {
      const d = Math.hypot(col - cx, row - cy);
      return Math.max(0.1, 1 / (1 + d * 0.35));
    });
    const total = weights.reduce((a, b) => a + b, 0);
    let rand = Math.random() * total;
    for (let i = 0; i < moves.length; i++) {
      rand -= weights[i];
      if (rand <= 0) { kCol = moves[i].col; kRow = moves[i].row; return; }
    }
    const m = moves[moves.length - 1]; kCol = m.col; kRow = m.row;
  }

  function squarePx(col, row) {
    return { x: _ox + col * _sq + _sq / 2, y: _oy + row * _sq + _sq / 2 };
  }

  function hopKnight() {
    knightNextSquare();
    const pos = squarePx(kCol, kRow);
    knight.style.transition = 'opacity .18s, transform .18s';
    knight.style.opacity = '0.05';
    knight.style.transform = 'translate(-50%,-50%) scale(0.45)';
    setTimeout(() => {
      knight.style.transition = 'none';
      knight.style.left = pos.x + 'px';
      knight.style.top  = pos.y + 'px';
      knight.style.fontSize = Math.round(_sq * 0.72) + 'px';
      requestAnimationFrame(() => requestAnimationFrame(() => {
        knight.style.transition = 'opacity .26s, transform .26s cubic-bezier(.34,1.56,.64,1)';
        knight.style.opacity = '1';
        knight.style.transform = 'translate(-50%,-50%) scale(1)';
      }));
    }, 200);
  }

  // Place at initial square
  const p0 = squarePx(kCol, kRow);
  knight.style.left = p0.x + 'px';
  knight.style.top  = p0.y + 'px';
  knight.style.fontSize = Math.round(_sq * 0.72) + 'px';

  setTimeout(() => {
    if (!document.getElementById('splash')) return;
    knight.style.opacity = '1';
    knight.style.transform = 'translate(-50%,-50%) scale(1)';
    kTimer = setInterval(() => {
      const s = document.getElementById('splash');
      if (!s || s.classList.contains('hidden')) { clearInterval(kTimer); return; }
      hopKnight();
    }, 850);
  }, 400);
}

function animateNum(id, from, to, duration) {
  const el = document.getElementById(id);
  const start = performance.now();
  function tick(now) {
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (to - from) * ease);
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// (Header dropdown removed — using tab bar dropdowns instead)

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
      html: `<div style="height:${_vs.HDR_H}px;padding:5px 14px 3px;font-size:.62rem;color:var(--muted);text-transform:uppercase;letter-spacing:1.2px;font-weight:700;background:var(--surface2);border-bottom:1px solid var(--border-light);box-sizing:border-box;display:flex;align-items:center">${esc(fam)} <span style="font-weight:400;opacity:.7;margin-left:4px">(${editions.length})</span></div>`
    });
    editions.forEach(({t, i}) => {
      flat.push({
        type: 'item', h: _vs.ITEM_H, idx: i,
        html: `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" style="height:${_vs.ITEM_H}px;box-sizing:border-box" onclick="selectFromDrop(${i})" onkeydown="if(event.key==='Enter')selectFromDrop(${i})" tabindex="0" role="option"><span class="cat-item-name" style="padding-left:6px">${t.year}</span><span class="cat-item-meta">${fmt(t.current_count)} entries</span></div>`
      });
    });
  });

  // Footer summary
  const footerText = filtered.length === 0
    ? 'No matches'
    : `${filtered.length} editions across ${families.length} families`;
  flat.push({
    type: 'footer', h: _vs.FOOTER_H,
    html: `<div style="height:${_vs.FOOTER_H}px;padding:6px 14px;font-size:.68rem;color:var(--muted);border-top:1px solid var(--border-light);display:flex;align-items:center;box-sizing:border-box">${footerText}</div>`
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
    `<button class="seg-btn ${_tourneyTab === k ? 'active' : ''}" role="tab" aria-selected="${_tourneyTab === k}" data-seg="${k}" onclick="event.stopPropagation();setTourneyTab('${k}')">${label}<span class="seg-count">${count}</span></button>`;

  let html = '';
  html += '<div class="tourney-picker-header">';
  html += `<div class="seg-control" role="tablist" aria-label="Tournament category">${seg('live', 'Upcoming', live.length)}${seg('complete', 'Complete', complete.length)}${seg('hist', 'Historical', hist.length)}</div>`;
  html += '</div>';

  html += '<div class="tourney-picker-body">';
  if (_tourneyTab === 'live') {
    html += '<div class="tourney-list">';
    live.forEach(({t, i}) => {
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" onclick="selectFromTourneyPicker(${i})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectFromTourneyPicker(${i})}" tabindex="0" role="option">`;
      html += `<span class="cat-item-name"><span class="live-dot"></span>${esc(t.family)}</span>`;
      html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg · ${t.days_remaining}d</span>`;
      html += '</div>';
    });
    html += '</div>';
  } else if (_tourneyTab === 'complete') {
    html += '<div class="tourney-list">';
    complete.forEach(({t, i}) => {
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" onclick="selectFromTourneyPicker(${i})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectFromTourneyPicker(${i})}" tabindex="0" role="option">`;
      html += `<span class="cat-item-name">${esc(t.family)}</span>`;
      html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)}</span>`;
      html += '</div>';
    });
    html += '</div>';
  } else if (_tourneyTab === 'hist') {
    html += '<div class="tab-search-bar">';
    html += '<span style="opacity:.5">&#128269;</span>';
    html += '<input class="tab-search-input" id="tourneyHistSearch" type="text" placeholder="Search tournaments..." oninput="filterTourneyHistResults(this.value)" autocomplete="off">';
    html += '</div>';
    html += '<div class="tourney-list" id="tourneyHistList">';
    hist.forEach(({t, i}) => {
      const dataName = String(t.family || '').toLowerCase();
      html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" data-name="${esc(dataName)}" onclick="selectFromTourneyPicker(${i})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();selectFromTourneyPicker(${i})}" tabindex="0" role="option">`;
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
  const focusables = menu.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), [tabindex="0"]'
  );
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
  html += `<div class="cat-btn cat-btn--live" id="dropBtn_live" onclick="toggleDrop('live',event)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleDrop('live',event)}" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `<span class="live-dot"></span>Upcoming <span class="cat-count" style="background:var(--green-dim);color:var(--green)">${live.length}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu" id="dropMenu_live" role="listbox" aria-label="Upcoming tournaments">`;
  live.sort((a, b) => a.t.days_remaining - b.t.days_remaining).forEach(({t, i}) => {
    html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" onclick="selectFromDrop(${i})" onkeydown="if(event.key==='Enter')selectFromDrop(${i})" tabindex="0" role="option">`;
    html += `<span class="cat-item-name"><span class="live-dot"></span>${esc(t.family)}${paceBadgeHTML(getPaceAlert(t))}</span>`;
    html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)} reg</span></div>`;
  });
  html += `</div></div>`;

  // ── Complete dropdown ──
  html += `<div class="drop-wrap">`;
  html += `<div class="cat-btn cat-btn--complete" id="dropBtn_complete" onclick="toggleDrop('complete',event)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleDrop('complete',event)}" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `Complete <span class="cat-count">${complete.length}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu" id="dropMenu_complete" role="listbox" aria-label="Completed tournaments">`;
  complete.forEach(({t, i}) => {
    html += `<div class="cat-item ${i === selectedIndex ? 'active' : ''}" onclick="selectFromDrop(${i})" onkeydown="if(event.key==='Enter')selectFromDrop(${i})" tabindex="0" role="option">`;
    html += `<span class="cat-item-name">${esc(t.family)}</span>`;
    html += `<span class="cat-item-meta">${fmtDate(t.event_start)} · ${fmt(t.current_count)}</span></div>`;
  });
  html += `</div></div>`;

  // ── Historical search dropdown ──
  html += `<div class="drop-wrap">`;
  html += `<div class="cat-btn cat-btn--hist" id="dropBtn_hist" onclick="toggleDrop('hist',event)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleDrop('hist',event)}" tabindex="0" role="button" aria-expanded="false" aria-haspopup="true">`;
  html += `<span style="opacity:.6">&#128269;</span> Historical <span class="cat-count" style="background:var(--purple-dim);color:var(--purple)">${nHist}</span> <span class="cat-arrow">&#9662;</span></div>`;
  html += `<div class="drop-menu drop-menu-search" id="dropMenu_hist" role="listbox" aria-label="Historical tournaments">`;
  html += `<div class="tab-search-bar">`;
  html += `<span style="opacity:.5">&#128269;</span>`;
  html += `<input class="tab-search-input" id="histSearchInput" type="text" placeholder="Search tournaments..." oninput="filterHistResults(this.value)" autocomplete="off">`;
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

  // Multi-year at-T context (alerts.py output). Stripped from a separate
  // banner; lives here as a sub-line. Empty for tournaments without a
  // pace_alert (insufficient historical daily data).
  if (ctx) {
    const alert = getPaceAlert(t);
    ctx.textContent = (alert && alert.message) ? alert.message : '';
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
        main.textContent = `${t.family} ${t.year} — Above Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% above historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `+${absDiff}%`;
        val.className = 'delta-value green';
      } else if (diff < -5) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `${t.family} ${t.year} — Below Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% below historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `-${absDiff}%`;
        val.className = 'delta-value red';
      } else {
        banner.className = 'delta-banner gold';
        icon.innerHTML = '&#9654;';
        main.textContent = `${t.family} ${t.year} — On Par`;
        sub.textContent = `${fmt(t.current_count)} entries · In line with historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`;
        val.className = 'delta-value gold';
      }
    } else {
      banner.className = 'delta-banner muted';
      icon.innerHTML = '&#10003;';
      main.textContent = `${t.family} ${t.year} — Complete`;
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
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at this point in ${lastYrLabel}${paceSuffix}`;
        val.textContent = `+${absPct}%`;
        val.className = 'delta-value green';
      } else if (diff < 0) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `Tracking behind ${lastYrLabel} pace`;
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at this point in ${lastYrLabel}${paceSuffix}`;
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
  main.textContent = `${t.family} — Registration in progress`;
  sub.textContent = `${fmt(t.current_count)} entries registered · ${t.days_remaining} days until event · predicted final: ${fmt(t.point_estimate)}`;
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
  return `Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted. ${yr} backtest (${nEvents} events, asof ${asof}) shows the model has been ${dir} by ${absBias}% on avg — kept conservative on purpose. See Performance tab for full breakdown.`;
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
  // Animate number count-up
  const target = t.point_estimate;
  const duration = 600;
  const start = performance.now();
  function animHero(now) {
    const p = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    heroNum.textContent = fmt(Math.round(target * ease));
    if (p < 1) requestAnimationFrame(animHero);
  }
  requestAnimationFrame(animHero);
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
    ? ` <span title="${nHist} qualifying historical edition${nHist===1?'':'s'} for this family. Below 4 editions, the model marks the prediction low-confidence." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:.62rem;font-weight:700;background:rgba(0,0,0,.3);border:1px solid ${confColor};color:${confColor};margin-left:6px;vertical-align:middle;cursor:help">${confLabel} · ${nHist} edition${nHist===1?'':'s'}</span>`
    : '';

  // Audit telemetry: surface fallback tier when prediction didn't use direct family ratios.
  const tierBadge = (!isDone(t) && t.prediction_tier && t.prediction_tier !== 'family-direct')
    ? ` <span title="Prediction used the '${t.prediction_tier}' fallback path. 'family-alias' pools history from related families; 'size-matched' uses families with comparable historical size when this family has no direct history." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:.62rem;font-weight:700;background:rgba(0,0,0,.3);border:1px solid var(--blue);color:var(--blue);margin-left:6px;vertical-align:middle;cursor:help">${t.prediction_tier.replace('-',' ')}</span>`
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
    ciHtml = `
      <div class="ci-bar" role="img" aria-label="80% confidence interval from ${fmt(lo)} to ${fmt(hi)}, point estimate ${fmt(pe)}">
        <span class="ci-bound ci-bound-lo">${fmt(lo)}</span>
        <div class="ci-track">
          <div class="ci-track-fill"></div>
          <div class="ci-marker" style="left:${pct.toFixed(2)}%" title="Point estimate: ${fmt(pe)}"></div>
        </div>
        <span class="ci-bound ci-bound-hi">${fmt(hi)}</span>
      </div>
      <div class="ci-meta">${ciLevel}% CI${confBadge}${tierBadge}</div>
    `;
  }
  document.getElementById('heroCi').innerHTML = ciHtml;

  // Hero narrative — a one-or-two sentence summary that ties the headline
  // numbers together in plain English. Surfaces context the hero KPIs
  // alone don't make obvious: how this tracks vs prior years, what the
  // current pace implies, what milestone is next.
  document.getElementById('heroNarrative').innerHTML = buildHeroNarrative(t);

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
  document.getElementById('kpiDays').innerHTML = `
    <div class="kpi-label">${isDone(t) ? 'Event Date' : 'Days to Event'}</div>
    <div class="kpi-value ${daysColor}">${isDone(t) ? fmtDate(t.event_start) : t.days_remaining}</div>
    <div class="kpi-sub">${isDone(t) ? (t.event_end ? fmtDate(t.event_start) + ' – ' + fmtDate(t.event_end) : '') : fmtDate(t.event_start)}</div>
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
      // Expected remaining registrations per day to hit prediction
      const remaining = t.point_estimate - t.current_count;
      const neededNum = t.days_remaining > 0 ? remaining / t.days_remaining : 0;
      const neededRate = neededNum >= 0.05 ? neededNum.toFixed(1) : '0';
      // Ratio of current rate to needed rate. >=1 means on/ahead-of pace.
      const ratio = neededNum > 0 ? rateNum / neededNum : (rateNum > 0 ? 1.5 : 0);
      // SVG arc gauge: 180-degree semicircle, fill proportional to
      // min(ratio, 1.5) so the gauge maxes at 150% of needed (deep green).
      const gaugeCap = 1.5;
      const gaugePct = Math.max(0, Math.min(gaugeCap, ratio)) / gaugeCap;
      const arcColor = ratio >= 0.95 ? 'var(--green)'
                     : ratio >= 0.6 ? 'var(--gold)'
                     : 'var(--red)';
      // Semicircle path: arc from (10, 30) to (70, 30), radius 30.
      // Length of full half-arc = pi*r = 94.25; dasharray uses that to
      // encode fill percentage.
      const arcLen = 94.25;
      const dash = (gaugePct * arcLen).toFixed(2);
      paceHtml = `
        <div class="kpi-label">Daily Pace</div>
        <div class="kpi-gauge" aria-label="Pace gauge: ${rate} per day, need ${neededRate} per day">
          <svg class="kpi-gauge-svg" viewBox="0 0 80 42" aria-hidden="true">
            <path class="kpi-gauge-track" d="M 10 32 A 30 30 0 0 1 70 32" />
            <path class="kpi-gauge-fill" d="M 10 32 A 30 30 0 0 1 70 32"
              style="stroke:${arcColor}; stroke-dasharray:${dash} ${arcLen};" />
          </svg>
          <div class="kpi-gauge-value">${rate}<span class="kpi-gauge-unit">/d</span></div>
        </div>
        <div class="kpi-sub">need ${neededRate}/day</div>
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
    <div class="kpi-value" style="font-size:1.1rem;color:var(--muted)">–</div>
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
          <div class="kpi-value v-green" style="font-size:1.1rem">Final</div>
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
        <div class="kpi-value" style="font-size:1.1rem;color:var(--muted)">–</div>
        <div class="kpi-sub">No prediction</div>
      `;
    }
  }

  // ── Last 7 days breakdown ──
  const weekEl = document.getElementById('weekBreakdown');
  const barsEl = document.getElementById('weekBars');
  if (!isDone(t) && t.daily_data && t.daily_data.length >= 2) {
    // Get last 7 data points and compute daily new entries
    const dd = t.daily_data;
    const recent = dd.slice(-8); // need 8 to get 7 diffs
    const days = [];
    for (let i = 1; i < recent.length; i++) {
      const dayGap = recent[i][0] - recent[i-1][0];
      const newEntries = recent[i][1] - recent[i-1][1];
      // If gap > 1, spread evenly (data may skip days)
      if (dayGap > 0) {
        const perDay = newEntries / dayGap;
        for (let g = 0; g < dayGap && days.length < 7; g++) {
          days.push(Math.round(perDay));
        }
      }
    }
    if (days.length === 0 || days.every(n => n === 0)) {
      // No recent activity — render a quiet placeholder instead of nothing
      // so the hero-week column doesn't suddenly collapse to zero height.
      barsEl.innerHTML = `<div class="hero-week-empty">No registrations in the last 7 days</div>`;
      weekEl.style.display = '';
    } else if (days.length >= 2) {
      const maxNew = Math.max(...days, 1);
      const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      // Anchor bar labels to the server-side scrape date. The cron runs at
      // ~00:20 EDT, so the delta captured by scrape N vs scrape N-1 reflects
      // registrations during the calendar day BEFORE scrape N — shift back 1
      // day so each bar's date matches when players actually registered.
      const genStr = (typeof TOURNAMENT_DATA !== 'undefined' && TOURNAMENT_DATA.generated) ? TOURNAMENT_DATA.generated : null;
      const anchor = genStr ? new Date(genStr + 'T00:00:00') : new Date();
      const lastBarDay = new Date(anchor);
      lastBarDay.setDate(lastBarDay.getDate() - 1);
      barsEl.innerHTML = days.slice(-7).map((n, i, arr) => {
        const d = new Date(lastBarDay);
        d.setDate(d.getDate() - (arr.length - 1 - i));
        const label = `${dayNames[d.getDay()]} ${months[d.getMonth()]} ${d.getDate()}`;
        const pct = Math.max((n / maxNew) * 100, 2);
        const color = n === maxNew ? 'var(--gold)' : 'var(--blue)';
        return `<div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:.6rem;color:var(--muted);width:62px;text-align:right;white-space:nowrap">${label}</span>
          <div style="flex:1;height:11px;background:var(--surface2);border-radius:2px;overflow:hidden">
            <div style="width:${pct}%;height:100%;background:${color};border-radius:2px;transition:width .35s cubic-bezier(.22,1,.36,1)"></div>
          </div>
          <span style="font-size:.64rem;color:var(--text2);width:24px;font-weight:${n === maxNew ? '700' : '400'}">+${n}</span>
        </div>`;
      }).join('');
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

  const totalDays = t.daily_data[t.daily_data.length-1][0] + t.days_remaining || 120;
  const elapsed = totalDays - t.days_remaining;
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

// ══════════════════════════════════════════════════════════
// CHART
// ══════════════════════════════════════════════════════════
function renderChart(t) {
  const ctx = document.getElementById('mainChart');
  if (chart) { chart.destroy(); chart = null; }

  if (!t.daily_data || t.daily_data.length === 0 || !t.event_start) {
    // No registration timeline data or missing event date — show placeholder
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = `${t.family} ${t.year} — No registration timeline available`;
    document.getElementById('chartCard').classList.remove('live-glow');
    return;
  }

  const eventStart = t.event_start;
  const datasets = [];
  const lastDay = t.daily_data[t.daily_data.length - 1];
  const totalSpan = lastDay[0] + t.days_remaining;
  const regOpenDate = addDays(eventStart, -totalSpan);

  // Actual data
  const actualData = t.daily_data.map(d => ({
    x: addDays(eventStart, -(totalSpan - d[0])),
    y: d[1]
  }));

  // Only show point for first, last, and every 7th day to avoid clutter
  const pointRadii = actualData.map((_, i) => {
    if (i === actualData.length-1 && !isDone(t)) return 6; // today - prominent
    if (i === actualData.length-1 && isDone(t)) return 4;  // final point
    if (i === 0) return 3;  // first point
    return 0;  // hide intermediate points
  });

  // Gradient fill under actual data
  const createGradient = (ctx2) => {
    const g = ctx2.createLinearGradient(0, 0, 0, 380);
    g.addColorStop(0, 'rgba(88,166,255,0.15)');
    g.addColorStop(1, 'rgba(88,166,255,0.01)');
    return g;
  };

  datasets.push({
    label: 'Actual Entries',
    data: actualData,
    borderColor: '#58a6ff',
    backgroundColor: (context) => {
      const chart2 = context.chart;
      const { ctx: ctx2 } = chart2;
      return createGradient(ctx2);
    },
    fill: true,
    borderWidth: 2.5,
    pointRadius: pointRadii,
    pointHoverRadius: 6,
    pointHoverBackgroundColor: '#58a6ff',
    pointHoverBorderColor: '#fff',
    pointHoverBorderWidth: 2,
    pointBackgroundColor: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? '#fff' : '#58a6ff'),
    pointBorderColor: '#58a6ff',
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
      borderColor: '#f0c040',
      borderWidth: 2,
      borderDash: [6, 4],
      pointRadius: 0,
      pointHoverRadius: 6,
      pointHoverBackgroundColor: '#f0c040',
      pointHoverBorderColor: '#fff',
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
    datasets.push({
      label: 'CI Upper', data: ciUp,
      borderColor: 'transparent',
      backgroundColor: 'rgba(240,192,64,0.08)',
      fill: '+1', pointRadius: 0, tension: 0.3, order: 5
    });
    datasets.push({
      label: 'CI Lower', data: ciLo,
      borderColor: 'transparent',
      backgroundColor: 'rgba(240,192,64,0.08)',
      pointRadius: 0, tension: 0.3, order: 5
    });
  }

  // Historical traces — dashed lines, no points, for past year curves of this family
  if (t.historical && t.registration_curve) {
    const histColors = [
      'rgba(139,148,158,0.55)',  // most recent — brightest
      'rgba(139,148,158,0.40)',
      'rgba(139,148,158,0.28)',
      'rgba(139,148,158,0.18)',
      'rgba(139,148,158,0.12)',
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
      const dd = real.daily_data;
      const maxDay = dd[dd.length - 1][0];
      dd.forEach(p => {
        const T = maxDay - p[0];
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
        borderWidth: 1.5,
        borderDash: [5, 4],
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: histColors[colorIdx] || histColors[histColors.length - 1],
        pointHoverBorderColor: '#e6edf3',
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
        pointBorderColor: '#e6edf3',
        pointBorderWidth: 1.5,
        order: 4
      });
    });
  }

  // Vertical lines plugin
  const vertLinePlugin = {
    id: 'vertLines',
    afterDraw(chartInstance) {
      const ctx2 = chartInstance.ctx;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      const lines = [];
      const _isM = _mobileVP();
      // On mobile, only the Today line — Early Bird and Event labels overlap on
      // narrow screens (the days-to-event KPI card tells the user already).
      if (!_isM && hasValidEarlyBird(t)) lines.push({ date: new Date(t.early_bird_deadline + 'T00:00:00'), label: 'Early Bird', color: '#3fb950' });
      if (!isDone(t)) lines.push({ date: new Date(TOURNAMENT_DATA.generated + 'T00:00:00'), label: 'Today', color: '#58a6ff' });
      if (!_isM && t.event_start) lines.push({ date: new Date(t.event_start + 'T00:00:00'), label: 'Event', color: '#f85149' });

      const isMobile = _mobileVP();
      const annoFont = isMobile ? 'bold 9px' : 'bold 11px';
      const pillH = isMobile ? 14 : 16;
      const pillYOff = isMobile ? 16 : 18;
      const textYOff = isMobile ? 5 : 6;
      const rowGap = 3;
      // Track drawn pill bounding boxes so a new pill that horizontally
      // overlaps any drawn pill stacks onto a higher row instead of
      // colliding (e.g. Early Bird + Event when their dates are 3 days
      // apart — pills are ~60-70px wide so they always overlap).
      const drawn = [];
      lines.forEach(line => {
        const x = xScale.getPixelForValue(line.date);
        if (x < xScale.left || x > xScale.right) return;
        ctx2.save();
        ctx2.beginPath();
        ctx2.setLineDash([4, 4]);
        ctx2.strokeStyle = line.color;
        ctx2.globalAlpha = 0.7;
        ctx2.lineWidth = 1;
        ctx2.moveTo(x, yScale.top);
        ctx2.lineTo(x, yScale.bottom);
        ctx2.stroke();
        ctx2.setLineDash([]);
        ctx2.globalAlpha = 1;
        ctx2.font = `${annoFont} -apple-system, system-ui, sans-serif`;
        ctx2.textAlign = 'center';
        const textW = ctx2.measureText(line.label).width;
        const pillW = textW + 10;
        // Clamp pill horizontally so it never spills past the chart area.
        // Right-edge clipping was visible on tournaments where the Event
        // line sits at the far right of the extended axis.
        let pillX = x - textW / 2 - 5;
        if (pillX + pillW > xScale.right) pillX = xScale.right - pillW;
        if (pillX < xScale.left) pillX = xScale.left;
        // Pick a vertical row that doesn't horizontally overlap a drawn
        // pill. Row 0 = original Y; row N stacks upward by pillH + gap.
        let row = 0;
        while (drawn.some(d => d.row === row &&
                                !(pillX + pillW < d.x || pillX > d.x2))) {
          row++;
        }
        const pillY = yScale.top - pillYOff - row * (pillH + rowGap);
        drawn.push({ x: pillX, x2: pillX + pillW, row });
        ctx2.fillStyle = 'rgba(13,17,23,0.85)';
        ctx2.beginPath();
        ctx2.roundRect(pillX, pillY, pillW, pillH, 4);
        ctx2.fill();
        ctx2.strokeStyle = line.color;
        ctx2.lineWidth = 1;
        ctx2.globalAlpha = 0.6;
        ctx2.stroke();
        ctx2.globalAlpha = 1;
        // Draw label text centered on the pill (not on the line) so the
        // clamp + stack stay legible.
        ctx2.fillStyle = line.color;
        ctx2.fillText(line.label, pillX + pillW / 2, pillY + pillH - textYOff);
        ctx2.restore();
      });
    }
  };

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
      ctx2.strokeStyle = 'rgba(139,148,158,0.35)';
      ctx2.lineWidth = 1;
      ctx2.moveTo(x, yScale.top);
      ctx2.lineTo(x, yScale.bottom);
      ctx2.stroke();
      ctx2.restore();
    }
  };

  // Custom interaction mode: find nearest point by x-pixel in EACH dataset
  // independently, so datasets with different date ranges align correctly.
  // Only includes a dataset if the hovered x falls within its data range
  // (with a small pixel margin), preventing stale endpoint matches.
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
        const margin = 15;
        if (mouseX < firstPx - margin || mouseX > lastPx + margin) return;
        let bestIdx = -1, bestDist = Infinity;
        for (let idx = firstHitIdx; idx < meta.data.length; idx++) {
          const dist = Math.abs(meta.data[idx].x - mouseX);
          if (dist < bestDist) { bestDist = dist; bestIdx = idx; }
        }
        if (bestIdx >= 0 && bestDist < 50) {
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

  chart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    plugins: [vertLinePlugin, crosshairPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'xAligned', intersect: false },
      hover: { mode: 'xAligned', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          position: 'cornerAway',
          xAlign: undefined, yAlign: 'top',
          caretSize: 0,
          backgroundColor: 'rgba(13,17,23,0.95)', borderColor: 'rgba(48,54,61,0.8)', borderWidth: 1,
          titleColor: '#e6edf3', bodyColor: '#c9d1d9', footerColor: '#8b949e',
          padding: _mobileVP() ? 9 : 12, cornerRadius: 8,
          // Mobile tooltip: tighter padding, smaller text, smaller point swatches,
          // capped width so a long historical comparison list can't overflow the
          // chart area or the viewport. Desktop unchanged.
          boxPadding: 4,
          boxWidth: _mobileVP() ? 6 : 10,
          displayColors: true,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
          bodyFont: { size: _mobileVP() ? 11 : 12 },
          footerFont: { size: _mobileVP() ? 10 : 11, style: 'italic' },
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
                  const prev = item.dataset.data[item.dataIndex - 1].y;
                  const delta = item.raw.y - prev;
                  if (delta > 0) return ` Actual: ${val}  (+${fmt(delta)}/day)`;
                  if (delta === 0) return ` Actual: ${val}  (no change)`;
                  return ` Actual: ${val}  (${fmt(delta)}/day)`;
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
          const oc = row.getAttribute('onclick') || '';
          if (oc.includes('selectTournament(' + idx + ')')) {
            row.classList.add('chart-highlight');
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
          time: _mobileVP()
            ? { unit: 'month', displayFormats: { month: 'MMM' } }
            : { unit: 'week', displayFormats: { week: 'MMM d' } },
          // Extend the axis 5 days past event day so the finals-marker dot for
          // each historical year has visible space and is clearly separate
          // from the chart's data region (the day-of / post-event surge).
          max: t.event_start ? addDays(new Date(t.event_start + 'T00:00:00'), 5) : undefined,
          grid: { color: 'rgba(48,54,61,0.4)', drawBorder: false },
          ticks: { color: '#8b949e', font: { size: _mobileVP() ? 10 : 11 }, maxRotation: 0 }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(48,54,61,0.4)', drawBorder: false },
          ticks: { color: '#8b949e', font: { size: _mobileVP() ? 10 : 11 }, maxTicksLimit: _mobileVP() ? 5 : 8, callback: v => v >= 1000 ? (v/1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k' : v }
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
    legendHtml += '<div class="legend-item"><div class="legend-swatch dashed" style="background:repeating-linear-gradient(90deg,rgba(139,148,158,0.5) 0 4px,transparent 4px 8px)"></div>Historical</div>';
  }
  document.getElementById('chartLegend').innerHTML = legendHtml;

  // Subtitle
  let sub = `${t.family} ${t.year} — Registration Trajectory`;
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
      <div class="timeline-node"><div class="timeline-dot past"></div><div class="timeline-label">Final Count</div><div class="timeline-date" style="color:var(--gold);font-size:.9rem">${fmt(t.current_count)}</div></div>
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
    wrap.innerHTML = `<div style="text-align:center;padding:20px 0;color:var(--muted);font-size:.8rem;opacity:.6">No historical editions on record</div>`;
    return;
  }

  const hist = t.historical.slice(-6);
  const histFlags = hist.map(h => h.adjusted ? { kind: h.adjusted, raw: h.count_raw } : null);
  const hasAdjusted = histFlags.some(Boolean);
  const labels = [...hist.map(h => h.adjusted ? `${h.year}*` : String(h.year)), String(t.year)];
  const counts = [...hist.map(h => h.count), isDone(t) ? t.current_count : t.point_estimate];
  const colors = counts.map((_, i) => i === counts.length-1 ? 'rgba(240,192,64,0.75)' : 'rgba(88,166,255,0.45)');
  const borders = counts.map((_, i) => i === counts.length-1 ? '#f0c040' : '#58a6ff');

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
        borderWidth: 1, borderRadius: 4
      }]
    },
    plugins: [avgLinePlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(13,17,23,0.95)', borderColor: 'rgba(48,54,61,0.8)', borderWidth: 1,
          titleColor: '#e6edf3', bodyColor: '#c9d1d9', footerColor: '#8b949e',
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
        x: { grid: { display: false }, ticks: { color: '#8b949e', font: { size: _mobileVP() ? 9 : 10 }, maxRotation: 0 } },
        y: { beginAtZero: true, grid: { color: 'rgba(48,54,61,0.4)', drawBorder: false }, ticks: { color: '#8b949e', font: { size: _mobileVP() ? 9 : 10 }, maxTicksLimit: _mobileVP() ? 4 : 6, callback: v => v >= 1000 ? (v/1000).toFixed(0) + 'k' : v } }
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
      ? `${fmt(h.count)} <span style="color:var(--muted);font-size:.75rem">(was ${fmt(h.count_raw)})</span>`
      : fmt(h.count);
    return `<tr${rowClass}><td data-label="Year">${yearLabel}</td><td data-label="Count">${countCell}</td><td data-label="YoY" class="${cls}">${diff != null ? (diff > 0 ? '+' : '') + fmt(diff) : '–'}</td><td data-label="Change" class="${cls}">${pct != null ? (diff > 0 ? '+' : '') + pct + '%' : '–'}</td></tr>`;
  }).join('');

  const footnote = hasAdjusted
    ? `<div style="margin-top:8px;color:var(--muted);font-size:.72rem;line-height:1.45">* 2019 and 2022 World Open were a single combined registration page (9 sections). Counts adjusted to top-6 only for apples-to-apples vs the 2023+ split. Estimates use chessevents.com final-standings ratios.</div>`
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

  // "You are here" annotation plugin for reg curve
  const regCurveAnnotation = {
    id: 'regCurveAnnotation',
    afterDraw(chartInstance) {
      if (isDone(t)) return;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      // Find the label index closest to today
      let idx = -1;
      let minDiff = Infinity;
      labels.forEach((db, i) => {
        const d = Math.abs(db - t.days_remaining);
        if (d < minDiff) { minDiff = d; idx = i; }
      });
      if (idx < 0) return;
      const x = xScale.getPixelForValue(idx);
      const ctx2 = chartInstance.ctx;
      ctx2.save();
      ctx2.beginPath();
      ctx2.setLineDash([3, 3]);
      ctx2.strokeStyle = 'rgba(88,166,255,0.6)';
      ctx2.lineWidth = 1;
      ctx2.moveTo(x, yScale.top);
      ctx2.lineTo(x, yScale.bottom);
      ctx2.stroke();
      ctx2.fillStyle = 'rgba(88,166,255,0.8)';
      ctx2.font = '9px -apple-system, system-ui, sans-serif';
      ctx2.textAlign = 'center';
      ctx2.fillText('Today', x, yScale.top - 3);
      ctx2.restore();
    }
  };

  regCurveObj = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.map(db => db === 0 ? 'Event' : db >= 7 ? `${db}d` : `${db}d`),
      datasets: [{
        data,
        borderColor: 'rgba(240,192,64,0.6)',
        backgroundColor: 'rgba(240,192,64,0.05)',
        fill: true,
        borderWidth: 2,
        pointRadius: labels.map(db => db === 0 || db === t.days_remaining ? 5 : 0),
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        tension: 0.4
      }]
    },
    plugins: [regCurveAnnotation],
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(13,17,23,0.95)', borderColor: 'rgba(48,54,61,0.8)', borderWidth: 1,
          titleColor: '#e6edf3', bodyColor: '#c9d1d9', footerColor: '#8b949e',
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
          ticks: { color: '#8b949e', font: { size: _mobileVP() ? 8 : 9 }, maxRotation: 0, maxTicksLimit: _mobileVP() ? 6 : 12 }
        },
        y: {
          min: 0, max: 105,
          grid: { color: 'rgba(48,54,61,0.4)', drawBorder: false },
          ticks: {
            color: '#8b949e', font: { size: _mobileVP() ? 8 : 9 },
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
      `At T-${t.days_remaining}: expected ${expectedPct}%, actual ${actualPct}% of predicted final — ${ahead ? 'ahead' : 'behind'} typical pace by ${Math.abs(diff)} percentage points`;
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
      <p style="color:var(--muted);font-size:.78rem;opacity:.6">Fee data not available for this tournament.</p>
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
      <div style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Current Rate</div>
      <div style="font-size:2.2rem;font-weight:900;color:var(--gold)">$${currentFee}</div>
      <div style="font-size:.78rem;color:var(--muted);margin-top:4px">${feeStatus}</div>
    </div>`;
  }

  html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;text-align:center">';
  if (t.early_bird_fee && t.regular_fee && t.early_bird_fee < t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Early Bird</div>
      <div style="font-size:1.1rem;font-weight:700;color:var(--green)">$${t.early_bird_fee}</div>
    </div>`;
  }
  if (t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Regular</div>
      <div style="font-size:1.1rem;font-weight:700;color:var(--text2)">$${t.regular_fee}</div>
    </div>`;
  }
  if (t.onsite_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">On-site</div>
      <div style="font-size:1.1rem;font-weight:700;color:var(--orange)">$${t.onsite_fee}</div>
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
        paceStr = `<span style="font-size:.72rem;color:var(--green)">${rate}/day</span>`;
      }
    }

    return `<tr onclick="selectTournament(${i});window.scrollTo({top:0,behavior:'smooth'})" onkeydown="if(event.key==='Enter'){selectTournament(${i});window.scrollTo({top:0,behavior:'smooth'})}" tabindex="0" style="cursor:pointer">
      <td data-label="Tournament"><div class="t-name">${esc(t.family)}</div><div class="t-sub">${t.year}${isLive ? ' · ' + t.days_remaining + 'd out' : ''}</div></td>
      <td data-label="Status">${pill}</td>
      <td data-label="Event Date">${fmtDate(t.event_start)}${t.event_end ? ' – ' + fmtDate(t.event_end) : ''}</td>
      <td data-label="Current" style="font-weight:600;color:var(--blue)">${fmt(t.current_count)} ${paceStr}</td>
      <td data-label="Predicted" style="font-weight:700;color:var(--gold)">${fmt(t.point_estimate)}</td>
      <td data-label="Likely Range" style="font-size:.82rem;color:var(--muted)">${ci}</td>
      <td data-label="Progress">
        <span class="pace-bar-wrap"><span class="pace-bar-fill" style="width:${pct}%;background:${paceColor}"></span></span>
        <span style="font-size:.72rem;color:var(--muted)">${pct}%</span>
      </td>
    </tr>`;
  }).join('');
  if (active.length === 0) {
    body.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px 0;color:var(--muted);font-size:.85rem">No tournaments match the current filter.</td></tr>`;
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
    ${nextEvent ? `<span style="cursor:pointer" onclick="selectTournament(${TOURNAMENT_DATA.tournaments.indexOf(nextEvent)})">Next: <strong style="color:var(--gold)">${nextEvent.family}</strong> in ${nextEvent.days_remaining}d</span>` : ''}
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
      onclick="selectTournament(${idx})"
      aria-current="${isActive ? 'true' : 'false'}"
      aria-label="${esc(subLabel)} — predicted ${fmt(pred)}, ${fmt(current)} registered">
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
    <button class="acc-row" onclick="switchPageTab('performance')" aria-label="Open full model performance tab">
      <span class="acc-cell acc-grade">
        <span class="acc-grade-letter acc-${gradeCls(grade)}">${grade}</span>
        <span class="acc-grade-label">Model grade${nEvents ? ` · ${nEvents} tests` : ''}</span>
      </span>
      ${mae != null ? `<span class="acc-cell">
        <span class="acc-num">${mae.toFixed(1)}%</span>
        <span class="acc-lab">Avg miss at 2 weeks out</span>
      </span>` : ''}
      ${cov != null ? `<span class="acc-cell">
        <span class="acc-num">${Math.round(cov * 100)}%</span>
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
    const ariaLabel = `${e.t.family} on ${monthDay}, T-${e.daysOut}, predicted ${fmt(e.t.point_estimate || 0)}`;
    html += `<button class="cal-dot cal-pace-${pace}" style="left:${xPct.toFixed(2)}%;width:${sizePx}px;height:${sizePx}px"
      onclick="selectTournament(${e.idx})" title="${esc(e.t.family)} — ${monthDay} (T-${e.daysOut})"
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
}

// ══════════════════════════════════════════════════════════
// UPCOMING MINI CARDS
// ══════════════════════════════════════════════════════════
function renderMiniCards() {
  const el = document.getElementById('miniGrid');
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.map((t, i) => ({t, i}))
    .filter(({t}) => t.status === 'live')
    .sort((a, b) => a.t.days_remaining - b.t.days_remaining);

  el.innerHTML = live.map(({t, i}) => {
    const isSelected = i === selectedIndex;
    const pct = t.point_estimate > 0 ? (t.current_count / t.point_estimate * 100).toFixed(0) : 0;
    // Today's delta (latest scrape - prior scrape) surfaces velocity on the
    // selector card itself instead of forcing a click through to see it.
    let todayDelta = null;
    if (t.daily_data && t.daily_data.length >= 2) {
      todayDelta = t.daily_data[t.daily_data.length - 1][1]
                 - t.daily_data[t.daily_data.length - 2][1];
    }
    const deltaChip = todayDelta != null && todayDelta !== 0
      ? `<span class="mini-card-delta ${todayDelta > 0 ? 'pos' : 'neg'}" title="Today's change">${todayDelta > 0 ? '+' : ''}${todayDelta}</span>`
      : '';
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
        paceIndicator = `<span style="color:var(--green);font-size:.68rem">&#9650; ahead</span>`;
      } else if (t.current_count < expectedCount * 0.95) {
        paceIndicator = `<span style="color:var(--orange);font-size:.68rem">&#9660; behind</span>`;
      } else {
        paceIndicator = `<span style="color:var(--muted);font-size:.68rem">&#8212; on pace</span>`;
      }
    }
    return `<div class="mini-card ${isSelected ? 'mini-card-active' : ''}" onclick="selectTournament(${i})" onkeydown="if(event.key==='Enter')selectTournament(${i})" tabindex="0" role="button" aria-label="${esc(t.family)} - ${fmt(t.point_estimate)} predicted">
      <div class="mini-card-header">
        <span class="mini-card-name">${esc(t.family)}</span>
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
  }).join('');
}

// ══════════════════════════════════════════════════════════
// DEEP LINKING (hash routing)
// ══════════════════════════════════════════════════════════
const VALID_TABS = ['predictions', 'dataentry', 'email', 'performance', 'about', 'puzzles'];

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
  if (route.tab === 'predictions' && route.idx !== null && route.idx >= 0 && route.idx <= maxIdx) {
    selectTournament(route.idx, true);
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
  document.getElementById('tournLabel').textContent = `${t.family} ${t.year}`;
  document.title = `${t.family} ${t.year} — CCA Entry Predictor`;

  updateFavButton(t.family);
  updateCompareBtn();

  // Staggered fade-in for visual polish
  const sections = document.querySelectorAll('.delta-banner, .chart-card, .kpi-row, .progress-row, .grid-2');
  sections.forEach(s => s.style.opacity = '0');

  setTimeout(() => {
    renderTabs();
    renderCalendar();
    renderAccuracyStrip();
    renderMiniCards();
    renderDelta(t);
    renderHero(t);
    renderKPIRow(t);
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
      help: 'Letter grade from the 2026 evaluation cohort. Based on T-14 MAE and CI coverage.',
    });
  }

  grid.innerHTML = tiles.map(t =>
    '<div title="' + t.help.replace(/"/g, '&quot;') + '" style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;cursor:help">' +
    '<div style="font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">' + t.label + '</div>' +
    '<div style="font-size:1.6rem;font-weight:800;color:' + t.color + ';line-height:1">' + t.value + '</div>' +
    '<div style="font-size:.7rem;color:var(--text2);margin-top:6px">' + t.sub + '</div>' +
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
        warnEl.innerHTML = '<div style="font-size:.78rem;color:var(--green);padding:10px 12px;background:rgba(72,187,120,.08);border:1px solid rgba(72,187,120,.3);border-radius:8px">Latest pipeline run: 0 warnings (clean).</div>';
        return;
      }
      const rows = data.warnings.map(w =>
        '<tr><td style="padding:4px 8px;color:var(--muted);font-size:.72rem;white-space:nowrap">' +
        w.step.split('(')[0].trim() + '</td><td style="padding:4px 8px;color:var(--text2);font-size:.78rem">' +
        w.text + '</td></tr>'
      ).join('');
      warnEl.innerHTML =
        '<details style="background:rgba(214,158,46,.08);border:1px solid rgba(214,158,46,.3);border-radius:8px;padding:10px 12px">' +
        '<summary style="cursor:pointer;font-size:.78rem;color:var(--gold);font-weight:600">Latest pipeline run: ' + c + ' warning' + (c === 1 ? '' : 's') + ' (click to expand)</summary>' +
        '<table style="width:100%;margin-top:10px;border-collapse:collapse">' + rows + '</table></details>';
    })
    .catch(() => { warnEl.innerHTML = ''; });
}


function init() {
  // --- Stale data warning banner ---
  if (TOURNAMENT_DATA.is_stale) {
    const banner = document.getElementById('staleBanner');
    const bannerText = document.getElementById('staleBannerText');
    if (banner && bannerText) {
      const ts = TOURNAMENT_DATA.last_updated || TOURNAMENT_DATA.generated;
      bannerText.textContent = '\u26A0 Predictions last updated ' + ts + '. Live data temporarily unavailable.';
      banner.style.display = 'block';
      // Push page content down so banner doesn't overlap
      document.body.style.paddingTop = banner.offsetHeight + 'px';
    }
  }

  renderModelHealth();
  document.getElementById('lastUpdated').textContent = fmtDateTimeLong(TOURNAMENT_DATA.generated_time || TOURNAMENT_DATA.generated);
  // Always show splash on load
  initSplash();

  // Logo click re-shows splash
  const logo = document.querySelector('.logo');
  if (logo) {
    logo.style.cursor = 'pointer';
    logo.addEventListener('click', showSplash);
  }

  renderAllTournaments();
  renderSummaryBar();

  // Set default sort indicator on the date column
  const defaultSortTh = document.querySelector(`.tourney-table th[onclick*="'date'"]`);
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
  if (e.target.tagName === 'INPUT') return;
  const n = TOURNAMENT_DATA.tournaments.length;
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    selectTournament((selectedIndex + 1) % n);
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    selectTournament((selectedIndex - 1 + n) % n);
  }
});

// ══════════════════════════════════════════════════════════
// DATA ENTRY PANEL
// ══════════════════════════════════════════════════════════
function toggleDataEntry() {
  const toggle = document.getElementById('deToggle');
  const panel = document.getElementById('dePanel');
  toggle.classList.toggle('open');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) renderDataEntry();
}

function renderDataEntry() {
  const body = document.getElementById('deBody');
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.filter(t => t.status === 'live').sort((a,b) => a.days_remaining - b.days_remaining);
  const overrides = JSON.parse(localStorage.getItem('cca_overrides') || '{}');

  // Each input carries data-pristine (the pipeline value at render time) and
  // data-saved (the value already persisted to localStorage, if any). On save
  // we only write fields where the current input value differs from BOTH —
  // this prevents the long-standing bug where opening the panel and clicking
  // Save froze every visible field as an override even if the user only
  // touched one row.
  body.innerHTML = live.map(t => {
    const o = overrides[t.family] || {};
    const entries = o.current_count !== undefined ? o.current_count : t.current_count;
    const start = o.event_start || t.event_start || '';
    const ebDeadline = o.early_bird_deadline || t.early_bird_deadline || '';
    const ebFee = o.early_bird_fee !== undefined ? o.early_bird_fee : (t.early_bird_fee || '');
    const regFee = o.regular_fee !== undefined ? o.regular_fee : (t.regular_fee || '');
    const onsiteFee = o.onsite_fee !== undefined ? o.onsite_fee : (t.onsite_fee || '');
    const pristine = (k, v) => `data-pristine="${v == null ? '' : esc(String(v))}" data-saved="${o[k] != null ? esc(String(o[k])) : ''}"`;
    return `<tr>
      <td class="fam-name" data-label="Tournament">${esc(t.family)}</td>
      <td data-label="Entries"><input type="number" data-family="${esc(t.family)}" data-field="current_count" ${pristine('current_count', t.current_count)} value="${entries}" min="0"></td>
      <td data-label="Event Start"><input type="date" data-family="${esc(t.family)}" data-field="event_start" ${pristine('event_start', t.event_start || '')} value="${start}"></td>
      <td data-label="Early Bird Deadline"><input type="date" data-family="${esc(t.family)}" data-field="early_bird_deadline" ${pristine('early_bird_deadline', t.early_bird_deadline || '')} value="${ebDeadline}"></td>
      <td data-label="Early Bird Fee"><input type="number" data-family="${esc(t.family)}" data-field="early_bird_fee" ${pristine('early_bird_fee', t.early_bird_fee || '')} value="${ebFee}" min="0"></td>
      <td data-label="Reg Fee"><input type="number" data-family="${esc(t.family)}" data-field="regular_fee" ${pristine('regular_fee', t.regular_fee || '')} value="${regFee}" min="0"></td>
      <td data-label="Onsite Fee"><input type="number" data-family="${esc(t.family)}" data-field="onsite_fee" ${pristine('onsite_fee', t.onsite_fee || '')} value="${onsiteFee}" min="0"></td>
    </tr>`;
  }).join('');
}

function saveDataEntry() {
  const inputs = document.querySelectorAll('#deBody input');
  const overrides = JSON.parse(localStorage.getItem('cca_overrides') || '{}');

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

  // Show saved message
  const msg = document.getElementById('deSavedMsg');
  msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
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
  // Refresh favorites tab if it's currently visible
  if (_currentTab === 'favorites') renderFavoritesTab();
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

function renderFavoritesTab() {
  const el = document.getElementById('favoritesContent');
  if (!el) return;
  const favs = getFavorites();

  if (favs.length === 0) {
    el.innerHTML = `<div class="fav-empty">
      <div style="font-size:2.5rem;margin-bottom:12px">&#9734;</div>
      <div style="font-size:1rem;font-weight:600;margin-bottom:6px">No favorites yet</div>
      <div style="font-size:.82rem;color:var(--muted)">Click &#9733; on any tournament to add it here</div>
    </div>`;
    return;
  }

  const cards = favs.map(family => {
    const t = TOURNAMENT_DATA.tournaments.find(x => x.family === family);
    if (!t) return '';
    const i = TOURNAMENT_DATA.tournaments.indexOf(t);
    const isLive = t.status === 'live';
    const isComplete = t.status === 'complete';
    const statusLabel = isLive ? 'Live' : isComplete ? 'Complete' : 'Upcoming';
    const statusClass = isLive ? 'badge-live' : isComplete ? 'badge-complete' : 'badge-upcoming';
    const daysInfo = isLive ? `${t.days_remaining}d remaining` : isComplete ? 'Finished' : t.days_remaining != null ? `Starts in ${t.days_remaining}d` : '';
    const ciRange = t.ci_lower && t.ci_upper ? `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}` : '—';

    return `<div class="fav-card" onclick="switchPageTab('predictions');selectTournament(${i});window.scrollTo({top:0,behavior:'smooth'})" tabindex="0" onkeydown="if(event.key==='Enter'){switchPageTab('predictions');selectTournament(${i});window.scrollTo({top:0,behavior:'smooth'})}">
      <div class="fav-card-header">
        <span class="fav-card-name">${esc(t.family)} ${t.year}</span>
        <button class="fav-btn fav-active fav-remove" onclick="event.stopPropagation();toggleFavorite('${esc(t.family).replace(/'/g, "\\'")}')" title="Remove from favorites">&#9733;</button>
      </div>
      <div class="fav-card-status">
        <span class="mini-badge ${statusClass}">${isLive ? '<span class="live-dot" style="width:5px;height:5px"></span>' : ''}${statusLabel}</span>
        <span style="color:var(--muted);font-size:.75rem">${daysInfo}</span>
      </div>
      <div class="fav-card-stats">
        <div class="fav-stat">
          <span class="fav-stat-label">Predicted</span>
          <span class="fav-stat-value" style="color:var(--gold)">${fmt(t.point_estimate)}</span>
        </div>
        <div class="fav-stat">
          <span class="fav-stat-label">CI Range</span>
          <span class="fav-stat-value">${ciRange}</span>
        </div>
        <div class="fav-stat">
          <span class="fav-stat-label">Current</span>
          <span class="fav-stat-value" style="color:var(--blue)">${fmt(t.current_count)}</span>
        </div>
      </div>
      ${(() => { const pa = getPaceAlert(t); if (!pa) return ''; const cls = pa.status === 'above_pace' ? 'above' : pa.status === 'below_pace' ? 'below' : 'on'; const label = pa.status === 'above_pace' ? 'Above pace' : pa.status === 'below_pace' ? 'Below pace' : 'On pace'; return `<div class="fav-pace-row"><span class="fav-pace-dot ${cls}"></span><span style="color:var(--${cls === 'above' ? 'green' : cls === 'below' ? 'red' : 'blue'})">${label}</span><span style="color:var(--muted)">${pa.deviation_pct > 0 ? '+' : ''}${pa.deviation_pct}% vs historical</span></div>`; })()}
    </div>`;
  }).filter(Boolean).join('');

  el.innerHTML = `
    <div style="margin:18px 0 16px">
      <h2 style="font-size:1.3rem;font-weight:800;color:var(--gold);margin-bottom:4px">&#9733; My Tournaments</h2>
      <p style="font-size:.78rem;color:var(--muted)">${favs.length} tournament${favs.length !== 1 ? 's' : ''} saved</p>
    </div>
    <div class="fav-grid">${cards}</div>`;
}

// ══════════════════════════════════════════════════════════
// COMPARE (side-by-side tournament comparison)
// ══════════════════════════════════════════════════════════
const COMPARE_KEY = 'cca_compare';
const COMPARE_COLORS = ['#58a6ff', '#f0c040', '#3fb950'];
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

  // Build selector UI
  let selectorHTML = '<div class="compare-selectors">';
  for (let s = 0; s < 3; s++) {
    const currentIdx = _compareSlots[s];
    const colorDot = `<span class="compare-color-dot" style="background:${COMPARE_COLORS[s]}"></span>`;
    selectorHTML += `<div class="compare-selector">
      ${colorDot}
      <select class="compare-dropdown" onchange="compareSlotChanged(${s}, this.value)">
        <option value="">— Select tournament —</option>
        ${tournaments.map((t, i) => {
          const sel = i === currentIdx ? 'selected' : '';
          const label = esc(t.family) + ' ' + t.year;
          return `<option value="${i}" ${sel}>${label}</option>`;
        }).join('')}
      </select>
      ${currentIdx != null ? `<button class="compare-remove-btn" onclick="compareSlotRemove(${s})" title="Remove">&#10005;</button>` : ''}
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
      <div style="font-size:.82rem;color:var(--muted)">Use the dropdowns above or click &#9878; on any tournament in the Predictions tab</div>
    </div>`;
  }

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
      // Convert daily_data ([day_idx, cumulative]) to (days_before, %).
      const dd = t.daily_data;
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
        pointRadius: 0,
        pointHoverRadius: 5,
        tension: 0.25,
      });
      // Today dot — the very last actual data point.
      if (t.status === 'live') {
        const last = data[data.length - 1];
        datasets.push({
          label: `${t.family} — Today`,
          data: [last],
          borderColor: color,
          backgroundColor: color,
          pointRadius: 7,
          pointStyle: 'circle',
          pointBorderWidth: 2,
          pointBorderColor: 'var(--bg)',
          showLine: false,
        });
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
        const priorLast = prior.daily_data[prior.daily_data.length - 1][0];
        const priorData = prior.daily_data.map(p => ({
          x: priorLast - p[0],
          y: (p[1] / priorTarget) * 100,
        }));
        datasets.push({
          label: `${t.family} — ${prior.year} (prior)`,
          data: priorData,
          borderColor: color,
          borderDash: [4, 4],
          borderWidth: 1.5,
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

  _compareChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'linear',
          reverse: true,
          title: { display: !_mobileVP(), text: 'Days Before Event', color: 'rgba(139,148,158,0.8)', font: { size: 11 } },
          ticks: { color: 'rgba(139,148,158,0.6)', font: { size: _mobileVP() ? 9 : 10 }, maxTicksLimit: _mobileVP() ? 5 : 8, maxRotation: 0,
            callback(v) { return v === 0 ? 'Event' : v + 'd'; }
          },
          grid: { color: 'rgba(48,54,61,0.4)' }
        },
        y: {
          title: { display: !_mobileVP(), text: '% of Final Entries', color: 'rgba(139,148,158,0.8)', font: { size: 11 } },
          ticks: { color: 'rgba(139,148,158,0.6)', font: { size: _mobileVP() ? 9 : 10 }, maxTicksLimit: _mobileVP() ? 5 : 8,
            callback(v) { return v + '%'; }
          },
          grid: { color: 'rgba(48,54,61,0.4)' },
          min: 0
        }
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: '#c9d1d9',
            font: { size: _mobileVP() ? 10 : 11 },
            boxWidth: _mobileVP() ? 8 : 12,
            padding: _mobileVP() ? 6 : 10,
            filter(item) { return !item.text.includes('— Today'); },
            usePointStyle: true, pointStyle: 'line'
          }
        },
        tooltip: {
          backgroundColor: 'rgba(13,17,23,0.95)',
          borderColor: 'rgba(48,54,61,0.8)',
          borderWidth: 1,
          titleColor: '#e6edf3',
          bodyColor: '#c9d1d9',
          padding: 12,
          cornerRadius: 8,
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

init();

// ══════════════════════════════════════════════════════════
// CHART-HIGHLIGHT STYLE (injected for click-to-table feature)
// ══════════════════════════════════════════════════════════
(function() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes chartHighlightPulse {
      0% { background-color: rgba(240,192,64,0.25); }
      100% { background-color: transparent; }
    }
    .chart-highlight {
      animation: chartHighlightPulse 2.5s ease-out forwards;
      outline: 1px solid rgba(240,192,64,0.4);
      outline-offset: -1px;
    }
  `;
  document.head.appendChild(style);
})();