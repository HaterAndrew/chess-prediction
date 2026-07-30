// panels_cal.js — calendar timeline, section disclosure and mini cards,
// split verbatim from app.js (C13).

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
