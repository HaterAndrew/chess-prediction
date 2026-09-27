// chart_main.js — renderChart (the main registration-trajectory chart),
// split verbatim from app.js (C10). One 750-line function: documented
// exception to the module size ceiling; do not split further.

// The draw-in plays on the first chart only; a tournament switch, a theme
// change or a resize lands on the finished line.
let _mainChartDrawn = false;

function renderChart(t) {
  const ctx = document.getElementById('mainChart');
  if (chart) { chart.destroy(); chart = null; }

  if (typeof Chart === 'undefined') {
    // The CDN script failed (blocked, offline, SRI mismatch). Say so in the
    // card instead of throwing; the rest of the page still renders.
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent =
      'Chart unavailable: the charting library did not load.';
    chartDescribe(ctx, { label: 'Cumulative entries chart unavailable.' });
    return;
  }

  if (!t.daily_data || t.daily_data.length === 0 || !t.event_start) {
    // No registration timeline data or missing event date — show placeholder
    document.getElementById('chartLegend').innerHTML = '';
    document.getElementById('chartSubtitle').textContent = 'No registration timeline yet.';
    chartDescribe(ctx, { label: 'Cumulative entries chart: no registration timeline yet.' });
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
    document.getElementById('chartSubtitle').textContent = 'No registration timeline yet.';
    chartDescribe(ctx, { label: 'Cumulative entries chart: no registration timeline yet.' });
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

  // Every point carries its date as a timestamp: the chart is built with
  // parsing off, so Chart.js takes the points as they are instead of
  // running each of the thousand or so through the date adapter on every
  // update (and normalized: each dataset is sorted by x with no repeats).
  const actualData = series.map(d => ({ x: dayToDate(d[0]).getTime(), y: d[1] }));

  // Visible x-window (range control) + right headroom; remember the inputs so
  // setChartRange can recompute without a full re-render.
  const cw = _chartWindow(t, series, dayToDate);
  _chartWindowState = { t, series, dayToDate };

  // The actual series is the blue pen with one flat tint under it, the way
  // a line is coloured in on the sheet: no gradient, no glow. Its point
  // options are scalars on purpose: a per-point array makes Chart.js resolve
  // every point's options through its proxy chain on each update, and that
  // was a third of the chart's build. The two points that show, the first
  // and the last, are the small dataset that follows.
  datasets.push({
    label: 'Actual Entries',
    data: actualData,
    borderColor: PALETTE.actual,
    backgroundColor: themeRgba(PALETTE.actual, 0.08),
    fill: true,
    borderWidth: 2.5,
    pointRadius: 0,
    pointHoverRadius: 6,
    pointHoverBackgroundColor: PALETTE.actual,
    pointHoverBorderColor: PALETTE.text,
    pointHoverBorderWidth: 2,
    // Monotone: a cumulative count never dips between two points, which a
    // plain tension curve can draw.
    cubicInterpolationMode: 'monotone',
    order: 2
  });
  // The first point, and today's (prominent: ink on the pen) or the final one.
  if (actualData.length) {
    const live = !isDone(t);
    const pts = actualData.length > 1 ? [actualData[0], actualData[actualData.length - 1]] : [actualData[0]];
    const last = i => i === pts.length - 1;
    datasets.push({
      label: 'Actual Points',
      data: pts,
      showLine: false,
      pointRadius: pts.map((_, i) => last(i) ? (live ? 6 : 4) : 3),
      pointHoverRadius: pts.map((_, i) => last(i) && live ? 8 : 6),
      pointBackgroundColor: pts.map((_, i) => last(i) && live ? PALETTE.text : PALETTE.actual),
      pointBorderColor: PALETTE.actual,
      pointBorderWidth: pts.map((_, i) => last(i) && live ? 3 : 0),
      pointHoverBackgroundColor: PALETTE.actual,
      pointHoverBorderColor: PALETTE.text,
      pointHoverBorderWidth: 2,
      order: 1
    });
  }

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
      projData.push({ x: projDate.getTime(), y: Math.round(scaleFactor * pct) });
    }

    datasets.push({
      label: 'Projected',
      data: projData,
      borderColor: PALETTE.projected,
      borderWidth: 2,
      borderDash: [6, 4],
      pointRadius: 0,
      pointHoverRadius: 6,
      pointHoverBackgroundColor: PALETTE.projected,
      pointHoverBorderColor: PALETTE.text,
      pointHoverBorderWidth: 2,
      cubicInterpolationMode: 'monotone',
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
      ciUp.push({ x: date.getTime(), y: Math.round(ciUpperScale * pctAtDb) });
      ciLo.push({ x: date.getTime(), y: Math.max(0, Math.round(ciLowerScale * pctAtDb)) });
    }
    // Band paint comes from CI Upper's fill('+1') alone: the likely range is
    // one flat tint of the blue pen with a hairline edge, the bracket drawn
    // round the forecast figure.
    datasets.push({
      label: 'CI Upper', data: ciUp,
      borderColor: themeRgba(PALETTE.actual, 0.3), borderWidth: 1,
      backgroundColor: PALETTE.band,
      fill: '+1', pointRadius: 0, cubicInterpolationMode: 'monotone', order: 5
    });
    datasets.push({
      label: 'CI Lower', data: ciLo,
      borderColor: themeRgba(PALETTE.actual, 0.3), borderWidth: 1,
      backgroundColor: PALETTE.band,
      pointRadius: 0, cubicInterpolationMode: 'monotone', order: 5
    });
  }

  // Past years: thin solid grey lines (a dash means the projection and
  // nothing else). Last year is the one labelled comparison, in the full grey
  // (4.5:1 on the sheet); older years share a lighter grey as context.
  let lastYear = null;
  let pastDrawn = 0;
  if (t.historical && t.registration_curve) {
    const pastColor = i => i === 0 ? PALETTE.hist : themeRgba(PALETTE.hist, 0.4);
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
          hData.push({ x: addDays(eventStart, -T).getTime(), y: p[1] });
        }
      });
      // Don't connect scrape-end to final with a line — the few remaining
      // entries (~10% gap, typically) get logged in the days after event day
      // when we're no longer scraping, so we don't know their exact timing.
      // The final-count marker dot below shows where the year ended.
      hData.sort((a, b) => a.x - b.x);
      const colorIdx = recent.length - 1 - i;
      const isLast = colorIdx === 0;
      if (isLast) lastYear = { year: h.year, count: h.count, data: hData };
      pastDrawn++;
      datasets.push({
        label: `${h.year}`,
        data: hData,
        borderColor: pastColor(colorIdx),
        borderWidth: isLast ? 1.5 : 1,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: pastColor(colorIdx),
        pointHoverBorderColor: PALETTE.text,
        pointHoverBorderWidth: 1.5,
        cubicInterpolationMode: 'monotone',
        order: 6
      });
      // Final-count marker, plotted as a single point (no line) at event day
      // in the same color as the year line. Shows the small gap between
      // scrape-end and the eventual final after post-event reconciliation.
      const markerColor = pastColor(colorIdx);
      datasets.push({
        label: `${h.year} final`,
        data: [{ x: addDays(eventStart, 0).getTime(), y: h.count }],
        showLine: false,
        backgroundColor: markerColor,
        borderColor: markerColor,
        pointStyle: 'circle',
        pointRadius: isLast ? 4 : 3,
        pointHoverRadius: 6,
        pointBorderColor: isLast ? PALETTE.surface : markerColor,
        pointBorderWidth: isLast ? 1.5 : 0,
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
    if (!_isM && hasValidEarlyBird(t)) lines.push({ value: new Date(t.early_bird_deadline + 'T00:00:00'), label: 'Early Bird', color: PALETTE.markerEarly });
    if (!isDone(t)) lines.push({ value: new Date(TOURNAMENT_DATA.generated + 'T00:00:00'), label: 'Today', color: PALETTE.markerToday });
    if (!_isM && t.event_start) lines.push({ value: new Date(t.event_start + 'T00:00:00'), label: 'Event', color: PALETTE.markerEvent });
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

  // The figures where the lines end, on every width: the forecast ("~258",
  // ink) beside its dot at event day, and last year's final ("2025 · 305",
  // in the past-year grey) beside its dot. Each sits right of its dot when
  // there is room, else left; two labels on one side that would overlap part
  // vertically around their midpoint.
  const endLabelsPlugin = {
    id: 'endLabels',
    afterDraw(c) {
      if (!t.event_start) return;
      const xS = c.scales.x, yS = c.scales.y;
      const px = xS.getPixelForValue(new Date(t.event_start + 'T00:00:00').getTime());
      if (px < xS.left || px > xS.right) return;
      const g = c.ctx;
      const boxH = 18, padX = 5, gap = 8;
      const labels = [];
      if (!isDone(t) && t.point_estimate) {
        labels.push({ y: yS.getPixelForValue(t.point_estimate), text: '~' + fmt(t.point_estimate),
                      color: PALETTE.text, font: chartLabelFont(12, 'bold'), dot: true });
      } else if (isDone(t) && actualData.length) {
        // A finished event's own final, in its pen, beside the line's end.
        const fin = actualData[actualData.length - 1].y;
        labels.push({ y: yS.getPixelForValue(fin), text: fmt(fin), color: PALETTE.actual, font: chartLabelFont(12, 'bold') });
      }
      if (lastYear) {
        labels.push({ y: yS.getPixelForValue(lastYear.count), text: `${lastYear.year} · ${fmt(lastYear.count)}`,
                      color: PALETTE.hist, font: chartLabelFont(12) });
      }
      g.save();
      labels.forEach(l => {
        g.font = l.font;
        l.w = _labelWidth(g, l.text) + padX * 2;
        l.right = px + gap + l.w <= c.width - 2;
        l.by = l.y - boxH / 2;
      });
      if (labels.length === 2 && labels[0].right === labels[1].right) {
        const [hi, lo] = labels[0].y <= labels[1].y ? labels : [labels[1], labels[0]];
        const need = boxH + 2;
        if (lo.by - hi.by < need) {
          const mid = (hi.by + lo.by) / 2;
          hi.by = mid - need / 2;
          lo.by = mid + need / 2;
        }
      }
      labels.forEach(l => {
        if (l.y < yS.top || l.y > yS.bottom) return;
        if (l.dot) {
          // the forecast's dot, the visual twin of the year-final markers
          g.beginPath();
          g.arc(px, l.y, 4, 0, Math.PI * 2);
          g.fillStyle = PALETTE.projected;
          g.fill();
          g.lineWidth = 1.5;
          g.strokeStyle = PALETTE.surface;
          g.stroke();
        }
        const bx = l.right ? px + gap : px - gap - l.w;
        const by = Math.max(yS.top - boxH / 2, Math.min(l.by, yS.bottom - boxH));
        g.fillStyle = themeRgba(PALETTE.surface, 0.85);
        g.fillRect(bx, by, l.w, boxH);
        g.font = l.font;
        g.fillStyle = l.color;
        g.textAlign = 'left';
        g.textBaseline = 'middle';
        g.fillText(l.text, bx + padX, by + boxH / 2 + 0.5);  // halo: the box filled above
      });
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

  // Progressive left-to-right draw-in on the first chart of the visit. Per-chart
  // animation config OVERRIDES the global Chart.defaults.animation kill, so
  // reduced motion must be handled explicitly here. The xStarted/yStarted flags live
  // on each element's $context and stop the stagger from replaying on later
  // updates; range clicks additionally use update('none').
  const _drawN = actualData.length || 1;
  const _drawPer = Math.min(700 / _drawN, 12);
  const drawInAnimation = (_reduceMotion() || _mainChartDrawn) ? false : {
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
  _mainChartDrawn = true;

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
    plugins: [vertLinePlugin, crosshairPlugin, endLabelsPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      parsing: false, normalized: true,
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
          padding: _mobileVP() ? 9 : 12, cornerRadius: 0,
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
              const dateStr = DATE_FMT.full.format(d);
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
              // The endpoint dots duplicate the actual line's first and last rows.
              if (item.dataset.label === 'Actual Points') return null;
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
                  lines.push(`  ${Math.round((t.ci_level || .8) * 100)}% range: ${fmt(ciLo.raw.y)} – ${fmt(ciUp.raw.y)}`);
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
          grid: chartGridX(),
          border: chartBorderX(),
          ticks: chartTicks()
        },
        y: {
          beginAtZero: true,
          grid: chartGridY(),
          border: chartBorderY(),
          ticks: chartTicks({ maxTicksLimit: _mobileVP() ? 5 : 8, callback: v => v >= 1000 ? (v/1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k' : v })
        }
      },
      // Desktop top padding fits two rows of annotation pills so when
      // Early Bird and Event lines overlap horizontally they can stack
      // vertically. Mobile only renders the "Today" pill (Early Bird +
      // Event are gated by !_isM in vertLinePlugin), so one 16px pill row
      // fits in 20px; any more steals plot area on phones.
      layout: { padding: { top: _mobileVP() ? 20 : 40 } }
    }
  });

  // The key: the actual line, the projection and its range while live, the
  // past years when any are drawn. Swatches are classes (forecast.css), so
  // they follow the theme.
  const ciPct = Math.round((t.ci_level || .8) * 100);
  let legendHtml = '<div class="legend-item"><div class="legend-swatch"></div>Actual</div>';
  if (!isDone(t)) {
    legendHtml += '<div class="legend-item"><div class="legend-swatch dashed"></div>Projected</div>';
    legendHtml += `<div class="legend-item"><div class="legend-swatch band"></div>${ciPct}% Range</div>`;
  }
  if (pastDrawn) legendHtml += '<div class="legend-item"><div class="legend-swatch past"></div>Past Years</div>';
  document.getElementById('chartLegend').innerHTML = legendHtml;
  _describeMainChart(t, ctx, { actualData, datasets, lastYear, ciPct });

  // Subtitle: the early-bird state, the one thing the chart title and the
  // page title do not already say. A non-breaking space holds the line when
  // there is none, so the card does not shift between tournaments.
  let sub = '';
  if (!isDone(t) && hasValidEarlyBird(t)) {
    const ebD = new Date(t.early_bird_deadline + 'T00:00:00');
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    sub = ebD < today
      ? `Early bird ended ${fmtDate(t.early_bird_deadline)}`
      : `Early bird ends in ${Math.ceil((ebD - today) / 86400000)}d`;
  }
  sub = sub || '\u00a0';
  const subEl = document.getElementById('chartSubtitle');
  subEl.textContent = sub;
  // Mobile truncates the subtitle with ellipsis (long family names eat
  // plot area). Mirror full text in the title attribute so long-press
  // / hover reveals it.
  subEl.setAttribute('title', sub);

  // The early bird and event dates the pills leave out on a phone are on the
  // milestone strip under the chart (panels_info.js renderMilestones).
  _syncChartRangeSeg(cw);
}

// The main chart's text alternative: a label with the figures a sighted
// reader takes from it, and a weekly table (chartDescribe, chart_kit.js).
function _describeMainChart(t, canvas, d) {
  const name = `${t.family} ${t.year}`;
  const eventDate = new Date(t.event_start + 'T00:00:00');
  const last = d.lastYear ? `; last year finished at ${fmt(d.lastYear.count)}` : '';
  const label = isDone(t)
    ? `${name}: ${fmt(t.current_count)} final entries, event ${fmtDate(t.event_start)}${last}.`
    : `${name}: ${fmt(t.current_count)} registered on ${fmtDate(TOURNAMENT_DATA.generated)}; forecast ~${fmt(t.point_estimate)} by ${fmtDate(t.event_start)}, ${d.ciPct}% range ${fmt(t.ci_lower)} to ${fmt(t.ci_upper)}${last}.`;
  const find = l => (d.datasets.find(x => x.label === l) || {}).data;
  const proj = find('Projected'), up = find('CI Upper'), lo = find('CI Lower');
  const cols = ['Date', 'Registered'];
  if (proj) cols.push('Forecast', `${d.ciPct}% Low`, `${d.ciPct}% High`);
  if (d.lastYear) cols.push(`${d.lastYear.year} at This Point`);
  const start = d.actualData.length ? d.actualData[0].x : eventDate.getTime();
  const rows = weeklyStops(eventDate.getTime(), start).map(x => {
    const r = [DATE_FMT.short.format(new Date(x)), _fmtOrNull(stepValueAt(d.actualData, x))];
    if (proj) r.push(_fmtOrNull(stepValueAt(proj, x)), _fmtOrNull(stepValueAt(lo, x)), _fmtOrNull(stepValueAt(up, x)));
    if (d.lastYear) r.push(_fmtOrNull(stepValueAt(d.lastYear.data, x)));
    return r;
  });
  chartDescribe(canvas, { label, caption: `${name}: cumulative entries by week`, columns: cols, rows });
}
function _fmtOrNull(v) { return v == null ? null : fmt(v); }

// (What-If panel removed)
