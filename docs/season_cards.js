// season_cards.js — the tournament card the Season view and the Forecast's
// Up Next strip share (season.css draws it): the family, today's change,
// the T-minus, the forecast figure with the pace verdict against last year,
// the count so far and the progress rule. renderMiniCards fills the Season's
// Next Up and Later rows; renderUpNext fills the Forecast's strip of the next
// three. Both mark the selected tournament with the highlighter.

// Today's change on the card itself. v3 P1: this used to be a raw
// last-minus-prior with no gap check, so a missing scrape day reported several
// days of registrations as "today's change" (the "+125 entries" incident).
// latestDailyChange returns null unless the final interval really is one
// day; a wider gap is labelled with its true span.
function _cardDeltaChip(t) {
  if (typeof DailySeries === 'undefined') return '';
  const todayDelta = DailySeries.latestDailyChange(t, { isLive: !isDone(t) });
  if (todayDelta != null && todayDelta !== 0) {
    return `<span class="card-delta ${todayDelta > 0 ? 'pos' : 'neg'}" title="Change since the previous day's scrape">${todayDelta > 0 ? '+' : ''}${todayDelta}</span>`;
  }
  const iv = DailySeries.latestInterval(t, { isLive: !isDone(t) });
  if (iv && iv.isGap && iv.added > 0) {
    return `<span class="card-delta pos" title="No scrape for ${iv.span} days: the value covers the whole period, not one day">+${iv.added} / ${iv.span}d</span>`;
  }
  return '';
}

// The same pace metric as the Forecast's note: the count now against last
// year's count at the same point (prior_year_pace), falling back to last
// year's final times the family curve only when the daily data is missing.
function _cardPaceTag(t) {
  let expected = null;
  if (t.prior_year_pace && t.prior_year_pace.count_at_same_point > 0) {
    expected = t.prior_year_pace.count_at_same_point;
  } else if (t.registration_curve && t.historical && t.historical.length > 0) {
    const lastYr = t.historical[t.historical.length - 1];
    const c = Math.round(lastYr.count * interpCurve(t.registration_curve, t.days_remaining));
    if (c > 0) expected = c;
  }
  if (expected == null) return '';
  if (t.current_count > expected * 1.05) return '<span class="tag tag-signal">Ahead</span>';
  if (t.current_count < expected * 0.95) return '<span class="tag tag-ember">Behind</span>';
  return '<span class="tag">On Pace</span>';
}

// act: the action a tap dispatches (actions.js). On the Season a card opens
// the Forecast on that tournament; on the Forecast's own strip it just
// selects, since the visitor is already there.
function seasonCard({ t, i }, act) {
  const isSelected = i === selectedIndex;
  const pct = t.point_estimate > 0 ? (t.current_count / t.point_estimate * 100).toFixed(0) : 0;
  return `<div class="mini-card${isSelected ? ' mini-card-active' : ''}" data-act="${act}" data-idx="${i}" data-keyable="1" data-keys="enter" tabindex="0" role="button" aria-label="${esc(t.family)} ${t.year}: ${fmt(t.point_estimate)} predicted" aria-current="${isSelected ? 'true' : 'false'}">
    <div class="mini-card-header">
      <span class="mini-card-name" title="${esc(t.family)} ${t.year}">${esc(t.family)}</span>
      <div class="mini-card-chips">${_cardDeltaChip(t)}<span class="tag tag-live"><span class="live-dot"></span>T-${t.days_remaining}</span></div>
    </div>
    <div class="mini-card-figure"><span class="mini-card-number">${fmt(t.point_estimate)}</span>${_cardPaceTag(t)}</div>
    <div class="mini-card-details">${fmt(t.current_count)} registered · ${fmtDate(t.event_start)}</div>
    <div class="rule-bar" aria-hidden="true"><div class="rule-bar-fill" style="width:${pct}%"></div></div>
  </div>`;
}

function _liveByDate() {
  return TOURNAMENT_DATA.tournaments.map((t, i) => ({ t, i }))
    .filter(({ t }) => t.status === 'live')
    .sort((a, b) => a.t.days_remaining - b.t.days_remaining);
}

// The Season: the next three events get the featured row; the rest stay
// compact. Everything remains clickable and information-identical.
function renderMiniCards() {
  const el = document.getElementById('miniGrid');
  if (!el) return;
  const live = _liveByDate();
  const featured = live.slice(0, 3);
  const later = live.slice(3);
  const card = x => seasonCard(x, 'select-tournament-forecast');
  el.classList.add('mini-grid-tiered');
  el.innerHTML =
    (featured.length ? `<div class="mini-section-label">Next Up</div><div class="mini-grid-featured">${featured.map(card).join('')}</div>` : '') +
    (later.length ? `<div class="mini-section-label">Later</div><div class="mini-grid-rest">${later.map(card).join('')}</div>` : '');
}

// The Forecast's Up Next strip: the next three, whichever is selected.
function renderUpNext() {
  const el = document.getElementById('upNextStrip');
  if (!el) return;
  const next = _liveByDate().slice(0, 3);
  el.innerHTML = next.length
    ? next.map(x => seasonCard(x, 'select-tournament')).join('')
    : '<div class="empty">No upcoming tournaments</div>';
}
