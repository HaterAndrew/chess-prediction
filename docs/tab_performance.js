// tab_performance.js — model performance tab, split verbatim from app.js (C5).
// Its two charts, Predicted vs Actual and Error by Lead Time, are in
// perf_charts.js.

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

    selector.innerHTML = '<div class="segmented" role="group" aria-label="Performance view">' +
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
  document.getElementById('perfGradeMeta').textContent = view.generated ? `Updated ${view.generated}` : '';

  if (!agg.length) {
    document.getElementById('perfKPIs').innerHTML = '';
    const sc = document.getElementById('perfScoring');
    if (sc) sc.innerHTML = '';
    document.getElementById('perfTable').innerHTML = '<div class="empty">No completed tournaments for this selection.</div>';
    perfClearCharts('No completed tournaments for this selection.');
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

  perfClearEmptyNotes();
  requestAnimationFrame(() => {
    perfDrawScatter(view, t14.T);
    perfDrawTimeline(view);
  });

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
      <div class="perf-scoring-note">Lower is better.</div>
    </div>`);
  }

  // ── Calibration: one dot per tournament (perf_calibration.js) ──
  parts.push(perfCalibrationHTML(data, t14.T));

  el.innerHTML = parts.join('');
  perfCalibrationFill(el, data);
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
      <td data-label="Final" class="num">${fmt(t.final_count)}</td>`;
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
