// shell.js — the application shell around the views: the view title under
// the top bar, the rail (the side rail on a desktop, the bottom bar on a
// phone; one element, styled apart in shell.css), the rail's collapse
// toggle, the More sheet that lists the views the bottom bar has no room
// for, and the toast. app.js's switchPageTab calls reflectNav() after every
// view change; the controls are wired through actions.js.

const VIEW_TITLES = {
  predictions: 'Forecast',
  season: 'Season',
  performance: 'Performance',
  compare: 'Compare',
  ask: 'Ask',
  email: 'Email',
  audit: 'Audit',
  about: 'About the Model',
  puzzles: 'Puzzles',
};
const RAIL_KEY = 'cep:rail';
const TOAST_MS = 2500;
let _toastTimer = null;
let _railCollapsed = false;
// Between the rail's own breakpoint and the wide layout the rail is always
// the 64 px icon rail; the stored choice applies from 1280 px up.
const _railNarrow = window.matchMedia('(min-width: 1024px) and (max-width: 1279px)');

function navButtons() {
  return Array.from(document.querySelectorAll('#rail [data-act="page-tab"]'));
}

// The bar pins four views; every other view sits behind More, which then
// reads as the open one.
function moreHolds(tab) {
  const btn = document.querySelector(`#rail [data-act="page-tab"][data-tab="${tab}"]`);
  return !!btn && btn.dataset.bar !== 'pinned';
}

function reflectNav(tab) {
  navButtons().forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  const more = document.getElementById('moreNav');
  if (more) more.classList.toggle('active', moreHolds(tab));
  const title = document.getElementById('viewTitle');
  if (title) title.textContent = VIEW_TITLES[tab] || '';
}

// ── Rail collapse ──
function applyRail() {
  const rail = document.getElementById('rail');
  const shell = document.querySelector('.app-shell');
  const toggle = document.getElementById('railToggle');
  if (!rail || !shell || !toggle) return;
  const collapsed = _railCollapsed || _railNarrow.matches;
  rail.classList.toggle('collapsed', collapsed);
  shell.classList.toggle('rail-collapsed', collapsed);
  toggle.setAttribute('aria-expanded', String(!_railCollapsed));
  const label = _railCollapsed ? 'Expand the Rail' : 'Collapse the Rail';
  toggle.setAttribute('aria-label', label);
  toggle.title = label;
  // An icon-only item names itself on hover and, for the keyboard, beside
  // the icon on focus (shell.css reads the title).
  rail.querySelectorAll('nav button').forEach(item => {
    if (collapsed) item.title = item.textContent.trim();
    else item.removeAttribute('title');
  });
}

function toggleRail() {
  _railCollapsed = !_railCollapsed;
  applyRail();
  try { localStorage.setItem(RAIL_KEY, _railCollapsed ? 'collapsed' : 'open'); } catch (_) {}
}

(function initRail() {
  try { _railCollapsed = localStorage.getItem(RAIL_KEY) === 'collapsed'; } catch (_) { _railCollapsed = false; }
  applyRail();
  if (typeof _railNarrow.addEventListener === 'function') _railNarrow.addEventListener('change', applyRail);
})();

// ── More sheet ──
// The rows are the nav's own buttons: the same icon markup, the same label,
// the same page-tab action, so who opens what is decided in one place.
function openMoreSheet() {
  const list = document.getElementById('moreSheetList');
  if (!list) return;
  const current = typeof _currentTab !== 'undefined' ? _currentTab : 'predictions';
  list.innerHTML = navButtons().filter(b => b.dataset.bar !== 'pinned').map(b => {
    const iconEl = b.querySelector('.nav-icon');
    const label = b.querySelector('b');
    const on = b.dataset.tab === current;
    return `<button type="button" class="sheet-row${on ? ' active' : ''}" data-act="page-tab" ` +
      `data-tab="${b.dataset.tab}"${on ? ' aria-current="page"' : ''}>` +
      `${iconEl ? iconEl.outerHTML : ''}<b>${esc(label ? label.textContent : b.dataset.tab)}</b></button>`;
  }).join('');
  openSheet('moreSheet');
}

// ── Toast ──
// One line, inverted, above the bottom bar on phones; kind is 'success' or
// 'error' (overlays.css). Replaces the Data Entry banner.
function showToast(text, kind) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = text;
  el.className = 'show' + (kind ? ' toast-' + kind : '');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, TOAST_MS);
}
