// tab_email.js — email generator tab, split verbatim from app.js (C4): the
// picks, the length and format, Generate and Copy. The text and the HTML
// are composed in email_compose.js. The output pane and the Copy buttons
// stay hidden until the first Generate.

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
  // Nothing to copy or switch between before the first Generate.
  const ready = !!split && !split.hidden;
  const tab = (split && split.dataset.tab) || 'source';
  const isMobile = window.matchMedia('(max-width: 639px)').matches;
  // Two columns only when the source and the preview both show (email.css).
  if (split) split.classList.toggle('email-split-both', emailFormat === 'html' && !isMobile);

  if (emailFormat === 'html') {
    out.classList.add('mode-html');
    if (copyHtmlBtn) copyHtmlBtn.style.display = ready ? '' : 'none';
    if (isMobile) {
      if (tabs) tabs.style.display = ready ? '' : 'none';
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

function generateEmail() {
  const selected = emailGetSelected();
  const out = document.getElementById('emailOutput');
  const pv = document.getElementById('emailPreview');
  const subjField = document.getElementById('emailSubject');
  const introField = document.getElementById('emailIntro');
  const signField = document.getElementById('emailSignoff');
  const signoff = signField && signField.value.trim() ? signField.value.trim() : '';
  document.getElementById('emailSplit').hidden = false;
  document.getElementById('emailCopyBtn').hidden = false;
  applyEmailViewState();

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
