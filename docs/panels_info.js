// panels_info.js — the pace note, the progress lines folded under the hero's
// figures, the milestone strip under the chart and the fee panel.

// ══════════════════════════════════════════════════════════
// PACE NOTE
// ══════════════════════════════════════════════════════════
// The verdict against last year at the top of the Forecast, printed on the
// stock its state calls for: blue for ahead, pink for behind, yellow for on
// pace or no comparison (controls.css .note, forecast.css .pace-note).
// Returns the kind, so the multi-year line can tell whether it adds anything.
function _paceNote(kind, main, sub, figure) {
  const banner = document.getElementById('deltaBanner');
  const stock = { ahead: 'note-blue', behind: 'note-ember', even: 'note-amber', plain: '' }[kind] || '';
  banner.className = `note pace-note ${stock}`.trim();
  document.getElementById('deltaMain').textContent = main;
  document.getElementById('deltaSub').textContent = sub;
  const val = document.getElementById('deltaValue');
  val.textContent = figure;
  val.className = `pace-figure num pace-${kind === 'plain' ? 'even' : kind}`;
  return kind;
}

// The multi-year line under the verdict, printed only when it disagrees with
// it: "Behind 2025 Pace" over "Behind the 4-year pace" says one thing twice.
// Verdict-first phrasing ("Ahead of the 4-year pace") so the eye lands on the
// direction first.
const PACE_ALERT_KIND = { above_pace: 'ahead', below_pace: 'behind', on_pace: 'even' };
function _paceContext(t, kind) {
  const ctx = document.getElementById('deltaContext');
  if (!ctx) return;
  const alert = getPaceAlert(t);
  if (!alert || !alert.status || PACE_ALERT_KIND[alert.status] === kind) { ctx.textContent = ''; return; }
  const verdict = alert.status === 'above_pace' ? 'Ahead of'
                : alert.status === 'below_pace' ? 'Behind'
                : 'On';
  // Prefer the explicit n_years field (pipeline 2026-05-17+); fall back to
  // the older message string for a stale website_data.json.
  const n = alert.n_years || ((alert.message || '').match(/(\d+)-year/) || [])[1];
  const yrs = n ? `${n}-year` : 'multi-year';
  const dev = alert.deviation_pct;
  ctx.textContent = `${verdict} the ${yrs} pace (${dev > 0 ? '+' : ''}${dev}%)`;
}

// A finished event against its past editions. The figure above already says
// the final count, so the note does not repeat it.
function _renderDeltaDone(t) {
  if (!t.historical || t.historical.length === 0) {
    return _paceNote('plain', 'Complete', 'No prior editions on record', '');
  }
  const n = t.historical.length;
  const avg = t.historical.reduce((s, h) => s + h.count, 0) / n;
  const diff = (t.current_count - avg) / avg * 100;
  const absDiff = Math.abs(diff).toFixed(1);
  const sub = `vs a ${fmt(Math.round(avg))} average over ${n} edition${n === 1 ? '' : 's'}`;
  if (diff > 5) return _paceNote('ahead', 'Above Average', sub, `+${absDiff}%`);
  if (diff < -5) return _paceNote('behind', 'Below Average', sub, `-${absDiff}%`);
  return _paceNote('even', 'On Par', sub, `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`);
}

// Live: compare to last year's count at the same days-to-event mark. Prefer
// the explicit prior_year_pace.count_at_same_point, derived from last year's
// actual daily registrations on this calendar day; fall back to the
// family-average curve only when that field is missing (no prior daily data
// for this family), since a curve estimate can drift when the prior year's
// curve was unusual.
function _renderDeltaLive(t) {
  if (t.historical && t.historical.length > 0) {
    const lastYr = t.historical[t.historical.length - 1];
    const priorPace = t.prior_year_pace;
    const lastYrAtT = (priorPace && priorPace.count_at_same_point != null)
      ? priorPace.count_at_same_point
      : (t.registration_curve
          ? Math.round(lastYr.count * interpCurve(t.registration_curve, t.days_remaining))
          : null);
    const lastYrLabel = priorPace?.year ?? lastYr.year;
    if (lastYrAtT && lastYrAtT > 0) {
      const diff = t.current_count - lastYrAtT;
      const absPct = Math.abs(diff / lastYrAtT * 100).toFixed(1);
      const compared = `${fmt(t.current_count)} now vs ${fmt(lastYrAtT)} at T-${t.days_remaining} in ${lastYrLabel}`;
      if (diff > 0) return _paceNote('ahead', `Ahead of ${lastYrLabel} Pace`, compared, `+${absPct}%`);
      if (diff < 0) return _paceNote('behind', `Behind ${lastYrLabel} Pace`, compared, `-${absPct}%`);
      return _paceNote('even', `On ${lastYrLabel} Pace`, compared, '0%');
    }
  }

  // No historical comparison available
  return _paceNote('even', 'No Prior Edition',
    _eventStarted(t) ? `${fmt(t.current_count)} entries · online registration open` : `${fmt(t.current_count)} entries so far`,
    `T-${t.days_remaining}`);
}

function renderDelta(t) {
  _paceContext(t, isDone(t) ? _renderDeltaDone(t) : _renderDeltaLive(t));
}

// Has a live event's first day passed? Its countdown then runs to the close
// of online registration, not to the event.
function _eventStarted(t) {
  return !!t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
}

// ══════════════════════════════════════════════════════════
// PROGRESS LINES (folded under Registered and Days to Event)
// ══════════════════════════════════════════════════════════
// The bar and one label: "21% of forecast".
function _foldHTML(pct, of) {
  return `<div class="fold-track" aria-hidden="true"><div class="fold-fill" style="width:${pct}%"></div></div>
    <div class="fold-sub"><span class="num">${pct}%</span> of ${of}</div>`;
}

