// chart_hist.js — historical bar chart + table and the registration-curve
// chart, split verbatim from app.js (C11).

// ══════════════════════════════════════════════════════════
// HISTORICAL CHART + TABLE
// ══════════════════════════════════════════════════════════
function renderHistorical(t) {
  // Bar chart
  const ctx = document.getElementById('histChart');
  if (histChartObj) { histChartObj.destroy(); histChartObj = null; }
  const wrap = document.getElementById('compTableWrap');
  if (!t.historical || t.historical.length === 0) {
    wrap.innerHTML = `<div style="text-align:center;padding:20px 0;color:var(--muted);font-size:var(--fs-2);opacity:.6">No historical editions on record</div>`;
    return;
  }

  const hist = t.historical.slice(-6);
  const histFlags = hist.map(h => h.adjusted ? { kind: h.adjusted, raw: h.count_raw } : null);
  const hasAdjusted = histFlags.some(Boolean);
  const labels = [...hist.map(h => h.adjusted ? `${h.year}*` : String(h.year)), String(t.year)];
  const counts = [...hist.map(h => h.count), isDone(t) ? t.current_count : t.point_estimate];
  // Gradient bars: current year in gold, history in blue, both fading toward
  // the baseline. One cache per bucket; scriptable by dataIndex.
  const _goldBarGrad = {}, _blueBarGrad = {};
  const colors = (context) => {
    const isCurrent = context.dataIndex === counts.length - 1;
    return isCurrent
      ? areaGradient(context.chart, _goldBarGrad, [
          [0, themeRgba(PALETTE.goldBright, 0.85)],
          [1, themeRgba(PALETTE.gold, 0.45)]
        ])
      : areaGradient(context.chart, _blueBarGrad, [
          [0, themeRgba(PALETTE.blue, 0.55)],
          [1, themeRgba(PALETTE.blue, 0.18)]
        ]);
  };
  const hoverColors = counts.map((_, i) => i === counts.length-1
    ? themeRgba(PALETTE.goldBright, 0.95) : themeRgba(PALETTE.blue, 0.7));
  const borders = counts.map((_, i) => i === counts.length-1 ? PALETTE.gold : PALETTE.blue);
  const hoverBorders = counts.map((_, i) => i === counts.length-1 ? PALETTE.goldBright : PALETTE.blueBright);

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
      ctx2.strokeStyle = 'rgba(188,140,255,0.5)';
      ctx2.lineWidth = 1;
      ctx2.moveTo(yScale.left, y);
      ctx2.lineTo(chartInstance.scales.x.right, y);
      ctx2.stroke();
      ctx2.fillStyle = 'rgba(188,140,255,0.7)';
      ctx2.font = '9px -apple-system, system-ui, sans-serif';
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
        borderWidth: 1.5, borderRadius: 6, borderSkipped: 'bottom',
        categoryPercentage: 0.72, barPercentage: 0.85
      }]
    },
    plugins: [avgLinePlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: 14, weight: 'bold' }, bodyFont: { size: 12 }, footerFont: { size: 11, style: 'italic' },
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
        }
      },
      onClick(evt, elements) {
        if (!elements.length) return;
        const clickedYear = labels[elements[0].index];
        // Highlight the corresponding row in the comp-table
        const compRows = document.querySelectorAll('.comp-table tbody tr');
        compRows.forEach(row => {
          row.classList.remove('chart-highlight');
          if (row.cells[0] && row.cells[0].textContent.trim().startsWith(clickedYear)) {
            row.classList.add('chart-highlight');
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => row.classList.remove('chart-highlight'), 2500);
          }
        });
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0 } },
        y: { beginAtZero: true, grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false }, ticks: { color: PALETTE.muted, font: { size: 11 }, maxTicksLimit: _mobileVP() ? 4 : 6, callback: v => v >= 1000 ? (v/1000).toFixed(0) + 'k' : v } }
      }
    }
  });

  // Table — show year-over-year change
  const allYears = [...hist, { year: t.year, count: isDone(t) ? t.current_count : t.point_estimate, isCurrent: true }];
  const rows = allYears.map((h, idx) => {
    const prev = idx > 0 ? allYears[idx - 1].count : null;
    const diff = prev ? h.count - prev : null;
    const pct = prev ? ((diff / prev) * 100).toFixed(1) : null;
    const cls = diff > 0 ? 'delta-pos' : diff < 0 ? 'delta-neg' : '';
    const star = h.adjusted ? '*' : '';
    const yearLabel = h.isCurrent ? `${h.year} ${isDone(t) ? '(final)' : '(est)'}` : `${h.year}${star}`;
    const rowClass = h.isCurrent ? ' class="current-year"' : '';
    const countCell = h.adjusted
      ? `${fmt(h.count)} <span style="color:var(--muted);font-size:var(--fs-2)">(was ${fmt(h.count_raw)})</span>`
      : fmt(h.count);
    return `<tr${rowClass}><td data-label="Year">${yearLabel}</td><td data-label="Count">${countCell}</td><td data-label="YoY" class="${cls}">${diff != null ? (diff > 0 ? '+' : '') + fmt(diff) : '–'}</td><td data-label="Change" class="${cls}">${pct != null ? (diff > 0 ? '+' : '') + pct + '%' : '–'}</td></tr>`;
  }).join('');

  const footnote = hasAdjusted
    ? `<div style="margin-top:8px;color:var(--muted);font-size:var(--fs-2);line-height:1.45">* 2019 and 2022 World Open were a single combined registration page (9 sections). Counts adjusted to top-6 only for apples-to-apples vs the 2023+ split. Estimates use chessevents.com final-standings ratios.</div>`
    : '';

  wrap.innerHTML = `
    <div class="comp-table-wrap">
    <table class="comp-table">
      <thead><tr><th>Year</th><th>Count</th><th title="Year-over-Year">YoY</th><th>Change</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
    ${footnote}
  `;
}

