// panels_grid.js — the Season's tournament table and summary line, the
// festival cluster and the Likely Range header's measured tooltip, split
// from app.js (C12).

// ══════════════════════════════════════════════════════════
// ALL TOURNAMENTS TABLE
// ══════════════════════════════════════════════════════════
let tableSortCol = 'date';
let tableSortDir = 'asc';

function sortTable(col, ev) {
  if (tableSortCol === col) {
    tableSortDir = tableSortDir === 'asc' ? 'desc' : 'asc';
  } else {
    tableSortCol = col;
    tableSortDir = 'asc';
  }
  // Update header classes
  document.querySelectorAll('.tourney-table th.sortable').forEach(th => th.classList.remove('asc', 'desc'));
  const header = ev && ev.target ? ev.target.closest('th') : document.querySelector(`.tourney-table th[onclick*="'${col}'"]`);
  if (header) header.classList.add(tableSortDir);
  renderAllTournaments();
}

// Filter state for the all-tournaments table. status filter is one of
// 'all' | 'live' | 'complete', opening on the upcoming events; query is a
// free-text substring match against family/year/state/city. Both apply on
// top of the existing sort.
let _ttStatusFilter = 'live';
function filterTourneyTable(status) {
  if (status) {
    _ttStatusFilter = status;
    document.querySelectorAll('.tt-filter').forEach(b =>
      b.classList.toggle('active', b.dataset.filter === status));
  }
  renderAllTournaments();
}

// "2026" or "2026–27": the seasons of the cards the overview table lists. Next
// season's events open while this season's are still running, so the heading
// follows the data instead of naming one year.
function overviewSeasonLabel(tournaments) {
  const years = [...new Set(tournaments
    .filter(t => t.status === 'live' || t.status === 'complete')
    .map(t => t.year))].sort();
  if (!years.length) return '';
  const first = String(years[0]);
  const last = String(years[years.length - 1]);
  return years.length === 1 ? first : `${first}–${last.slice(-2)}`;
}

// Entries since the previous scrape, for the Last day column. Read through
// DailySeries so a missed scrape is labelled with its true span instead of
// passing as one day (v3 P1), and only when the series reaches today's
// scrape: an older tail is not "last day".
function _lastDay(t) {
  if (t.status !== 'live' || typeof DailySeries === 'undefined') return null;
  return DailySeries.latestIntervalOn(t, TOURNAMENT_DATA.generated, { isLive: true });
}

function _lastDayCell(t) {
  const iv = _lastDay(t);
  if (!iv) return '–';
  const cls = iv.added > 0 ? ' pos' : iv.added < 0 ? ' neg' : '';
  const sign = iv.added > 0 ? '+' : '';
  if (iv.isGap) {
    return `<span class="td-delta${cls}" title="No scrape for ${iv.span} days: the value covers the whole period, not one day">${sign}${fmt(iv.added)}</span><span class="td-pace">/ ${iv.span}d</span>`;
  }
  return `<span class="td-delta${cls}" title="Change since the previous day's scrape">${sign}${fmt(iv.added)}</span>`;
}

