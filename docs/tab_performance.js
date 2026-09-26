// tab_performance.js — model performance tab, split verbatim from app.js (C5).

// ══════════════════════════════════════════════════════════
// MODEL PERFORMANCE TAB
// ══════════════════════════════════════════════════════════
let perfInited = false;
let perfSelectedKey = null;

function initPerformanceTab() {
  if (perfInited) return;
  perfInited = true;
  // The per-tournament records (400 KB) are fetched when this tab first
  // opens; the page itself carries only PERFORMANCE_SUMMARY.
  perfShowStatus('--', 'LOADING', 'Loading the performance data…');
  loadDataFile('performance').then(perfInitFromData, err => {
    // Let the next visit to the tab retry rather than sit on a blank panel.
    perfInited = false;
    console.error(err);
    perfShowStatus('--', 'UNAVAILABLE',
      'Could not load the performance data. Check your connection and reopen this tab.');
  });
}

function perfShowStatus(letter, label, detail) {
  document.getElementById('perfGradeLetter').textContent = letter;
  document.getElementById('perfGradeLabel').textContent = label;
  document.getElementById('perfGradeDetail').textContent = detail;
}

function perfInitFromData() {
  const data = typeof PERFORMANCE_DATA !== 'undefined' ? PERFORMANCE_DATA : {};
  const hasYears = data.years && Object.values(data.years).some(y => y && y.n_tournaments > 0);
  const hasCumulative = data.cumulative && data.cumulative.n_tournaments > 0;
  const hasFlat = data.aggregate && data.aggregate.length > 0;

  if (!hasYears && !hasCumulative && !hasFlat) {
    perfShowStatus('--', 'NO DATA', 'Performance data will appear once tournaments complete.');
    return;
  }

  const selector = document.getElementById('perfYearSelector');
  if (selector && (hasYears || hasCumulative)) {
    const buttons = [];
    const nowYear = new Date().getFullYear();
    const years = data.years
      ? Object.keys(data.years).map(Number).filter(y => data.years[y] && data.years[y].n_tournaments > 0).sort()
      : [];
    years.forEach(y => buttons.push({key: String(y), label: y === nowYear ? `${y} YTD` : String(y)}));
    if (hasCumulative) buttons.push({key: 'cumulative', label: 'Cumulative'});

    selector.innerHTML = '<span class="perf-view-label">View</span><div class="segmented" role="group" aria-label="Performance view">' +
      buttons.map(b => `<button data-act="perf-year" data-year="${b.key}" id="perfYearBtn_${b.key}">${b.label}</button>`).join('') + '</div>';

    const defaultKey = years.includes(nowYear) ? String(nowYear) : (years.length ? String(years[years.length - 1]) : 'cumulative');
    perfSelectYear(defaultKey);
  } else {
    if (selector) selector.style.display = 'none';
    perfRenderFlat(data);
  }
}

function perfSelectYear(key) {
  perfSelectedKey = key;
  document.querySelectorAll('[id^="perfYearBtn_"]').forEach(btn => {
    btn.classList.toggle('active', btn.id === 'perfYearBtn_' + key);
  });
  perfRender();
}

function perfRender() {
  // A theme switch re-renders the active tab; before the lazy file has
  // landed there is nothing to draw yet.
  if (typeof PERFORMANCE_DATA === 'undefined') return;
  const data = PERFORMANCE_DATA;
  const key = perfSelectedKey;
  const baseData = key === 'cumulative' ? data.cumulative : (data.years && data.years[key]);
  if (!baseData) return perfRenderFlat(data);

  const nowYear = new Date().getFullYear();
  const isYTD = key === String(nowYear);
  const desc = key === 'cumulative'
    ? `Blind-tested across ${baseData.n_tournaments} tournaments (all years)`
    : `Blind-tested on ${baseData.n_tournaments} ${key} tournaments${isYTD ? ' (YTD)' : ''}`;

  perfPaint({
    aggregate: baseData.aggregate,
    tournaments: baseData.tournaments || [],
    grade: baseData.grade,
    n_tournaments: baseData.n_tournaments,
    detail: desc,
    generated: data.generated,
  });
}