// ══════════════════════════════════════════════════════════
// REGISTRATION CURVE CHART
// ══════════════════════════════════════════════════════════
let regCurveObj = null;
function renderRegCurve(t) {
  const ctx = document.getElementById('regCurveChart');
  if (regCurveObj) { regCurveObj.destroy(); regCurveObj = null; }
  if (!t.registration_curve || t.registration_curve.length === 0) {
    document.getElementById('regCurveCaption').textContent = 'No curve data available';
    return;
  }

  const sorted = [...t.registration_curve].sort((a, b) => b.days_before - a.days_before);
  const labels = sorted.map(pt => pt.days_before);
  const data = sorted.map(pt => ((pt.cumulative_pct || pt.pct || 0) * 100));

  // Mark where "today" is
  const todayIdx = labels.findIndex(db => db <= t.days_remaining);
  const pointColors = labels.map((db, i) => {
    if (isDone(t)) return 'rgba(88,166,255,0.6)';
    return db >= t.days_remaining ? 'rgba(88,166,255,0.6)' : 'rgba(240,192,64,0.6)';
  });

  const _regGrad = {};

  // "You are here" annotation plugin for reg curve
  const regCurveAnnotation = makeVertMarkersPlugin('regCurveAnnotation', () => {
    if (isDone(t)) return [];
    // Find the label index closest to today
    let idx = -1;
    let minDiff = Infinity;
    labels.forEach((db, i) => {
      const d = Math.abs(db - t.days_remaining);
      if (d < minDiff) { minDiff = d; idx = i; }
    });
    if (idx < 0) return [];
    return [{ value: idx, label: 'Today', color: PALETTE.blue }];
  });

  regCurveObj = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.map(db => db === 0 ? 'Event' : db >= 7 ? `${db}d` : `${db}d`),
      datasets: [{
        data,
        borderColor: 'rgba(240,192,64,0.6)',
        backgroundColor: (context) => areaGradient(context.chart, _regGrad, [
          [0, themeRgba(PALETTE.gold, 0.16)],
          [1, themeRgba(PALETTE.gold, 0.02)]
        ]),
        fill: true,
        borderWidth: 2.25,
        // Elapsed/ahead split at today, matching pointColors and the main
        // chart: blue = behind us, gold = still to come. Done tournaments
        // keep the flat base color (no split to show).
        segment: {
          borderColor: (c) => isDone(t) ? undefined :
            (c.p1DataIndex <= todayIdx ? themeRgba(PALETTE.blue, 0.75)
                                       : themeRgba(PALETTE.gold, 0.75))
        },
        pointRadius: labels.map(db => db === 0 || db === t.days_remaining ? 5 : 0),
        pointHoverRadius: 6,
        pointHitRadius: 10,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        tension: 0.4
      }]
    },
    plugins: [regCurveAnnotation],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom for the shared marker pill (drawn 18px above the plot top).
      layout: { padding: { top: 22 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: 12, cornerRadius: 8,
          titleFont: { size: 14, weight: 'bold' }, bodyFont: { size: 12 }, footerFont: { size: 11, style: 'italic' },
          displayColors: true,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = labels[items[0].dataIndex];
              if (db === 0) return 'Event Day';
              return `T-${db} (${db} days before event)`;
            },
            label(item) {
              return ` ${item.raw.toFixed(1)}% of final entries`;
            },
            afterBody(items) {
              if (!items.length) return [];
              const lines = [];
              const db = labels[items[0].dataIndex];
              const pct = items[0].raw / 100;
              // Estimated count at this point
              if (t.point_estimate) {
                const estCount = Math.round(t.point_estimate * pct);
                lines.push(`  Est. entries: ~${fmt(estCount)}`);
              }
              // Compare to current if live
              if (!isDone(t) && db === t.days_remaining) {
                lines.push(`  Actual now: ${fmt(t.current_count)}`);
              }
              return lines;
            },
            footer(items) {
              if (!items.length || isDone(t)) return '';
              const db = labels[items[0].dataIndex];
              if (db > t.days_remaining) return 'Already passed';
              if (db === t.days_remaining) return 'You are here';
              return '';
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0, maxTicksLimit: _mobileVP() ? 6 : 12 }
        },
        y: {
          min: 0, max: 105,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: {
            color: PALETTE.muted, font: { size: 11 },
            maxTicksLimit: _mobileVP() ? 4 : 6,
            callback: v => v + '%'
          }
        }
      }
    }
  });

  // Caption
  const todayPct = interpCurve(t.registration_curve, t.days_remaining);
  if (!isDone(t)) {
    const actualPct = (t.current_count / t.point_estimate * 100).toFixed(1);
    const expectedPct = (todayPct * 100).toFixed(1);
    const diff = (actualPct - expectedPct).toFixed(1);
    const ahead = parseFloat(diff) > 0;
    document.getElementById('regCurveCaption').textContent =
      `At T-${t.days_remaining}: expected ${expectedPct}%, actual ${actualPct}% of predicted final; ${ahead ? 'ahead' : 'behind'} typical pace by ${Math.abs(diff)} percentage points`;
  } else {
    document.getElementById('regCurveCaption').textContent =
      `Historical registration pattern for ${t.family}. Shows % of final entries at each lead time.`;
  }
}
