// compare_chart.js — the Compare view's chart: each pick's registration curve
// by days before its event, with the prior edition dimmed and the legend
// naming the lines (split from tab_compare.js).

function renderCompareChart(selected) {
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  const canvas = document.getElementById('compareChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // Build datasets from each tournament's ACTUAL daily_data (current edition's
  // real trajectory), not the smoothed prediction curve. y-axis is normalized
  // to % of predicted final, so different-sized tournaments compare cleanly
  // on the same scale. Each live tournament gets:
  //   - A solid line of its actual trajectory so far (this year's daily_data)
  //   - A dashed line of its prior year at T-N (where available) for context
  //   - A "today" dot at the latest data point
  // Completed tournaments get a single solid trace of their full daily_data.
  const datasets = [];
  selected.forEach((s, ci) => {
    const t = s.t;
    const color = compareColors()[ci];
    const dimColor = compareColorsDim()[ci];
    // The y scaling target — predicted for live, actual final for completed.
    const target = (t.status === 'live')
      ? (t.point_estimate || 1)
      : (t.current_count || 1);
    if (target <= 0) return;

    // Current edition trajectory (solid line).
    if (t.daily_data && t.daily_data.length > 0 && t.event_start) {
      // Same contract as the main chart (v3 P1): draw the sanitised series,
      // never the raw array — raw points above the scraped total are
      // impossible and skew the normalized %.
      const dd = (typeof DailySeries !== 'undefined')
        ? DailySeries.sanitizeSeries(t.daily_data, {
            currentCount: t.current_count, isLive: t.status === 'live' }).points
        : t.daily_data;
      // Guard block (not an early return): an empty sanitised series must not
      // silently drop this tournament's prior-year trace below.
      if (dd.length) {
        // Convert daily_data ([day_idx, cumulative]) to (days_before, %).
        const lastDay = dd[dd.length - 1][0];
        const data = dd.map(p => ({
          x: lastDay - p[0] + (t.days_remaining || 0),
          y: (p[1] / target) * 100,
        }));
        datasets.push({
          label: `${t.family} ${t.year}`,
          data,
          borderColor: color,
          backgroundColor: dimColor,
          fill: ci === 0,
          borderWidth: 2.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 5,
          tension: 0.25,
        });
        // Today dot — the very last actual data point.
        if (t.status === 'live') {
          const last = data[data.length - 1];
          datasets.push({
            label: `${t.family} · Today`,
            data: [last],
            borderColor: color,
            backgroundColor: color,
            pointRadius: 7,
            pointStyle: 'circle',
            pointBorderWidth: 2,
            // Canvas cannot resolve CSS custom properties, so the ring reads the
            // paper through PALETTE (a var() here painted it black on every theme).
            pointBorderColor: PALETTE.bg,
            showLine: false,
          });
        }
      }
    }

    // Prior-year context — dashed line of the most recent historical edition
    // (model uses this as part of its training). Surfaces "is this year
    // tracking ahead/behind last year at the same T?" visually.
    if (t.status === 'live' && t.historical && t.historical.length > 0) {
      const prior = t.historical[t.historical.length - 1];
      if (prior && prior.daily_data && prior.daily_data.length > 0
          && prior.count && prior.count > 0) {
        const priorTarget = prior.count;
        const pdd = (typeof DailySeries !== 'undefined')
          ? DailySeries.sanitizeSeries(prior.daily_data, {
              currentCount: prior.count, isLive: false }).points
          : prior.daily_data;
        const priorLast = pdd.length ? pdd[pdd.length - 1][0] : 0;
        const priorData = pdd.map(p => ({
          x: priorLast - p[0],
          y: (p[1] / priorTarget) * 100,
        }));
        datasets.push({
          label: `${t.family} · ${prior.year} (prior)`,
          data: priorData,
          borderColor: color,
          borderDash: [4, 4],
          borderWidth: 1.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 3,
          tension: 0.25,
          fill: false,
        });
      }
    }

    // Final-count fallback: if we couldn't build a daily line (e.g. no
    // daily_data for a completed tournament), at least render a single
    // marker at x=0 (event day) at 100%.
    if (!t.daily_data || t.daily_data.length === 0) {
      datasets.push({
        label: `${t.family} ${t.year}`,
        data: [{ x: 0, y: 100 }],
        borderColor: color, backgroundColor: color,
        pointRadius: 8, pointStyle: 'circle', showLine: false,
      });
    }
  });

  if (datasets.length === 0) return;

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
          title: chartAxisTitle('% of Final Entries'),
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
}