function renderAllTournaments() {
  _syncLikelyRangeTitle();
  const body = document.getElementById('tourneyBody');
  const seasonTitle = `${overviewSeasonLabel(TOURNAMENT_DATA.tournaments)} Tournament Overview`.trim();
  document.querySelectorAll('[data-season-title]').forEach(el => { el.textContent = seasonTitle; });
  const filterInput = document.getElementById('tourneyFilter');
  const q = filterInput ? filterInput.value.trim().toLowerCase() : '';
  // Only show upcoming + complete (not 361 historical rows)
  const active = TOURNAMENT_DATA.tournaments
    .map((t, i) => ({t, i}))
    .filter(({t}) => {
      if (t.status !== 'live' && t.status !== 'complete') return false;
      if (_ttStatusFilter !== 'all' && t.status !== _ttStatusFilter) return false;
      if (q) {
        const hay = `${t.family} ${t.year} ${t.venue_city || ''} ${t.venue_state || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

  // Sort
  const dir = tableSortDir === 'asc' ? 1 : -1;
  active.sort((a, b) => {
    const ta = a.t, tb = b.t;
    switch (tableSortCol) {
      case 'name': return dir * ta.family.localeCompare(tb.family);
      case 'status': return dir * (ta.status === 'live' ? -1 : 1);
      // ISO dates order as plain strings; localeCompare would load the
      // collator (30 ms at 4x CPU throttle) on the default sort.
      case 'date': return dir * ((ta.event_start || '') < (tb.event_start || '') ? -1 : (ta.event_start || '') > (tb.event_start || '') ? 1 : 0);
      case 'current': return dir * (ta.current_count - tb.current_count);
      case 'lastday': {
        // Rows with no figure sink to the bottom in either direction.
        const da = _lastDay(ta), db = _lastDay(tb);
        if (!da || !db) return (da ? 0 : 1) - (db ? 0 : 1);
        return dir * (da.added - db.added);
      }
      case 'predicted': return dir * (ta.point_estimate - tb.point_estimate);
      case 'progress': {
        const pa = ta.point_estimate > 0 ? ta.current_count / ta.point_estimate : 0;
        const pb = tb.point_estimate > 0 ? tb.current_count / tb.point_estimate : 0;
        return dir * (pa - pb);
      }
      default: return 0;
    }
  });

  body.innerHTML = active.map(({t, i}) => {
    const isLive = t.status === 'live';
    const pill = isLive
      ? '<span class="status-pill pill-live"><span class="live-dot"></span>Upcoming</span>'
      : '<span class="status-pill pill-complete">Complete</span>';

    const pct = t.point_estimate > 0 ? Math.min(100, (t.current_count / t.point_estimate * 100)).toFixed(0) : 100;
    const ci = t.ci_lower === t.ci_upper ? '–' : `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}`;

    // The recent daily pace, for live tournaments
    let paceStr = '';
    if (isLive && t.daily_data && t.daily_data.length >= 3) {
      const recent = t.daily_data.slice(-7);
      if (recent.length >= 2) {
        const daySpan = recent[recent.length-1][0] - recent[0][0];
        const regSpan = recent[recent.length-1][1] - recent[0][1];
        const rate = daySpan > 0 ? (regSpan / daySpan).toFixed(1) : '0';
        paceStr = `<span class="td-pace">${rate}/day</span>`;
      }
    }

    // A phone shows the name and the forecast; this line under the name
    // carries the date, the countdown or state, and the count (season.css).
    const phoneSub = `${fmtDate(t.event_start)} · ${isLive ? 'T-' + t.days_remaining : 'Complete'} · ${fmt(t.current_count)} ${isLive ? 'registered' : 'entries'}`;
    return `<tr data-act="select-tournament-forecast" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0">
      <td data-label="Tournament"><div class="t-name" title="${esc(t.family)} ${t.year}">${esc(t.family)}</div><div class="t-sub">${t.year}${isLive ? ' · T-' + t.days_remaining : ''}</div><div class="t-sub-m">${phoneSub}</div></td>
      <td data-label="Status">${pill}</td>
      <td data-label="Event Date" class="num">${fmtDate(t.event_start)}${t.event_end ? ' – ' + fmtDate(t.event_end) : ''}</td>
      <td data-label="Current"><span class="td-current">${fmt(t.current_count)}</span>${paceStr}</td>
      <td data-label="Last day" class="num">${_lastDayCell(t)}</td>
      <td data-label="Predicted" class="td-predicted">${fmt(t.point_estimate)}</td>
      <td data-label="Likely Range" class="td-range">${ci}</td>
      <td data-label="Progress"><span class="td-progress"><span class="pace-bar-wrap" aria-hidden="true"><span class="pace-bar-fill" style="width:${pct}%"></span></span><span class="td-pct">${pct}%</span></span></td>
    </tr>`;
  }).join('');
  if (active.length === 0) {
    const cols = document.querySelectorAll('#tourneyTable thead th:not([hidden])').length;
    body.innerHTML = `<tr><td colspan="${cols}" class="tt-empty">No tournaments match the current filter.</td></tr>`;
  }
}

// ══════════════════════════════════════════════════════════
// SUMMARY BAR
// ══════════════════════════════════════════════════════════
function renderSummaryBar() {
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.filter(t => t.status === 'live');
  const complete = ts.filter(t => t.status === 'complete');
  // Seasons the finished cards belong to, as '26 or '26–'27: next season's
  // events open while this season's are still finishing.
  const seasons = [...new Set(complete.map(t => t.year))].sort();
  const seasonLabel = seasons.map(y => "'" + String(y).slice(-2)).join('–');
  const totalRegs = ts.filter(t => t.status !== 'historical').reduce((s, t) => s + t.current_count, 0);

  const el = document.getElementById('summaryBar');
  el.innerHTML = `
    <span><strong class="num">${live.length}</strong> upcoming</span>
    <span><strong class="num">${complete.length}</strong> complete ${seasonLabel}</span>
    <span><strong class="num">${fmt(totalRegs)}</strong> YTD entries</span>
  `;
}


// Confidence breakdown panel removed in iter 25 — the hero narrative +
// confidence badge already say "tracking on pace" or "low confidence
// (3 editions)" in plain English, which is the same info this 4-row
// audit panel surfaced more verbosely.

// ══════════════════════════════════════════════════════════
// FESTIVAL CLUSTER (e.g. World Open's 3 sub-events as one festival)
// ══════════════════════════════════════════════════════════
// When the selected tournament is one of several sub-events that
// share a festival lineage (currently World Open's top 6 / lower
// sections / Under 13), surface the sibling sub-events inline so
// the user can switch between them without navigating back out to
// the selector. Each sibling shows its current count + predicted
// final + days until its own event_start.
const FESTIVAL_GROUPS = [
  {
    name: 'World Open',
    families: [
      'World Open top 6 sections',
      'World Open lower sections',
      'World Open Under 13 Championship',
    ],
  },
];

function renderFestivalCluster(t) {
  const el = document.getElementById('festivalCluster');
  if (!el) return;
  if (!t || !t.family || !t.year) { el.innerHTML = ''; return; }
  const group = FESTIVAL_GROUPS.find(g =>
    g.families.includes(t.family) ||
    g.families.some(f => t.family.startsWith(f.split(' ').slice(0, 2).join(' '))));
  if (!group) { el.innerHTML = ''; return; }
  // Find sibling tournaments — same year, family in the group.
  const siblings = TOURNAMENT_DATA.tournaments
    .map((tt, idx) => ({ tt, idx }))
    .filter(({ tt }) => tt.year === t.year && group.families.includes(tt.family));
  if (siblings.length < 2) { el.innerHTML = ''; return; }

  // Sort by event_start so sub-events appear in chronological order.
  siblings.sort((a, b) => (a.tt.event_start || '').localeCompare(b.tt.event_start || ''));

  let html = `<div class="fc-head">
    <span class="fc-title">${esc(group.name)} ${t.year} festival</span>
    <span class="fc-sub">${siblings.length} sub-events</span>
  </div>
  <div class="fc-rows">`;
  siblings.forEach(({ tt, idx }) => {
    const isActive = idx === selectedIndex;
    // Short label — strip the redundant "World Open " prefix.
    const shortName = tt.family.replace(/^World Open\s*/, '').trim() || 'World Open';
    const subLabel = shortName.replace('top 6 sections', 'Top 6')
                              .replace('lower sections', 'Lower')
                              .replace('Under 13 Championship', 'Under 13');
    const current = isDone(tt) ? tt.current_count : tt.current_count;
    const pred = tt.point_estimate;
    const eventDate = tt.event_start
      ? fmtDate(tt.event_start)
      : '—';
    html += `<button class="fc-card ${isActive ? 'fc-card-active' : ''}"
      data-act="select-tournament" data-idx="${idx}"
      aria-current="${isActive ? 'true' : 'false'}"
      aria-label="${esc(subLabel)}: predicted ${fmt(pred)}, ${fmt(current)} registered">
      <div class="fc-card-label">${esc(subLabel)}</div>
      <div class="fc-card-num">${fmt(pred)}</div>
      <div class="fc-card-sub">${fmt(current)} reg · ${eventDate}</div>
    </button>`;
  });
  html += '</div>';
  el.innerHTML = html;
}

// ══════════════════════════════════════════════════════════
// LIKELY RANGE HEADER
// ══════════════════════════════════════════════════════════
// The "Likely Range" column header used to assert "8 times out of 10" as a
// flat fact. Measured cumulative coverage is below the 80% target at most
// horizons, and the About view renders the real figure from this same
// payload, so the tooltip states the measured rate at two weeks out
// (2026-09-07 review). renderAllTournaments calls it with the table.
function _syncLikelyRangeTitle() {
  const th = document.getElementById('thLikelyRange');
  const data = (typeof PERFORMANCE_SUMMARY !== 'undefined') ? PERFORMANCE_SUMMARY : null;
  const cumulative = data && (data.cumulative || data);
  if (!th || !cumulative || !cumulative.aggregate) return;
  const agg = cumulative.aggregate;
  // The T-14 bucket if it exists; else the nearest one inside 7 to 21 days.
  const t14 = agg.find(a => a.T === 14) || agg.find(a => a.T >= 7 && a.T <= 21);
  if (!t14 || t14.ci_coverage == null) return;
  const nEvents = cumulative.n_tournaments ?? data.n_tournaments ?? null;
  th.title = `Targets an 80% range. Measured: actual entries landed inside `
    + `it ${Math.round(t14.ci_coverage)}% of the time at two weeks out`
    + (nEvents ? `, across ${nEvents} tournaments in the walk-forward backtest.` : '.');
}
