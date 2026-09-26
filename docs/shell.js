// shell.js — the application shell around the views: the top bar's subject
// (the selected tournament with its status and T-minus), the four-item nav
// (in the top bar on a desktop, the bottom bar on a phone: one element,
// styled apart in shell.css), the two group sheets behind Model and Tools,
// the view title with the Forecast's action row, and the toast. app.js's
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
  puzzles: 'Puzzles',
};
// The views each nav group holds; the group reads as open while one of its
// views is. The sheets in index.html list the same views in the same order.
const NAV_GROUPS = {
  model: ['performance', 'audit', 'about'],
  tools: ['compare', 'ask', 'email', 'puzzles'],
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
  document.querySelectorAll('#primaryNav [data-act="open-group-sheet"]').forEach(b => {
    const on = b.dataset.group === group;
    b.classList.toggle('active', on);
    if (on) b.setAttribute('aria-current', 'true');
    else b.removeAttribute('aria-current');
  });
  // The Forecast is titled by its subject; every other view by its name. The
  // dateline and the action row (Add to Compare) belong to the Forecast alone.
  const title = document.getElementById('viewTitle');
  if (title) title.textContent = (tab === 'predictions' && _subjectTitle) ? _subjectTitle : (VIEW_TITLES[tab] || '');
  const dateline = document.getElementById('viewDateline');
  if (dateline) dateline.hidden = tab !== 'predictions' || !_subjectTitle;
  const actions = document.getElementById('viewActions');
  if (actions) actions.hidden = tab !== 'predictions';
}

// ── Group sheets ──
// Model and Tools open their sheet under the nav item on a desktop and from
// the foot on a phone; the rows are page-tab buttons like the nav's own.
function openGroupSheet(group, anchor) {
  openSheet(group + 'Sheet', anchor);
}

// ── The subject ──
// The top bar names the selected tournament with its status pill and, for
// an upcoming one, its T-minus; the Forecast's title and dateline follow it.
// selectTournament calls this on every change.
let _subjectTitle = '';

function _subjectDateline(t) {
  const parts = [t.status === 'live' ? 'Upcoming' : t.status === 'complete' ? 'Complete' : 'Historical'];
  if (t.status === 'live' && t.days_remaining != null) parts.push(`<span class="num">T-${t.days_remaining}</span>`);
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
  const pill = document.getElementById('tournStatus');
  if (pill) {
    const live = t.status === 'live';
    const kind = live ? 'live' : t.status === 'complete' ? 'complete' : 'hist';
    pill.className = 'pill pill-' + kind;
    pill.innerHTML = (live ? '<span class="live-dot"></span>' : '') +
      (live ? 'Upcoming' : t.status === 'complete' ? 'Complete' : 'Historical');
    pill.hidden = false;
  }
  const tminus = document.getElementById('tournTminus');
  if (tminus) {
    const show = t.status === 'live' && t.days_remaining != null;
    if (show) tminus.textContent = 'T-' + t.days_remaining;
    tminus.hidden = !show;
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