function perfRenderFlat(data) {
  perfPaint({
    aggregate: data.aggregate || [],
    tournaments: data.tournaments || [],
    grade: data.grade,
    n_tournaments: data.n_tournaments,
    detail: data.grade_detail || `Blind-tested on ${data.n_tournaments} completed tournaments`,
    generated: data.generated,
  });
}

// The pens for a figure against its mark: blue when it meets it, ink when
// it is fair, red when it misses. Classes, not colours: the stylesheet owns
// the palette in both themes.
function _perfTone(good, fair) {
  return good ? 'v-blue' : fair ? 'v-ink' : 'v-red';
}

function perfPaint(view) {
  const agg = view.aggregate || [];
  const letter = document.getElementById('perfGradeLetter');
  const grade = view.grade || '--';
  letter.textContent = grade;
  letter.classList.remove('grade-good', 'grade-warn', 'grade-bad');
  if (/^[AB]/.test(grade)) letter.classList.add('grade-good');
  else if (/^C/.test(grade)) letter.classList.add('grade-warn');
  else if (/^[DF]/.test(grade)) letter.classList.add('grade-bad');
  document.getElementById('perfGradeLabel').textContent = 'Model Grade';
  document.getElementById('perfGradeDetail').textContent = view.detail;
  document.getElementById('perfGradeMeta').textContent = `N5v4_Final Ensemble \u00b7 Rolling retrain + auto-recalibration \u00b7 Updated ${view.generated || ''}`;

  // v3 T7: the grade above describes predict_nowcast. The online-window engine
  // handles live multi-schedule events and is graded separately by 04e. Shown
  // as its own line, never folded into the letter above: it is scored 0-2 days
  // from registration close against the headline's T-14/7/3, so a better letter
  // here means an easier question, not a better model.
  const secondEl = document.getElementById('perfSecondEngine');
  if (secondEl) {
    const we = PERFORMANCE_DATA.window_engine;
    secondEl.textContent = (we && we.grade && we.grade !== 'N/A')
      ? `Second engine (live registration window): ${we.grade} \u00b7 `
        + `${we.n} predictions across ${we.n_events} events \u00b7 `
        + `MAE ${we.mae_pct}%, CI coverage ${we.ci_coverage}% \u00b7 `
        + `shorter horizon than the grade above, not comparable to it`
      : '';
  }

  if (!agg.length) {
    document.getElementById('perfKPIs').innerHTML = '';
    document.getElementById('perfHorizonStrip').innerHTML = '';
    const sc = document.getElementById('perfScoring');
    if (sc) sc.innerHTML = '';
    document.getElementById('perfTable').innerHTML = '<div class="empty">No completed tournaments for this selection.</div>';
    return;
  }

  const t14 = agg.find(a => a.T === 14) || agg[0];
  const t1 = agg.find(a => a.T === 1);
  const avgCov = Math.round(agg.reduce((s, a) => s + a.ci_coverage, 0) / agg.length);
  const avgBias = +(agg.reduce((s, a) => s + a.bias_pct, 0) / agg.length).toFixed(1);

  const kpis = [
    {v: t14.mae_pct.toFixed(1) + '%', l: '2-Week Error', s: 'MAE at T-14', c: _perfTone(t14.mae_pct <= 8, t14.mae_pct <= 15)},
    {v: t1 ? t1.mae_pct.toFixed(1) + '%' : '--', l: 'Day Before', s: 'MAE at T-1', c: _perfTone(t1 && t1.mae_pct <= 5, true)},
    // Blue means "meets the advertised 80%", not "close enough". The old
    // threshold passed at >= 75, below the number the site itself advertises,
    // so a miscalibrated interval read as healthy (2026-09-07 review).
    {v: avgCov + '%', l: 'CI Coverage', s: 'Target 80%', c: _perfTone(avgCov >= 80, avgCov >= 70)},
    {v: (avgBias > 0 ? '+' : '') + avgBias + '%', l: 'Bias', s: avgBias > 2 ? 'Over-predicts' : avgBias < -2 ? 'Under-predicts' : 'Well-centered', c: _perfTone(Math.abs(avgBias) <= 5, true)},
  ];
  document.getElementById('perfKPIs').innerHTML = kpis.map(k => `
    <div class="perf-kpi">
      <div class="kpi-label">${k.l}</div>
      <div class="kpi-value ${k.c}">${k.v}</div>
      <div class="kpi-sub">${k.s}</div>
    </div>`).join('');

  requestAnimationFrame(() => {
    perfDrawScatter(view);
    perfDrawTimeline(view);
  });

  const strip = document.getElementById('perfHorizonStrip');
  strip.innerHTML = agg.map(a => {
    // One encoding: the MAE value alone carries the pen.
    const tc = _perfTone(a.mae_pct <= 8, a.mae_pct <= 12);
    const isTip = a.interval_score_pct != null
      ? `, interval score ${a.interval_score_pct}% of final (lower is better)` : '';
    return `<div class="horizon-tile" title="n=${a.n}, bias ${a.bias_pct > 0 ? '+' : ''}${a.bias_pct}%${isTip}">
      <div class="horizon-t">T-${a.T}</div>
      <div class="horizon-val ${tc}">${a.mae_pct.toFixed(1)}%</div>
      <div class="horizon-ci">CI ${a.ci_coverage}%</div>
    </div>`;
  }).join('');

  perfDrawScoring(view);
  perfDrawTable(view);
}

