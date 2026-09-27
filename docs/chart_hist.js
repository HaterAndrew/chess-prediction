// chart_hist.js — the History bars: past editions and this one, each with its
// count, a live edition's 80% range as a whisker, and an empty slot for
// missing years (split from app.js, C11; the registration curve is
// chart_curve.js).

// ══════════════════════════════════════════════════════════
// HISTORY
// ══════════════════════════════════════════════════════════
// Each bar's count over its top, or over the whisker on a live edition,
// which reads "~N" until it is final. A gap slot reads a dash. Counts sit on
// a halo so the average line passes behind them, and a count that would meet
// its left neighbour's (narrow slots on a phone) lifts one line above it.
function _barValuesPlugin(slots, done, rangeTop) {
  return {
    id: 'barValues',
    afterDatasetsDraw(c) {
      const g = c.ctx, xS = c.scales.x, yS = c.scales.y;
      g.save();
      let prev = null;
      slots.forEach((s, i) => {
        const x = xS.getPixelForValue(i);
        if (s.kind === 'gap') {
          g.fillStyle = PALETTE.muted;
          g.font = chartLabelFont(11);
          chartHaloText(g, '—', x, yS.bottom - 10, 'center');
          return;
        }
        const current = s.kind === 'current';
        const barTop = yS.getPixelForValue(s.count);
        const top = current && rangeTop != null ? Math.min(barTop, yS.getPixelForValue(rangeTop)) : barTop;
        const text = current && !done ? `~${fmt(s.count)}` : fmt(s.count);
        g.font = chartLabelFont(11, current ? '700' : '');
        const half = _labelWidth(g, text) / 2 + 5;
        let y = top - 10;
        if (prev && x - half < prev.right && Math.abs(y - prev.y) < 17) y = prev.y - 17;
        prev = { right: x + half, y };
        g.fillStyle = current ? PALETTE.text : PALETTE.muted;
        chartHaloText(g, text, x, y, 'center');
      });
      g.restore();
    }
  };
}

// A live edition's 80% range, an ink whisker with caps through its bar: the
// estimate is a range, not a fact (Padilla, Kay & Hullman on uncertainty).
function _rangeWhiskerPlugin(idx, lo, hi) {
  return {
    id: 'rangeWhisker',
    afterDatasetsDraw(c) {
      const g = c.ctx, x = c.scales.x.getPixelForValue(idx), yS = c.scales.y;
      const yLo = yS.getPixelForValue(lo), yHi = yS.getPixelForValue(hi);
      g.save();
      g.strokeStyle = PALETTE.text;
      g.lineWidth = 1.5;
      g.beginPath();
      g.moveTo(x, yLo); g.lineTo(x, yHi);
      g.moveTo(x - 5, yLo); g.lineTo(x + 5, yLo);
      g.moveTo(x - 5, yHi); g.lineTo(x + 5, yHi);
      g.stroke();
      g.restore();
    }
  };
}

// The past editions' average: a solid hairline behind the bars (a dash is
// kept for projections) with its figure outside the plot on the right, clear
// of every bar's count: "avg 313" on one line, or "avg" over "313" on a
// phone, where the plot needs the width.
// The room it needs, measured in the label font before the chart is built.
function _avgPad(avg) {
  const g = document.createElement('canvas').getContext('2d');
  g.font = chartLabelFont(11);
  const w = _mobileVP()
    ? Math.max(g.measureText('avg').width, g.measureText(fmt(avg)).width) + 4
    : g.measureText(`avg ${fmt(avg)}`).width + 6;
  return Math.ceil(w) + 4;
}
function _avgLinePlugin(avg) {
  return {
    id: 'avgLine',
    beforeDatasetsDraw(c) {
      const g = c.ctx, xS = c.scales.x, y = c.scales.y.getPixelForValue(avg);
      g.save();
      g.strokeStyle = PALETTE.muted;
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(xS.left, y);
      g.lineTo(xS.right, y);
      g.stroke();
      g.fillStyle = PALETTE.muted;
      g.font = chartLabelFont(11);
      g.textAlign = 'left';
      g.textBaseline = 'middle';
      // Outside the plot, in the right padding _avgPad sized.
      if (_mobileVP()) {
        g.fillText('avg', xS.right + 4, y - 7);  // halo: outside the plot
        g.fillText(fmt(avg), xS.right + 4, y + 7);  // halo: outside the plot
      } else {
        g.fillText(`avg ${fmt(avg)}`, xS.right + 6, y);  // halo: outside the plot
      }
      g.restore();
    }
  };
}

// Tick labels: the full year, or "'19" and "'20–21" on a phone, so every
// slot keeps its label instead of Chart.js skipping every other one.
function _histTick(label) {
  return _mobileVP() ? label.replace(/^20(\d\d)/, "'$1") : label;
}

function _histMessage(note, text) {
  note.innerHTML = `<div class="hist-empty">${text}</div>`;
}

