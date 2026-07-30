// tab_email.js — email generator tab, split verbatim from app.js (C4).

// ══════════════════════════════════════════════════════════
// EMAIL GENERATOR
// ══════════════════════════════════════════════════════════
let emailLength = 'medium';
let emailFormat = 'plain';
let emailLive = [];
let emailInited = false;

function initEmailTab() {
  if (emailInited) return;
  emailInited = true;
  emailLive = TOURNAMENT_DATA.tournaments
    .filter(t => t.status === 'live')
    .sort((a, b) => a.days_remaining - b.days_remaining);
  const grid = document.getElementById('emailGrid');
  grid.innerHTML = '';
  emailLive.forEach((t, i) => {
    const lbl = document.createElement('label');
    const defaultOn = t.days_remaining <= 60;
    lbl.innerHTML = `<input type="checkbox" data-eidx="${i}" ${defaultOn ? 'checked' : ''}>
      <span>${esc(t.family)}</span>
      <span class="email-tourn-days">${t.days_remaining}d</span>`;
    grid.appendChild(lbl);
  });
  // Auto-suggest subject line on first init
  const subj = document.getElementById('emailSubject');
  if (subj && !subj.value) subj.placeholder = emailAutoSubject(emailGetSelected());
}

function emailGetSelected() {
  const sel = [];
  document.querySelectorAll('#emailGrid input[type="checkbox"]').forEach(cb => {
    if (cb.checked) sel.push(emailLive[parseInt(cb.dataset.eidx)]);
  });
  return sel;
}
function emailSelectAll() { document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = true); }
function emailSelectNone() { document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = false); }
function emailSelectClose() {
  document.querySelectorAll('#emailGrid input').forEach(cb => {
    cb.checked = emailLive[parseInt(cb.dataset.eidx)].days_remaining <= 60;
  });
}
function emailSelectLiveOnly() {
  // All emailLive are already live; this just re-checks all (alias for All within live set)
  document.querySelectorAll('#emailGrid input').forEach(cb => cb.checked = true);
}

function setEmailLength(len) {
  emailLength = len;
  document.querySelectorAll('#emailLenToggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.len === len);
  });
}

function setEmailFormat(fmt) {
  emailFormat = fmt;
  document.querySelectorAll('#emailFormatToggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.fmt === fmt);
  });
  applyEmailViewState();
}

function setEmailSplitTab(tab) {
  const split = document.getElementById('emailSplit');
  if (!split) return;
  split.dataset.tab = tab;
  document.querySelectorAll('#emailSplitTabs .email-split-tab').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  applyEmailViewState();
}

function applyEmailViewState() {
  const out = document.getElementById('emailOutput');
  const pv = document.getElementById('emailPreview');
  const split = document.getElementById('emailSplit');
  const tabs = document.getElementById('emailSplitTabs');
  const copyHtmlBtn = document.getElementById('emailCopyHtmlBtn');
  if (!out || !pv) return;
  const tab = (split && split.dataset.tab) || 'source';
  const isMobile = window.matchMedia('(max-width: 639px)').matches;

  if (emailFormat === 'html') {
    out.classList.add('mode-html');
    if (copyHtmlBtn) copyHtmlBtn.style.display = '';
    if (isMobile) {
      if (tabs) tabs.style.display = '';
      out.style.display = (tab === 'source') ? '' : 'none';
      pv.style.display = (tab === 'preview') ? '' : 'none';
    } else {
      if (tabs) tabs.style.display = 'none';
      out.style.display = '';
      pv.style.display = '';
    }
  } else {
    out.classList.remove('mode-html');
    if (copyHtmlBtn) copyHtmlBtn.style.display = 'none';
    if (tabs) tabs.style.display = 'none';
    out.style.display = '';
    pv.style.display = 'none';
  }
}

window.addEventListener('resize', () => {
  if (typeof emailFormat !== 'undefined') applyEmailViewState();
});

function emailLastYear(t) {
  if (!t.historical || !t.historical.length) return null;
  return [...t.historical].sort((a, b) => b.year - a.year)[0];
}
function emailHistAvg(t) {
  if (!t.historical || !t.historical.length) return null;
  const c = t.historical.map(h => h.count);
  return Math.round(c.reduce((a, b) => a + b, 0) / c.length);
}