// Proper scoring rules and the naive baselines (2026-09-07 review).
//
// MAE plus coverage is gameable in one direction: widening every interval
// raises coverage and leaves MAE untouched, so the pair cannot distinguish a
// well-calibrated interval from a merely large one. The interval score charges
// for width and for misses in the same units. The baselines answer the separate
// question the site could not previously answer at all: is the model better
// than doing nothing?
function perfDrawScoring(data) {
  const el = document.getElementById('perfScoring');
  if (!el) return;
  const agg = (data && data.aggregate) || [];
  const t14 = agg.find(a => a.T === 14) || agg.find(a => a.T === 7) || agg[0];
  if (!t14) { el.innerHTML = ''; return; }

  const parts = [];

  // ── Model vs. doing nothing, at the planning horizon ──
  const bl = t14.baselines || {};
  const rows = [
    {k: 'model', label: 'This model', mae: t14.mae_pct, n: t14.n},
    {k: 'baseline_ratio', label: 'Today\u2019s count \u00d7 typical pace',
     mae: bl.baseline_ratio && bl.baseline_ratio.mae_pct, n: bl.baseline_ratio && bl.baseline_ratio.n},
    {k: 'baseline_last_year', label: 'Last year\u2019s final count',
     mae: bl.baseline_last_year && bl.baseline_last_year.mae_pct, n: bl.baseline_last_year && bl.baseline_last_year.n},
  ].filter(r => r.mae != null);

  if (rows.length > 1) {
    const worst = Math.max(...rows.map(r => r.mae));
    parts.push(`<div class="perf-scoring-block">
      <div class="perf-scoring-title">Against doing nothing &middot; average miss at T-${t14.T}</div>
      ${rows.map(r => {
        const pct = worst > 0 ? Math.max(4, Math.round(r.mae / worst * 100)) : 4;
        const mod = r.k === 'model' ? ' is-model' : '';
        return `<div class="perf-bar-row">
          <div class="perf-bar-label">${r.label}</div>
          <div class="perf-bar-track"><div class="perf-bar-fill${mod}" style="width:${pct}%"></div></div>
          <div class="perf-bar-val${mod}">${r.mae.toFixed(1)}%</div>
        </div>`;
      }).join('')}
      <div class="perf-scoring-note">Lower is better. A baseline that matches or beats
        the model at any horizon is a finding, not a rounding artifact.</div>
    </div>`);
  }

  // ── Calibration (PIT) ──
  // A well-calibrated forecaster spreads outcomes evenly across the interval.
  // Mass piled at both ends means the intervals are too narrow; a lean to one
  // side means the point estimate is biased.
  const pit = t14.pit;
  if (pit && pit.n && pit.counts) {
    const maxC = Math.max(...pit.counts, 1);
    const expected = pit.n / pit.bins;
    parts.push(`<div class="perf-scoring-block">
      <div class="perf-scoring-title">Calibration at T-${t14.T}
        <span class="perf-scoring-sub">where the actual landed inside the predicted range (n=${pit.n})</span></div>
      <div class="perf-pit">
        ${pit.counts.map((c, i) => {
          const h = Math.max(2, Math.round(c / maxC * 46));
          const over = c > expected * 1.5;
          return `<div class="perf-pit-col" title="${(i * 10)}\u2013${(i + 1) * 10}% of the range: ${c} tournament(s), even split would be ${expected.toFixed(1)}">
            <div class="perf-pit-bar${over ? ' is-over' : ''}" style="height:${h}px"></div>
          </div>`;
        }).join('')}
      </div>
      <div class="perf-pit-axis"><span>low end of range</span><span>middle</span><span>high end</span></div>
      <div class="perf-scoring-note">An even set of bars means the range is honest.
        Tall bars at both ends mean it is too narrow.</div>
    </div>`);
  }

  el.innerHTML = parts.join('');
}

