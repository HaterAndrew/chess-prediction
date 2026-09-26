// shell.js — the application shell around the views: the top bar's subject
// (the selected tournament with one state tag), the four-item nav (in the
// top bar on a desktop, the bottom bar on a phone: one element, styled
// apart in shell.css), the Tools sheet, the view title with its dateline
// and action row, and the toast. app.js's
// switchPageTab calls reflectNav() after every view change and
// selectTournament calls reflectSubject(); the controls are wired through
// actions.js.

const VIEW_TITLES = {
  predictions: 'Forecast',
  season: 'Season',
  performance: 'Performance',
  compare: 'Compare',
  ask: 'Ask',
  email: 'Email',
  audit: 'Audit',
  about: 'About the Model',
};
// The views each nav group holds; the group reads as open while one of its
// views is. Model is Performance and the About view it links to; the Tools
// sheet in index.html lists its views in the same order.
const NAV_GROUPS = {
  model: ['performance', 'about'],
  tools: ['compare', 'ask', 'email', 'audit'],
};
const TOAST_MS = 2500;
let _toastTimer = null;

function navButtons() {
  return Array.from(document.querySelectorAll('#primaryNav [data-act="page-tab"], .group-sheet [data-act="page-tab"]'));
}

function navGroupOf(tab) {
  return Object.keys(NAV_GROUPS).find(g => NAV_GROUPS[g].includes(tab)) || null;
}

function reflectNav(tab) {
  navButtons().forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  const group = navGroupOf(tab);
  document.querySelectorAll('#primaryNav [data-group]').forEach(b => {
    if (b.dataset.tab === tab) return;  // the view's own button, marked above
    const on = b.dataset.group === group;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'true');
    else b.removeAttribute('aria-current');
  });
  // The Forecast is titled by its subject; every other view by its name. The
  // dateline belongs to the Forecast; the action row (the link to About) to
  // Performance.
  const title = document.getElementById('viewTitle');
  if (title) title.textContent = (tab === 'predictions' && _subjectTitle) ? _subjectTitle : (VIEW_TITLES[tab] || '');
  const dateline = document.getElementById('viewDateline');
  if (dateline) dateline.hidden = tab !== 'predictions' || !_subjectTitle;
  const actions = document.getElementById('viewActions');
  if (actions) actions.hidden = tab !== 'performance';
}

// ── Group sheets ──
// Tools opens its sheet under the nav item on a desktop and from
// the foot on a phone; the rows are page-tab buttons like the nav's own.
function openGroupSheet(group, anchor) {
  openSheet(group + 'Sheet', anchor);
}

// ── The subject ──
// The top bar names the selected tournament with one tag for its state: the
// T-minus while it is upcoming, else Complete or Historical. The Forecast's
// title and dateline (the dates and the venue) follow it.
// selectTournament calls this on every change.
let _subjectTitle = '';

function _subjectDateline(t) {
  const parts = [];
  if (t.event_start) {
    const span = (t.event_end && t.event_end !== t.event_start) ? `${fmtDate(t.event_start)} to ${fmtDate(t.event_end)}` : fmtDate(t.event_start);
    parts.push(`<span class="num">${span}</span>`);
  }
  const venue = [t.venue_city, t.venue_state].filter(Boolean).join(', ');
  if (venue) parts.push(esc(venue));
  return parts.join(' · ');
}

function reflectSubject(t) {
  _subjectTitle = `${t.family} ${t.year}`;
  const label = document.getElementById('tournLabel');
  if (label) {
    label.textContent = _subjectTitle;
    label.title = _subjectTitle;
  }
  const onForecast = typeof _currentTab === 'undefined' || _currentTab === 'predictions';
  const title = document.getElementById('viewTitle');
  if (title && onForecast) title.textContent = _subjectTitle;
  const dateline = document.getElementById('viewDateline');
  if (dateline) {
    dateline.innerHTML = _subjectDateline(t);
    dateline.hidden = !onForecast;
  }
  const tag = document.getElementById('tournStatus');
  if (tag) {
    if (t.status === 'live' && t.days_remaining != null) {
      tag.className = 'tourn-tminus';
      tag.innerHTML = '<span class="live-dot"></span>T-' + t.days_remaining;
    } else {
      tag.className = 'pill pill-' + (t.status === 'complete' ? 'complete' : t.status === 'live' ? 'live' : 'hist');
      tag.textContent = t.status === 'complete' ? 'Complete' : t.status === 'live' ? 'Upcoming' : 'Historical';
    }
    tag.hidden = false;
  }
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
