// chart_curve.js — the registration-curve chart and its caption in the
// Registration Curve and Fees section (split from chart_hist.js).

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
  if (typeof Chart === 'undefined') {
    document.getElementById('regCurveCaption').textContent = 'Chart unavailable (the charting library did not load)';
    return;
  }

  const sorted = [...t.registration_curve].sort((a, b) => b.days_before - a.days_before);
  const labels = sorted.map(pt => pt.days_before);
  const data = sorted.map(pt => ((pt.cumulative_pct || pt.pct || 0) * 100));

  // Mark where "today" is: the elapsed days in the blue pen, the days still
  // to come in ink; a finished event is all elapsed.
  const todayIdx = labels.findIndex(db => db <= t.days_remaining);
  const pointColors = labels.map(db =>
    isDone(t) || db >= t.days_remaining ? PALETTE.actual : PALETTE.projected);

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
    return [{ value: idx, label: 'Today', color: PALETTE.markerToday }];
  });

  regCurveObj = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels.map(db => db === 0 ? 'Event' : db >= 7 ? `${db}d` : `${db}d`),
      datasets: [{
        data,
        borderColor: PALETTE.actual,
        backgroundColor: themeRgba(PALETTE.actual, 0.06),
        fill: true,
        borderWidth: 2.25,
        // Elapsed/ahead split at today, matching pointColors and the main
        // chart: blue = behind us, ink = still to come. Done tournaments
        // keep the base pen (no split to show).
        segment: {
          borderColor: (c) => isDone(t) ? undefined :
            (c.p1DataIndex <= todayIdx ? PALETTE.actual : PALETTE.projected)
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
        tooltip: chartTooltip({
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
        })
      },
      scales: {
        x: {
          grid: chartGridX(),
          border: chartBorderX(),
          ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 6 : 12 })
        },
        y: {
          min: 0, max: 105,
          grid: chartGridY(),
          border: chartBorderY(),
          ticks: chartTicks({
            maxTicksLimit: _mobileVP() ? 4 : 6,
            callback: v => v + '%'
          })
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
