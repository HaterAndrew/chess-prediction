// hero_kpi.js — the hero cell: the label, the figure under the highlighter,
// and the range bracket with its caption. hero_figures.js draws the three
// figures and the week's bars.

// ══════════════════════════════════════════════════════════
// HERO + KPI
// ══════════════════════════════════════════════════════════

// The hero cell (forecast.css): the label, the figure under the highlighter,
// the range bracket with its caption, the festival cluster, the week's bars
// and the three figures. renderProgress (panels_info.js) folds the progress
// lines into the first two figures after this runs.
function renderHero(t) {
  const done = isDone(t);
  _renderHeroFigure(t, done);
  document.getElementById('heroCi').innerHTML = _heroRangeHTML(t, done);
  // Festival cluster — renders inline if this tournament is part of a
  // multi-sub-event festival (e.g. World Open). No-op otherwise.
  renderFestivalCluster(t);
  _renderHeroFigures(t, done);
  _renderWeekBars(t, done);
}

// The figure counts up on the first load only; a later switch lands on the
// value, so moving between tournaments reads as a change, not a replay.
let _heroCounted = false;

function _renderHeroFigure(t, done) {
  const statusPrefix = t.status === 'historical' ? `${t.year} ` : '';
  const heroLabel = document.getElementById('heroLabel');
  heroLabel.textContent = done ? `${statusPrefix}Final Entries` : 'Predicted Final Entries';
  const heroNum = document.getElementById('heroNumber');
  // A forecast sits under the highlighter; a final count is a fact in ink.
  heroNum.classList.toggle('hero-number-final', done);
  const target = t.point_estimate;
  // #heroNumber is aria-hidden and the tween writes it every frame; the value
  // reaches assistive tech once, from this dedicated live region, with the
  // label included so the number is not announced bare (2026-09-07 review).
  const announce = document.getElementById('heroAnnounce');
  if (announce) announce.textContent = `${heroLabel.textContent.trim()}: ${fmt(Math.round(target))}`;
  if (_heroCounted || _reduceMotion()) { heroNum.textContent = fmt(Math.round(target)); return; }
  _heroCounted = true;
  const duration = 600;
  const start = performance.now();
  (function animHero(now) {
    const p = Math.min(((now || performance.now()) - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    heroNum.textContent = fmt(Math.round(target * ease));
    if (p < 1) requestAnimationFrame(animHero);
  })(performance.now());
}

// The fallback tier, when the prediction did not use direct family ratios.
const HERO_TIER_LABELS = {
  'family-alias': 'Pooled history',
  'size-matched': 'No family history',
  'roster-pending': 'Interim estimate',
};

// The caption under the range, one plain line: "80% range · Medium
// confidence, 4 editions · Interim estimate". Low confidence is in ember.
function _heroCaption(t, ciLevel) {
  // Audit telemetry: prefer the explicit low_confidence flag over the derived
  // nHist count. n_historical_editions is the audit-canonical count (excludes
  // COVID/online); the historical array length is the fallback.
  const nHist = (typeof t.n_historical_editions === 'number')
    ? t.n_historical_editions
    : (t.historical ? t.historical.length : 0);
  const isLow = (typeof t.low_confidence === 'boolean') ? t.low_confidence : (nHist < 4);
  const confLabel = isLow
    ? (nHist >= 2 ? 'Low confidence' : 'Very low confidence')
    : (nHist >= 8 ? 'High confidence' : 'Medium confidence');
  const conf = `${confLabel}, ${nHist} edition${nHist === 1 ? '' : 's'}`;
  const parts = [`${ciLevel}% range`, isLow ? `<span class="conf-low">${conf}</span>` : conf];
  const tier = t.prediction_tier;
  if (tier && tier !== 'family-direct') parts.push(HERO_TIER_LABELS[tier] || tier.replace('-', ' '));
  return parts.join(' · ');
}

// Why the model is as confident as it is, in one sentence.
function _confidenceReason(t) {
  const conf = (t.confidence_label || '').toLowerCase();
  const tier = (t.prediction_tier || 'family-direct').toLowerCase();
  if (tier === 'family-direct' && conf.includes('high')) return 'Strong prior data: 5+ years of same-month history for this family.';
  if (tier === 'family-direct' && conf.includes('medium')) return 'Moderate prior data: 3–4 years of comparable history.';
  if (tier === 'family-direct' && conf.includes('low') && !conf.includes('very')) return 'Sparse prior data: under 3 comparable years.';
  if (conf.includes('very')) return 'Limited or no comparable history; estimate falls back to family average.';
  if (tier === 'family-alias') return 'No direct history: pooled from related families for this prediction.';
  if (tier === 'size-matched') return 'No family history: drawn from families with comparable historical size.';
  return `${t.confidence_label || 'Confidence'} based on ${tier.replace('-', ' ')} history.`;
}

// The 80% range as a bracket, the estimate's pen tick placed inside it, and
// its caption. A completed tournament's figure is its final count, with
// nothing to bracket.
function _heroRangeHTML(t, done) {
  if (t.ci_lower === t.ci_upper) return '';
  const ciLevel = Math.round((t.ci_level || .8) * 100);
  const lo = t.ci_lower, hi = t.ci_upper, pe = t.point_estimate;
  // Clamp so an off-band point estimate (a rare model edge case) still lands inside the bracket.
  const pct = Math.max(0, Math.min(100, ((pe - lo) / (hi - lo)) * 100));
  const reason = _confidenceReason(t);
  return `
      <div class="range" role="img" aria-label="${ciLevel}% confidence interval from ${fmt(lo)} to ${fmt(hi)}, point estimate ${fmt(pe)}. ${reason}" title="${reason}">
        <span class="range-bound">${fmt(lo)}</span>
        <div class="range-track"><div class="range-mark" style="left:${pct.toFixed(2)}%"></div></div>
        <span class="range-bound">${fmt(hi)}</span>
      </div>
      <div class="range-caption">${done ? `${ciLevel}% range` : _heroCaption(t, ciLevel)}</div>`;
}