function perfDrawScatter(data) {
  const canvas = document.getElementById('perfScatterCanvas');
  if (!canvas) return;
  // perfSelectYear re-runs perfPaint on every view click; Chart.js throws
  // "Canvas is already in use" without an explicit destroy.
  if (perfScatterChart) { perfScatterChart.destroy(); perfScatterChart = null; }

  const pts = [];
  data.tournaments.forEach(t => {
    const p = t.predictions.find(p => p.T === 14) || t.predictions.find(p => p.T === 28) || t.predictions[0];
    if (p) pts.push({f: t.family, a: t.final_count, p: p.predicted, lo: p.ci_lower, hi: p.ci_upper, ok: p.in_ci});
  });
  if (!pts.length) return;

  const maxV = Math.round(Math.max(...pts.map(p => Math.max(p.a, p.p, p.hi))) * 1.12);
  const toXY = arr => arr.map(p => ({ x: p.a, y: p.p, f: p.f, lo: p.lo, hi: p.hi, ok: p.ok }));

  // CI whiskers (vertical lo..hi at each point's actual-x, with 3px caps) +
  // the "Perfect prediction" caption. Both lived in the hand-rolled renderer.
  const ciWhiskers = {
    id: 'ciWhiskers',
    afterDatasetsDraw(c) {
      const xS = c.scales.x, yS = c.scales.y, ctx2 = c.ctx;
      ctx2.save();
      pts.forEach(p => {
        const px = xS.getPixelForValue(p.a);
        if (px < xS.left || px > xS.right) return;
        const col = p.ok ? PALETTE.green : PALETTE.red;
        const yLo = yS.getPixelForValue(p.lo), yHi = yS.getPixelForValue(p.hi);
        ctx2.strokeStyle = col; ctx2.globalAlpha = 0.25; ctx2.lineWidth = 2;
        ctx2.beginPath();
        ctx2.moveTo(px, yLo); ctx2.lineTo(px, yHi);
        ctx2.moveTo(px - 3, yLo); ctx2.lineTo(px + 3, yLo);
        ctx2.moveTo(px - 3, yHi); ctx2.lineTo(px + 3, yHi);
        ctx2.stroke();
        ctx2.globalAlpha = 1;
      });
      ctx2.fillStyle = PALETTE.muted;
      ctx2.font = `${_mobileVP() ? 9 : 8}px system-ui`;
      ctx2.textAlign = 'right';
      ctx2.fillText('Perfect prediction', xS.right - 2, yS.top + 10);
      ctx2.restore();
    }
  };

  const dotCfg = (color) => ({
    pointRadius: 4.5, pointHoverRadius: 7, pointHitRadius: 8,
    pointBackgroundColor: color, pointBorderColor: PALETTE.surface,
    pointBorderWidth: 1.2, pointHoverBorderColor: PALETTE.text, pointHoverBorderWidth: 1.5,
    showLine: false
  });

  perfScatterChart = new Chart(canvas, {
    type: 'scatter',
    data: {
      datasets: [
        { label: 'Within CI', data: toXY(pts.filter(p => p.ok)), ...dotCfg(PALETTE.green) },
        { label: 'Outside CI', data: toXY(pts.filter(p => !p.ok)), ...dotCfg(PALETTE.red) },
        { label: 'perfect', type: 'line', data: [{ x: 0, y: 0 }, { x: maxV, y: maxV }],
          borderColor: themeRgba(PALETTE.text, 0.35), borderDash: [8, 5], borderWidth: 1.5,
          pointRadius: 0, pointHitRadius: 0, pointHoverRadius: 0 }
      ]
    },
    plugins: [ciWhiskers],
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: {
          type: 'linear', min: 0, max: maxV,
          title: { display: !_mobileVP(), text: 'Actual Entries', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: _mobileVP() ? 10 : 9 }, maxTicksLimit: 6, maxRotation: 0,
            callback(v) { return v.toLocaleString(); } },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        },
        y: {
          type: 'linear', min: 0, max: maxV,
          title: { display: !_mobileVP(), text: 'Predicted', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: _mobileVP() ? 10 : 9 }, maxTicksLimit: 5,
            callback(v) { return v.toLocaleString(); } },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' }, bodyFont: { size: 12 },
          footerFont: { size: 11, style: 'italic' },
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          filter(item) { return item.dataset.label !== 'perfect'; },
          callbacks: {
            title(items) { return items.length ? items[0].raw.f : ''; },
            label(item) { return ` Predicted: ${fmt(item.raw.y)}`; },
            afterLabel(item) {
              return [` Actual: ${fmt(item.raw.x)}`, ` CI: ${fmt(item.raw.lo)} – ${fmt(item.raw.hi)}`];
            },
            footer(items) {
              if (!items.length) return '';
              return items[0].raw.ok ? 'Within CI' : 'Outside CI';
            }
          }
        }
      }
    }
  });
}