function renderProgress(t) {
  const cur = document.getElementById('kpiCurrentFold');
  const days = document.getElementById('kpiDaysFold');
  if (!cur || !days) return;
  if (isDone(t) || !t.daily_data || t.daily_data.length === 0) { cur.innerHTML = ''; days.innerHTML = ''; return; }

  // v3 P3: span the registration window from its real start date to the event,
  // not from the tail of the data array. The old form (last point's day index
  // plus days_remaining) silently assumed the last scrape happened today, so a
  // stale or gappy tail shortened the window and this line contradicted the
  // pace note rendered from the same card.
  let totalDays;
  if (t.daily_start_date && t.event_start) {
    totalDays = daysBetween(t.daily_start_date, t.event_start);
  }
  if (!totalDays || totalDays <= 0) {
    totalDays = t.daily_data[t.daily_data.length - 1][0] + t.days_remaining || 120;
  }
  const elapsed = Math.max(0, totalDays - t.days_remaining);
  const timePct = Math.min(100, (elapsed / totalDays * 100)).toFixed(0);
  const regPct = Math.min(100, (t.current_count / t.point_estimate * 100)).toFixed(0);
  cur.innerHTML = _foldHTML(regPct, 'forecast');
  days.innerHTML = _foldHTML(timePct, 'registration window');
}

// ══════════════════════════════════════════════════════════
// MILESTONE STRIP (under the chart)
// ══════════════════════════════════════════════════════════
// Today, then the early bird while it is ahead and the nearest checkpoints,
// then the event day: at most six stops on one rule, each with its date and
// the entries expected by then. A finished or started event has none.
const MILESTONE_CHECKPOINTS = [
  [60, '60 Days Out'], [42, '6 Weeks Out'], [28, '4 Weeks Out'], [14, '2 Weeks Out'],
  [7, '1 Week Out'], [3, '3 Days Out'], [1, 'Day Before'],
];
const MILESTONE_MIDDLE_STOPS = 4;

// The stops between today and the event day, soonest first: the early bird
// when it is still ahead, then the checkpoints nearest to today.
function _milestoneMiddle(t) {
  const early = [];
  let ebDB = null;
  if (hasValidEarlyBird(t)) {
    ebDB = daysBetween(t.early_bird_deadline, t.event_start);
    if (ebDB <= t.days_remaining) early.push({ db: ebDB, label: 'Early Bird' });
  }
  const checkpoints = MILESTONE_CHECKPOINTS
    .filter(([db]) => db < t.days_remaining && db !== ebDB)
    .map(([db, label]) => ({ db, label }))
    .slice(0, MILESTONE_MIDDLE_STOPS - early.length);
  return early.concat(checkpoints).sort((a, b) => b.db - a.db);
}

function _milestoneStops(t) {
  // The curve's share at a lead time, floored at today's count: a checkpoint
  // cannot expect fewer entries than are already in.
  const expected = db => Math.max(t.current_count,
    Math.round(t.point_estimate * interpCurve(t.registration_curve, db)));
  return [
    { label: 'Today', date: fmtDate(TOURNAMENT_DATA.generated), count: fmt(t.current_count), now: true },
    ..._milestoneMiddle(t).map(m => ({
      label: m.label, date: DATE_FMT.short.format(addDays(t.event_start, -m.db)), count: `~${fmt(expected(m.db))}`,
    })),
    { label: 'Event Day', date: fmtDate(t.event_start), count: `~${fmt(t.point_estimate)}` },
  ];
}

function renderMilestones(t) {
  const el = document.getElementById('milestoneStrip');
  if (!el) return;
  if (isDone(t) || !t.event_start || _eventStarted(t)) { el.innerHTML = ''; return; }
  const stops = _milestoneStops(t);
  el.innerHTML = `<div class="ms-strip" role="list" aria-label="Milestones" style="--stops:${stops.length}">
    <div class="ms-line" aria-hidden="true"></div>` +
    stops.map(s => `<div class="ms-node${s.now ? ' ms-now' : ''}" role="listitem">
      <div class="ms-dot" aria-hidden="true"></div>
      <div class="ms-node-label">${s.label}</div>
      <div class="ms-node-date">${s.date}</div>
      <div class="ms-node-count">${s.count}</div>
    </div>`).join('') + '</div>';
}

// ══════════════════════════════════════════════════════════
// FEE PANEL
// ══════════════════════════════════════════════════════════
function renderFees(t) {
  const el = document.getElementById('feeContent');
  if (!t.early_bird_fee && !t.regular_fee && !t.onsite_fee) {
    el.innerHTML = '<div class="fee-empty">Fee data not available for this tournament.</div>';
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
    html += `<div class="fee-current">
      <div class="fee-current-label">Current Rate</div>
      <div class="fee-current-amount">$${currentFee}</div>
      <div class="fee-current-status">${feeStatus}</div>
    </div>`;
  }
  const cell = (cls, label, fee) => `<div class="fee-cell ${cls}"><div class="fee-cell-label">${label}</div><div class="fee-cell-amount">$${fee}</div></div>`;
  html += '<div class="fee-grid">';
  if (t.early_bird_fee && t.regular_fee && t.early_bird_fee < t.regular_fee) html += cell('fee-cell-early', 'Early Bird', t.early_bird_fee);
  if (t.regular_fee) html += cell('fee-cell-regular', 'Regular', t.regular_fee);
  if (t.onsite_fee) html += cell('fee-cell-onsite', 'On-Site', t.onsite_fee);
  html += '</div>';
  el.innerHTML = html;
}