// Tab-separated table — tabs align natively in every email client
function emailTable(headers, rows) {
  const cell = c => (c !== '' && c != null) ? String(c) : '';
  const line = cols => cols.map(cell).join('\t');
  return line(headers) + '\n' + rows.map(r => line(r)).join('\n');
}

function emailFormatTournament(t, len) {
  const ly = emailLastYear(t);
  const avg = emailHistAvg(t);
  const pace = t.prior_year_pace;
  const name = t.family.toUpperCase();
  const sorted = t.historical ? [...t.historical].sort((a, b) => b.year - a.year) : [];
  const parts = [];

  // ── SHORT ──
  if (len === 'short') {
    let s = `${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`;
    if (ly) s += `  Last year was ${ly.count}.`;
    parts.push(s);
    if (pace) {
      const d = t.current_count - pace.count_at_same_point;
      if (d > 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are ahead of pace.`);
      else if (d < 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are a bit behind.`);
      else parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}.`);
    }
    return parts.join('  ');
  }

  // ── MEDIUM ──
  if (len === 'medium') {
    let main = `${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`;
    if (ly) {
      const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
      if (pct > 10) main += `  Last year was ${ly.count}, so we are ahead.`;
      else if (pct < -10) main += `  Last year was ${ly.count}, so we are still behind.`;
      else if (pct < -3) main += `  Last year was ${ly.count}, so we are a little behind.`;
      else main += `  Last year was ${ly.count}.`;
    }
    parts.push(main);
    if (pace) {
      const d = t.current_count - pace.count_at_same_point;
      if (d > 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are ahead of pace.`);
      else if (d < 0) parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}, so we are a bit behind.`);
      else parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}.`);
    }
    if (sorted.length >= 2) {
      const rows = [[2026, t.current_count, t.point_estimate, '']];
      sorted.forEach(h => rows.push([h.year, '', '', h.count]));
      parts.push(emailTable(['YEAR', 'ENTRIES', 'PROJECTION', 'FINAL'], rows));
    }
    return parts.join('\n');
  }

  // ── LONG ──
  parts.push(`${name}:  We are at ${t.current_count} entries which projects to ${t.point_estimate} with a range of ${t.ci_lower} to ${t.ci_upper}.`);

  if (ly) {
    const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
    if (pct > 15) parts.push(`Last year was ${ly.count}, so the projection has us well ahead.`);
    else if (pct > 5) parts.push(`Last year was ${ly.count}, so we are tracking ahead.`);
    else if (pct > -5) parts.push(`Last year was ${ly.count}, so we are in the same neighborhood.`);
    else if (pct > -15) parts.push(`Last year was ${ly.count}, so we are still a bit behind.`);
    else parts.push(`Last year was ${ly.count}, so we are lagging.`);
  }

  if (avg && sorted.length >= 3) {
    const pct = Math.round((t.point_estimate - avg) / avg * 100);
    if (pct < -10) parts.push(`The historical average is ${avg}, so we are still below the norm.`);
    else if (pct > 10) parts.push(`The historical average is ${avg}, so we are trending above average.`);
  }

  if (pace) {
    const d = t.current_count - pace.count_at_same_point;
    parts.push(`At this point last year we were at ${pace.count_at_same_point} and finished at ${pace.final}` +
      (d > 0 ? `, so we are ahead of pace.` : d < 0 ? `, so we are behind.` : `.`));
  }

  if (sorted.length >= 3) {
    const counts = sorted.map(h => h.count);
    const worst = Math.min(...counts);
    const best = Math.max(...counts);
    const worstYr = sorted.find(h => h.count === worst).year;
    const bestYr = sorted.find(h => h.count === best).year;
    if (t.point_estimate < worst) parts.push(`The last time we were this low was ${worstYr} when we got ${worst}.`);
    else if (t.point_estimate > best) parts.push(`If we hit the projection, it would be the best year since at least ${bestYr} (${best}).`);
  }

  if (sorted.length >= 2) {
    const rows = [[2026, t.current_count, t.point_estimate, `${t.ci_lower}-${t.ci_upper}`, '']];
    sorted.forEach(h => rows.push([h.year, '', '', '', h.count]));
    parts.push(emailTable(['YEAR', 'ENTRIES', 'PROJECTION', 'RANGE', 'FINAL'], rows));
  }

  return parts.join('\n');
}

