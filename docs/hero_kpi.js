// hero_kpi.js — hero card, KPI row and favorites, split verbatim from
// app.js (C9).

// ══════════════════════════════════════════════════════════
// HERO + KPI
// ══════════════════════════════════════════════════════════

// Build the prediction-tile tooltip from live PERFORMANCE_DATA so every
// pipeline run (daily auto_update + monthly recalibration) refreshes the
// numbers automatically. No hardcoded counts/biases.
function _calibrationTooltip() {
  const fallback = 'Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted.';
  if (typeof PERFORMANCE_DATA === 'undefined' || !PERFORMANCE_DATA) return fallback;
  const yr = String(new Date().getFullYear());
  const yearData = (PERFORMANCE_DATA.years || {})[yr] || PERFORMANCE_DATA;
  const agg = yearData.aggregate || PERFORMANCE_DATA.aggregate || [];
  if (!agg.length) return fallback;
  // n-weighted mean of |bias_pct| across T-points: how much the model
  // typically over- or under-shoots in the current year.
  let nSum = 0, biasNum = 0;
  for (const a of agg) {
    if (typeof a.bias_pct === 'number' && typeof a.n === 'number') {
      biasNum += a.bias_pct * a.n;
      nSum += a.n;
    }
  }
  const meanBias = nSum > 0 ? biasNum / nSum : null;
  const nEvents = yearData.n_tournaments ?? PERFORMANCE_DATA.n_tournaments ?? null;
  const asof = PERFORMANCE_DATA.generated || '';
  if (meanBias == null || nEvents == null) return fallback;
  const dir = meanBias > 0 ? 'over-predicting' : 'under-predicting';
  const absBias = Math.abs(meanBias).toFixed(1);
  return `Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted. ${yr} backtest (${nEvents} events, asof ${asof}) shows the model has been ${dir} by ${absBias}% on avg; kept conservative on purpose. See Performance tab for full breakdown.`;
}

