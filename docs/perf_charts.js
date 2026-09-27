// perf_charts.js — the Performance view's two charts: Predicted vs Actual and
// Error by Lead Time (split from tab_performance.js).

// Log-axis ticks a reader can place: the 1-2-5 series within the data.
const PERF_LOG_TICKS = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

function _perfScatterPoints(data, T) {
  const pts = [];
  data.tournaments.forEach(t => {
    const p = t.predictions.find(x => x.T === T);
    if (p && p.predicted > 0 && t.final_count > 0) {
      pts.push({ x: t.final_count, y: p.predicted, f: t.family, yr: (t.event_start || '').slice(0, 4),
                 lo: p.ci_lower, hi: p.ci_upper, ok: !!p.in_ci });
    }
  });
  return pts;
}

// The key under the tile title, drawn with the chart's own marks.
function _perfScatterKey(T, n) {
  const sub = document.getElementById('perfScatterSub');
  if (sub) sub.textContent = `at T-${T} · ${n} tournaments`;
  const key = document.getElementById('perfScatterKey');
  if (key) {
    key.innerHTML = '<span class="pk"><i class="pk-dot"></i>Inside 80% range</span>' +
      '<span class="pk"><i class="pk-ring"></i>Outside</span>' +
      '<span class="pk"><i class="pk-line"></i>Perfect</span>' +
      '<span class="pk"><i class="pk-band"></i>Within 10%</span>';
  }
}

