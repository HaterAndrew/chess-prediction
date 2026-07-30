// panels_grid.js — all-tournaments table, summary bar, festival cluster
// and accuracy strip, split verbatim from app.js (C12).

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
// 'all' | 'live' | 'complete'; query is a free-text substring match against
// family/year/state/city. Both apply on top of the existing sort.
let _ttStatusFilter = 'all';
function filterTourneyTable(status) {
  if (status) {
    _ttStatusFilter = status;
    document.querySelectorAll('.tt-filter').forEach(b =>
      b.classList.toggle('tt-filter-active', b.dataset.filter === status));
  }
  renderAllTournaments();
}

function renderAllTournaments() {
  const body = document.getElementById('tourneyBody');
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
      case 'date': return dir * ((ta.event_start || '').localeCompare(tb.event_start || ''));
      case 'current': return dir * (ta.current_count - tb.current_count);
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
    const paceColor = isLive ? (pct > 30 ? 'var(--green)' : pct > 15 ? 'var(--gold)' : 'var(--blue)') : 'var(--muted)';

    const ci = t.ci_lower === t.ci_upper ? '–' : `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}`;

    // Compute daily pace for live tournaments
    let paceStr = '';
    if (isLive && t.daily_data && t.daily_data.length >= 3) {
      const recent = t.daily_data.slice(-7);
      if (recent.length >= 2) {
        const daySpan = recent[recent.length-1][0] - recent[0][0];
        const regSpan = recent[recent.length-1][1] - recent[0][1];
        const rate = daySpan > 0 ? (regSpan / daySpan).toFixed(1) : '0';
        paceStr = `<span style="font-size:var(--fs-2);color:var(--green)">${rate}/day</span>`;
      }
    }

    return `<tr data-act="select-tournament-top" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" style="cursor:pointer">
      <td data-label="Tournament"><div class="t-name" title="${esc(t.family)} ${t.year}">${esc(t.family)}</div><div class="t-sub">${t.year}${isLive ? ' · ' + t.days_remaining + 'd out' : ''}</div></td>
      <td data-label="Status">${pill}</td>
      <td data-label="Event Date">${fmtDate(t.event_start)}${t.event_end ? ' – ' + fmtDate(t.event_end) : ''}</td>
      <td data-label="Current" style="font-weight:600;color:var(--blue)">${fmt(t.current_count)} ${paceStr}</td>
      <td data-label="Predicted" style="font-weight:700;color:var(--gold)">${fmt(t.point_estimate)}</td>
      <td data-label="Likely Range" style="font-size:var(--fs-3);color:var(--muted)">${ci}</td>
      <td data-label="Progress">
        <span class="pace-bar-wrap"><span class="pace-bar-fill" style="width:${pct}%;background:${paceColor}"></span></span>
        <span style="font-size:var(--fs-2);color:var(--muted)">${pct}%</span>
      </td>
    </tr>`;
  }).join('');
  if (active.length === 0) {
    body.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px 0;color:var(--muted);font-size:var(--fs-3)">No tournaments match the current filter.</td></tr>`;
  }
}

// ══════════════════════════════════════════════════════════
// SUMMARY BAR
// ══════════════════════════════════════════════════════════
function renderSummaryBar() {
  const ts = TOURNAMENT_DATA.tournaments;
  const live = ts.filter(t => t.status === 'live');
  const complete2026 = ts.filter(t => t.status === 'complete');
  const historical = ts.filter(t => t.status === 'historical');
  const totalRegs = ts.filter(t => t.status !== 'historical').reduce((s, t) => s + t.current_count, 0);
  const nextEvent = [...live].sort((a, b) => a.days_remaining - b.days_remaining)[0];

  const el = document.getElementById('summaryBar');
  el.innerHTML = `
    <span><strong style="color:var(--green)">${live.length}</strong> upcoming</span>
    <span><strong style="color:var(--muted)">${complete2026.length}</strong> complete '26</span>
    <span><strong style="color:var(--purple)">${historical.length}</strong> historical</span>
    <span><strong style="color:var(--blue)">${fmt(totalRegs)}</strong> YTD entries</span>
    ${nextEvent ? `<span style="cursor:pointer" data-act="select-tournament" data-idx="${TOURNAMENT_DATA.tournaments.indexOf(nextEvent)}">Next: <strong style="color:var(--gold)">${nextEvent.family}</strong> in ${nextEvent.days_remaining}d</span>` : ''}
  `;
}

// Movements widget removed in iter 24 — today's delta is already on each
// mini-card via the delta chip (iter 9). Calendar timeline still surfaces
// the portfolio view by event date.

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
      ? new Date(tt.event_start + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
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

// Recent-finishes feed removed in iter 26 — the all-tournaments table
// at the bottom already lists completed tournaments and is sortable +
// filterable. Model accuracy summary lives in the strip just below the
// calendar; the per-tournament drilldown lives in the Performance tab.

// ══════════════════════════════════════════════════════════
// INLINE MODEL ACCURACY STRIP (Predictions tab)
// ══════════════════════════════════════════════════════════
// Compact "the model has been right X% of the time at T-14" strip that
// pulls from PERFORMANCE_DATA. Surfaces trustworthiness inline without
// making the user click into the Performance tab. Three cells: grade,
// T-14 MAE, T-14 CI coverage. Click the strip to jump to the full
// Performance tab.
function renderAccuracyStrip() {
  const el = document.getElementById('accuracyStrip');
  if (!el) return;
  const data = (typeof PERFORMANCE_DATA !== 'undefined') ? PERFORMANCE_DATA : null;
  if (!data) { el.innerHTML = ''; return; }
  const cumulative = data.cumulative || data;
  if (!cumulative || !cumulative.aggregate) { el.innerHTML = ''; return; }
  const agg = cumulative.aggregate;
  // Find the T-14 bucket if it exists; fall back to nearest under-21d.
  let t14 = agg.find(a => a.T === 14);
  if (!t14) t14 = agg.find(a => a.T >= 7 && a.T <= 21);
  const grade = cumulative.grade || data.grade || '–';
  const nEvents = cumulative.n_tournaments ?? data.n_tournaments ?? null;
  const mae = t14 ? t14.mae_pct : null;
  const cov = t14 ? t14.ci_coverage : null;

  // Grade-color mapping (matches the Performance tab letter conventions).
  function gradeCls(g) {
    if (!g) return 'flat';
    const first = g[0];
    if (first === 'A') return 'pos';
    if (first === 'B') return 'flat';
    return 'neg';
  }

  el.innerHTML = `
    <button class="acc-row" data-act="page-tab" data-tab="performance" aria-label="Open full model performance tab">
      <span class="acc-cell acc-grade">
        <span class="acc-grade-letter acc-${gradeCls(grade)}">${grade}</span>
        <span class="acc-grade-label">Model grade${nEvents ? ` · ${nEvents} tests` : ''}</span>
      </span>
      ${mae != null ? `<span class="acc-cell">
        <span class="acc-num">${mae.toFixed(1)}%</span>
        <span class="acc-lab">Avg miss at 2 weeks out</span>
      </span>` : ''}
      ${cov != null ? `<span class="acc-cell">
        <span class="acc-num">${Math.round(cov)}%</span>
        <span class="acc-lab">In range at 2 weeks out</span>
      </span>` : ''}
      <span class="acc-cta">View details &rarr;</span>
    </button>
  `;
}
