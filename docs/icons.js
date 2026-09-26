// icons.js — the stroke icons that JS-generated markup needs, as inline SVG.
//
// The shell's own icons (the nav, the top bar, the brand mark) are written
// straight into index.html; this map serves the markup the scripts build at
// runtime (the picker lists, the toast, the sheet rows), so a glyph never
// comes from an emoji or dingbat entity again. Paths are Lucide's
// (lucide.dev, ISC licence), 24 x 24, drawn with a 2 px round stroke.

const ICONS = {
  'search': '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  'chevron-up': '<path d="m18 15-6-6-6 6"/>',
  'chevron-right': '<path d="m9 18 6-6-6-6"/>',
  'chevrons-left': '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
  'arrow-up': '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
  'x': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  'more': '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  'check': '<path d="M20 6 9 17l-5-5"/>',
  'star': '<path d="M11.5 2.6a.6.6 0 0 1 1 0l2.6 5.4 5.9.9a.6.6 0 0 1 .3 1l-4.3 4.2 1 5.9a.6.6 0 0 1-.9.6L12 17.8l-5.3 2.8a.6.6 0 0 1-.9-.6l1-5.9L2.6 9.9a.6.6 0 0 1 .3-1l5.9-.9z"/>',
  'scale': '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
  'trending-up': '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
  'trending-down': '<path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/>',
  'minus': '<path d="M5 12h14"/>',
  'alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  'crown': '<path d="M11.56 3.27a.5.5 0 0 1 .88 0l2.6 4.72 4.2-3.02a.5.5 0 0 1 .78.53L18 17H6L3.98 5.5a.5.5 0 0 1 .78-.53l4.2 3.02z"/><path d="M5 21h14"/>',
};

// An inline SVG for `name`, sized in CSS pixels, carrying `cls` on the
// element. Decorative by default (aria-hidden); pass a label to expose it.
function icon(name, size, cls, label) {
  const body = ICONS[name];
  if (!body) return '';
  const px = size || 16;
  const a11y = label ? ` role="img" aria-label="${label}"` : ' aria-hidden="true"';
  return `<svg class="icon${cls ? ' ' + cls : ''}" width="${px}" height="${px}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${a11y}>${body}</svg>`;
}