function perfDrawScatter(data, T) {
  const canvas = document.getElementById('perfScatterCanvas');
  if (!canvas) return;
  // perfSelectYear re-runs perfPaint on every view click; Chart.js throws
  // "Canvas is already in use" without an explicit destroy.
  if (perfScatterChart) { perfScatterChart.destroy(); perfScatterChart = null; }

  // Only events with a real prediction at T: the title says T, so no event
  // silently stands in with another horizon's forecast.
  const pts = _perfScatterPoints(data, T);
  _perfScatterKey(T, pts.length);
  if (!pts.length) {
    chartDescribe(canvas, { label: `Predicted versus actual at T-${T}: no tournaments.` });
    return;
  }
  const vals = pts.flatMap(p => [p.x, p.y, p.lo || p.y, p.hi || p.y]);
  const min = Math.max(1, Math.min(...vals) * 0.8), max = Math.max(...vals) * 1.15;
  const ticks = PERF_LOG_TICKS.filter(v => v >= min && v <= max);

  // The ±10% band round the diagonal, then each event's 80% range as a
  // whisker, behind the dots. On log axes both are straight.
  const guides = {
    id: 'perfGuides',
    beforeDatasetsDraw(c) {
      const xS = c.scales.x, yS = c.scales.y, g = c.ctx, a = c.chartArea;
      const P = (x, y) => [xS.getPixelForValue(x), yS.getPixelForValue(y)];
      g.save();
      g.beginPath(); g.rect(a.left, a.top, a.right - a.left, a.bottom - a.top); g.clip();
      g.fillStyle = themeRgba(PALETTE.hist, 0.14);
      g.beginPath();
      [[min, min * 0.9], [max, max * 0.9], [max, max * 1.1], [min, min * 1.1]].forEach(([x, y], i) => {
        const [px, py] = P(x, y);
        if (i) g.lineTo(px, py); else g.moveTo(px, py);
      });
      g.fill();
      g.strokeStyle = PALETTE.muted; g.lineWidth = 1;
      g.beginPath(); g.moveTo(...P(min, min)); g.lineTo(...P(max, max)); g.stroke();
      pts.forEach(p => {
        if (!p.lo || !p.hi) return;
        const [px, yLo] = P(p.x, p.lo), yHi = yS.getPixelForValue(p.hi);
        g.strokeStyle = themeRgba(p.ok ? PALETTE.blue : PALETTE.red, 0.5); g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(px, yLo); g.lineTo(px, yHi);
        g.moveTo(px - 3, yLo); g.lineTo(px + 3, yLo); g.moveTo(px - 3, yHi); g.lineTo(px + 3, yHi);
        g.stroke();
      });
      g.restore();
    }
  };

  const logAxis = title => ({
    type: 'logarithmic', min, max, title: chartAxisTitle(title),
    afterBuildTicks(axis) { axis.ticks = ticks.map(v => ({ value: v })); },
    ticks: chartTicks({ autoSkip: false, callback: v => fmt(v) })
  });
  const inside = { pointRadius: 4.5, pointBackgroundColor: PALETTE.blue, pointBorderColor: PALETTE.surface, pointBorderWidth: 1.2 };
  // A miss is a ring: it reads without colour too.
  const outside = { pointRadius: 4.5, pointBackgroundColor: PALETTE.surface, pointBorderColor: PALETTE.red, pointBorderWidth: 2 };

  perfScatterChart = new Chart(canvas, {
    type: 'scatter',
    data: { datasets: [
      Object.assign({ label: 'Inside 80% range', data: pts.filter(p => p.ok), pointHoverRadius: 7, pointHitRadius: 8 }, inside),
      Object.assign({ label: 'Outside', data: pts.filter(p => !p.ok), pointHoverRadius: 7, pointHitRadius: 8 }, outside),
    ] },
    plugins: [guides],
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: Object.assign(logAxis('Actual Entries'), { grid: chartGridX(), border: chartBorderX() }),
        y: Object.assign(logAxis('Predicted'), { grid: chartGridY(), border: chartBorderY() })
      },
      plugins: {
        legend: { display: false },
        tooltip: chartTooltip({
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) { return items.length ? `${items[0].raw.f} ${items[0].raw.yr}` : ''; },
            label(item) { return ` Predicted: ${fmt(item.raw.y)}`; },
            afterLabel(item) {
              const miss = ((item.raw.y - item.raw.x) / item.raw.x * 100).toFixed(1);
              return [` Actual: ${fmt(item.raw.x)} (miss ${miss > 0 ? '+' : ''}${miss}%)`,
                      ` 80% range: ${fmt(item.raw.lo)} – ${fmt(item.raw.hi)}`];
            },
            footer(items) { return items.length ? (items[0].raw.ok ? 'Inside the 80% range' : 'Outside the 80% range') : ''; }
          }
        })
      }
    }
  });

  const misses = pts.map(p => Math.abs(p.y - p.x) / p.x * 100).sort((a, b) => a - b);
  const median = misses[Math.floor(misses.length / 2)];
  chartDescribe(canvas, {
    label: `Predicted versus actual entries at T-${T} for ${pts.length} tournaments: ${pts.filter(p => p.ok).length} finals inside their 80% range; median miss ${median.toFixed(1)}%.`,
    caption: `Predicted versus actual entries at T-${T}`,
    columns: ['Tournament', 'Actual', 'Predicted', '80% Range', 'Inside the Range'],
    rows: pts.map(p => [`${p.f} ${p.yr}`, fmt(p.x), fmt(p.y), `${fmt(p.lo)} to ${fmt(p.hi)}`, p.ok ? 'Yes' : 'No'])
  });
}