function emailOverallTheme(selected) {
  let ahead = 0, behind = 0;
  selected.forEach(t => {
    const ly = emailLastYear(t);
    if (!ly) return;
    const pct = (t.point_estimate - ly.count) / ly.count;
    if (pct > 0.05) ahead++;
    else if (pct < -0.05) behind++;
  });
  const total = ahead + behind;
  if (total === 0) return 'Things are holding steady across the board.';
  if (behind === 0) return 'The overall theme is improvement across the board.';
  if (ahead === 0) return 'The overall theme is we are still lagging across the board.';
  if (ahead >= behind) return 'The overall theme is a mixed bag \u2014 some improvement, but we are still behind on a few events.';
  return 'The overall theme today is there has been some improvement, but we are still lagging.';
}

// ── Highlights: biggest mover, fastest pace, behind-pace flags ──
function emailComputeHighlights(selected) {
  const h = { biggestUp: null, biggestDown: null, fastestPace: null, behindPace: [] };
  selected.forEach(t => {
    const ly = emailLastYear(t);
    if (ly && ly.count > 0 && t.point_estimate) {
      const pct = (t.point_estimate - ly.count) / ly.count;
      if (!h.biggestUp || pct > h.biggestUp.pct) h.biggestUp = { t, pct };
      if (!h.biggestDown || pct < h.biggestDown.pct) h.biggestDown = { t, pct };
    }
    const pa = getPaceAlert(t);
    if (pa) {
      if (pa.status === 'above_pace' && (!h.fastestPace || pa.deviation_pct > h.fastestPace.pct)) {
        h.fastestPace = { t, pct: pa.deviation_pct };
      }
      if (pa.status === 'below_pace') h.behindPace.push({ t, pct: pa.deviation_pct });
    }
  });
  return h;
}

function emailHighlightBullets(h) {
  const lines = [];
  if (h.biggestUp && h.biggestUp.pct > 0.05) {
    lines.push(`${h.biggestUp.t.family} is the biggest mover, projecting +${Math.round(h.biggestUp.pct * 100)}% vs last year.`);
  }
  if (h.biggestDown && h.biggestDown.pct < -0.05 && (!h.biggestUp || h.biggestDown.t.family !== h.biggestUp.t.family)) {
    lines.push(`${h.biggestDown.t.family} is tracking lowest, projecting ${Math.round(h.biggestDown.pct * 100)}% vs last year.`);
  }
  if (h.fastestPace) {
    lines.push(`${h.fastestPace.t.family} is running ${h.fastestPace.pct > 0 ? '+' : ''}${h.fastestPace.pct}% vs historical pace.`);
  }
  if (h.behindPace.length) {
    const names = h.behindPace.map(x => x.t.family).join(', ');
    lines.push(`Behind pace: ${names}.`);
  }
  return lines;
}

// ── Auto subject line ──
function emailAutoSubject(selected) {
  const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const n = selected.length;
  if (n === 0) return `CCA Entries Update: ${today}`;
  if (n === 1) return `CCA Entries Update: ${selected[0].family} (${today})`;
  return `CCA Entries Update: ${n} events (${today})`;
}

// ── HTML email formatter (email-client-safe: tables + inline styles, no flex/grid) ──
const EM = {
  bg: '#ffffff', text: '#1a1a1a', muted: '#6a6a6a',
  border: '#d9d9d9', accent: '#c99000',
  green: '#2ca444', red: '#c44646', blue: '#1a6fbc',
  surface: '#f9f7f0',
};

