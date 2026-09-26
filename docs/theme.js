// theme.js — light/dark switching. Light is the default for everyone; dark
// is opt-in through the header toggle and persists in localStorage. The OS
// preference is deliberately not consulted (owner decision, 2026-09).
//
// boot.js sets the attribute before first paint; this file owns everything
// after: the toggle, the cross-fade, the meta theme-color, the Chart.js
// defaults, and rebuilding the charts that are on screen (canvases hold
// their painted colours, so they must be redrawn from the new PALETTE).

const THEME_KEY = 'cep:theme';
const THEME_FADE_MS = 200;
let _themeFadeTimer = null;

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function reflectTheme() {
  const theme = currentTheme();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--void').trim();
    if (bg) meta.setAttribute('content', bg);
  }
  const btn = document.getElementById('themeToggle');
  if (btn) {
    const next = theme === 'dark' ? 'Light' : 'Dark';
    btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    btn.setAttribute('aria-label', 'Switch to the ' + next + ' Theme');
    btn.title = 'Switch to the ' + next + ' Theme';
  }
}

// Chart.js reads these once per chart construction, so they must be set
// before the first render and again on every switch.
function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.color = PALETTE.tick;
  Chart.defaults.borderColor = PALETTE.grid;
  Chart.defaults.font.family = PALETTE.fontDisplay;
  if (_reduceMotion()) Chart.defaults.animation = false;
}

// Redraw whatever charts the active tab shows. Other tabs rebuild on their
// next switch, which they already do.
function rerenderVisibleCharts() {
  if (typeof TOURNAMENT_DATA === 'undefined') return;
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  const tab = typeof _currentTab !== 'undefined' ? _currentTab : 'predictions';
  if (tab === 'predictions' && t) {
    renderChart(t);
    renderHistorical(t);
    renderRegCurve(t);
  } else if (tab === 'performance' && typeof perfRender === 'function') {
    perfRender();
  } else if (tab === 'compare' && typeof renderCompareTab === 'function') {
    renderCompareTab();
  }
}

// opts.animate: cross-fade colours over THEME_FADE_MS (skipped under
// prefers-reduced-motion). opts.persist: store the choice (false for the
// print round-trip, which must not overwrite the user's preference).
function applyTheme(next, opts) {
  const o = opts || {};
  const animate = o.animate !== false && !_reduceMotion();
  const persist = o.persist !== false;
  const root = document.documentElement;

  if (animate) {
    root.classList.add('theme-switching');
    clearTimeout(_themeFadeTimer);
    _themeFadeTimer = setTimeout(() => root.classList.remove('theme-switching'), THEME_FADE_MS + 60);
  }
  root.setAttribute('data-theme', next === 'dark' ? 'dark' : 'light');
  if (persist) {
    try { localStorage.setItem(THEME_KEY, next === 'dark' ? 'dark' : 'light'); } catch (_) {}
  }
  reflectTheme();
  rebuildPalette();
  applyChartDefaults();

  // Canvases cannot transition, so fade the chart wraps out, redraw, fade in.
  const wraps = document.querySelectorAll('.chart-wrap, .chart-box, .chart-tile-body');
  if (animate && wraps.length) {
    wraps.forEach(w => { w.style.transition = 'opacity 120ms ease'; w.style.opacity = '0'; });
    setTimeout(() => {
      rerenderVisibleCharts();
      wraps.forEach(w => { w.style.opacity = ''; });
      setTimeout(() => wraps.forEach(w => { w.style.transition = ''; }), 140);
    }, 120);
  } else {
    rerenderVisibleCharts();
  }
}

function toggleTheme() {
  applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
}

// Print is always light. Flip without persisting, then restore.
let _themeBeforePrint = null;
window.addEventListener('beforeprint', () => {
  if (currentTheme() === 'dark') {
    _themeBeforePrint = 'dark';
    applyTheme('light', { animate: false, persist: false });
  }
});
window.addEventListener('afterprint', () => {
  if (_themeBeforePrint) {
    applyTheme(_themeBeforePrint, { animate: false, persist: false });
    _themeBeforePrint = null;
  }
});

// First paint already has the attribute from boot.js; this syncs the button
// and theme-color and sets the Chart.js defaults before app.js renders.
reflectTheme();
applyChartDefaults();
