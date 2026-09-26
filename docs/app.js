// ══════════════════════════════════════════════════════════
// PAGE TABS
// ══════════════════════════════════════════════════════════
let _currentTab = 'predictions';
function switchPageTab(tab, skipHash) {
  if (_mobileVP() && _currentTab !== tab) _haptic(8);
  _currentTab = tab;
  // The rail, the phone's bottom bar and the More sheet mark the open view,
  // and the view title under the top bar names it: shell.js owns all four.
  reflectNav(tab);
  closeSheet();
  document.querySelectorAll('.page-tab-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('panel-' + tab);
  panel.classList.add('active');
  if (tab === 'email') initEmailTab();
  if (tab === 'performance') initPerformanceTab();
  if (tab === 'compare') renderCompareTab();
  if (tab === 'ask') initAskTab();
  if (tab === 'audit') initAuditTab();
  if (tab === 'about') ensureModelHealth();
  // Focus management: move focus to new panel for screen readers
  panel.setAttribute('tabindex', '-1');
  panel.focus({ preventScroll: true });
  if (!skipHash) updateHash();
}

// The order a phone swipes through the views (gestures.js).
const PAGE_TAB_ORDER = ['predictions', 'season', 'performance', 'compare', 'ask', 'email', 'audit', 'about'];

// ══════════════════════════════════════════════════════════
// DEEP LINKING (hash routing)
// ══════════════════════════════════════════════════════════
const VALID_TABS = ['predictions', 'season', 'performance', 'compare', 'ask', 'email', 'audit', 'about'];

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
  } else if (!_subjectRendered) {
    // A deep link to another view (#season, #compare) still needs a subject:
    // the top bar names it, and the Season's timeline and cards render from
    // the same pass. Without this a fresh load on #season showed "Loading..."
    // in the top bar and a Season with no cards.
    selectTournament(_defaultTournamentIndex(), true);
  }
  // Set hash without re-triggering (already at the right hash)
  return true;
}

// The tournament a fresh load opens on: the Chicago Open when it is live,
// else the first live one, else the first in the list.
function _defaultTournamentIndex() {
  const ts = TOURNAMENT_DATA.tournaments;
  const chiIdx = ts.findIndex(t => t.status === 'live' && t.family.includes('Chicago Open'));
  const liveIdx = chiIdx >= 0 ? chiIdx : ts.findIndex(t => t.status === 'live');
  return liveIdx >= 0 ? liveIdx : 0;
}
let _subjectRendered = false;

window.addEventListener('hashchange', () => navigateToHash());

// ══════════════════════════════════════════════════════════
// MAIN ORCHESTRATOR
// ══════════════════════════════════════════════════════════
// Bumped on every selectTournament call; a render phase that wakes up to find
// a newer generation exits, so a quick run of arrow keys renders only the
// tournament the visitor stopped on.
let _renderGen = 0;

// Run the phases in order, each in its own task with a paint in between, so
// no single task holds the main thread for the whole render. Under 4x CPU
// throttling the old one-shot render was a 250-320 ms task behind a 120 ms
// timer; the phases are 60-130 ms each and the chart is on screen before the
// rest starts. The chain is abandoned when a newer generation has begun.
function _runRenderPhases(gen, phases) {
  const step = i => {
    if (gen !== _renderGen || i >= phases.length) return;
    phases[i]();
    requestAnimationFrame(() => setTimeout(() => step(i + 1), 0));
  };
  // The first phase gets its own task too, so it never extends the one that
  // called us: the deferred-script evaluation on first load, a keydown
  // handler on the arrow keys.
  setTimeout(() => step(0), 0);
}

