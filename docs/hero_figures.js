// hero_figures.js — the hero cell's three figures (Registered, Days to Event,
// 7-Day Pace), the week's bars and the KPI row (renderKPIRow, which nothing
// calls today; it stays for the owner's call). renderHero (hero_kpi.js)
// calls the renderers here; renderProgress (panels_info.js) folds the
// progress lines into the first two figures after it.

function _kpiHTML(label, value, sub, cls, foldId) {
  return `<div class="kpi-label">${label}</div>
    <div class="kpi-value${cls ? ' ' + cls : ''}">${value}</div>
    <div class="kpi-sub">${sub}</div>${foldId ? `<div class="kpi-fold" id="${foldId}"></div>` : ''}`;
}

// The three figures: Registered, Days to Event, 7-Day Pace.
function _renderHeroFigures(t, done) {
  document.getElementById('kpiCurrent').innerHTML =
    _kpiHTML('Registered', fmt(t.current_count), done ? 'Final' : 'as of today', 'v-blue', 'kpiCurrentFold');

  // Once the event has started, the live countdown is to online-registration
  // close (the 2-day schedule), not to an event start that already passed.
  const evStarted = !done && t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  let daysLabel, daysValue, daysSub, daysClass = '';
  if (done) {
    daysLabel = 'Event Date';
    daysValue = fmtDate(t.event_start);
    daysSub = t.event_end ? fmtDate(t.event_start) + ' – ' + fmtDate(t.event_end) : '';
    daysClass = 'kpi-value-text';
  } else if (evStarted) {
    daysLabel = 'Days to Reg. Close';
    daysValue = t.days_remaining;
    daysSub = t.registration_close ? fmtDate(t.registration_close) : 'event underway';
  } else {
    daysLabel = 'Days to Event';
    daysValue = t.days_remaining;
    daysSub = fmtDate(t.event_start);
  }
  if (!done && t.days_remaining <= 7) daysClass = 'v-red';
  document.getElementById('kpiDays').innerHTML = _kpiHTML(daysLabel, daysValue, daysSub, daysClass, 'kpiDaysFold');

  let paceHtml = '';
  if (!done && t.daily_data && t.daily_data.length >= 3) {
    const recent = t.daily_data.slice(-7);
    if (recent.length >= 2) {
      const daySpan = recent[recent.length - 1][0] - recent[0][0];
      const regSpan = recent[recent.length - 1][1] - recent[0][1];
      const rate = (daySpan > 0 ? regSpan / daySpan : 0).toFixed(1);
      paceHtml = _kpiHTML('7-Day Pace', rate, 'entries / day', '');
    }
  } else if (done && t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length);
    const diff = t.current_count - avg;
    const pct = ((diff / avg) * 100).toFixed(0);
    paceHtml = _kpiHTML('vs Average', `${diff >= 0 ? '+' : ''}${pct}%`, `hist avg: ${fmt(avg)}`, diff >= 0 ? 'v-blue' : 'v-red');
  }
  document.getElementById('kpiPace').innerHTML = paceHtml || _kpiHTML('Historical', '–', 'No pace data', 'kpi-value-text');
}

// 4th figure, progress to the predicted final. There is no #kpiProgress in
// the markup today; the renderer stays for the owner's call on it.
function _renderKpiProgress(t, done) {
  const kpiProg = document.getElementById('kpiProgress');
  if (!kpiProg) return;
  if (done) {
    // For complete tournaments, show YoY change vs last year
    const lastYr = emailLastYear ? emailLastYear(t) : null;
    if (lastYr && lastYr.count) {
      const diff = t.current_count - lastYr.count;
      const pct = ((diff / lastYr.count) * 100).toFixed(0);
      kpiProg.innerHTML = _kpiHTML(`vs ${lastYr.year}`, `${diff >= 0 ? '+' : ''}${pct}%`, `${fmt(lastYr.count)} prior`, diff >= 0 ? 'v-blue' : 'v-red');
    } else {
      kpiProg.innerHTML = _kpiHTML('Status', 'Final', fmtDate(t.event_start), 'v-blue kpi-value-text');
    }
  } else if (t.point_estimate > 0) {
    const pct = Math.min(100, Math.round(t.current_count / t.point_estimate * 100));
    const color = pct >= 40 && pct < 80 ? 'v-ink' : 'v-blue';
    kpiProg.innerHTML = _kpiHTML('Progress', `${pct}%`, 'of predicted', color);
  } else {
    kpiProg.innerHTML = _kpiHTML('Progress', '–', 'No prediction', 'kpi-value-text');
  }
}

