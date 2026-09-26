// perf_charts.js — the Performance view's two charts: Predicted vs Actual at
// T-14 and Error by Lead Time (split from tab_performance.js).

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
        const col = p.ok ? PALETTE.blue : PALETTE.red;
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
        { label: 'Within CI', data: toXY(pts.filter(p => p.ok)), ...dotCfg(PALETTE.blue) },
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
            callback(v) { return fmt(v); } },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        },
        y: {
          type: 'linear', min: 0, max: maxV,
          title: { display: !_mobileVP(), text: 'Predicted', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: _mobileVP() ? 10 : 9 }, maxTicksLimit: 5,
            callback(v) { return fmt(v); } },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 0,
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
  // The pens as on the tiles: blue for good, ink for fair, red for a miss.
  const threshold = v => v <= 8 ? PALETTE.blue : v <= 12 ? PALETTE.text : PALETTE.red;
  const dotColors = agg.map(a => threshold(a.mae_pct));

  // The good zone under the 10% MAE line, one wash of the blue pen.
  const goodZone = {
    id: 'goodZone',
    beforeDraw(c) {
      const area = c.chartArea;
      const y10 = c.scales.y.getPixelForValue(10);
      if (y10 >= area.bottom) return;
      c.ctx.save();
      c.ctx.fillStyle = themeRgba(PALETTE.blue, 0.06);
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
        borderColor: PALETTE.projected,
        borderWidth: 2.5,
        borderCapStyle: 'round',
        backgroundColor: themeRgba(PALETTE.text, 0.04),
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
          padding: 12, cornerRadius: 0,
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
