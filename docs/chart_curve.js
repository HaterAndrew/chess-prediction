// chart_curve.js — the registration-curve chart and its caption in the
// Registration Curve and Fees section (split from chart_hist.js).

// ══════════════════════════════════════════════════════════
// REGISTRATION CURVE CHART
// ══════════════════════════════════════════════════════════
// The curve is the typical share of final entries by days before the event,
// drawn on a true time scale: the checkpoints are 120, 90, 75 … 1 days out,
// and spacing them evenly bent the shape. Straight segments join the
// measured points (no smoothing between them), grey because it is context.
// While the event is live, two points mark today: where a typical year
// stands and where this event stands against its forecast.
let regCurveObj = null;

const CURVE_TICKS = { wide: [120, 90, 60, 30, 14, 0], phone: [120, 60, 30, 0] };

function _curveTodayPoints(t) {
  if (isDone(t) || !t.point_estimate) return null;
  const typical = interpCurve(t.registration_curve, t.days_remaining) * 100;
  const now = t.current_count / t.point_estimate * 100;
  return { db: t.days_remaining, typical, now, gap: paceGap(typical, now) };
}

// The two dots at today, a hairline between them, and their labels on the
// side with more room; labels closer than a line apart part vertically.
function _curveTodayPlugin(pts) {
  return {
    id: 'curveToday',
    afterDatasetsDraw(c) {
      if (!pts) return;
      const g = c.ctx, xS = c.scales.x, yS = c.scales.y;
      const x = xS.getPixelForValue(pts.db);
      if (x < xS.left || x > xS.right) return;
      const yT = yS.getPixelForValue(Math.min(pts.typical, 100));
      const yN = yS.getPixelForValue(Math.min(pts.now, 100));
      const labels = [
        { y: yT, text: `Typical year ${Math.round(pts.typical)}%`, color: PALETTE.hist },
        { y: yN, text: `This event ${Math.round(pts.now)}%`, color: PALETTE.actual },
      ];
      const [hi, lo] = yT <= yN ? labels : [labels[1], labels[0]];
      const need = 17;
      if (lo.y - hi.y < need) {
        const mid = (hi.y + lo.y) / 2;
        hi.y = mid - need / 2;
        lo.y = mid + need / 2;
      }
      const right = x - xS.left < xS.right - x;
      g.save();
      g.strokeStyle = PALETTE.muted;
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(x, yT); g.lineTo(x, yN); g.stroke();
      [[yT, PALETTE.hist], [yN, PALETTE.actual]].forEach(([y, col]) => {
        g.beginPath(); g.arc(x, y, 4.5, 0, Math.PI * 2);
        g.fillStyle = col; g.fill();
        g.lineWidth = 1.5; g.strokeStyle = PALETTE.surface; g.stroke();
      });
      g.font = chartLabelFont(12, 'bold');
      labels.forEach(l => {
        g.fillStyle = l.color;
        chartHaloText(g, l.text, right ? x + 10 : x - 10, l.y, right ? 'left' : 'right');
      });
      g.restore();
    }
  };
}

function renderRegCurve(t) {
  const ctx = document.getElementById('regCurveChart');
  const caption = document.getElementById('regCurveCaption');
  if (regCurveObj) { regCurveObj.destroy(); regCurveObj = null; }
  if (!t.registration_curve || t.registration_curve.length === 0) {
    caption.textContent = 'No curve data available';
    chartDescribe(ctx, { label: 'Registration curve: no curve data available.' });
    return;
  }
  if (typeof Chart === 'undefined') {
    caption.textContent = 'Chart unavailable (the charting library did not load)';
    chartDescribe(ctx, { label: 'Registration curve unavailable.' });
    return;
  }

  const pts = [...t.registration_curve]
    .map(pt => ({ x: pt.days_before, y: (pt.cumulative_pct || pt.pct || 0) * 100 }))
    .sort((a, b) => b.x - a.x);
  const maxDB = pts[0].x;
  const today = _curveTodayPoints(t);
  const ticks = (_mobileVP() ? CURVE_TICKS.phone : CURVE_TICKS.wide).filter(v => v <= maxDB);
  const todayMarker = makeVertMarkersPlugin('regCurveAnnotation', () =>
    today && today.db <= maxDB ? [{ value: today.db, label: 'Today', color: PALETTE.markerToday }] : []);

  regCurveObj = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        data: pts,
        borderColor: PALETTE.hist,
        borderWidth: 2,
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHitRadius: 10,
        pointHoverBackgroundColor: PALETTE.hist,
        pointHoverBorderColor: PALETTE.surface,
        tension: 0
      }]
    },
    plugins: [todayMarker, _curveTodayPlugin(today)],
    options: {
      responsive: true, maintainAspectRatio: false,
      // Headroom for the shared marker pill (drawn 18px above the plot top).
      layout: { padding: { top: 22, right: 8 } },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: chartTooltip({
          displayColors: false,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = items[0].raw.x;
              return db === 0 ? 'Event Day' : `T-${db} (${db} days before event)`;
            },
            label(item) {
              return ` Typical year: ${item.raw.y.toFixed(1)}% of final entries`;
            },
            afterBody(items) {
              if (!items.length || !t.point_estimate) return [];
              return [`  Est. entries at this share: ~${fmt(Math.round(t.point_estimate * items[0].raw.y / 100))}`];
            }
          }
        })
      },
      scales: {
        x: {
          type: 'linear', reverse: true, min: 0, max: maxDB,
          grid: chartGridX(),
          border: chartBorderX(),
          afterBuildTicks(axis) { axis.ticks = ticks.map(v => ({ value: v })); },
          ticks: chartTicks({ autoSkip: false, callback: v => v === 0 ? 'Event' : `${v}d` })
        },
        y: {
          min: 0, max: 100,
          grid: chartGridY(),
          border: chartBorderY(),
          ticks: chartTicks({ stepSize: 25, callback: v => v + '%' })
        }
      }
    }
  });

  const text = today
    ? `At T-${today.db}, a typical year has ${Math.round(today.typical)}% of its final entries; this event has ${Math.round(today.now)}% of its forecast, ${today.gap.text}.`
    : `How ${t.family} registrations typically build, as a share of final entries.`;
  caption.textContent = text;
  const at = db => `${Math.round(interpCurve(t.registration_curve, db) * 100)}%`;
  chartDescribe(ctx, {
    label: today ? text : `${t.family} typical registration curve: ${at(30)} of final entries by 30 days out, ${at(7)} by 7 days out.`,
    caption: `${t.family}: typical share of final entries by days before the event`,
    columns: ['Days Before Event', 'Typical Share of Final Entries'],
    rows: pts.map(p => [p.x === 0 ? 'Event day' : `${p.x}`, `${p.y.toFixed(1)}%`]),
  });
}