// Phase A: what the visitor is looking at, without the chart. The renders run inside try/finally
// so a throw in any one of them can never strand the page on the skeleton
// loader again. That was the refresh bug: renderChart threw while Chart.js
// was still loading, the callback aborted before hideSkeletons(), and the
// sections stayed at opacity 0 until a reload. The error still surfaces in
// the console.
let _aboveTheFoldRendered = false;
function _renderAboveTheFold(t, sections) {
  try {
    renderDelta(t);
    renderHero(t);
    renderProgress(t);
    // The milestone strip is plain markup under the chart; drawing it here,
    // before the placeholders go, keeps the chart card from growing later.
    renderMilestones(t);
    // Scroll to the delta banner when the visitor switches tournaments. The
    // first render leaves the page at the top: on a phone the banner sits
    // under the hero, and a landing that opens half a screen down reads as
    // a jump.
    if (_aboveTheFoldRendered) {
      document.getElementById('deltaBanner').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    _aboveTheFoldRendered = true;
  } finally {
    // Hide skeleton loaders and reveal the sections whether or not every
    // render succeeded; a half-rendered page beats a blank one. One opacity
    // fade (19-motion.css), all sections together.
    hideSkeletons();
    sections.forEach(s => { s.style.opacity = ''; });
  }
}

// The chart is the one heavy render (Chart.js builds every point and reads
// the container's style), so it gets a task of its own after the hero has
// painted: the figure is on screen before the chart's work starts, and
// Chart.js reads a clean layout instead of forcing one.
function _renderMainChart(t) {
  renderChart(t);
}

// The Season's cards and the Forecast's Up Next, which follow every
// selection.
function _renderCards() {
  renderMiniCards();
  renderUpNext();
}

// Everything below the chart, one chart per task so none of them holds the
// main thread past a frame.
function _renderHistoricalChart(t) {
  renderHistorical(t);
}
function _renderCurveAndFees(t) {
  renderRegCurve(t);
  renderFees(t);
  // Hide fee panel for historical tournaments (no fee data)
  const feePanel = document.getElementById('feePanel');
  if (feePanel) feePanel.style.display = (!t.early_bird_fee && !t.regular_fee && !t.onsite_fee) ? 'none' : '';
}

// The Forecast's sections a tournament switch fades (19-motion.css).
const FORECAST_FADE_SECTIONS = '#panel-predictions :is(.pace-note, .chart-card, .sect, .up-next)';

function selectTournament(index, skipHash) {
  selectedIndex = index;
  _subjectRendered = true;
  const t = TOURNAMENT_DATA.tournaments[index];
  const gen = ++_renderGen;
  if (!skipHash) updateHash();

  // The top bar's subject (shell.js) and the page title
  reflectSubject(t);
  document.title = `${t.family} ${t.year} · CCA Entry Predictor`;

  // The sections fade out here and back in once the fold has rendered.
  const sections = document.querySelectorAll(FORECAST_FADE_SECTIONS);
  sections.forEach(s => s.style.opacity = '0');

  _runRenderPhases(gen, [
    () => _renderAboveTheFold(t, sections),
    () => _renderMainChart(t),
    () => _renderCards(),
    () => _renderHistoricalChart(t),
    () => _renderCurveAndFees(t),
  ]);
}

// renderModelHealth fills static spans from PERFORMANCE_SUMMARY; once is
// enough, whether the idle pass or an early visit to the About tab gets there
// first.
let _modelHealthRendered = false;
function ensureModelHealth() {
  if (_modelHealthRendered) return;
  _modelHealthRendered = true;
  renderModelHealth();
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
        msg = 'The update pipeline failed on its last run. Showing the last '
            + 'complete data, from ' + ts + '. Counts and predictions below may be out of date.';
      } else if (freshness.reason === 'age' && !TOURNAMENT_DATA.is_stale) {
        // Nothing flagged this, but the browser clock says the data is old,
        // the case a mid-run crash used to hide entirely.
        const days = Math.floor(freshness.ageHours / 24);
        msg = 'This data is ' + (days >= 1 ? days + ' day' + (days === 1 ? '' : 's') : Math.round(freshness.ageHours) + ' hours')
            + ' old (generated ' + ts + '). The nightly update has not completed since then.';
      } else {
        msg = 'Predictions last updated ' + ts + '. Live data temporarily unavailable.';
      }
      bannerText.textContent = msg;
      // A note at the top of the main column, in the flow: nothing to push down.
      banner.hidden = false;
    }
  }

  // The About tab's telemetry and the tournament table below the fold are
  // not on the first-paint path: they render when the main thread is idle,
  // or on demand if the visitor gets there first (switchPageTab, the table's
  // own sort and filter handlers).
  _idle(ensureModelHealth);
  _idle(renderAllTournaments);
  document.getElementById('lastUpdated').textContent = fmtDateTimeLong(TOURNAMENT_DATA.generated_time || TOURNAMENT_DATA.generated);

  renderSummaryBar();

  // The sections open per their data-open on load and when the width class
  // changes; print opens every one and restores them after.
  syncSectionDisclosure();
  window.addEventListener('resize', () => syncSectionDisclosure());
  window.addEventListener('beforeprint', () => {
    document.querySelectorAll('details.sect').forEach(d => { d.dataset.wasOpen = d.open ? '1' : '0'; d.open = true; });
  });
  window.addEventListener('afterprint', () => {
    document.querySelectorAll('details.sect').forEach(d => { if ('wasOpen' in d.dataset) d.open = d.dataset.wasOpen === '1'; });
  });

  // Set default sort indicator on the date column
  const defaultSortTh = document.querySelector('.tourney-table th[data-act="sort-table"][data-col="date"]');
  if (defaultSortTh) defaultSortTh.classList.add('asc');

  // Part B: Deep link from hash, or the default tournament
  if (!navigateToHash()) selectTournament(_defaultTournamentIndex());
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
  if (sheetIsOpen()) return;
  // L5: never hijack arrows while typing (INPUT/TEXTAREA/contenteditable) or on
  // any tab other than Predictions — otherwise arrows in the Ask box silently
  // switch tournaments and rewrite the hash.
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return;
  if (typeof _currentTab !== 'undefined' && _currentTab !== 'predictions') return;
  const n = TOURNAMENT_DATA.tournaments.length;
  if (e.key === 'ArrowRight') {
    e.preventDefault();
    selectTournament((selectedIndex + 1) % n);
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    selectTournament((selectedIndex - 1 + n) % n);
  }
});

applyOverrides();

init();
