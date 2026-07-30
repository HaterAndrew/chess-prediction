// tab_about.js — renderModelHealth (About-the-Model tab telemetry),
// split verbatim from app.js (C14).

// AUDIT.md follow-up #3 — Model Health panel populates audit telemetry on the
// About-the-Model tab. Pulls cumulative CI coverage from PERFORMANCE_DATA,
// walkin/tier/low_confidence counts from TOURNAMENT_DATA, and fetches
// audit_warnings.json for the latest pipeline-run warnings.
function renderModelHealth() {
  const grid = document.getElementById('mh-grid');
  if (!grid) return;
  const updated = document.getElementById('mh-updated');
  if (updated) {
    const ts = TOURNAMENT_DATA.last_updated || TOURNAMENT_DATA.generated;
    updated.textContent = ts ? 'Pipeline last ran ' + ts : '';
  }

  // v3 T7: say what the grade actually covers, and give the second engine its
  // own measured number rather than leaving it implied.
  //
  // Several paths reach the page. predict_nowcast produces the headline grade.
  // The online-window estimator handles multi-schedule events that have already
  // started, and it is now graded separately (04e writes performance_data
  // .window_engine). The remaining cards use interim fallbacks — pace,
  // historical average, or the raw live count — which no grade covers, and
  // those are marked low-confidence.
  //
  // The two letters are deliberately not combined. The window engine is scored
  // 0-2 days from registration close with most of the field already in; the
  // headline is scored at T-14/7/3 before the event starts. Averaging them, or
  // showing one as though it described the other, would read as a better model
  // when it is only an easier question.
  const scopeEl = document.getElementById('mh-grade-scope');
  if (scopeEl && typeof TOURNAMENT_DATA !== 'undefined') {
    const live = TOURNAMENT_DATA.tournaments.filter(t => t.status === 'live');
    const graded = live.filter(t => t.prediction_source === 'model');
    const windowed = live.filter(t => t.prediction_source === 'model_online_window');
    if (live.length) {
      const other = live.length - graded.length - windowed.length;
      const parts = [
        `Grade scope: the headline grade is measured on the main model, which `
        + `currently produces ${graded.length} of ${live.length} live predictions.`,
      ];
      const we = (typeof PERFORMANCE_DATA !== 'undefined')
        ? PERFORMANCE_DATA.window_engine : null;
      if (windowed.length && we && we.grade && we.grade !== 'N/A') {
        parts.push(
          `${windowed.length} come from the online-registration-window model, `
          + `graded ${we.grade} separately over ${we.n} predictions: a shorter, `
          + `easier horizon than the headline, so the two are not comparable.`);
      } else if (windowed.length) {
        parts.push(
          `${windowed.length} come from the online-registration-window model, `
          + `graded separately.`);
      }
      if (other > 0) {
        parts.push(
          `The other ${other} use interim fallbacks (pace, historical average, `
          + `or the live count) that no grade covers; those cards are marked `
          + `low-confidence.`);
      }
      scopeEl.textContent = parts.join(' ');
    }
  }

  // v3 T10: the footer corpus size comes from the data too. It was hardcoded as
  // "192K entry records across 778 tournaments" and had drifted from the real
  // 781 / 194.5K.
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const tc = document.getElementById('footerTournamentCount');
    if (tc && PERFORMANCE_DATA.n_corpus_tournaments) {
      tc.textContent = PERFORMANCE_DATA.n_corpus_tournaments.toLocaleString();
    }
    const er = document.getElementById('footerEntryRecords');
    if (er && PERFORMANCE_DATA.n_entry_records) {
      const n = PERFORMANCE_DATA.n_entry_records;
      er.textContent = n >= 1000 ? Math.round(n / 1000) + 'K' : String(n);
    }
  }

  // K1/L2: single-source the "How We Tested It" prose numbers from
  // PERFORMANCE_DATA so they can never drift from the graded truth. Cumulative
  // T-14 drives the headline; cumulative T-3 the close-in coverage caveat.
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const cum = PERFORMANCE_DATA.cumulative || {};
    const cagg = cum.aggregate || [];
    const at = (T) => cagg.find(a => a.T === T);
    const t14 = at(14), t3 = at(3);
    const setTxt = (id, v) => { const e = document.getElementById(id); if (e && v != null) e.textContent = v; };
    setTxt('about-n', cum.n_tournaments);
    setTxt('about-prior-n', cum.n_tournaments);
    if (t14) {
      const cov14 = Math.round(t14.ci_coverage);
      setTxt('about-median', t14.median_ape_pct + '%');
      setTxt('about-prior-median', t14.median_ape_pct + '%');
      setTxt('about-cov', cov14 + '%');
      setTxt('about-prior-cov', cov14 + '%');
      // Methodology callout / sanity-check / footer coverage stats (same source).
      setTxt('mc-ci-cover', cov14 + '%');
      setTxt('mc-ci-cover-inline', cov14 + '%');
      setTxt('mc-ci-cover-footer', cov14 + '%');
    }
    if (t3) setTxt('about-cov-close', Math.round(t3.ci_coverage) + '%');
    const yrs = Object.keys(PERFORMANCE_DATA.years || {})
      .filter(y => (PERFORMANCE_DATA.years[y].n_tournaments || 0) > 0).sort();
    if (cum.n_tournaments && yrs.length) {
      setTxt('about-span-note', `${cum.n_tournaments} tournaments across ${yrs[0]}–${yrs[yrs.length - 1]}.`);
    }
  }

  const tiles = [];

  // Tile 1: cumulative T-14 CI coverage vs nominal 80%
  let covPct = null;
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA) {
    const cum = PERFORMANCE_DATA.cumulative || {};
    const cumT14 = (cum.aggregate || []).find(a => a.T === 14);
    if (cumT14) covPct = cumT14.ci_coverage;
  }
  if (covPct !== null) {
    const drift = Math.abs(covPct - 80);
    const color = drift <= 3 ? 'var(--green)' : drift <= 7 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'CI coverage (cumulative T-14)',
      value: covPct + '%',
      sub: 'target 80% / drift ' + Math.round(drift) + 'pp',
      color,
      help: 'Cumulative empirical coverage of the 80% confidence interval across years 2023-2026. Should sit near 80%.',
    });
  }

  // Tile 2: walk-in source distribution
  const walkinSrc = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(t => {
    if (t.walkin_source) walkinSrc[t.walkin_source] = (walkinSrc[t.walkin_source] || 0) + 1;
  });
  const walkinTotal = Object.values(walkinSrc).reduce((a, b) => a + b, 0);
  if (walkinTotal > 0) {
    const fam = walkinSrc.family || 0;
    const est = walkinSrc.estimate || 0;
    const famPct = Math.round(100 * fam / walkinTotal);
    const color = famPct >= 80 ? 'var(--green)' : famPct >= 50 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Walk-in family-level coverage',
      value: famPct + '%',
      sub: fam + ' family / ' + est + ' estimate (n=' + walkinTotal + ')',
      color,
      help: 'How many tournaments use family-specific walk-in multipliers vs the global 1.1x fallback.',
    });
  }

  // Tile 3: prediction tier on live cohort
  const tierCounts = {};
  (TOURNAMENT_DATA.tournaments || []).forEach(t => {
    if (t.status === 'live' && t.prediction_tier) {
      tierCounts[t.prediction_tier] = (tierCounts[t.prediction_tier] || 0) + 1;
    }
  });
  const liveTotal = Object.values(tierCounts).reduce((a, b) => a + b, 0);
  if (liveTotal > 0) {
    const direct = tierCounts['family-direct'] || 0;
    const fallback = liveTotal - direct;
    const directPct = Math.round(100 * direct / liveTotal);
    const color = directPct >= 90 ? 'var(--green)' : directPct >= 70 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Live cohort direct family ratio',
      value: directPct + '%',
      sub: direct + ' direct / ' + fallback + ' fallback (n=' + liveTotal + ')',
      color,
      help: 'Of live-cohort predictions, how many used direct family ratios vs a fallback path.',
    });
  }

  // Tile 4: low-confidence count
  const lowConf = (TOURNAMENT_DATA.tournaments || []).filter(t => t.low_confidence).length;
  const totalTournaments = (TOURNAMENT_DATA.tournaments || []).length;
  if (totalTournaments > 0) {
    const pct = Math.round(100 * lowConf / totalTournaments);
    const color = pct <= 5 ? 'var(--green)' : pct <= 15 ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: 'Low-confidence predictions',
      value: String(lowConf),
      sub: pct + '% of ' + totalTournaments + ' tournaments / n<4 history',
      color,
      help: 'Predictions for families with <4 qualifying historical editions. Lognormal CI is unreliable below 4.',
    });
  }

  // Tile 5: 2026 backtest grade
  if (typeof PERFORMANCE_DATA !== 'undefined' && PERFORMANCE_DATA && PERFORMANCE_DATA.years && PERFORMANCE_DATA.years['2026']) {
    const yr = PERFORMANCE_DATA.years['2026'];
    const grade = yr.grade || 'N/A';
    const color = grade.startsWith('A') ? 'var(--green)' : grade.startsWith('B') ? 'var(--gold)' : 'var(--red)';
    tiles.push({
      label: '2026 backtest grade',
      value: grade,
      sub: yr.grade_detail || ((yr.n_tournaments || 0) + ' tournaments'),
      color,
      help: 'Letter grade from the 2026 evaluation cohort: worst of the T-14/T-7/T-3 lead times (MAE + CI coverage), leave-one-out so no tournament grades itself.',
    });
  }

  grid.innerHTML = tiles.map(t =>
    '<div title="' + t.help.replace(/"/g, '&quot;') + '" style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px;cursor:help">' +
    '<div style="font-size:var(--fs-1);color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">' + t.label + '</div>' +
    '<div style="font-size:1.6rem;font-weight:800;color:' + t.color + ';line-height:1">' + t.value + '</div>' +
    '<div style="font-size:var(--fs-1);color:var(--text2);margin-top:6px">' + t.sub + '</div>' +
    '</div>'
  ).join('');

  // Pipeline warnings — async fetch
  const warnEl = document.getElementById('mh-warnings');
  if (!warnEl) return;
  fetch('audit_warnings.json', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || !data.warnings) { warnEl.innerHTML = ''; return; }
      const c = data.count || 0;
      if (c === 0) {
        warnEl.innerHTML = '<div style="font-size:var(--fs-2);color:var(--green);padding:10px 12px;background:rgba(72,187,120,.08);border:1px solid rgba(72,187,120,.3);border-radius:8px">Latest pipeline run: 0 warnings (clean).</div>';
        return;
      }
      // v5 Cat V: warnings are deduped upstream and carry a per-entry count;
      // step/text pass through esc() — pipeline-controlled or not, nothing
      // lands in innerHTML unescaped.
      const rows = data.warnings.map(w =>
        '<tr><td style="padding:4px 8px;color:var(--muted);font-size:var(--fs-2);white-space:nowrap">' +
        esc(w.step.split('(')[0].trim()) + '</td><td style="padding:4px 8px;color:var(--text2);font-size:var(--fs-2)">' +
        esc(w.text) + (w.count > 1 ? ' <span style="color:var(--muted)">×' + w.count + '</span>' : '') + '</td></tr>'
      ).join('');
      warnEl.innerHTML =
        '<details style="background:rgba(214,158,46,.08);border:1px solid rgba(214,158,46,.3);border-radius:8px;padding:10px 12px">' +
        '<summary style="cursor:pointer;font-size:var(--fs-2);color:var(--gold);font-weight:600">Latest pipeline run: ' + c + ' distinct warning' + (c === 1 ? '' : 's') + ' (click to expand)</summary>' +
        '<table style="width:100%;margin-top:10px;border-collapse:collapse">' + rows + '</table></details>';
    })
    .catch(() => { warnEl.innerHTML = ''; });
}
