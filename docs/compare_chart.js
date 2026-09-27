// compare_chart.js — the Compare view's chart: each pick's registrations by
// days before its event as a share of its final (the forecast, for a live
// event), its prior edition as a thin line in the pick's colour, and a dot
// at today (split from tab_compare.js).

// Days before the event for a point [day, count]: from the edition's own
// start and event dates, the main chart's anchor; without them, from the
// tail, taking the last point as tailDB days out.
function _compareDaysBefore(ed, points, tailDB) {
  if (ed.daily_start_date && ed.event_start) {
    const span = daysBetween(ed.daily_start_date, ed.event_start);
    return p => span - p[0];
  }
  const last = points[points.length - 1][0];
  return p => last - p[0] + tailDB;
}

// An edition's sanitised daily series as {x: days before, y: % of target}.
// Same contract as the main chart (v3 P1): points above the scraped total
// are impossible and would skew the share.
function _compareSeries(ed, target, isLive, tailDB) {
  const pts = (typeof DailySeries !== 'undefined')
    ? DailySeries.sanitizeSeries(ed.daily_data, { currentCount: ed.current_count, isLive }).points
    : ed.daily_data;
  if (!pts.length) return [];
  const db = _compareDaysBefore(ed, pts, tailDB);
  return pts.map(p => ({ x: db(p), y: p[1] / target * 100 }));
}

// The latest earlier edition with a daily series. The cards' own
// `historical` list carries counts only; the series live on the historical
// editions in TOURNAMENT_DATA, where the main chart reads them too.
function _comparePrior(t) {
  return (TOURNAMENT_DATA.tournaments || [])
    .filter(o => o.family === t.family && o.status === 'historical' && o.year < t.year &&
                 o.current_count > 0 && Array.isArray(o.daily_data) && o.daily_data.length > 1)
    .sort((a, b) => b.year - a.year)[0] || null;
}

// One pick's lines: this edition (a finished event with no series gets its
// final as one dot on event day), the prior edition for a live event unless
// it is itself a pick, and today's dot at days_remaining, the main chart's
// anchor.
function _compareDatasets(t, ci, picked) {
  const color = compareColors()[ci], live = t.status === 'live';
  const target = live ? t.point_estimate : t.current_count;
  if (!(target > 0)) return [];
  const out = [];
  const line = t.daily_data && t.daily_data.length && t.event_start
    ? _compareSeries(t, target, live, t.days_remaining || 0) : [];
  if (line.length) {
    out.push({
      label: `${t.family} ${t.year}`, data: line,
      borderColor: color, backgroundColor: compareColorsDim()[ci], fill: ci === 0,
      borderWidth: 2.5, borderCapStyle: 'round', pointRadius: 0, pointHoverRadius: 5,
      cubicInterpolationMode: 'monotone',
    });
  } else if (!live) {
    out.push({
      label: `${t.family} ${t.year}`, data: [{ x: 0, y: 100 }],
      borderColor: color, backgroundColor: color, pointRadius: 8, pointStyle: 'circle', showLine: false,
    });
  }
  if (!live) return out;
  let prior = _comparePrior(t);
  if (prior && picked.has(`${prior.family}|${prior.year}`)) prior = null;
  const priorLine = prior ? _compareSeries(prior, prior.current_count, false, 0) : [];
  // Context, not a projection: solid and thin in the pick's colour at 60%,
  // the least that clears 3:1 on the sheet in both themes (a dash means the
  // projection and nothing else).
  if (priorLine.length) {
    out.push({
      label: `${t.family} · ${prior.year} (prior)`, data: priorLine,
      borderColor: themeRgba(color, 0.6), borderWidth: 1.5, borderCapStyle: 'round',
      pointRadius: 0, pointHoverRadius: 3, cubicInterpolationMode: 'monotone', fill: false,
    });
  }
  out.push({
    label: `${t.family} · Today`, data: [{ x: t.days_remaining || 0, y: t.current_count / target * 100 }],
    borderColor: color, backgroundColor: color, pointRadius: 7, pointStyle: 'circle', pointBorderWidth: 2,
    // Canvas cannot resolve CSS custom properties, so the ring reads the
    // paper through PALETTE (a var() here painted it black on every theme).
    pointBorderColor: PALETTE.bg, showLine: false,
  });
  return out;
}

function _compareLabel(selected) {
  const anyLive = selected.some(s => s.t.status === 'live');
  const parts = selected.map(({ t }) => t.status === 'live' && t.point_estimate > 0
    ? `${t.family} ${t.year} at ${Math.round(t.current_count / t.point_estimate * 100)}% of its forecast with ${t.days_remaining} days to go`
    : `${t.family} ${t.year} finished with ${fmt(t.current_count)} entries`);
  return `Registrations by days before each event as a share of the final${anyLive ? ' (the forecast, for a live event)' : ''}: ${parts.join('; ')}.`;
}

function renderCompareChart(selected) {
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  const canvas = document.getElementById('compareChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const picked = new Set(selected.map(s => `${s.t.family}|${s.t.year}`));
  const datasets = selected.flatMap((s, ci) => _compareDatasets(s.t, ci, picked));
  if (!datasets.length) {
    const message = 'No registration data for these picks.';
    const note = document.createElement('div');
    note.className = 'chart-tile-empty';
    note.textContent = message;
    canvas.parentNode.appendChild(note);
    chartDescribe(canvas, { label: message });
    return;
  }
  const allDone = selected.every(s => s.t.status !== 'live');

  _compareChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // v4 U6: without this the chart falls back to nearest+intersect:true and a
      // fingertip has to land on the 2.5px line itself. Same contract as the
      // scatter and timeline charts.
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: {
          type: 'linear',
          reverse: true,
          title: chartAxisTitle('Days Before Event'),
          ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 5 : 8,
            callback(v) { return v === 0 ? 'Event' : v + 'd'; }
          }),
          grid: chartGridX(),
          border: chartBorderX()
        },
        y: {
          title: chartAxisTitle(allDone ? '% of Final Entries' : '% of Final (Forecast for Live Events)'),
          ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 5 : 8,
            callback(v) { return v + '%'; }
          }),
          grid: chartGridY(),
          border: chartBorderY(),
          min: 0
        }
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: PALETTE.text2,
            font: { size: 11 },
            boxWidth: _mobileVP() ? 8 : 12,
            padding: _mobileVP() ? 6 : 10,
            filter(item) { return !item.text.includes('· Today'); },
            usePointStyle: true, pointStyle: 'line'
          }
        },
        tooltip: chartTooltip({
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = items[0].parsed.x;
              return db === 0 ? 'Event Day' : `T-${db} (${db} days before)`;
            },
            label(item) {
              return ` ${item.dataset.label}: ${item.parsed.y.toFixed(1)}%`;
            }
          }
        })
      }
    }
  });
  chartDescribe(canvas, { label: _compareLabel(selected) });
}
