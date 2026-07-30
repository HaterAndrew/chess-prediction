// panels_info.js — delta banner, progress bars, timeline, milestones and
// fee panel renderers, split verbatim from app.js (C8).

// ══════════════════════════════════════════════════════════
// DELTA BANNER
// ══════════════════════════════════════════════════════════
function renderDelta(t) {
  const banner = document.getElementById('deltaBanner');
  const icon = document.getElementById('deltaIcon');
  const main = document.getElementById('deltaMain');
  const sub = document.getElementById('deltaSub');
  const ctx = document.getElementById('deltaContext');
  const val = document.getElementById('deltaValue');

  // Multi-year at-T context — stakeholder-requested sub-line under the YoY
  // headline. Verdict-first phrasing ("Tracking [ahead/behind/on pace] with
  // N-year pace") so the eye lands on the direction before parsing the %.
  if (ctx) {
    const alert = getPaceAlert(t);
    if (alert && alert.status) {
      const verdict = alert.status === 'above_pace' ? 'ahead of'
                    : alert.status === 'below_pace' ? 'behind'
                    : 'on pace with';
      // Prefer the explicit n_years field (pipeline 2026-05-17+); fall back
      // to regex on the older message string for any stale website_data.json.
      const n = alert.n_years || ((alert.message || '').match(/(\d+)-year/) || [])[1];
      const yrs = n ? `${n}-year aggregate` : 'multi-year aggregate';
      const dev = alert.deviation_pct;
      const devStr = (dev > 0 ? `+${dev}` : `${dev}`) + '%';
      ctx.textContent = `Tracking ${verdict} ${yrs} pace (${devStr})`;
    } else {
      ctx.textContent = '';
    }
  }

  if (isDone(t)) {
    // Compare to historical average
    if (t.historical && t.historical.length > 0) {
      const avg = t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length;
      const diff = ((t.current_count - avg) / avg * 100);
      const absDiff = Math.abs(diff).toFixed(1);
      if (diff > 5) {
        banner.className = 'delta-banner green';
        icon.innerHTML = '&#9650;';
        main.textContent = `${t.family} ${t.year}: Above Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% above historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `+${absDiff}%`;
        val.className = 'delta-value green';
      } else if (diff < -5) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `${t.family} ${t.year}: Below Average`;
        sub.textContent = `${fmt(t.current_count)} entries · ${absDiff}% below historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `-${absDiff}%`;
        val.className = 'delta-value red';
      } else {
        banner.className = 'delta-banner gold';
        icon.innerHTML = '&#9654;';
        main.textContent = `${t.family} ${t.year}: On Par`;
        sub.textContent = `${fmt(t.current_count)} entries · In line with historical average of ${fmt(Math.round(avg))}`;
        val.textContent = `${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%`;
        val.className = 'delta-value gold';
      }
    } else {
      banner.className = 'delta-banner muted';
      icon.innerHTML = '&#10003;';
      main.textContent = `${t.family} ${t.year}: Complete`;
      sub.textContent = `Final count: ${fmt(t.current_count)} entries`;
      val.textContent = '';
      val.className = 'delta-value';
    }
    return;
  }

  // Live tournament — compare to historical pace
  if (t.historical && t.historical.length > 0) {
    const lastYr = t.historical[t.historical.length - 1];
    // Prefer the explicit prior_year_pace.count_at_same_point — it's derived
    // from last year's actual daily registrations on this calendar day.
    // Fall back to the family-average curve only when the explicit field is
    // missing (no 2025 daily data for this family). Curve-derived estimates
    // can drift wildly from reality when the prior year's curve was unusual.
    const priorPace = t.prior_year_pace;
    const lastYrAtT = (priorPace && priorPace.count_at_same_point != null)
      ? priorPace.count_at_same_point
      : (t.registration_curve
          ? Math.round(lastYr.count * interpCurve(t.registration_curve, t.days_remaining))
          : null);
    const lastYrLabel = priorPace?.year ?? lastYr.year;

    if (lastYrAtT && lastYrAtT > 0) {
      const diff = t.current_count - lastYrAtT;
      const pctVal = ((diff / lastYrAtT) * 100);
      const pct = pctVal.toFixed(1);
      const absPct = Math.abs(pctVal).toFixed(1);

      // Compute recent daily pace
      let paceSuffix = '';
      if (t.daily_data && t.daily_data.length >= 3) {
        const recent = t.daily_data.slice(-7);
        if (recent.length >= 2) {
          const daySpan = recent[recent.length-1][0] - recent[0][0];
          const regSpan = recent[recent.length-1][1] - recent[0][1];
          if (daySpan > 0) {
            paceSuffix = ` · ${(regSpan / daySpan).toFixed(1)}/day recent pace`;
          }
        }
      }

      if (diff > 0) {
        banner.className = 'delta-banner green';
        icon.innerHTML = '&#9650;';
        main.textContent = `Tracking ahead of ${lastYrLabel} pace`;
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at the same days-to-event mark in ${lastYrLabel}${paceSuffix}`;
        val.textContent = `+${absPct}%`;
        val.className = 'delta-value green';
      } else if (diff < 0) {
        banner.className = 'delta-banner red';
        icon.innerHTML = '&#9660;';
        main.textContent = `Tracking behind ${lastYrLabel} pace`;
        sub.textContent = `${fmt(t.current_count)} registered now vs ${fmt(lastYrAtT)} at the same days-to-event mark in ${lastYrLabel}${paceSuffix}`;
        val.textContent = `-${absPct}%`;
        val.className = 'delta-value red';
      } else {
        banner.className = 'delta-banner gold';
        icon.innerHTML = '&#9654;';
        main.textContent = `Tracking on pace with ${lastYrLabel}`;
        sub.textContent = `${fmt(t.current_count)} registered${paceSuffix}`;
        val.textContent = '0%';
        val.className = 'delta-value gold';
      }
      return;
    }
  }

  // Fallback — no historical comparison available
  banner.className = 'delta-banner gold';
  icon.innerHTML = '&#9654;';
  main.textContent = `${t.family}: Registration in progress`;
  const _evStarted = t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  const _countdown = _evStarted
    ? `${t.days_remaining} days of online registration left`
    : `${t.days_remaining} days until event`;
  sub.textContent = `${fmt(t.current_count)} entries registered · ${_countdown} · predicted final: ${fmt(t.point_estimate)}`;
  val.textContent = `T-${t.days_remaining}`;
  val.className = 'delta-value gold';
}

// ══════════════════════════════════════════════════════════
// PROGRESS BARS
// ══════════════════════════════════════════════════════════
function renderProgress(t) {
  const el = document.getElementById('progressRow');
  if (isDone(t) || !t.daily_data || t.daily_data.length === 0) { el.innerHTML = ''; return; }

  // v3 P3: span the registration window from its real start date to the event,
  // not from the tail of the data array. The old form (last point's day index
  // plus days_remaining) silently assumed the last scrape happened today, so a
  // stale or gappy tail shortened the window and this bar contradicted the pace
  // banner rendered from the same card.
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

  el.innerHTML = `
    <div class="progress-block">
      <div class="progress-header"><span>Time Elapsed <span style="opacity:.5">(${elapsed} of ${totalDays} days)</span></span><span>${timePct}%</span></div>
      <div class="progress-bar"><div class="progress-fill pf-blue" style="width:${timePct}%"></div></div>
    </div>
    <div class="progress-block">
      <div class="progress-header"><span>Entries Received <span style="opacity:.5">(${fmt(t.current_count)} of ~${fmt(t.point_estimate)})</span></span><span>${regPct}%</span></div>
      <div class="progress-bar"><div class="progress-fill pf-gold" style="width:${regPct}%"></div></div>
    </div>
  `;
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
      <div class="timeline-node"><div class="timeline-dot past"></div><div class="timeline-label">Final Count</div><div class="timeline-date" style="color:var(--gold);font-size:var(--fs-4)">${fmt(t.current_count)}</div></div>
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
    el.innerHTML = `<div style="text-align:center;padding:24px 0">
      <p style="color:var(--muted);font-size:var(--fs-2);opacity:.6">Fee data not available for this tournament.</p>
    </div>`;
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
    html += `<div style="text-align:center;padding:16px 0 20px;border-bottom:1px solid var(--border);margin-bottom:16px">
      <div style="font-size:var(--fs-2);color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Current Rate</div>
      <div style="font-size:2.2rem;font-weight:900;color:var(--gold)">$${currentFee}</div>
      <div style="font-size:var(--fs-2);color:var(--muted);margin-top:4px">${feeStatus}</div>
    </div>`;
  }

  html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;text-align:center">';
  if (t.early_bird_fee && t.regular_fee && t.early_bird_fee < t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Early Bird</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--green)">$${t.early_bird_fee}</div>
    </div>`;
  }
  if (t.regular_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Regular</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--text2)">$${t.regular_fee}</div>
    </div>`;
  }
  if (t.onsite_fee) {
    html += `<div style="padding:10px;background:var(--surface3);border-radius:8px">
      <div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">On-site</div>
      <div style="font-size:var(--fs-5);font-weight:700;color:var(--orange)">$${t.onsite_fee}</div>
    </div>`;
  }
  html += '</div>';

  el.innerHTML = html;
}