function renderHero(t) {
  const statusPrefix = t.status === 'historical' ? `${t.year} ` : '';
  const heroLabel = document.getElementById('heroLabel');
  if (isDone(t)) {
    heroLabel.textContent = `${statusPrefix}Final Entries`;
    heroLabel.removeAttribute('title');
    heroLabel.style.cursor = '';
  } else {
    heroLabel.innerHTML = `Predicted Final Entries <span style="opacity:.55;font-weight:400;cursor:help" title="${esc(_calibrationTooltip())}">ⓘ</span>`;
    heroLabel.style.cursor = 'default';
  }
  const heroNum = document.getElementById('heroNumber');
  // Animate number count-up (skip the tween under prefers-reduced-motion)
  const target = t.point_estimate;
  if (_reduceMotion()) {
    heroNum.textContent = fmt(Math.round(target));
  } else {
    const duration = 600;
    const start = performance.now();
    (function animHero(now) {
      const p = Math.min(((now || performance.now()) - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      heroNum.textContent = fmt(Math.round(target * ease));
      if (p < 1) requestAnimationFrame(animHero);
    })(performance.now());
  }
  // Solid color: gold for live predictions, blue for completed totals.
  // Prior gradient-text + background-clip path was killed in iter 1 of
  // this UX pass (banned anti-pattern, mushy at small sizes). Re-applying
  // the gradient inline here would have undone that fix.
  heroNum.style.background = '';
  heroNum.style.backgroundClip = '';
  heroNum.style.webkitBackgroundClip = '';
  heroNum.style.webkitTextFillColor = '';
  heroNum.style.color = isDone(t) ? 'var(--blue-bright)' : 'var(--gold)';

  // Audit telemetry: prefer explicit low_confidence flag over derived nHist count.
  // n_historical_editions is the audit-canonical count (excludes COVID/online); fall back
  // to the historical array length only when the audit fields aren't present.
  const nHist = (typeof t.n_historical_editions === 'number')
    ? t.n_historical_editions
    : (t.historical ? t.historical.length : 0);
  const isLowConfidence = (typeof t.low_confidence === 'boolean')
    ? t.low_confidence
    : (nHist < 4);
  const confLabel = isLowConfidence
    ? (nHist >= 2 ? 'Low Confidence' : 'Very Low Confidence')
    : (nHist >= 8 ? 'High Confidence' : 'Medium Confidence');
  const confColor = isLowConfidence
    ? (nHist >= 2 ? 'var(--orange)' : 'var(--red)')
    : (nHist >= 8 ? 'var(--green)' : 'var(--gold)');
  const confBadge = !isDone(t) && t.ci_lower !== t.ci_upper
    ? ` <span title="${nHist} qualifying historical edition${nHist===1?'':'s'} for this family. Below 4 editions, the model marks the prediction low-confidence." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:var(--fs-1);font-weight:700;background:rgba(0,0,0,.3);border:1px solid ${confColor};color:${confColor};margin-left:6px;vertical-align:middle;cursor:help">${confLabel} · ${nHist} edition${nHist===1?'':'s'}</span>`
    : '';

  // Audit telemetry: surface fallback tier when prediction didn't use direct family ratios.
  // Expand tier badge text so the meaning is visible without a tooltip dive.
  const tierLabelMap = {
    'family-direct': 'direct · 5+ yr history',
    'family-alias':  'family alias · pooled history',
    'size-matched':  'size matched · no family history',
    'roster-pending': 'interim · not in roster yet',
  };
  const tierBadge = (!isDone(t) && t.prediction_tier && t.prediction_tier !== 'family-direct')
    ? ` <span title="Prediction used the '${t.prediction_tier}' fallback path. 'family-alias' pools history from related families; 'size-matched' uses families with comparable historical size when this family has no direct history." style="display:inline-block;padding:2px 8px;border-radius:100px;font-size:var(--fs-1);font-weight:700;background:rgba(0,0,0,.3);border:1px solid var(--blue);color:var(--blue);margin-left:6px;vertical-align:middle;cursor:help">${tierLabelMap[t.prediction_tier] || t.prediction_tier.replace('-',' ')}</span>`
    : '';

  // Confidence interval visualization. For completed tournaments we still
  // just show the final count (no CI to visualize). For live tournaments
  // with a real CI range, render a horizontal bar with the point estimate
  // marker positioned by where it sits inside [ci_lower, ci_upper].
  const ciLevel = Math.round((t.ci_level || .8) * 100);
  let ciHtml;
  if (t.ci_lower === t.ci_upper) {
    ciHtml = `<span class="ci-final">${fmt(t.current_count)} total entries</span>${confBadge}${tierBadge}`;
  } else {
    const lo = t.ci_lower, hi = t.ci_upper, pe = t.point_estimate;
    // Position 0-100% along the CI span. Clamp so off-band point estimates
    // (rare model edge cases) still render visibly inside the bar.
    const pct = Math.max(0, Math.min(100, ((pe - lo) / (hi - lo)) * 100));
    // Inline confidence rationale: surface WHY the model is N% confident.
    // Maps the qualitative confidence label + tier to a one-sentence reason.
    const conf = (t.confidence_label || '').toLowerCase();
    const tier = (t.prediction_tier || 'family-direct').toLowerCase();
    let reason;
    if (tier === 'family-direct' && conf.includes('high')) reason = 'Strong prior data: 5+ years of same-month history for this family.';
    else if (tier === 'family-direct' && conf.includes('medium')) reason = 'Moderate prior data: 3–4 years of comparable history.';
    else if (tier === 'family-direct' && conf.includes('low') && !conf.includes('very')) reason = 'Sparse prior data: under 3 comparable years.';
    else if (conf.includes('very')) reason = 'Limited or no comparable history; estimate falls back to family average.';
    else if (tier === 'family-alias') reason = 'No direct history: pooled from related families for this prediction.';
    else if (tier === 'size-matched') reason = 'No family history: drawn from families with comparable historical size.';
    else reason = `${t.confidence_label || 'Confidence'} based on ${tier.replace('-',' ')} history.`;
    ciHtml = `
      <div class="ci-bar" role="img" aria-label="${ciLevel}% confidence interval from ${fmt(lo)} to ${fmt(hi)}, point estimate ${fmt(pe)}. ${reason}" title="${reason}">
        <span class="ci-bound ci-bound-lo">${fmt(lo)}</span>
        <div class="ci-track">
          <div class="ci-track-fill"></div>
          <div class="ci-marker" style="left:${pct.toFixed(2)}%" title="Point estimate: ${fmt(pe)}. ${reason}"></div>
        </div>
        <span class="ci-bound ci-bound-hi">${fmt(hi)}</span>
      </div>
      <div class="ci-caption" style="font-size:var(--fs-1);color:var(--muted);margin-top:2px">Estimated final entries &middot; ${ciLevel}% range</div>
      <div class="ci-meta">${ciLevel}% CI${confBadge}${tierBadge}</div>
    `;
  }
  document.getElementById('heroCi').innerHTML = ciHtml;

  // Hero narrative removed — the pace verdict is already in the delta banner
  // above and the daily-pace KPI shows the 7-day pace, so the
  // paragraph here just duplicated info and threw the hero row out of
  // vertical balance with the week bars + KPI strip.
  document.getElementById('heroNarrative').innerHTML = '';

  // Festival cluster — renders inline if this tournament is part of a
  // multi-sub-event festival (e.g. World Open). No-op otherwise.
  renderFestivalCluster(t);

  // Side KPI cards
  document.getElementById('kpiCurrent').innerHTML = `
    <div class="kpi-label">Registered</div>
    <div class="kpi-value v-blue">${fmt(t.current_count)}</div>
    <div class="kpi-sub">${isDone(t) ? 'Final' : 'as of today'}</div>
  `;

  const daysColor = isDone(t) ? '' : t.days_remaining <= 7 ? 'v-red' : t.days_remaining <= 28 ? 'v-orange' : t.days_remaining <= 60 ? 'v-gold' : '';
  // Once the event has started, the live countdown is to online-registration
  // close (the 2-day schedule), not to an event start that already passed.
  const evStarted = !isDone(t) && t.event_start &&
    new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
  let daysLabel, daysValue, daysSub;
  if (isDone(t)) {
    daysLabel = 'Event Date';
    daysValue = fmtDate(t.event_start);
    daysSub = t.event_end ? fmtDate(t.event_start) + ' – ' + fmtDate(t.event_end) : '';
  } else if (evStarted) {
    daysLabel = 'Days to Reg. Close';
    daysValue = t.days_remaining;
    daysSub = t.registration_close ? fmtDate(t.registration_close) : 'event underway';
  } else {
    daysLabel = 'Days to Event';
    daysValue = t.days_remaining;
    daysSub = fmtDate(t.event_start);
  }
  document.getElementById('kpiDays').innerHTML = `
    <div class="kpi-label">${daysLabel}</div>
    <div class="kpi-value ${daysColor}">${daysValue}</div>
    <div class="kpi-sub">${daysSub}</div>
  `;

  // Pace/velocity card
  let paceHtml = '';
  if (!isDone(t) && t.daily_data && t.daily_data.length >= 3) {
    const recent = t.daily_data.slice(-7);
    if (recent.length >= 2) {
      const daySpan = recent[recent.length-1][0] - recent[0][0];
      const regSpan = recent[recent.length-1][1] - recent[0][1];
      const rateNum = daySpan > 0 ? regSpan / daySpan : 0;
      const rate = rateNum.toFixed(1);
      paceHtml = `
        <div class="kpi-label">7-Day Pace</div>
        <div class="kpi-value">${rate}</div>
        <div class="kpi-sub">entries / day</div>
      `;
    }
  } else if (isDone(t) && t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length);
    const diff = t.current_count - avg;
    const pct = ((diff / avg) * 100).toFixed(0);
    paceHtml = `
      <div class="kpi-label">vs Average</div>
      <div class="kpi-value ${diff >= 0 ? 'v-green' : 'v-red'}">${diff >= 0 ? '+' : ''}${pct}%</div>
      <div class="kpi-sub">hist avg: ${fmt(avg)}</div>
    `;
  }
  document.getElementById('kpiPace').innerHTML = paceHtml || `
    <div class="kpi-label">Historical</div>
    <div class="kpi-value" style="font-size:var(--fs-5);color:var(--muted)">–</div>
    <div class="kpi-sub">No pace data</div>
  `;

  // 4th card — Progress to predicted final (mobile fills 2x2 grid cleanly)
  const kpiProg = document.getElementById('kpiProgress');
  if (kpiProg) {
    if (isDone(t)) {
      // For complete tournaments, show YoY change vs last year
      const lastYr = emailLastYear ? emailLastYear(t) : null;
      if (lastYr && lastYr.count) {
        const diff = t.current_count - lastYr.count;
        const pct = ((diff / lastYr.count) * 100).toFixed(0);
        kpiProg.innerHTML = `
          <div class="kpi-label">vs ${lastYr.year}</div>
          <div class="kpi-value ${diff >= 0 ? 'v-green' : 'v-red'}">${diff >= 0 ? '+' : ''}${pct}%</div>
          <div class="kpi-sub">${fmt(lastYr.count)} prior</div>
        `;
      } else {
        kpiProg.innerHTML = `
          <div class="kpi-label">Status</div>
          <div class="kpi-value v-green" style="font-size:var(--fs-5)">Final</div>
          <div class="kpi-sub">${fmtDate(t.event_start)}</div>
        `;
      }
    } else if (t.point_estimate > 0) {
      const pct = Math.min(100, Math.round(t.current_count / t.point_estimate * 100));
      const color = pct >= 80 ? 'v-green' : pct >= 40 ? 'v-gold' : 'v-blue';
      kpiProg.innerHTML = `
        <div class="kpi-label">Progress</div>
        <div class="kpi-value ${color}">${pct}%</div>
        <div class="kpi-sub">of predicted</div>
      `;
    } else {
      kpiProg.innerHTML = `
        <div class="kpi-label">Progress</div>
        <div class="kpi-value" style="font-size:var(--fs-5);color:var(--muted)">–</div>
        <div class="kpi-sub">No prediction</div>
      `;
    }
  }

  // ── Last 7 days breakdown ──
  const weekEl = document.getElementById('weekBreakdown');
  const barsEl = document.getElementById('weekBars');
  if (!isDone(t) && t.daily_data && t.daily_data.length >= 2) {
    // Build one bar per real calendar day (v3 P1). Each bar carries its own
    // date, derived from the point's day_from_start against the exported
    // daily_start_date anchor — never from its position in the array. Days
    // covered by a scrape gap are spread across the gap and marked, so a
    // multi-day jump can no longer be drawn as a single day's registrations.
    const ivs = (typeof DailySeries !== 'undefined')
      ? DailySeries.intervals(t, { isLive: !isDone(t) })
      : [];
    const days = [];      // {n, date, estimated}
    for (const iv of ivs) {
      const perDay = iv.added / iv.span;
      for (let g = 0; g < iv.span; g++) {
        // Date of each covered day, counting forward from the interval start.
        const d = (typeof DailySeries !== 'undefined')
          ? DailySeries.pointDate(t, iv.fromDay + g + 1) : null;
        days.push({ n: Math.round(perDay), date: d, estimated: iv.isGap });
      }
    }
    while (days.length > 7) days.shift();
    if (days.length === 0 || days.every(o => o.n === 0)) {
      // No recent activity — render a quiet placeholder instead of nothing
      // so the hero-week column doesn't suddenly collapse to zero height.
      barsEl.innerHTML = `<div class="hero-week-empty">No registrations in the last 7 days</div>`;
      weekEl.style.display = '';
    } else if (days.length >= 2) {
      // Bar scale uses every day, but the "busiest day" highlight only considers
      // observed ones — an average spread across a scrape gap is not evidence
      // that that day was the peak.
      const maxNew = Math.max(...days.map(o => o.n), 1);
      const observed = days.filter(o => !o.estimated).map(o => o.n);
      const maxObserved = observed.length ? Math.max(...observed) : null;
      const anyEstimated = days.some(o => o.estimated);
      barsEl.innerHTML = days.map(o => {
        const label = (o.date && typeof DailySeries !== 'undefined')
          ? DailySeries.fmtPointDate(o.date) : '';
        const pct = Math.max((o.n / maxNew) * 100, 2);
        const isPeak = !o.estimated && maxObserved !== null && o.n === maxObserved;
        const color = isPeak ? 'var(--gold)' : 'var(--blue)';
        // A bar covering a scrape gap is an average, not an observation. Mark it
        // rather than presenting a spread-out figure as a measured daily count.
        // The dimming has to live in this one style attribute — a second style=
        // on the same element is discarded by the parser, which drops the flex
        // layout and stacks the row.
        const rowStyle = `display:flex;align-items:center;gap:6px${o.estimated ? ';opacity:.55' : ''}`;
        const tip = o.estimated ? ' title="Estimated: this day was covered by a gap in scraping"' : '';
        return `<div${tip} style="${rowStyle}">
          <span style="font-size:var(--fs-1);color:var(--muted);width:62px;text-align:right;white-space:nowrap">${label}</span>
          <div style="flex:1;height:11px;background:var(--surface2);border-radius:2px;overflow:hidden">
            <div style="width:${pct}%;height:100%;background:${color};border-radius:2px;transition:width .35s cubic-bezier(.22,1,.36,1)"></div>
          </div>
          <span style="font-size:var(--fs-1);color:var(--text2);width:30px;font-weight:${isPeak ? '700' : '400'}">${o.estimated ? '~' : '+'}${o.n}</span>
        </div>`;
      }).join('');
      if (anyEstimated) {
        barsEl.innerHTML += `<div style="font-size:var(--fs-1);color:var(--muted);margin-top:4px">~ estimated across a gap in scraping</div>`;
      }
      weekEl.style.display = '';
    } else {
      weekEl.style.display = 'none';
    }
  } else {
    weekEl.style.display = 'none';
  }
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
      <div class="kpi-value v-green">${regPct}%</div>
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
      <div class="kpi-value ${ebPassed ? 'v-red' : 'v-green'}">${ebPassed ? 'Ended' : daysToEB + 'd'}</div>
      <div class="kpi-sub">${fmtDate(t.early_bird_deadline)}${t.early_bird_fee ? ' · $' + t.early_bird_fee : ''}</div>
    </div>`);
  }

  // Historical avg
  if (t.historical && t.historical.length > 0) {
    const avg = Math.round(t.historical.reduce((s,h) => s+h.count, 0) / t.historical.length);
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Past Average</div>
      <div class="kpi-value v-purple">${fmt(avg)}</div>
      <div class="kpi-sub">${t.historical.length} editions</div>
    </div>`);

    // Historical rank (for completed tournaments)
    if (isDone(t)) {
      const allCounts = [...t.historical.map(h => h.count), t.current_count].sort((a,b) => b - a);
      const rank = allCounts.indexOf(t.current_count) + 1;
      const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th';
      cards.push(`<div class="kpi-card">
        <div class="kpi-label">All-Time Rank</div>
        <div class="kpi-value ${rank <= 3 ? 'v-gold' : ''}">${rank}${suffix}</div>
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
      <div class="kpi-value v-orange">&plusmn;${widthPct}%</div>
      <div class="kpi-sub">${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}</div>
    </div>`);
  }

  // Regular fee
  if (t.regular_fee) {
    cards.push(`<div class="kpi-card">
      <div class="kpi-label">Regular Fee</div>
      <div class="kpi-value" style="color:var(--text2)">$${t.regular_fee}</div>
      <div class="kpi-sub">${t.onsite_fee ? 'Onsite: $' + t.onsite_fee : ''}</div>
    </div>`);
  }

  el.innerHTML = cards.join('');
}

// Apply any saved overrides on load
// ══════════════════════════════════════════════════════════
// FAVORITES (My Tournaments)
// ══════════════════════════════════════════════════════════
const FAV_KEY = 'cca_favorites';

function getFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function saveFavorites(favs) {
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
}

function isFavorite(family) {
  return getFavorites().includes(family);
}

function toggleFavorite(family) {
  const favs = getFavorites();
  const idx = favs.indexOf(family);
  if (idx >= 0) favs.splice(idx, 1);
  else favs.push(family);
  saveFavorites(favs);
  updateFavButton(family);
}

function toggleFavoriteSelected() {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  if (t) toggleFavorite(t.family);
}

function updateFavButton(family) {
  const btn = document.getElementById('favToggle');
  if (!btn) return;
  const fav = isFavorite(family);
  btn.innerHTML = fav ? '&#9733;' : '&#9734;';
  btn.classList.toggle('fav-active', fav);
  btn.title = fav ? 'Remove from My Tournaments' : 'Add to My Tournaments';
}
