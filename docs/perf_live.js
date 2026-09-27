// perf_live.js — the Performance view's live record: the forecasts the site
// published, graded against the finals (perf/live_record.py). The views above
// score today's model re-run on each date; this scores what visitors saw,
// from every model version that was live, so the two can disagree.

const LIVE_ROUTES = {
  model: 'main model',
  metadata_pace: 'pace',
  metadata_historical_avg: 'historical average',
  model_online_window: 'online window',
};

function _liveSigned(v, digits) {
  const s = v.toFixed(digits);
  return (Number(s) > 0 ? '+' : '') + s;
}

function _liveRow(T, m) {
  const med = m.median_error_ci || [];
  const cov = m.coverage_ci || [];
  // The red pen only where the interval sits wholly below the 80% target.
  const low = cov[1] != null && cov[1] < 80;
  return `<tr>
    <td data-label="Lead Time" class="perf-cell">T-${T}<div class="perf-cell-ci">n=${m.n}</div></td>
    <td data-label="Average Miss" class="perf-cell">${m.mae_pct.toFixed(1)}%</td>
    <td data-label="Typical Miss" class="perf-cell">${_liveSigned(m.median_error_pct, 1)}%` +
      (med[0] != null ? `<div class="perf-cell-ci">${_liveSigned(med[0], 0)} to ${_liveSigned(med[1], 0)}%</div>` : '') + `</td>
    <td data-label="Inside the Range" class="perf-cell${low ? ' perf-miss-big' : ''}">${Math.round(m.coverage)}%` +
      (cov[0] != null ? `<div class="perf-cell-ci">${Math.round(cov[0])}–${Math.round(cov[1])}%</div>` : '') + `</td>
  </tr>`;
}

function _liveRoutes(live) {
  const counts = Object.entries(live.by_route || {}).map(([route, byT]) =>
    [LIVE_ROUTES[route] || route, Object.values(byT).reduce((s, m) => s + m.n, 0)]);
  counts.sort((a, b) => b[1] - a[1]);
  return counts.map(([label, n]) => `${label} ${n}`).join(', ');
}

function perfDrawLive(data) {
  const el = document.getElementById('perfLive');
  if (!el) return;
  const live = data && data.live_record;
  if (!live || !live.n_records) {
    el.innerHTML = '<div class="empty">No published forecast has a final yet.</div>';
    return;
  }
  const p = live.protocol || {};
  const eras = (live.eras || []).length;
  const rows = Object.entries(live.pooled || {})
    .sort((a, b) => Number(b[0]) - Number(a[0]))
    .map(([T, m]) => _liveRow(T, m)).join('');
  el.innerHTML = `<p class="perf-table-key">${live.n_records} forecasts of ${live.n_events} finished events,
      published ${p.first_date} to ${p.last_date} by ${eras} model version${eras === 1 ? '' : 's'}.
      Each is the last one shown on the day, or up to ${p.match_days} days earlier. By route: ${_liveRoutes(live)}.</p>
    <table class="perf-table perf-live-table">
      <thead><tr><th>Lead Time</th><th>Average Miss</th><th>Typical Miss</th><th>Inside the Range</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="perf-table-key">n is the forecasts graded at that lead time. Typical miss is the median, above zero when forecasts ran high; the small figures under it and under inside the range are 95% intervals. Inside the range in red: its interval sits wholly below the 80% target.</p>`;
}
