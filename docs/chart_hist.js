// chart_hist.js — the History bars: past editions and this one, each with its
// count (split from app.js, C11; the registration curve is chart_curve.js).

// ══════════════════════════════════════════════════════════
// HISTORY
// ══════════════════════════════════════════════════════════
// Each bar's count over its top; this edition's reads "est" until it is final.
function _barValuesPlugin(counts, done) {
  return {
    id: 'barValues',
    afterDatasetsDraw(chartInstance) {
      const ctx2 = chartInstance.ctx;
      const bars = chartInstance.getDatasetMeta(0).data;
      ctx2.save();
      ctx2.textAlign = 'center';
      ctx2.textBaseline = 'bottom';
      bars.forEach((bar, i) => {
        const current = i === counts.length - 1;
        ctx2.fillStyle = current ? PALETTE.text : PALETTE.muted;
        ctx2.font = chartLabelFont(11, current ? '700' : '');
        ctx2.fillText(`${fmt(counts[i])}${current && !done ? ' est' : ''}`, bar.x, bar.y - 4);
      });
      ctx2.restore();
    }
  };
}

function renderHistorical(t) {
  const ctx = document.getElementById('histChart');
  if (histChartObj) { histChartObj.destroy(); histChartObj = null; }
  const note = document.getElementById('histNote');
  note.innerHTML = '';
  if (!t.historical || t.historical.length === 0) {
    note.innerHTML = `<div style="text-align:center;padding:20px 0;color:var(--muted);font-size:var(--fs-body);opacity:.6">No historical editions on record</div>`;
    return;
  }
  if (typeof Chart === 'undefined') {
    // Charting library did not load (CDN blocked or offline): say so rather
    // than throw, so the rest of the panel still renders.
    note.innerHTML = `<div style="text-align:center;padding:20px 0;color:var(--muted);font-size:var(--fs-body);opacity:.6">Chart unavailable (the charting library did not load)</div>`;
    return;
  }

  const hist = t.historical.slice(-6);
  const histFlags = hist.map(h => h.adjusted ? { kind: h.adjusted, raw: h.count_raw } : null);
  const hasAdjusted = histFlags.some(Boolean);
  const labels = [...hist.map(h => h.adjusted ? `${h.year}*` : String(h.year)), String(t.year)];
  const counts = [...hist.map(h => h.count), isDone(t) ? t.current_count : t.point_estimate];
  // Flat bars: past editions in the history grey, this edition on the
  // highlighter with an ink rule round it (the current thing on the sheet).
  const isCurrent = i => i === counts.length - 1;
  const colors = counts.map((_, i) => isCurrent(i) ? PALETTE.mark : themeRgba(PALETTE.hist, 0.35));
  const hoverColors = counts.map((_, i) => isCurrent(i) ? PALETTE.mark : themeRgba(PALETTE.hist, 0.55));
  const borders = counts.map((_, i) => isCurrent(i) ? PALETTE.text : PALETTE.hist);
  const hoverBorders = counts.map(() => PALETTE.text);

  // Average line plugin
  const histAvg = Math.round(hist.reduce((s, h) => s + h.count, 0) / hist.length);
  const avgLinePlugin = {
    id: 'avgLine',
    afterDraw(chartInstance) {
      const yScale = chartInstance.scales.y;
      const ctx2 = chartInstance.ctx;
      const y = yScale.getPixelForValue(histAvg);
      ctx2.save();
      ctx2.beginPath();
      ctx2.setLineDash([6, 4]);
      ctx2.strokeStyle = PALETTE.muted;
      ctx2.lineWidth = 1;
      // Span the plot area, not the y-axis bounding box. yScale.left sits
      // behind the tick labels, so the line started well left of the first bar
      // while its other end already used the x scale (2026-09-07 review).
      ctx2.moveTo(chartInstance.scales.x.left, y);
      ctx2.lineTo(chartInstance.scales.x.right, y);
      ctx2.stroke();
      ctx2.fillStyle = PALETTE.muted;
      ctx2.font = chartLabelFont(11);
      ctx2.textAlign = 'right';
      ctx2.fillText(`avg ${fmt(histAvg)}`, chartInstance.scales.x.right, y - 4);
      ctx2.restore();
    }
  };

  histChartObj = new Chart(ctx, {
    type: 'bar',
    data: {
      labels, datasets: [{
        data: counts, backgroundColor: colors, borderColor: borders,
        hoverBackgroundColor: hoverColors, hoverBorderColor: hoverBorders,
        borderWidth: 1.5, borderRadius: 0, borderSkipped: 'bottom',
        categoryPercentage: 0.72, barPercentage: 0.85
      }]
    },
    plugins: [avgLinePlugin, _barValuesPlugin(counts, isDone(t))],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom for the counts over the bars.
      layout: { padding: { top: 18 } },
      plugins: {
        legend: { display: false },
        tooltip: chartTooltip({
          displayColors: true,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              return labels[items[0].dataIndex] + ' Edition';
            },
            label(item) {
              return ` Entries: ${fmt(item.raw)}`;
            },
            afterBody(items) {
              if (!items.length) return [];
              const lines = [];
              const idx = items[0].dataIndex;
              const val = counts[idx];
              // Year-over-year change
              if (idx > 0) {
                const prev = counts[idx - 1];
                const diff = val - prev;
                const pct = ((diff / prev) * 100).toFixed(1);
                const sign = diff > 0 ? '+' : '';
                lines.push(`  YoY: ${sign}${fmt(diff)} (${sign}${pct}%)`);
              }
              // vs historical average
              lines.push(`  Hist avg: ${fmt(histAvg)}`);
              const diffAvg = ((val - histAvg) / histAvg * 100).toFixed(1);
              const signA = diffAvg > 0 ? '+' : '';
              lines.push(`  vs avg: ${signA}${diffAvg}%`);
              // Flag pre-split top-6 adjustment (idx into hist array, exclude current year)
              if (idx < histFlags.length && histFlags[idx]) {
                const flag = histFlags[idx];
                lines.push(`  * adjusted from ${fmt(flag.raw)} (excludes lower sections)`);
              }
              return lines;
            },
            footer(items) {
              if (!items.length) return '';
              const idx = items[0].dataIndex;
              if (idx === counts.length - 1 && !isDone(t)) return 'Predicted (not final)';
              return '';
            }
          }
        })
      },
      scales: {
        x: { grid: chartGridX(), border: chartBorderX(), ticks: chartTicks() },
        y: { beginAtZero: true, grid: chartGridY(), border: chartBorderY(), ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 4 : 6, callback: v => v >= 1000 ? (v/1000).toFixed(0) + 'k' : v }) }
      }
    }
  });

  const footnote = hasAdjusted
    ? `<div class="comp-footnote">* 2019 and 2022 World Open were a single combined registration page (9 sections). Counts adjusted to top-6 only for apples-to-apples vs the 2023+ split. Estimates use chessevents.com final-standings ratios.</div>`
    : '';

  note.innerHTML = footnote;
}