function emailHTMLTable(headers, rows) {
  const th = headers.map(h => `<th style="text-align:left;padding:6px 12px;border-bottom:1px solid ${EM.border};text-transform:uppercase;font-size:11px;letter-spacing:.05em;color:${EM.muted};font-weight:700">${esc(String(h))}</th>`).join('');
  const tr = rows.map(r => {
    const tds = r.map(c => `<td style="padding:6px 12px;border-bottom:1px solid ${EM.border};font-size:14px">${c === '' || c == null ? '&nbsp;' : esc(String(c))}</td>`).join('');
    return `<tr>${tds}</tr>`;
  }).join('');
  return `<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:8px 0 14px;font-family:Arial,Helvetica,sans-serif;border:1px solid ${EM.border}"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

function emailHTMLTournament(t, len) {
  const ly = emailLastYear(t);
  const avg = emailHistAvg(t);
  const pace = t.prior_year_pace;
  const sorted = t.historical ? [...t.historical].sort((a, b) => b.year - a.year) : [];
  const parts = [];
  const name = esc(t.family);
  const B = v => `<strong style="color:${EM.text}">${esc(String(v))}</strong>`;
  const colorFor = pct => pct > 0 ? EM.green : pct < 0 ? EM.red : EM.text;

  parts.push(`<h3 style="margin:22px 0 6px;font-size:15px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:${EM.text}">${name}</h3>`);
  parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">We are at ${B(t.current_count)} entries which projects to ${B(t.point_estimate)} with a range of ${B(t.ci_lower)}&ndash;${B(t.ci_upper)}.</p>`);

  if (ly) {
    const pct = Math.round((t.point_estimate - ly.count) / ly.count * 100);
    let verdict;
    if (len === 'short') verdict = '';
    else if (pct > 15) verdict = ', so the projection has us well ahead.';
    else if (pct > 5) verdict = ', so we are tracking ahead.';
    else if (pct > -5) verdict = ', so we are in the same neighborhood.';
    else if (pct > -15) verdict = ', so we are still a bit behind.';
    else verdict = ', so we are lagging.';
    parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">Last year was ${B(ly.count)}${verdict}</p>`);
  }

  if (pace) {
    const d = t.current_count - pace.count_at_same_point;
    const col = d > 0 ? EM.green : d < 0 ? EM.red : EM.text;
    const suffix = d > 0 ? `, so we are <span style="color:${col};font-weight:600">ahead of pace</span>.`
                 : d < 0 ? `, so we are <span style="color:${col};font-weight:600">a bit behind</span>.`
                 : '.';
    parts.push(`<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:${EM.text}">At this point last year we were at ${B(pace.count_at_same_point)} and finished at ${B(pace.final)}${suffix}</p>`);
  }

  if (len === 'long' && avg && sorted.length >= 3) {
    const pct = Math.round((t.point_estimate - avg) / avg * 100);
    if (pct < -10) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The historical average is ${B(avg)}, so we are still below the norm.</p>`);
    else if (pct > 10) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The historical average is ${B(avg)}, so we are trending above average.</p>`);
  }

  if (len === 'long' && sorted.length >= 3) {
    const counts = sorted.map(h => h.count);
    const worst = Math.min(...counts);
    const best = Math.max(...counts);
    const worstYr = sorted.find(h => h.count === worst).year;
    const bestYr = sorted.find(h => h.count === best).year;
    if (t.point_estimate < worst) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">The last time we were this low was ${worstYr} when we got ${B(worst)}.</p>`);
    else if (t.point_estimate > best) parts.push(`<p style="margin:0 0 8px;font-size:14px;color:${EM.text}">If we hit the projection, it would be the best year since at least ${bestYr} (${B(best)}).</p>`);
  }

  if (len !== 'short' && sorted.length >= 2) {
    const hdrs = len === 'long' ? ['Year', 'Entries', 'Projection', 'Range', 'Final'] : ['Year', 'Entries', 'Projection', 'Final'];
    const rows = [];
    if (len === 'long') {
      rows.push([2026, t.current_count, t.point_estimate, `${t.ci_lower}\u2013${t.ci_upper}`, '']);
      sorted.forEach(h => rows.push([h.year, '', '', '', h.count]));
    } else {
      rows.push([2026, t.current_count, t.point_estimate, '']);
      sorted.forEach(h => rows.push([h.year, '', '', h.count]));
    }
    parts.push(emailHTMLTable(hdrs, rows));
  }

  return parts.join('\n');
}