function renderHistorical(t) {
  const ctx = document.getElementById('histChart');
  if (histChartObj) { histChartObj.destroy(); histChartObj = null; }
  const note = document.getElementById('histNote');
  note.innerHTML = '';
  if (!t.historical || t.historical.length === 0) {
    _histMessage(note, 'No historical editions on record');
    chartDescribe(ctx, { label: 'History chart: no historical editions on record.' });
    return;
  }
  if (typeof Chart === 'undefined') {
    // Charting library did not load (CDN blocked or offline): say so rather
    // than throw, so the rest of the panel still renders.
    _histMessage(note, 'Chart unavailable (the charting library did not load)');
    chartDescribe(ctx, { label: 'History chart unavailable.' });
    return;
  }

  const done = isDone(t);
  const hist = t.historical.slice(-6);
  const slots = historySlots(hist, { year: t.year, count: done ? t.current_count : t.point_estimate });
  const curIdx = slots.length - 1;
  const showRange = !done && t.ci_lower != null && t.ci_upper != null && t.ci_lower !== t.ci_upper;
  const counts = slots.map(s => s.count);
  // Flat bars: past editions in the history grey, this edition on the
  // highlighter with an ink rule round it (the current thing on the sheet).
  const isCurrent = i => i === curIdx;
  const colors = counts.map((_, i) => isCurrent(i) ? PALETTE.mark : themeRgba(PALETTE.hist, 0.35));
  const hoverColors = counts.map((_, i) => isCurrent(i) ? PALETTE.mark : themeRgba(PALETTE.hist, 0.55));
  const borders = counts.map((_, i) => isCurrent(i) ? PALETTE.text : PALETTE.hist);
  const histAvg = Math.round(hist.reduce((s, h) => s + h.count, 0) / hist.length);
  // The edition before slot i, skipping gap slots, for the change figures.
  const prevIdx = i => { for (let j = i - 1; j >= 0; j--) if (slots[j].kind !== 'gap') return j; return -1; };
  const plugins = [_avgLinePlugin(histAvg), _barValuesPlugin(slots, done, showRange ? t.ci_upper : null)];
  if (showRange) plugins.push(_rangeWhiskerPlugin(curIdx, t.ci_lower, t.ci_upper));

  histChartObj = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: slots.map(s => s.label), datasets: [{
        data: counts, backgroundColor: colors, borderColor: borders,
        hoverBackgroundColor: hoverColors, hoverBorderColor: counts.map(() => PALETTE.text),
        borderWidth: 1.5, borderRadius: 0, borderSkipped: 'bottom',
        categoryPercentage: 0.72, barPercentage: 0.85
      }]
    },
    plugins,
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom for the counts over the bars; room on the right for "avg N".
      // A lifted count on a phone needs a second line of headroom.
      layout: { padding: { top: _mobileVP() ? 34 : 18, right: _avgPad(histAvg) } },
      plugins: {
        legend: { display: false },
        tooltip: chartTooltip({
          displayColors: true,
          filter: item => item.raw != null,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              return slots[items[0].dataIndex].label + ' Edition';
            },
            label(item) {
              return ` Entries: ${fmt(item.raw)}`;
            },
            afterBody(items) {
              if (!items.length) return [];
              const lines = [];
              const idx = items[0].dataIndex;
              const val = counts[idx];
              const p = prevIdx(idx);
              if (p >= 0) {
                const diff = val - counts[p];
                const pct = ((diff / counts[p]) * 100).toFixed(1);
                const sign = diff > 0 ? '+' : '';
                lines.push(`  vs ${slots[p].label}: ${sign}${fmt(diff)} (${sign}${pct}%)`);
              }
              if (isCurrent(idx) && showRange) {
                lines.push(`  80% range: ${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}`);
              }
              lines.push(`  Hist avg: ${fmt(histAvg)}`);
              const diffAvg = ((val - histAvg) / histAvg * 100).toFixed(1);
              lines.push(`  vs avg: ${diffAvg > 0 ? '+' : ''}${diffAvg}%`);
              const flag = slots[idx].flag;
              if (flag) lines.push(`  * adjusted from ${fmt(flag.raw)} (excludes lower sections)`);
              return lines;
            },
            footer(items) {
              if (!items.length) return '';
              return isCurrent(items[0].dataIndex) && !done ? 'Predicted (not final)' : '';
            }
          }
        })
      },
      scales: {
        x: { grid: chartGridX(), border: chartBorderX(),
             ticks: chartTicks({ autoSkip: false, callback(v) { return _histTick(this.getLabelForValue(v)); } }) },
        y: { beginAtZero: true, suggestedMax: showRange ? t.ci_upper : undefined,
             grid: chartGridY(), border: chartBorderY(),
             ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 4 : 6, callback: v => v >= 1000 ? (v/1000).toFixed(0) + 'k' : v }) }
      }
    }
  });

  _describeHistory(t, ctx, slots, { done, showRange, histAvg, prevIdx });
  if (slots.some(s => s.flag)) {
    note.innerHTML = `<div class="comp-footnote">* 2019 and 2022 World Open were a single combined registration page (9 sections). Counts adjusted to top-6 only for apples-to-apples vs the 2023+ split. Estimates use chessevents.com final-standings ratios.</div>`;
  }
}

// The History chart's text alternative: the editions in a sentence, and a
// table with each edition's change on the one before (hover-only on screen).
function _describeHistory(t, canvas, slots, d) {
  const eds = slots.filter(s => s.kind !== 'gap');
  const cur = eds[eds.length - 1];
  const now = d.done
    ? `${cur.label} ${fmt(cur.count)} final`
    : `${cur.label} forecast ~${fmt(cur.count)}${d.showRange ? ` (80% range ${fmt(t.ci_lower)} to ${fmt(t.ci_upper)})` : ''}`;
  const label = `${t.family} entries by edition, ${eds[0].label} to ${cur.label}: ${now}; past average ${fmt(d.histAvg)}.`;
  const rows = slots.map((s, i) => {
    if (s.kind === 'gap') return [s.label, 'No edition on record', null];
    const p = d.prevIdx(i);
    const change = p >= 0 ? `${((s.count - slots[p].count) / slots[p].count * 100).toFixed(1)}%` : null;
    const entries = s.kind === 'current' && !d.done ? `~${fmt(s.count)} (forecast)` : fmt(s.count);
    return [s.label, entries, change];
  });
  chartDescribe(canvas, { label, caption: `${t.family}: entries by edition`, columns: ['Edition', 'Entries', 'Change on the Edition Before'], rows });
}