function perfDrawTimeline(data) {
  const canvas = document.getElementById('perfTimelineCanvas');
  if (!canvas) return;
  if (perfTimelineChart) { perfTimelineChart.destroy(); perfTimelineChart = null; }

  const agg = [...data.aggregate].sort((a, b) => b.T - a.T);
  if (!agg.length) return;

  const maxMAE = Math.max(15, ...agg.map(a => a.mae_pct)) * 1.2;
  const threshold = v => v <= 8 ? PALETTE.green : v <= 12 ? PALETTE.greenBright : PALETTE.gold;
  const dotColors = agg.map(a => threshold(a.mae_pct));
  const _tlGrad = {};

  // Green "good zone" under the 10% MAE line.
  const goodZone = {
    id: 'goodZone',
    beforeDraw(c) {
      const area = c.chartArea;
      const y10 = c.scales.y.getPixelForValue(10);
      if (y10 >= area.bottom) return;
      c.ctx.save();
      c.ctx.fillStyle = themeRgba(PALETTE.green, 0.05);
      c.ctx.fillRect(area.left, y10, area.right - area.left, area.bottom - y10);
      c.ctx.restore();
    }
  };

  // Threshold-coloured dots and always-on value labels (redrawn over the
  // dataset's own points so each dot keeps its own pen).
  const dotsAndLabels = {
    id: 'tlDotsLabels',
    afterDatasetsDraw(c) {
      const meta = c.getDatasetMeta(0);
      const ctx2 = c.ctx;
      ctx2.save();
      meta.data.forEach((el, i) => {
        const col = dotColors[i];
        ctx2.fillStyle = col;
        ctx2.beginPath(); ctx2.arc(el.x, el.y, 4, 0, Math.PI * 2); ctx2.fill();
        ctx2.strokeStyle = PALETTE.surface2; ctx2.lineWidth = 1.5; ctx2.stroke();
        ctx2.fillStyle = PALETTE.text;
        ctx2.font = `bold ${_mobileVP() ? 10 : 9}px system-ui`;
        ctx2.textAlign = 'center';
        ctx2.fillText(agg[i].mae_pct.toFixed(1) + '%', el.x, el.y - 10);
      });
      ctx2.restore();
    }
  };

  perfTimelineChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: agg.map(a => 'T-' + a.T),
      datasets: [{
        data: agg.map(a => a.mae_pct),
        borderColor: PALETTE.gold,
        borderWidth: 2.5,
        borderCapStyle: 'round',
        backgroundColor: (context) => areaGradient(context.chart, _tlGrad, [
          [0, themeRgba(PALETTE.gold, 0.18)],
          [1, themeRgba(PALETTE.gold, 0.02)]
        ]),
        fill: 'origin',
        pointRadius: 4,
        pointHoverRadius: 7,
        pointHitRadius: 10,
        pointBackgroundColor: dotColors,
        pointBorderColor: PALETTE.surface2,
        pointBorderWidth: 1.5,
        tension: 0.3
      }]
    },
    plugins: [goodZone, dotsAndLabels],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom so value labels above the highest dot never clip.
      layout: { padding: { top: 16 } },
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: {
          title: { display: !_mobileVP(), text: 'Days Before Event', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: _mobileVP() ? 10 : 9 }, maxRotation: 0 },
          grid: { display: false }
        },
        y: {
          min: 0, max: Math.round(maxMAE * 10) / 10,
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: _mobileVP() ? 9 : 8 }, maxTicksLimit: 4,
            callback(v) { return v + '%'; } },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' }, bodyFont: { size: 12 },
          displayColors: false,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const a = agg[items[0].dataIndex];
              return `T-${a.T} (${a.T} days before event)`;
            },
            label(item) { return ` MAE: ${item.parsed.y.toFixed(1)}%`; },
            afterBody(items) {
              if (!items.length) return [];
              const a = agg[items[0].dataIndex];
              const bias = a.bias_pct > 0 ? `+${a.bias_pct}` : `${a.bias_pct}`;
              return [`  n=${a.n}`, `  Bias: ${bias}%`, `  CI coverage: ${a.ci_coverage}%`];
            }
          }
        }
      }
    }
  });
}

