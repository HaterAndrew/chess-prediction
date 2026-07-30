// tab_performance.js — model performance tab, split verbatim from app.js (C5).

// ══════════════════════════════════════════════════════════
// MODEL PERFORMANCE TAB
// ══════════════════════════════════════════════════════════
let perfInited = false;
let perfSelectedKey = null;

function initPerformanceTab() {
  if (perfInited) return;
  perfInited = true;

  const data = typeof PERFORMANCE_DATA !== 'undefined' ? PERFORMANCE_DATA : {};
  const hasYears = data.years && Object.values(data.years).some(y => y && y.n_tournaments > 0);
  const hasCumulative = data.cumulative && data.cumulative.n_tournaments > 0;
  const hasFlat = data.aggregate && data.aggregate.length > 0;

  if (!hasYears && !hasCumulative && !hasFlat) {
    document.getElementById('perfGradeLetter').textContent = '--';
    document.getElementById('perfGradeLabel').textContent = 'NO DATA';
    document.getElementById('perfGradeDetail').textContent = 'Performance data will appear once tournaments complete.';
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

    selector.innerHTML = '<span class="perf-view-label">View:</span>' +
      buttons.map(b => `<button data-act="perf-year" data-year="${b.key}" id="perfYearBtn_${b.key}" class="perf-year-btn">${b.label}</button>`).join('');

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

function perfPaint(view) {
  const agg = view.aggregate || [];
  const gc = {'A+':PALETTE.green,'A':PALETTE.green,'A-':PALETTE.greenBright,'B+':PALETTE.greenBright,'B':'var(--gold)','B-':'var(--gold)','C+':PALETTE.orangeBright,'C':PALETTE.orangeBright,'C-':PALETTE.orange,'D':PALETTE.red,'F':PALETTE.red};
  document.getElementById('perfGradeLetter').textContent = view.grade || '--';
  document.getElementById('perfGradeLetter').style.color = gc[view.grade] || 'var(--muted)';
  document.getElementById('perfGradeLabel').textContent = 'MODEL GRADE';
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
    document.getElementById('perfTable').innerHTML = '<div style="color:var(--muted);padding:12px 0;font-size:var(--fs-2)">No completed tournaments for this selection.</div>';
    return;
  }

  const t14 = agg.find(a => a.T === 14) || agg[0];
  const t1 = agg.find(a => a.T === 1);
  const avgCov = Math.round(agg.reduce((s, a) => s + a.ci_coverage, 0) / agg.length);
  const avgBias = +(agg.reduce((s, a) => s + a.bias_pct, 0) / agg.length).toFixed(1);

  const kpis = [
    {v: t14.mae_pct.toFixed(1) + '%', l: '2-Week Error', s: 'MAE at T-14', c: t14.mae_pct <= 8 ? PALETTE.green : t14.mae_pct <= 15 ? 'var(--gold)' : PALETTE.red},
    {v: t1 ? t1.mae_pct.toFixed(1) + '%' : '--', l: 'Day-Before', s: 'MAE at T-1', c: t1 && t1.mae_pct <= 5 ? PALETTE.green : PALETTE.greenBright},
    {v: avgCov + '%', l: 'CI Coverage', s: 'Target 80%', c: avgCov >= 75 ? PALETTE.green : avgCov >= 60 ? 'var(--gold)' : PALETTE.red},
    {v: (avgBias > 0 ? '+' : '') + avgBias + '%', l: 'Bias', s: avgBias > 2 ? 'Over-predicts' : avgBias < -2 ? 'Under-predicts' : 'Well-centered', c: Math.abs(avgBias) <= 5 ? PALETTE.green : 'var(--gold)'},
  ];
  document.getElementById('perfKPIs').innerHTML = kpis.map(k => `
    <div style="padding:12px 14px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;text-align:center">
      <div style="font-size:1.4rem;font-weight:800;color:${k.c};line-height:1;font-variant-numeric:tabular-nums">${k.v}</div>
      <div style="font-size:var(--fs-1);font-weight:600;color:var(--text);margin-top:5px;letter-spacing:.03em">${k.l}</div>
      <div style="font-size:var(--fs-1);color:var(--muted);margin-top:1px">${k.s}</div>
    </div>`).join('');

  requestAnimationFrame(() => {
    perfDrawScatter(view);
    perfDrawTimeline(view);
  });

  const strip = document.getElementById('perfHorizonStrip');
  strip.innerHTML = agg.map(a => {
    // One encoding: the MAE value alone carries the traffic color.
    const tc = a.mae_pct <= 8 ? PALETTE.green : a.mae_pct <= 12 ? 'var(--gold)' : PALETTE.red;
    return `<div class="horizon-tile" title="n=${a.n}, bias ${a.bias_pct > 0 ? '+' : ''}${a.bias_pct}%">
      <div class="horizon-t">T-${a.T}</div>
      <div class="horizon-val" style="color:${tc}">${a.mae_pct.toFixed(1)}%</div>
      <div class="horizon-ci">CI ${a.ci_coverage}%</div>
    </div>`;
  }).join('');

  perfDrawTable(view);
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
      ctx2.fillStyle = themeRgba(PALETTE.gold, 0.9);
      ctx2.font = `${_mobileVP() ? 9 : 8}px system-ui`;
      ctx2.textAlign = 'right';
      ctx2.fillText('Perfect prediction', xS.right - 2, yS.top + 10);
      ctx2.restore();
    }
  };

  // Per-dataset dot glow (the in-CI and out-CI buckets are separate datasets
  // precisely so each gets its own shadow color).
  const dotGlow = {
    id: 'perfDotGlow',
    beforeDatasetDraw(c, args) {
      if (args.index > 1) return;
      c.ctx.save();
      c.ctx.shadowBlur = 8;
      c.ctx.shadowColor = args.index === 0 ? PALETTE.green : PALETTE.red;
    },
    afterDatasetDraw(c, args) {
      if (args.index > 1) return;
      c.ctx.restore();
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
          borderColor: themeRgba(PALETTE.gold, 0.2), borderDash: [8, 5], borderWidth: 1.5,
          pointRadius: 0, pointHitRadius: 0, pointHoverRadius: 0 }
      ]
    },
    plugins: [ciWhiskers, dotGlow],
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

  // Threshold-colored glow dots + always-on value labels, as in the
  // hand-rolled renderer (shadowed redraws over the dataset's own points so
  // each dot keeps its own glow color).
  const dotsAndLabels = {
    id: 'tlDotsLabels',
    afterDatasetsDraw(c) {
      const meta = c.getDatasetMeta(0);
      const ctx2 = c.ctx;
      ctx2.save();
      meta.data.forEach((el, i) => {
        const col = dotColors[i];
        ctx2.shadowColor = col; ctx2.shadowBlur = 6;
        ctx2.fillStyle = col;
        ctx2.beginPath(); ctx2.arc(el.x, el.y, 4, 0, Math.PI * 2); ctx2.fill();
        ctx2.shadowBlur = 0;
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

  let html = `<table style="width:100%;border-collapse:collapse;font-size:var(--fs-2)">
    <thead><tr style="border-bottom:2px solid var(--border)">
      <th style="padding:8px 10px;text-align:left;white-space:nowrap">Tournament</th>
      <th style="padding:8px 8px;text-align:right;white-space:nowrap">Final</th>`;
  tPoints.forEach(T => { html += `<th style="padding:8px 4px;text-align:center;font-size:var(--fs-1);white-space:nowrap">T-${T}</th>`; });
  html += `</tr></thead><tbody>`;

  data.tournaments.forEach((t, idx) => {
    const bg = idx % 2 ? 'background:var(--surface2)' : '';
    html += `<tr style="border-bottom:1px solid ${themeRgba(PALETTE.border,.4)};${bg}">
      <td data-label="Tournament" style="padding:5px 10px;white-space:nowrap;font-weight:500">${esc(t.family)}</td>
      <td data-label="Final" style="padding:5px 8px;text-align:right;font-weight:700;font-variant-numeric:tabular-nums">${t.final_count.toLocaleString()}</td>`;
    tPoints.forEach(T => {
      const p = t.predictions.find(p => p.T === T);
      if (p) {
        // Neutral by default; color marks exceptions only (phase 6). A cell
        // goes red when the miss is large or the CI failed to cover.
        const bigMiss = Math.abs(p.error_pct) > 15;
        const ec = bigMiss ? PALETTE.red : PALETTE.text2;
        const ci = p.in_ci ? '\u2713' : '\u2717';
        const cic = p.in_ci ? PALETTE.muted : PALETTE.red;
        html += `<td data-label="T-${T}" style="padding:5px 4px;text-align:center;font-size:var(--fs-1)" title="Pred ${p.predicted} from ${p.count_at_T} reg, CI [${p.ci_lower}-${p.ci_upper}]">
          <span style="color:${ec};font-weight:600;font-variant-numeric:tabular-nums">${p.error_pct > 0 ? '+' : ''}${p.error_pct}%</span><span style="color:${cic};font-size:var(--fs-1);margin-left:2px">${ci}</span></td>`;
      } else {
        html += `<td data-label="T-${T}" style="padding:5px 4px;text-align:center;color:var(--muted)">\u2014</td>`;
      }
    });
    html += '</tr>';
  });

  // Aggregate
  html += `<tr style="border-top:2px solid var(--border);font-weight:700;background:rgba(240,192,64,.04)">
    <td data-label="Average" style="padding:8px 10px" colspan="2">Average (${data.n_tournaments})</td>`;
  tPoints.forEach(T => {
    const a = agg.find(x => x.T === T);
    if (a) {
      html += `<td data-label="T-${T}" style="padding:8px 4px;text-align:center;font-size:var(--fs-1)">
        <div style="color:var(--text)">${a.mae_pct}%</div>
        <div style="font-size:var(--fs-1);color:var(--muted);font-weight:400">CI ${a.ci_coverage}%</div></td>`;
    } else html += `<td data-label="T-${T}">\u2014</td>`;
  });
  html += '</tr></tbody></table>';
  table.innerHTML = html;
}