function perfDrawTimeline(data) {
  const canvas = document.getElementById('perfTimelineCanvas');
  if (!canvas) return;
  if (perfTimelineChart) { perfTimelineChart.destroy(); perfTimelineChart = null; }

  const agg = [...data.aggregate].sort((a, b) => b.T - a.T);
  if (!agg.length) return;
  const maxMAE = Math.max(...agg.map(a => a.mae_pct)) * 1.3;

  // Each horizon's figure beside its point, on a halo, in the first spot
  // clear of the line, the dots and the figures already placed.
  const values = {
    id: 'tlValues',
    afterDatasetsDraw(c) {
      const g = c.ctx, pts = c.getDatasetMeta(0).data;
      g.save();
      // 11px on a phone, where eight figures share the width.
      g.font = chartLabelFont(_mobileVP() ? 11 : 12, 'bold');
      g.fillStyle = PALETTE.text;
      const segments = pts.slice(1).map((el, i) => [pts[i].x, pts[i].y, el.x, el.y]);
      // A dot is 4px plus half its 1.5px ring.
      const taken = pts.map(el => ({ l: el.x - 5, r: el.x + 5, t: el.y - 5, b: el.y + 5 }));
      // Right of the y-axis figures, which a label beside the first point can cover.
      const area = { l: c.chartArea.left, t: 0, r: c.width, b: c.chartArea.bottom };
      pts.forEach((el, i) => {
        const text = agg[i].mae_pct.toFixed(1) + '%';
        const spot = chooseLabelSpot(el.x, el.y, _labelWidth(g, text) + 6, 15,
                                     { segments, taken, area, gap: 7, margin: 1.5, radius: 5 });
        taken.push(spot.box);
        chartHaloText(g, text, spot.x, spot.y, 'center');
      });
      g.restore();
    }
  };

  perfTimelineChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: agg.map(a => 'T-' + a.T),
      datasets: [{
        data: agg.map(a => a.mae_pct),
        borderColor: PALETTE.projected,
        borderWidth: 2,
        fill: false,
        tension: 0,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointHitRadius: 10,
        pointBackgroundColor: PALETTE.projected,
        pointBorderColor: PALETTE.surface,
        pointBorderWidth: 1.5
      }]
    },
    plugins: [values],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom so the figure over the highest point never clips.
      layout: { padding: { top: 22, left: 8, right: 8 } },
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: { title: chartAxisTitle('Days Before Event'), ticks: chartTicks(), grid: chartGridX(), border: chartBorderX() },
        y: {
          min: 0, max: Math.ceil(maxMAE),
          ticks: chartTicks({ maxTicksLimit: 4, callback(v) { return v + '%'; } }),
          grid: chartGridY(),
          border: chartBorderY()
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: chartTooltip({
          displayColors: false,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const a = agg[items[0].dataIndex];
              return `T-${a.T} (${a.T} days before event)`;
            },
            label(item) { return ` Average miss: ${item.parsed.y.toFixed(1)}%`; },
            afterBody(items) {
              if (!items.length) return [];
              const a = agg[items[0].dataIndex];
              const bias = a.bias_pct > 0 ? `+${a.bias_pct}` : `${a.bias_pct}`;
              return [`  n=${a.n}`, `  Bias: ${bias}%`, `  Inside 80% range: ${a.ci_coverage}%`];
            }
          }
        })
      }
    }
  });

  chartDescribe(canvas, {
    label: `Average miss by days before the event: ${agg[0].mae_pct}% at T-${agg[0].T}, ${agg[agg.length - 1].mae_pct}% at T-${agg[agg.length - 1].T}.`,
    caption: 'Average miss at each horizon',
    columns: ['Horizon', 'Average Miss', 'Tournaments', 'Bias', 'Inside 80% Range'],
    rows: agg.map(a => [`T-${a.T}`, `${a.mae_pct}%`, a.n, `${a.bias_pct > 0 ? '+' : ''}${a.bias_pct}%`, `${a.ci_coverage}%`])
  });
}

// An empty selection clears both charts and says so in their tiles.
function perfClearCharts(message) {
  if (perfScatterChart) { perfScatterChart.destroy(); perfScatterChart = null; }
  if (perfTimelineChart) { perfTimelineChart.destroy(); perfTimelineChart = null; }
  ['perfScatterCanvas', 'perfTimelineCanvas'].forEach(id => {
    const cv = document.getElementById(id);
    if (!cv) return;
    chartDescribe(cv, { label: message });
    const body = cv.parentNode;
    let note = body.querySelector('.chart-tile-empty');
    if (!note) {
      note = document.createElement('div');
      note.className = 'chart-tile-empty';
      body.appendChild(note);
    }
    note.textContent = message;
  });
  const key = document.getElementById('perfScatterKey');
  if (key) key.innerHTML = '';
}

function perfClearEmptyNotes() {
  document.querySelectorAll('.perf-charts-grid .chart-tile-empty').forEach(n => n.remove());
}