function perfDrawTable(data) {
  const table = document.getElementById('perfTable');
  const agg = data.aggregate;
  const tPoints = agg.map(a => a.T);

  let html = `<table class="perf-table">
    <thead><tr>
      <th>Tournament</th>
      <th class="num">Final</th>`;
  tPoints.forEach(T => { html += `<th class="perf-th-t">T-${T}</th>`; });
  html += `</tr></thead><tbody>`;

  data.tournaments.forEach(t => {
    html += `<tr>
      <td data-label="Tournament" class="perf-name">${esc(t.family)}</td>
      <td data-label="Final" class="num">${t.final_count.toLocaleString()}</td>`;
    tPoints.forEach(T => {
      const p = t.predictions.find(p => p.T === T);
      if (p) {
        // Neutral by default; the pen marks exceptions only. A large miss is
        // written in red; a result outside the range is boxed in red.
        const bigMiss = Math.abs(p.error_pct) > 15;
        const err = `${p.error_pct > 0 ? '+' : ''}${p.error_pct}%`;
        const title = `Predicted ${p.predicted} from ${p.count_at_T} registered, range ${p.ci_lower} to ${p.ci_upper}${p.in_ci ? '' : ', actual outside the range'}`;
        html += `<td data-label="T-${T}" class="perf-cell${bigMiss ? ' perf-miss-big' : ''}" title="${title}">${p.in_ci ? err : `<span class="perf-miss">${err}</span>`}</td>`;
      } else {
        html += `<td data-label="T-${T}" class="perf-cell perf-none">\u2014</td>`;
      }
    });
    html += '</tr>';
  });

  // Aggregate
  html += `<tr class="perf-agg">
    <td data-label="Average" colspan="2">Average (${data.n_tournaments})</td>`;
  tPoints.forEach(T => {
    const a = agg.find(x => x.T === T);
    if (a) {
      html += `<td data-label="T-${T}" class="perf-cell">
        <div>${a.mae_pct}%</div>
        <div class="perf-cell-ci">CI ${a.ci_coverage}%</div></td>`;
    } else html += `<td data-label="T-${T}" class="perf-cell perf-none">\u2014</td>`;
  });
  html += '</tr></tbody></table>';
  html += '<p class="perf-table-key">Each cell is the miss at that lead time. A miss over 15% is written in red; a figure boxed in red is one where the actual landed outside the predicted range.</p>';
  table.innerHTML = html;
}
