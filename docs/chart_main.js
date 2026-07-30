// chart_main.js — renderChart (the main registration-trajectory chart),
// split verbatim from app.js (C10). One 750-line function: documented
// exception to the module size ceiling; do not split further.

function renderChart(t) {
  const ctx = document.getElementById('mainChart');
  if (chart) { chart.destroy(); chart = null; }

  if (!t.daily_data || t.daily_data.length === 0 || !t.event_start) {
    // No registration timeline data or missing event date — show placeholder
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = `${t.family} ${t.year}: No registration timeline available`;
    document.getElementById('chartCard').classList.remove('live-glow');
    return;
  }

  const eventStart = t.event_start;
  const datasets = [];

  // v3 P1: draw the sanitised series, not the raw array. Points that exceed the
  // scraped entry total are impossible and used to be plotted as-is — that is
  // how a 625-entry curve was drawn for a 197-entry event.
  const series = (typeof DailySeries !== 'undefined')
    ? DailySeries.sanitizeSeries(t.daily_data, {
        currentCount: t.current_count, isLive: !isDone(t) }).points
    : t.daily_data;
  if (!series.length) {
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = `${t.family} ${t.year}: No registration timeline available`;
    document.getElementById('chartCard').classList.remove('live-glow');
    return;
  }

  const lastDay = series[series.length - 1];
  const totalSpan = lastDay[0] + t.days_remaining;

  // Date each point from its own day index against the exported anchor. The old
  // math (event_start minus (totalSpan - day)) assumed the final point was
  // exactly days_remaining from the event, i.e. that no scrape day was ever
  // missed. When one was, every x-date on the chart shifted.
  // Built with addDays (local midnight) rather than DailySeries.pointDate (UTC
  // midnight): every other series on this axis — projected, CI arms, historical
  // overlays — is local-anchored, and mixing the two conventions would offset
  // the actual line against them by the viewer's UTC offset.
  const dayToDate = (dayFromStart) => (
    t.daily_start_date
      ? addDays(t.daily_start_date, dayFromStart)
      : addDays(eventStart, -(totalSpan - dayFromStart))
  );
  const regOpenDate = dayToDate(0);

  // Actual data
  const actualData = series.map(d => ({ x: dayToDate(d[0]), y: d[1] }));

  // Visible x-window (range control) + right headroom; remember the inputs so
  // setChartRange can recompute without a full re-render.
  const cw = _chartWindow(t, series, dayToDate);
  _chartWindowState = { t, series, dayToDate };

  // Only show point for first, last, and every 7th day to avoid clutter
  const pointRadii = actualData.map((_, i) => {
    if (i === actualData.length-1 && !isDone(t)) return 6; // today - prominent
    if (i === actualData.length-1 && isDone(t)) return 4;  // final point
    if (i === 0) return 3;  // first point
    return 0;  // hide intermediate points
  });

  // Gradient fill under actual data. The old version hardcoded a 380px
  // gradient height (wrong whenever CSS resizes the plot) and allocated a
  // fresh CanvasGradient on every scriptable pass — areaGradient fixes both.
  const _actualGrad = {};

  datasets.push({
    label: 'Actual Entries',
    data: actualData,
    borderColor: PALETTE.blue,
    backgroundColor: (context) => areaGradient(context.chart, _actualGrad, [
      [0, themeRgba(PALETTE.blue, 0.22)],
      [1, themeRgba(PALETTE.blue, 0)]
    ]),
    fill: true,
    borderWidth: 2.5,
    pointRadius: pointRadii,
    pointHoverRadius: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? 8 : 6),
    pointHoverBackgroundColor: PALETTE.blue,
    pointHoverBorderColor: PALETTE.text,
    pointHoverBorderWidth: 2,
    pointBackgroundColor: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? PALETTE.text : PALETTE.blue),
    pointBorderColor: PALETTE.blue,
    pointBorderWidth: actualData.map((_, i) => i === actualData.length-1 && !isDone(t) ? 3 : 0),
    tension: 0.3,
    order: 2
  });

  // Build (year -> historical edition with daily_data) lookup once for the
  // historical-line overlay block below. Only years with multi-point daily
  // series qualify.
  const histLookup = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(other => {
    if (other.family === t.family && other.status === 'historical' &&
        Array.isArray(other.daily_data) && other.daily_data.length > 1) {
      histLookup[other.year] = other;
    }
  });

  // Projection + CI band for live
  if (!isDone(t) && t.registration_curve) {
    const projData = [];
    const todayDB = t.days_remaining;
    const todayPct = interpCurve(t.registration_curve, todayDB);

    // Project to the full point_estimate. The label says "Projected" and
    // the user reads it as "where will this finish" — silently discounting
    // it to a scrape-equivalent value is the wrong contract.
    const scaleFactor = todayPct > 0 ? t.point_estimate / interpCurve(t.registration_curve, 0) : t.point_estimate;

    // Start projection from the last actual data point to avoid a gap
    const lastActual = actualData.length > 0 ? actualData[actualData.length - 1] : null;
    if (lastActual) {
      projData.push({ x: lastActual.x, y: lastActual.y });
    }

    for (let db = todayDB; db >= 0; db--) {
      const pct = interpCurve(t.registration_curve, db);
      const projDate = addDays(eventStart, -db);
      // Skip points at or before the last actual data point
      if (lastActual && projDate <= lastActual.x) continue;
      projData.push({ x: projDate, y: Math.round(scaleFactor * pct) });
    }

    datasets.push({
      label: 'Projected',
      data: projData,
      borderColor: PALETTE.gold,
      borderWidth: 2,
      borderDash: [6, 4],
      pointRadius: 0,
      pointHoverRadius: 6,
      pointHoverBackgroundColor: PALETTE.gold,
      pointHoverBorderColor: PALETTE.text,
      pointHoverBorderWidth: 2,
      tension: 0.3,
      order: 3
    });

    // CI band — full ci_upper/ci_lower from the model, anchored to event day.
    const ciUp = [], ciLo = [];
    const pctAt0 = interpCurve(t.registration_curve, 0);
    const ciUpperScale = pctAt0 > 0 ? t.ci_upper / pctAt0 : t.ci_upper;
    const ciLowerScale = pctAt0 > 0 ? t.ci_lower / pctAt0 : t.ci_lower;
    for (let db = todayDB; db >= 0; db--) {
      const date = addDays(eventStart, -db);
      const pctAtDb = interpCurve(t.registration_curve, db);
      ciUp.push({ x: date, y: Math.round(ciUpperScale * pctAtDb) });
      ciLo.push({ x: date, y: Math.max(0, Math.round(ciLowerScale * pctAtDb)) });
    }
    // Band paint comes from CI Upper's fill('+1') alone; a vertical fade keeps
    // the band readable near the projection line without muddying the bottom.
    const _ciGrad = {};
    datasets.push({
      label: 'CI Upper', data: ciUp,
      borderColor: themeRgba(PALETTE.gold, 0.22), borderWidth: 1,
      backgroundColor: (context) => areaGradient(context.chart, _ciGrad, [
        [0, themeRgba(PALETTE.gold, 0.16)],
        [1, themeRgba(PALETTE.gold, 0.03)]
      ]),
      fill: '+1', pointRadius: 0, tension: 0.3, order: 5
    });
    datasets.push({
      label: 'CI Lower', data: ciLo,
      borderColor: themeRgba(PALETTE.gold, 0.22), borderWidth: 1,
      backgroundColor: themeRgba(PALETTE.gold, 0.12),
      pointRadius: 0, tension: 0.3, order: 5
    });
  }

  // Historical traces — dashed lines, no points, for past year curves of this family
  if (t.historical && t.registration_curve) {
    const histColors = [
      themeRgba(PALETTE.muted, 0.45),  // most recent — brightest
      themeRgba(PALETTE.muted, 0.32),
      themeRgba(PALETTE.muted, 0.22),
      themeRgba(PALETTE.muted, 0.14),
      themeRgba(PALETTE.muted, 0.10),
    ];
    // histLookup is built once at the top of renderChart (above the
    // projection block) so the scrape-ratio computation and the historical
    // line overlays share one source of truth. Cap to most recent N years
    // that HAVE real daily data: 1 on mobile, 5 on desktop.
    const realYears = t.historical.filter(h => histLookup[h.year]);
    const recent = realYears.slice(_mobileVP() ? -1 : -5);
    recent.forEach((h, i) => {
      const real = histLookup[h.year];
      const hData = [];
      // v4 U2 (audit/AUDIT_2026-07-26.md): same contract as the actual line and
      // the compare traces — draw the sanitised series, never the raw array.
      // Historical editions get no currentCount cap (isLive: false), but they
      // still need the duplicate-day and monotonicity cleaning: the server-side
      // historical path only sorts.
      const dd = (typeof DailySeries !== 'undefined')
        ? DailySeries.sanitizeSeries(real.daily_data, { isLive: false }).points
        : real.daily_data;
      if (!dd.length) return;
      const maxDay = dd[dd.length - 1][0];
      // v3 P4: anchor each historical curve to ITS OWN event date, not to the
      // tail of its data. The tail is wherever scraping happened to stop — the
      // code's own comment notes it misses ~10% of entries — so aligning on it
      // slid a year whose scraping ended early against the years around it, and
      // against the live curve it is meant to be compared with. When that year
      // exports a daily_start_date and an event_start, days-before-event is
      // computable exactly; otherwise fall back to the old tail anchor.
      const canAnchor = real.daily_start_date && real.event_start;
      // v4 U1 (audit/AUDIT_2026-07-26.md): pure day arithmetic, no Date
      // round-trip. The old form built a local-midnight Date and reprojected it
      // through toISOString()'s UTC, which lands on the previous calendar day
      // east of Greenwich and shifted every overlay one day left there.
      const spanToEvent = canAnchor
        ? daysBetween(real.daily_start_date, real.event_start)
        : null;
      dd.forEach(p => {
        // Distance of this point from its own year's event, in whole days.
        const T = canAnchor ? spanToEvent - p[0] : maxDay - p[0];
        if (T >= 0 && T <= 120) {
          hData.push({ x: addDays(eventStart, -T), y: p[1] });
        }
      });
      // Don't connect scrape-end to final with a line — the few remaining
      // entries (~10% gap, typically) get logged in the days after event day
      // when we're no longer scraping, so we don't know their exact timing.
      // The final-count marker dot below shows where the year ended.
      hData.sort((a, b) => a.x - b.x);
      const colorIdx = recent.length - 1 - i;
      datasets.push({
        label: `${h.year}`,
        data: hData,
        borderColor: histColors[colorIdx] || histColors[histColors.length - 1],
        borderWidth: 1.25,
        borderDash: [5, 4],
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: histColors[colorIdx] || histColors[histColors.length - 1],
        pointHoverBorderColor: PALETTE.text,
        pointHoverBorderWidth: 1.5,
        tension: 0.3,
        order: 6
      });
      // Final-count marker, plotted as a single point (no line) at event day
      // in the same color as the year line. Shows the small gap between
      // scrape-end and the eventual final after post-event reconciliation.
      const markerColor = histColors[colorIdx] || histColors[histColors.length - 1];
      datasets.push({
        label: `${h.year} final`,
        data: [{ x: addDays(eventStart, 0), y: h.count }],
        showLine: false,
        backgroundColor: markerColor,
        borderColor: markerColor,
        pointStyle: 'circle',
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBorderColor: PALETTE.text,
        pointBorderWidth: 1.5,
        order: 4
      });
    });
  }

  // Vertical lines plugin
  const vertLinePlugin = makeVertMarkersPlugin('vertLines', () => {
    const lines = [];
    const _isM = _mobileVP();
    // On mobile, only the Today line — Early Bird and Event labels overlap on
    // narrow screens (the days-to-event KPI card tells the user already).
    if (!_isM && hasValidEarlyBird(t)) lines.push({ value: new Date(t.early_bird_deadline + 'T00:00:00'), label: 'Early Bird', color: PALETTE.green });
    if (!isDone(t)) lines.push({ value: new Date(TOURNAMENT_DATA.generated + 'T00:00:00'), label: 'Today', color: PALETTE.blue });
    if (!_isM && t.event_start) lines.push({ value: new Date(t.event_start + 'T00:00:00'), label: 'Event', color: PALETTE.red });
    return lines;
  });

  // Crosshair plugin — vertical line that follows mouse x position
  const crosshairPlugin = {
    id: 'crosshair',
    _mouseX: null,
    afterEvent(chartInstance, args) {
      const evt = args.event;
      // Mouse events power desktop crosshair; touch events power mobile.
      // Without the touch branches, tapping the chart on a phone tooltips
      // but never shows the helpful vertical crosshair line.
      if (evt.type === 'mousemove' || evt.type === 'click' ||
          evt.type === 'touchmove' || evt.type === 'touchstart') {
        this._mouseX = evt.x;
      } else if (evt.type === 'mouseout' || evt.type === 'touchend' ||
                 evt.type === 'touchcancel') {
        this._mouseX = null;
      }
    },
    afterDraw(chartInstance) {
      if (this._mouseX == null) return;
      if (!chartInstance.tooltip?._active?.length) return;
      const ctx2 = chartInstance.ctx;
      const x = this._mouseX;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      if (x < xScale.left || x > xScale.right) return;

      ctx2.save();
      ctx2.beginPath();
      ctx2.setLineDash([3, 3]);
      ctx2.strokeStyle = themeRgba(PALETTE.muted, 0.35);
      ctx2.lineWidth = 1;
      ctx2.moveTo(x, yScale.top);
      ctx2.lineTo(x, yScale.bottom);
      ctx2.stroke();
      ctx2.restore();
    }
  };

  // Soft glow under the Actual line (dataset 0). Desktop only: shadowed
  // strokes cost a full extra raster pass per frame, and small screens get
  // no benefit at their line weight. The built-in filler runs before inline
  // plugins, so the area fill underneath stays un-shadowed.
  const lineGlowPlugin = {
    id: 'lineGlow',
    beforeDatasetDraw(chartInstance, args) {
      if (args.index !== 0 || _mobileVP()) return;
      chartInstance.ctx.save();
      chartInstance.ctx.shadowColor = themeRgba(PALETTE.blue, 0.55);
      chartInstance.ctx.shadowBlur = 6;
    },
    afterDatasetDraw(chartInstance, args) {
      if (args.index !== 0 || _mobileVP()) return;
      chartInstance.ctx.restore();
    }
  };

  // Projection endpoint: gold dot + "approx N" label at (event day, predicted
  // final). Desktop + live only; mobile keeps the hero number as the source.
  const endpointLabelPlugin = {
    id: 'endpointLabel',
    afterDraw(c) {
      if (isDone(t) || !t.point_estimate || !t.event_start || _mobileVP()) return;
      const xS = c.scales.x, yS = c.scales.y;
      const px = xS.getPixelForValue(new Date(t.event_start + 'T00:00:00').getTime());
      const py = yS.getPixelForValue(t.point_estimate);
      if (px < xS.left || px > xS.right || py < yS.top || py > yS.bottom) return;
      const g = c.ctx;
      g.save();
      // dot, visual twin of the year-final markers
      g.beginPath();
      g.arc(px, py, 4, 0, Math.PI * 2);
      g.fillStyle = PALETTE.gold;
      g.fill();
      g.lineWidth = 1.5;
      g.strokeStyle = PALETTE.text;
      g.stroke();
      // label with a surface halo; right of the dot, flip left at the edge
      const txt = '\u2248 ' + fmt(t.point_estimate);
      g.font = 'bold 11px ' + getComputedStyle(document.body).fontFamily;
      const tw = g.measureText(txt).width;
      const padX = 5, boxH = 18, gap = 8;
      let bx = px + gap;
      if (bx + tw + padX * 2 > xS.right) bx = px - gap - tw - padX * 2;
      let by = py - boxH / 2;
      // dodge the year-final dot cluster (same x pixel) if one lands in the box
      const finalYs = [];
      c.data.datasets.forEach(ds => {
        if (/ final$/.test(ds.label || '') && ds.data[0]) {
          finalYs.push(yS.getPixelForValue(ds.data[0].y));
        }
      });
      if (finalYs.some(fy => fy > by - 4 && fy < by + boxH + 4)) {
        const below = finalYs.every(fy => fy < py);
        by = below ? by + 12 : by - 12;
      }
      g.fillStyle = themeRgba(PALETTE.surface, 0.85);
      g.beginPath();
      g.roundRect(bx, by, tw + padX * 2, boxH, 4);
      g.fill();
      g.fillStyle = PALETTE.gold;
      g.textAlign = 'left';
      g.textBaseline = 'middle';
      g.fillText(txt, bx + padX, by + boxH / 2 + 0.5);
      g.restore();
    }
  };

  // Custom interaction mode: find nearest point by x-pixel in EACH dataset
  // independently, so datasets with different date ranges align correctly.
  // Only includes a dataset if the hovered x falls within its data range
  // (with a small pixel margin), preventing stale endpoint matches.
  // Chart.js ignores prefers-reduced-motion on its own; disable animation for
  // every chart in the page (reload-only, no matchMedia listener).
  if (!Chart.Interaction.modes.xAligned) {
    Chart.Interaction.modes.xAligned = function(chart2, e, options, useFinalPosition) {
      const items = [];
      const mouseX = e.x;
      chart2.data.datasets.forEach((ds, dsIdx) => {
        const meta = chart2.getDatasetMeta(dsIdx);
        if (!meta.visible || !meta.data.length) return;
        // Projection's index-0 point is a visual duplicate of Actual's last point
        // (glued together so the lines connect). Skip it for hit-testing so the
        // tooltip title doesn't get hijacked by Projected when the user is
        // actually hovering the Actual line near today/yesterday.
        const skipFirst = ds.label === 'Projected' && meta.data.length > 1;
        const firstHitIdx = skipFirst ? 1 : 0;
        if (firstHitIdx >= meta.data.length) return;
        const firstPx = meta.data[firstHitIdx].x;
        const lastPx = meta.data[meta.data.length - 1].x;
        // Registered once globally, so viewport class is checked per call.
        // Coarse pointers get a wider capture band: 15px is a comfortable
        // mouse margin but under a fingertip it makes edge points untappable.
        const _isM = _mobileVP();
        const margin = _isM ? 28 : 15;
        if (mouseX < firstPx - margin || mouseX > lastPx + margin) return;
        let bestIdx = -1, bestDist = Infinity;
        for (let idx = firstHitIdx; idx < meta.data.length; idx++) {
          const dist = Math.abs(meta.data[idx].x - mouseX);
          if (dist < bestDist) { bestDist = dist; bestIdx = idx; }
        }
        if (bestIdx >= 0 && bestDist < (_isM ? 60 : 50)) {
          items.push({ datasetIndex: dsIdx, index: bestIdx, element: meta.data[bestIdx] });
        }
      });
      return items;
    };
  }

  // Custom tooltip positioner: pin to the chart corner OPPOSITE the cursor's
  // x-position so the tooltip never occludes the line you're inspecting.
  // Stakeholder feedback: default 'average' position floated on top of the
  // data, blocking the chart while reading values.
  if (!Chart.Tooltip.positioners.cornerAway) {
    Chart.Tooltip.positioners.cornerAway = function(elements, eventPos) {
      const chartArea = this.chart.chartArea;
      if (!chartArea) return false;
      const midX = (chartArea.left + chartArea.right) / 2;
      const onRight = eventPos.x > midX;
      // Anchor to top-left when cursor is on the right half, and vice versa.
      // y stays high so the tooltip lives in the chart's top band.
      return {
        x: onRight ? chartArea.left + 8 : chartArea.right - 8,
        y: chartArea.top + 8,
      };
    };
  }

  // Progressive left-to-right draw-in on first render. Per-chart animation
  // config OVERRIDES the global Chart.defaults.animation kill, so reduced
  // motion must be handled explicitly here. The xStarted/yStarted flags live
  // on each element's $context and stop the stagger from replaying on later
  // updates; range clicks additionally use update('none').
  const _drawN = actualData.length || 1;
  const _drawPer = Math.min(700 / _drawN, 12);
  const drawInAnimation = _reduceMotion() ? false : {
    x: {
      type: 'number', easing: 'linear', duration: _drawPer, from: NaN,
      delay(c) {
        if (c.type !== 'data' || c.xStarted) return 0;
        c.xStarted = true;
        return c.index * _drawPer;
      }
    },
    y: {
      type: 'number', easing: 'linear', duration: _drawPer,
      from(c) {
        if (c.index === 0) return c.chart.scales.y.getPixelForValue(0);
        const prev = c.chart.getDatasetMeta(c.datasetIndex).data[c.index - 1];
        return prev ? prev.getProps(['y'], true).y : undefined;
      },
      delay(c) {
        if (c.type !== 'data' || c.yStarted) return 0;
        c.yStarted = true;
        return c.index * _drawPer;
      }
    }
  };

  // Hover emphasis for historical year traces. xAligned returns the nearest
  // point of EVERY dataset regardless of pointer y, so proximity to the trace
  // is checked here; without it the first year line would light up wherever
  // the cursor sat. Restore-then-set with a change guard keeps this at one
  // update('none') per trace change instead of one per mousemove.
  let _emphIdx = -1;
  function _emphasizeYearTrace(evt, elements, chart2) {
    if (_mobileVP()) return;
    let best = -1, bestDy = 14;
    for (const el of elements) {
      const lbl = chart2.data.datasets[el.datasetIndex]?.label || '';
      if (!/^\d{4}$/.test(lbl)) continue;
      const dy = Math.abs(el.element.y - evt.y);
      if (dy < bestDy) { bestDy = dy; best = el.datasetIndex; }
    }
    if (best === _emphIdx) return;
    if (_emphIdx >= 0) {
      const prev = chart2.data.datasets[_emphIdx];
      if (prev && prev._origBorder) {
        prev.borderColor = prev._origBorder.color;
        prev.borderWidth = prev._origBorder.width;
      }
    }
    if (best >= 0) {
      const ds = chart2.data.datasets[best];
      if (!ds._origBorder) ds._origBorder = { color: ds.borderColor, width: ds.borderWidth };
      ds.borderColor = themeRgba(PALETTE.muted, 0.8);
      ds.borderWidth = 2;
    }
    _emphIdx = best;
    chart2.update('none');
  }

  chart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    plugins: [vertLinePlugin, crosshairPlugin, endpointLabelPlugin, lineGlowPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: drawInAnimation,
      interaction: { mode: 'xAligned', intersect: false },
      hover: { mode: 'xAligned', intersect: false },
      onHover: _emphasizeYearTrace,
      plugins: {
        legend: { display: false },
        tooltip: {
          position: 'cornerAway',
          xAlign: undefined, yAlign: 'top',
          caretSize: 0,
          backgroundColor: themeRgba(PALETTE.surface, 0.95), borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
          titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
          padding: _mobileVP() ? 9 : 12, cornerRadius: 8,
          // Mobile tooltip: tighter padding, smaller text, smaller point swatches,
          // capped width so a long historical comparison list can't overflow the
          // chart area or the viewport. Desktop unchanged.
          boxPadding: 4,
          boxWidth: _mobileVP() ? 6 : 10,
          displayColors: true,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
          bodyFont: { size: 12 },
          footerFont: { size: 11, style: 'italic' },
          titleMarginBottom: 8, bodySpacing: _mobileVP() ? 4 : 5,
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              // Pick date from the most relevant dataset present in the tooltip.
              // Prefer Projected (in future) or Actual (in past) over historical years.
              const primary = items.find(i => i.dataset.label === 'Projected')
                           || items.find(i => i.dataset.label === 'Actual Entries')
                           || items[0];
              const d = primary.raw.x;
              const dateStr = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
              // Calculate days before event
              if (t.event_start) {
                const evDate = new Date(t.event_start + 'T00:00:00');
                const diff = Math.round((evDate - d) / 86400000);
                if (diff > 0) return `${dateStr}  ·  T-${diff}`;
                if (diff === 0) return `${dateStr}  ·  Event Day`;
                return `${dateStr}  ·  T+${Math.abs(diff)}`;
              }
              return dateStr;
            },
            label(item) {
              if (item.dataset.label === 'CI Upper' || item.dataset.label === 'CI Lower') return null;
              const val = fmt(item.raw.y);
              const hoveredDate = item.raw.x;
              const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
              const isHistorical = isDone(t);
              const isPastOrToday = hoveredDate <= today;

              // Per-year "final" marker is consolidated into the year line below;
              // suppress its own row so the tooltip doesn't double up.
              if (/^\d{4} final$/.test(item.dataset.label)) return null;

              if (item.dataset.label === 'Actual Entries') {
                // Only show actual line when hovering over real data (past/today),
                // not when hovering over future projected points
                if (!isHistorical && !isPastOrToday) return null;
                if (item.dataIndex > 0) {
                  const prevPt = item.dataset.data[item.dataIndex - 1];
                  const delta = item.raw.y - prevPt.y;
                  // v3 P7: label the real span. Adjacent chart points are not
                  // always one day apart — the current data holds 29 gaps wider
                  // than a day — and calling a multi-day total "/day" overstates
                  // the rate by exactly the size of the gap.
                  const spanDays = Math.max(1, Math.round(
                    (item.raw.x - prevPt.x) / 86400000));
                  const unit = spanDays === 1 ? '/day' : ` over ${spanDays} days`;
                  if (delta > 0) return ` Actual: ${val}  (+${fmt(delta)}${unit})`;
                  if (delta === 0) return ` Actual: ${val}  (no change)`;
                  return ` Actual: ${val}  (${fmt(delta)}${unit})`;
                }
                return ` Actual: ${val}`;
              }

              if (item.dataset.label === 'Projected') {
                // Only show projection when hovering over future dates
                if (isPastOrToday) return null;
                return ` Projected: ${val}`;
              }

              // Historical year row — pair the at-this-T value with the final
              // count if the matching "YYYY final" dataset exists. Reads off
              // chart.data.datasets so we don't depend on hover proximity to
              // the final-day marker dot.
              const yearMatch = item.dataset.label.match(/^(\d{4})( \(est\))?$/);
              if (yearMatch) {
                const finalDs = item.chart.data.datasets.find(
                  d => d.label === `${yearMatch[1]} final`);
                if (finalDs && finalDs.data.length > 0) {
                  return ` ${item.dataset.label}: ${val} → ${fmt(finalDs.data[0].y)}`;
                }
                return ` ${item.dataset.label}: ${val}`;
              }

              // Anything else
              return ` ${item.dataset.label}: ${val}`;
            },
            afterBody(items) {
              const lines = [];
              if (!items.length) return lines;
              const hoveredDate = items[0].raw.x;
              const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
              // Show CI when hovering future (projection) area
              if (hoveredDate > today) {
                const ciUp = items.find(i => i.dataset.label === 'CI Upper');
                const ciLo = items.find(i => i.dataset.label === 'CI Lower');
                if (ciUp && ciLo) {
                  lines.push('');
                  lines.push(`  Likely range: ${fmt(ciLo.raw.y)} – ${fmt(ciUp.raw.y)}`);
                }
              }
              // Pace vs. historical average AT THE SAME T (not vs final).
              // Comparing today's 32 to final-avg 203 read "-84%" even when
              // current is genuinely ahead of every historical year at this T.
              // Use the items already in the tooltip — each historical year
              // dataset reports its y at the hovered date.
              const yearItems = items.filter(i => /^\d{4}( \(est\))?$/.test(i.dataset.label));
              if (yearItems.length > 0) {
                const hAvgAtT = Math.round(yearItems.reduce((s, i) => s + i.raw.y, 0) / yearItems.length);
                const actual = items.find(i => i.dataset.label === 'Actual Entries');
                const projected = items.find(i => i.dataset.label === 'Projected');
                const ref = actual || projected;
                if (ref && ref.raw.y > 0 && hAvgAtT > 0) {
                  const pct = ((ref.raw.y - hAvgAtT) / hAvgAtT * 100).toFixed(1);
                  const sign = pct > 0 ? '+' : '';
                  lines.push(`  vs ${yearItems.length}-yr avg @ this T (${fmt(hAvgAtT)}): ${sign}${pct}%`);
                }
              }
              return lines;
            },
            footer(items) {
              if (!items.length) return '';
              if (t.point_estimate && !isDone(t)) {
                return `Predicted final: ${fmt(t.point_estimate)}`;
              }
              return '';
            }
          },
          filter(item) { return item.dataset.label !== 'CI Upper' && item.dataset.label !== 'CI Lower'; }
        }
      },
      onClick(evt, elements) {
        // Click a chart point to scroll to the tournament row in the data table
        if (!elements.length) return;
        const rows = document.querySelectorAll('.tourney-table tbody tr');
        const idx = TOURNAMENT_DATA.tournaments.indexOf(t);
        if (idx < 0) return;
        for (const row of rows) {
          row.classList.remove('chart-highlight');
          if (row.dataset.idx === String(idx)) {
            row.classList.add('chart-highlight');
            const wrap = row.closest('details.sect');
            if (wrap && !wrap.open) wrap.open = true;
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => row.classList.remove('chart-highlight'), 2500);
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          // Mobile: month-level labels (Mar/Apr/May) so the time axis isn't crowded.
          // Chart.js's time scale ignores maxTicksLimit on weekly units; switching
          // to monthly is the documented way to sparsen X labels.
          time: _chartTimeUnit(cw, t),
          min: cw.min,
          // Extend the axis 5 days past event day so the finals-marker dot for
          // each historical year has visible space and is clearly separate
          // from the chart's data region (the day-of / post-event surge).
          max: cw.max,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxRotation: 0 }
        },
        y: {
          beginAtZero: true,
          grid: { color: themeRgba(PALETTE.border, 0.4), drawBorder: false },
          ticks: { color: PALETTE.muted, font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8, callback: v => v >= 1000 ? (v/1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k' : v }
        }
      },
      // Desktop top padding fits two rows of annotation pills so when
      // Early Bird and Event lines overlap horizontally they can stack
      // vertically. Mobile only renders the "Today" pill (Early Bird +
      // Event are gated by !_isM in vertLinePlugin), so 14px is plenty —
      // any more steals plot area on phones.
      layout: { padding: { top: _mobileVP() ? 14 : 40 } }
    }
  });

  // Chart glow for live tournaments
  document.getElementById('chartCard').classList.toggle('live-glow', t.status === 'live');

  // Legend
  let legendHtml = '<div class="legend-item"><div class="legend-swatch" style="background:#58a6ff"></div>Actual</div>';
  if (!isDone(t)) {
    legendHtml += '<div class="legend-item"><div class="legend-swatch dashed"></div>Projected</div>';
    legendHtml += '<div class="legend-item"><div class="legend-swatch band" style="background:#f0c040"></div>Likely range</div>';
  }
  if (t.historical) {
    legendHtml += `<div class="legend-item"><div class="legend-swatch dashed" style="background:repeating-linear-gradient(90deg,${themeRgba(PALETTE.muted,0.5)} 0 4px,transparent 4px 8px)"></div>Historical</div>`;
  }
  document.getElementById('chartLegend').innerHTML = legendHtml;

  // Subtitle
  let sub = `${t.family} ${t.year} · Registration Trajectory`;
  if (!isDone(t) && hasValidEarlyBird(t)) {
    const ebD = new Date(t.early_bird_deadline + 'T00:00:00');
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    if (ebD < today) {
      sub += ` · Early bird ended ${fmtDate(t.early_bird_deadline)}`;
    } else {
      sub += ` · Early bird in ${Math.ceil((ebD - today) / 86400000)}d`;
    }
  }
  const subEl = document.getElementById('chartSubtitle');
  subEl.textContent = sub;
  // Mobile truncates the subtitle with ellipsis (long family names eat
  // plot area). Mirror full text in the title attribute so long-press
  // / hover reveals it.
  subEl.setAttribute('title', sub);

  // Mobile date strip: shows the EB + Event dates inline below the chart since
  // the pill annotations for those are hidden on phones. Desktop CSS hides
  // this element so it does not duplicate the pills.
  _syncChartRangeSeg(cw);

  const datesEl = document.getElementById('chartMobileDates');
  if (datesEl) {
    const parts = [];
    if (hasValidEarlyBird(t)) parts.push(`<span class="cmd-eb">EB · ${fmtDate(t.early_bird_deadline)}</span>`);
    if (t.event_start) parts.push(`<span class="cmd-event">Event · ${fmtDate(t.event_start)}</span>`);
    datesEl.innerHTML = parts.join(' &middot; ');
  }
}

// (What-If panel removed)