// ── Last 7 days: one bar per real calendar day (v3 P1). Each bar carries its
// own date, derived from the point's day_from_start against the exported
// daily_start_date anchor, never from its position in the array. Days
// covered by a scrape gap are spread across the gap and marked, so a
// multi-day jump can no longer be drawn as a single day's registrations. ──
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
  while (days.length > 7) days.shift();
  if (days.length === 0 || days.every(o => o.n === 0)) {
    // No recent activity: a quiet placeholder keeps the column from collapsing.
    barsEl.innerHTML = '<div class="hero-week-empty">No registrations in the last 7 days</div>';
    weekEl.style.display = '';
    return;
  }
  if (days.length < 2) { weekEl.style.display = 'none'; return; }
  // The bar scale uses every day, but the busiest-day mark only considers
  // observed ones: an average spread across a scrape gap is not evidence
  // that that day was the peak.
  const maxNew = Math.max(...days.map(o => o.n), 1);
  const observed = days.filter(o => !o.estimated).map(o => o.n);
  const maxObserved = observed.length ? Math.max(...observed) : null;
  barsEl.innerHTML = days.map(o => {
    const label = (o.date && typeof DailySeries !== 'undefined') ? DailySeries.fmtPointDate(o.date) : '';
    const pct = Math.max((o.n / maxNew) * 100, 2);
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

// ── KPI Row ──
function renderKPIRow(t) {
  const el = document.getElementById('kpiRow');
  const cards = [];

  // % registered (only for upcoming tournaments)
  if (!isDone(t)) {
    const regPct = t.point_estimate > 0 ? (t.current_count / t.point_estimate * 100).toFixed(1) : '–';
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">% Registered</div>
      <div class="kpi-value v-blue">${regPct}%</div>
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
      <div class="kpi-value ${ebPassed ? 'v-red' : 'v-blue'}">${ebPassed ? 'Ended' : daysToEB + 'd'}</div>
      <div class="kpi-sub">${fmtDate(t.early_bird_deadline)}${t.early_bird_fee ? ' · $' + t.early_bird_fee : ''}</div>
    </div>`);
  }

  // Historical avg
  if (t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length);
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Past Average</div>
      <div class="kpi-value v-ink">${fmt(avg)}</div>
      <div class="kpi-sub">${t.historical.length} editions</div>
    </div>`);

    // Historical rank (for completed tournaments)
    if (isDone(t)) {
      const allCounts = [...t.historical.map(h => h.count), t.current_count].sort((a,b) => b - a);
      const rank = allCounts.indexOf(t.current_count) + 1;
      const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th';
      cards.push(`<div class="kpi-card">
        <div class="kpi-label">All-Time Rank</div>
        <div class="kpi-value ${rank <= 3 ? 'v-ink' : ''}">${rank}${suffix}</div>
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
      <div class="kpi-value v-ink">&plusmn;${widthPct}%</div>
      <div class="kpi-sub">${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}</div>
    </div>`);
  }

  // Regular fee
  if (t.regular_fee) {
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Regular Fee</div>
      <div class="kpi-value v-ink">$${t.regular_fee}</div>
      <div class="kpi-sub">${t.onsite_fee ? 'Onsite: $' + t.onsite_fee : ''}</div>
    </div>`);
  }

  el.innerHTML = cards.join('');
}
