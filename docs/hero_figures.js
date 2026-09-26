// hero_figures.js — the hero cell's three figures (Registered, Days to Event,
// 7-Day Pace) and the week's bars. renderHero (hero_kpi.js) calls the
// renderers here; renderProgress (panels_info.js) folds the progress lines
// into the first two figures after it.

function _kpiHTML(label, value, sub, cls, foldId) {
  return `<div class="kpi-label">${label}</div>
    <div class="kpi-value${cls ? ' ' + cls : ''}">${value}</div>
    <div class="kpi-sub">${sub}</div>${foldId ? `<div class="kpi-fold" id="${foldId}"></div>` : ''}`;
}

// The three figures: Registered, Days to Event, 7-Day Pace. A finished event
// keeps the Event Date only: its final count is the figure above and the
// pace note already sets it against the average.
function _renderHeroFigures(t, done) {
  const cur = document.getElementById('kpiCurrent');
  const pace = document.getElementById('kpiPace');
  cur.hidden = done;
  pace.hidden = done;
  cur.innerHTML = done ? '' : _kpiHTML('Registered', fmt(t.current_count), 'entries', 'v-blue', 'kpiCurrentFold');

  // Once the event has started, the live countdown is to online-registration
  // close (the 2-day schedule), not to an event start that already passed.
  const evStarted = !done && _eventStarted(t);
  let daysLabel, daysValue, daysSub, daysClass = '';
  if (done) {
    daysLabel = 'Event Date';
    daysValue = fmtDate(t.event_start);
    daysSub = t.event_end && t.event_end !== t.event_start ? 'to ' + fmtDate(t.event_end) : '';
    daysClass = 'kpi-value-text';
  } else if (evStarted) {
    daysLabel = 'Days to Reg. Close';
    daysValue = t.days_remaining;
    daysSub = t.registration_close ? fmtDate(t.registration_close) : 'event underway';
  } else {
    daysLabel = 'Days to Event';
    daysValue = t.days_remaining;
    daysSub = t.days_remaining === 1 ? 'day' : 'days';
  }
  if (!done && t.days_remaining <= 7) daysClass = 'v-red';
  document.getElementById('kpiDays').innerHTML = _kpiHTML(daysLabel, daysValue, daysSub, daysClass, 'kpiDaysFold');

  if (done) { pace.innerHTML = ''; return; }
  let paceHtml = '';
  if (t.daily_data && t.daily_data.length >= 3) {
    const recent = t.daily_data.slice(-7);
    const daySpan = recent[recent.length - 1][0] - recent[0][0];
    const regSpan = recent[recent.length - 1][1] - recent[0][1];
    const rate = (daySpan > 0 ? regSpan / daySpan : 0).toFixed(1);
    paceHtml = _kpiHTML('7-Day Pace', rate, 'entries / day', '');
  }
  pace.innerHTML = paceHtml || _kpiHTML('7-Day Pace', '–', 'No pace data yet', 'kpi-value-text');
}

// ── Last 7 days: one bar per real calendar day (v3 P1). Each bar carries its
// own date, derived from the point's day_from_start against the exported
// daily_start_date anchor, never from its position in the array. Days
// covered by a scrape gap are spread across the gap and marked, so a
// multi-day jump can no longer be drawn as a single day's registrations.
// The bars scale against the busiest single day of the whole registration,
// not the week's own maximum: a +2 day in a week whose record is +9 draws at
// 22%, not full width. A day with no registrations draws no bar. ──
function _renderWeekBars(t, done) {
  const weekEl = document.getElementById('weekBreakdown');
  const barsEl = document.getElementById('weekBars');
  if (done || !t.daily_data || t.daily_data.length < 2) { weekEl.style.display = 'none'; return; }
  const ivs = (typeof DailySeries !== 'undefined') ? DailySeries.intervals(t, { isLive: !done }) : [];
  const days = [];      // {n, date, estimated}
  for (const iv of ivs) {
    const perDay = iv.added / iv.span;
    for (let g = 0; g < iv.span; g++) {
      const d = (typeof DailySeries !== 'undefined') ? DailySeries.pointDate(t, iv.fromDay + g + 1) : null;
      days.push({ n: Math.round(perDay), date: d, estimated: iv.isGap });
    }
  }
  const seriesMax = Math.max(...days.map(o => o.n), 1);
  while (days.length > 7) days.shift();
  if (days.length === 0 || days.every(o => o.n === 0)) {
    // No recent activity: a quiet placeholder keeps the column from collapsing.
    barsEl.innerHTML = '<div class="hero-week-empty">No registrations in the last 7 days</div>';
    weekEl.style.display = '';
    return;
  }
  if (days.length < 2) { weekEl.style.display = 'none'; return; }
  // The busiest-day mark only considers observed days: an average spread
  // across a scrape gap is not evidence that that day was the peak.
  const observed = days.filter(o => !o.estimated).map(o => o.n);
  const maxObserved = observed.length ? Math.max(...observed) : null;
  barsEl.innerHTML = days.map(o => {
    const label = (o.date && typeof DailySeries !== 'undefined') ? DailySeries.fmtPointDate(o.date) : '';
    const pct = (o.n / seriesMax) * 100;
    const isPeak = !o.estimated && maxObserved !== null && o.n === maxObserved;
    const tip = o.estimated ? ' title="Estimated: this day was covered by a gap in scraping"' : '';
    return `<div class="week-row${o.estimated ? ' week-est' : ''}"${tip}>
      <span class="week-date">${label}</span>
      <div class="week-track" aria-hidden="true"><div class="week-fill" style="width:${pct}%"></div></div>
      <span class="week-n${isPeak ? ' week-peak' : ''}">${o.estimated ? '~' : '+'}${o.n}</span>
    </div>`;
  }).join('');
  if (days.some(o => o.estimated)) {
    barsEl.innerHTML += '<div class="week-note">~ estimated across a gap in scraping</div>';
  }
  weekEl.style.display = '';
}