function emailBuildHTML(subject, intro, selected, len, highlights, signoff) {
  const theme = selected.length > 1 ? emailOverallTheme(selected) : '';
  const bullets = emailHighlightBullets(highlights);
  const greeting = intro && intro.trim() ? esc(intro.trim()) : 'Team,';
  const signName = signoff && signoff.trim() ? esc(signoff.trim()) : '';

  const highlightBlock = bullets.length
    ? `<table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;background:${EM.surface};border-left:4px solid ${EM.accent};margin:14px 0;width:100%"><tr><td style="padding:12px 16px;font-family:Arial,Helvetica,sans-serif">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:${EM.muted};font-weight:700;margin-bottom:6px">Highlights</div>
        ${bullets.map(b => `<div style="font-size:14px;line-height:1.5;color:${EM.text};margin:2px 0">&bull; ${esc(b)}</div>`).join('')}
      </td></tr></table>`
    : '';

  const themeBlock = (len !== 'short' && theme)
    ? `<p style="margin:10px 0;font-size:14px;line-height:1.55;color:${EM.text}">${esc(theme)}</p>`
    : '';

  const body = selected.map(t => emailHTMLTournament(t, len)).join('\n');

  return `<div style="font-family:Arial,Helvetica,sans-serif;color:${EM.text};background:${EM.bg};padding:16px 18px;max-width:720px;margin:0 auto">
  <p style="margin:0 0 10px;font-size:14px;color:${EM.text}">${greeting}</p>
  ${highlightBlock}
  ${themeBlock}
  ${body}
  ${signName ? `<p style="margin:20px 0 0;font-size:14px;color:${EM.text}">${signName}</p>` : ''}
</div>`;
}

function generateEmail() {
  const selected = emailGetSelected();
  const out = document.getElementById('emailOutput');
  const pv = document.getElementById('emailPreview');
  const subjField = document.getElementById('emailSubject');
  const introField = document.getElementById('emailIntro');
  const signField = document.getElementById('emailSignoff');
  const signoff = signField && signField.value.trim() ? signField.value.trim() : '';

  if (!selected.length) { out.textContent = 'No tournaments selected.'; if (pv) { pv.srcdoc = ''; } return; }

  // Auto-fill subject placeholder so user sees what it'll default to if empty
  if (subjField) subjField.placeholder = emailAutoSubject(selected);

  const len = emailLength;
  const highlights = emailComputeHighlights(selected);

  if (emailFormat === 'html') {
    const subject = (subjField && subjField.value) || emailAutoSubject(selected);
    const intro = introField ? introField.value : '';
    const html = emailBuildHTML(subject, intro, selected, len, highlights, signoff);
    out.textContent = html;
    if (pv) pv.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(subject)}</title></head><body style="margin:0;background:#f1f1f1">${html}</body></html>`;
  } else {
    // Plain text (original behavior + optional intro + highlight lines)
    const sections = [];
    const intro = introField && introField.value.trim() ? introField.value.trim() : 'Team';
    sections.push(intro + (intro.endsWith(',') ? '' : ''));

    const bullets = emailHighlightBullets(highlights);
    if (bullets.length && len !== 'short') {
      sections.push('HIGHLIGHTS\n' + bullets.map(b => `  \u2022 ${b}`).join('\n'));
    }

    if (len !== 'short' && selected.length > 1) {
      sections.push(emailOverallTheme(selected));
    }
    selected.forEach(t => { sections.push(emailFormatTournament(t, len)); });
    if (signoff) sections.push(signoff);
    out.textContent = sections.join('\n\n');
  }

  const btn = document.getElementById('emailCopyBtn');
  btn.textContent = 'Copy';
  btn.classList.remove('copied');
}

function _emailCopyFeedback(btn, label = 'Copy') {
  const orig = label;
  btn.textContent = 'Copied!';
  btn.classList.add('copied');
  setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
}

function copyEmail() {
  const text = document.getElementById('emailOutput').textContent;
  if (!text) return;
  const btn = document.getElementById('emailCopyBtn');
  navigator.clipboard.writeText(text).then(() => _emailCopyFeedback(btn, 'Copy'));
}

function copyEmailHTML() {
  // Copy the rendered HTML as rich text (text/html) so pasting into Outlook keeps formatting
  const html = document.getElementById('emailOutput').textContent;
  if (!html) return;
  const btn = document.getElementById('emailCopyHtmlBtn');
  const plain = document.getElementById('emailPreview')?.contentDocument?.body?.innerText || html.replace(/<[^>]+>/g, '');
  if (window.ClipboardItem && navigator.clipboard.write) {
    const item = new ClipboardItem({
      'text/html': new Blob([html], { type: 'text/html' }),
      'text/plain': new Blob([plain], { type: 'text/plain' }),
    });
    navigator.clipboard.write([item]).then(() => _emailCopyFeedback(btn, 'Copy HTML'));
  } else {
    navigator.clipboard.writeText(html).then(() => _emailCopyFeedback(btn, 'Copy HTML'));
  }
}
