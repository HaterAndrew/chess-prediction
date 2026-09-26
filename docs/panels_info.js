// panels_info.js — the pace note, the progress lines folded under the hero's
// figures, the key milestones, the milestone strip and the fee panel.

// ══════════════════════════════════════════════════════════
// PACE NOTE
// ══════════════════════════════════════════════════════════
// The verdict against last year at the top of the Forecast, printed on the
// stock its state calls for: blue for ahead, pink for behind, yellow for on
// pace or no comparison (controls.css .note, forecast.css .pace-note).
function _paceNote(kind, main, sub, figure) {
  const banner = document.getElementById('deltaBanner');
  const stock = { ahead: 'note-blue', behind: 'note-ember', even: 'note-amber', plain: '' }[kind] || '';
  banner.className = `note pace-note ${stock}`.trim();
  document.getElementById('deltaMain').textContent = main;
  document.getElementById('deltaSub').textContent = sub;
  const val = document.getElementById('deltaValue');
  val.textContent = figure;
  val.className = `pace-figure num pace-${kind === 'plain' ? 'even' : kind}`;
}

// The multi-year line under the verdict. Verdict-first phrasing ("Tracking
// ahead of 4-year aggregate pace") so the eye lands on the direction first.
function _paceContext(t) {
  const ctx = document.getElementById('deltaContext');
  if (!ctx) return;
  const alert = getPaceAlert(t);
  if (!alert || !alert.status) { ctx.textContent = ''; return; }
  const verdict = alert.status === 'above_pace' ? 'ahead of'
                : alert.status === 'below_pace' ? 'behind'
                : 'on pace with';
  // Prefer the explicit n_years field (pipeline 2026-05-17+); fall back to
  // the older message string for a stale website_data.json.
  const n = alert.n_years || ((alert.message || '').match(/(\d+)-year/) || [])[1];
  const yrs = n ? `${n}-year aggregate` : 'multi-year aggregate';
  const dev = alert.deviation_pct;
  ctx.textContent = `Tracking ${verdict} ${yrs} pace (${dev > 0 ? '+' : ''}${dev}%)`;
}

// The recent daily pace, for the verdict's second line.
function _recentPaceSuffix(t) {
  if (!t.daily_data || t.daily_data.length < 3) return '';
  const recent = t.daily_data.slice(-7);
  if (recent.length < 2) return '';
  const daySpan = recent[recent.length - 1][0] - recent[0][0];
  const regSpan = recent[recent.length - 1][1] - recent[0][1];
  return daySpan > 0 ? ` · ${(regSpan / daySpan).toFixed(1)}/day recent pace` : '';
}

function _renderDeltaDone(t) {
  if (!t.historical || t.historical.length === 0) {
    _paceNote('plain', `${t.family} ${t.year}: Complete`, `Final count: ${fmt(t.current_count)} entries`, '');
    return;
  }
  const avg = t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length;
  const diff = (t.current_count - avg) / avg * 100;
  const absDiff = Math.abs(diff).toFixed(1);
  if (diff > 5) {
    _paceNote('ahead', `${t.family} ${t.year}: Above Average`,
      `${fmt(t.current_count)} entries · ${absDiff}% above historical average of ${fmt(Math.round(avg))}`, `+${absDiff}%`);
  } else if (diff < -5) {
    _paceNote('behind', `${t.family} ${t.year}: Below Average`,
      `${fmt(t.current_count)} entries · ${absDiff}% below historical average of ${fmt(Math.round(avg))}`, `-${absDiff}%`);
  } else {
    _paceNote('even', `${t.family} ${t.year}: On Par`,
      `${fmt(t.current_count)} entries · In line with historical average of ${fmt(Math.round(avg))}`,
      `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`);
  }
}

function renderDelta(t) {
  _paceContext(t);
  if (isDone(t)) { _renderDeltaDone(t); return; }

  // Live: compare to last year's count at the same days-to-event mark. Prefer
  // the explicit prior_year_pace.count_at_same_point, derived from last
  // year's actual daily registrations on this calendar day; fall back to the
  // family-average curve only when that field is missing (no prior daily
  // data for this family), since a curve estimate can drift when the prior
  // year's curve was unusual.
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
      const compared = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at the same days-to-event mark in ${lastYrLabel}${_recentPaceSuffix(t)}`;
      if (diff > 0) _paceNote('ahead', `Tracking ahead of ${lastYrLabel} pace`, compared, `+${absPct}%`);
      else if (diff < 0) _paceNote('behind', `Tracking behind ${lastYrLabel} pace`, compared, `-${absPct}%`);
      else _paceNote('even', `Tracking on pace with ${lastYrLabel}`, `${fmt(t.current_count)} registered${_recentPaceSuffix(t)}`, '0%');
      return;
    }
  }

  // No historical comparison available
  const evStarted = t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const countdown = evStarted
    ? `${t.days_remaining} days of online registration left`
    : `${t.days_remaining} days until event`;
  _paceNote('even', `${t.family}: Registration in progress`,
    `${fmt(t.current_count)} entries registered · ${countdown} · predicted final: ${fmt(t.point_estimate)}`,
    `T-${t.days_remaining}`);
}

// ══════════════════════════════════════════════════════════
// PROGRESS LINES (folded under Registered and Days to Event)
// ══════════════════════════════════════════════════════════
function _foldHTML(label, pct, sub) {
  return `<div class="fold-head"><span>${label}</span><span class="num">${pct}%</span></div>
    <div class="fold-track" aria-hidden="true"><div class="fold-fill" style="width:${pct}%"></div></div>
    <div class="fold-sub">${sub}</div>`;
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
  cur.innerHTML = _foldHTML('Entries Received', regPct, `${fmt(t.current_count)} of ~${fmt(t.point_estimate)}`);
  days.innerHTML = _foldHTML('Time Elapsed', timePct, `${elapsed} of ${totalDays} days`);
}

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
      <div class="timeline-node"><div class="timeline-dot past"></div><div class="timeline-label">Final Count</div><div class="timeline-date timeline-figure">${fmt(t.current_count)}</div></div>
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
