---
name: CCA Entry Predictor
description: The pairing sheet taped to the ballroom wall, with a forecast on it.
colors:
  paper: "#FFFFFF"
  paper-sheet: "#FFFFFF"
  paper-raised: "#F4F4F2"
  paper-hover: "#EDEDEA"
  paper-grid: "#E6E6E6"
  rule: "#111111"
  rule-soft: "#C9C9C9"
  rule-faint: "#E6E6E6"
  ink: "#111111"
  ink-2: "#3D3D3D"
  ink-muted: "#5A5A5A"
  ink-dim: "#767676"
  pen-blue: "#1F4E9C"
  pen-blue-pressed: "#173C7A"
  pen-red: "#C8102E"
  highlighter: "#FFE94D"
  highlighter-ink: "#111111"
  stock-yellow: "#FFF1A8"
  stock-blue: "#DCE8F8"
  stock-pink: "#FBDCE2"
  stock-green: "#D9F0DE"
  stock-grey: "#EDEDEA"
  charcoal: "#151517"
  charcoal-sheet: "#151517"
  charcoal-raised: "#1F1F23"
  charcoal-hover: "#26262A"
  charcoal-grid: "#2E2E32"
  charcoal-rule: "#8F8F8E"
  charcoal-rule-soft: "#4A4A4E"
  charcoal-rule-faint: "#2E2E32"
  charcoal-ink: "#F2F2EF"
  charcoal-ink-2: "#D4D4CF"
  charcoal-ink-muted: "#A7A7A3"
  charcoal-ink-dim: "#8A8A86"
  charcoal-pen-blue: "#8FB4F0"
  charcoal-pen-blue-pressed: "#B3CCF5"
  charcoal-pen-red: "#FF7A8A"
  charcoal-highlighter-ink: "#151517"
  charcoal-stock-yellow: "#3A3418"
  charcoal-stock-blue: "#1C2A44"
  charcoal-stock-pink: "#3A1F27"
  charcoal-stock-green: "#1B3324"
  charcoal-stock-grey: "#26262A"
typography:
  display:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "clamp(28px, 2.6vw, 34px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.01em"
    fontVariation: "wdth 75"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.04em"
    fontVariation: "wdth 85"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.04em"
    fontVariation: "wdth 85"
  figure:
    fontFamily: "Courier Prime, Courier New, monospace"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  hero-figure:
    fontFamily: "Courier Prime, Courier New, monospace"
    fontSize: "clamp(52px, 6vw, 80px)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontFeature: "tnum"
  meta:
    fontFamily: "Courier Prime, Courier New, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  none: "0"
spacing:
  s-1: "4px"
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "20px"
  s-6: "28px"
  s-7: "40px"
  gutter: "12px"
components:
  button-primary:
    backgroundColor: "{colors.pen-blue}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.pen-blue-pressed}"
    textColor: "{colors.paper}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "36px"
  button-outline-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  field:
    backgroundColor: "{colors.paper-sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "6px 10px"
    height: "36px"
  segmented-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "30px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 10px"
    height: "34px"
  nav-item-active:
    backgroundColor: "{colors.highlighter}"
    textColor: "{colors.highlighter-ink}"
  tag:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.title}"
    rounded: "{rounded.none}"
    padding: "3px 7px"
  pill-live:
    backgroundColor: "{colors.stock-blue}"
    textColor: "{colors.pen-blue}"
    typography: "{typography.title}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
  note:
    backgroundColor: "{colors.paper-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "12px 16px"
  note-signal:
    backgroundColor: "{colors.stock-blue}"
    textColor: "{colors.ink}"
  note-amber:
    backgroundColor: "{colors.stock-yellow}"
    textColor: "{colors.ink}"
  note-ember:
    backgroundColor: "{colors.stock-pink}"
    textColor: "{colors.ink}"
  hero-figure:
    backgroundColor: "{colors.highlighter}"
    textColor: "{colors.highlighter-ink}"
    typography: "{typography.hero-figure}"
    rounded: "{rounded.none}"
    padding: "0 0.06em"
  panel:
    backgroundColor: "{colors.paper-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "16px"
  sheet:
    backgroundColor: "{colors.paper-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "20px"
    width: "min(420px, calc(100vw - 32px))"
---

# Design System: CCA Entry Predictor

## Overview

**Creative North Star: "The Wallchart"**

The site is the pairing sheet taped to the ballroom wall: white paper, black rules, figures typed on a Courier ribbon, and two pens. A tournament director reads it the way they read the wallchart between rounds, standing, from a phone in a hotel corridor or at a desk weeks out, to answer one question: is this event filling. Everything on the page is a thing that could be on that sheet. Sections are ruled off, not boxed in shadow. Titles are condensed capitals. Numbers are typed. The only colour that is not a pen is the material's own: each note is printed on its own coloured stock, and the director's highlighter marks the thing you are looking at right now.

The world is Operate, not Persuade. Density is high and even, the grid is visible, and the surface never tries to be admired; the forecast and its range against prior years' pace carry the page. Dark mode is the same sheet in charcoal, not a chalkboard: the pens lift so they still read, the stocks deepen, and the highlighter stays exactly the highlighter with dark type on it. Motion is physical and short: a sheet you can drag shut, a view that follows the finger, everything on one house spring that is critically damped unless a flick preceded it.

**Key Characteristics:**
- Ruled paper: 1px ink rules divide, 2px rules head a section or a table, nothing is rounded, nothing floats except a sheet held over the page.
- Two pens: blue for the actual series and for ahead or good, red for the event line and for behind or a miss. Ink is fair. There is no third pen.
- Coloured stock, not coloured text: yellow, blue, pink, green and grey stocks carry notes and rows; the type on them stays ink.
- One highlighter per view: the active nav item, the selected card, the forecast figure, the current row.
- Typed figures: every number is Courier Prime with tabular figures, so columns of counts line up like a printout.
- Condensed capitals for lettering: Archivo's width axis draws the display at 75% and labels at 85%.

## Colors

Two inks and two pens on paper; every other colour is a sheet of stock or the highlighter.

### Primary
- **Pen Blue** (`{colors.pen-blue}`, charcoal `{colors.charcoal-pen-blue}`): the one accent. The actual entries line, the filled button, focus, links, selection tint, and the state "ahead" or "within range". Pressed or hovered, the darker `{colors.pen-blue-pressed}`. It is used on well under a tenth of any screen.
- **Highlighter** (`{colors.highlighter}` in both modes, type `{colors.highlighter-ink}` on it): the current thing. The active nav item, the selected Up Next card, the forecast figure, the current year's row and bar, the active row in the search dialog. It never marks state and never appears twice for the same reason on one view.

### Secondary
- **Pen Red** (`{colors.pen-red}`, charcoal `{colors.charcoal-pen-red}`): the event line on the chart and the state "behind" or "miss". Text, a 1px box, or a dot; never a fill.

### Neutral
- **Paper** (`{colors.paper}`) and **Charcoal** (`{colors.charcoal}`): the page and every sheet on it. Raised controls sit on `{colors.paper-raised}` (hover `{colors.paper-hover}`); the chart grid on `{colors.paper-grid}`.
- **Ink** (`{colors.ink}` / `{colors.charcoal-ink}`): headings, figures, body. **Ink 2** (`{colors.ink-2}`) for secondary text and nav items at rest; **Muted** (`{colors.ink-muted}`) for labels and captions; **Dim** (`{colors.ink-dim}`, the lightest grey that still clears 4.5:1 on paper) for placeholders, small metadata and the historical chart traces.
- **Rule** (`{colors.rule}` / `{colors.charcoal-rule}`): the black rule between sections, round panels, under the top bar. **Rule Soft** (`{colors.rule-soft}`) between table rows and inside a panel; **Rule Faint** (`{colors.rule-faint}`) for the chart grid.
- **Stocks**: `{colors.stock-yellow}` for on-pace and warnings, `{colors.stock-blue}` for good news and live status, `{colors.stock-pink}` for behind and danger, `{colors.stock-green}` for a puzzle solved, `{colors.stock-grey}` for historical. Each has a charcoal twin (`{colors.charcoal-stock-yellow}` and so on). Type on a stock is ink, or the matching pen when the stock is the pen's own tint (a live pill is pen blue on blue stock).

### Named Rules
**The Two Pens Rule.** Blue means ahead, good, or the actual series. Red means behind, a miss, or the event. Ink means fair. Any other colour on the page is a stock or the highlighter, never a third state colour; green and amber resolve to blue and ink respectively.

**The Stock Rule.** Colour fields are paper stock: a tinted ground with ink on it, one stock per note, no gradient, no border in the stock's colour unless it is the pen's own tint. A stock is never stacked on another stock.

**The One Highlighter Rule.** The highlighter marks exactly the current thing in a view: one nav item, one card, one figure, one row. If two things want it, one of them wants a rule instead.

**The Canvas Rule.** Charts read the same tokens through the palette bridge (`docs/foundation.js` PALETTE): actual in pen blue, projected in ink dashed, the likely range one flat 14% blue tint, history in dim ink, today in ink, early bird in blue, the event in red, this year's bar on the highlighter with an ink rule. No gradients, no glow, square tooltips.

## Typography

**Display Font:** Archivo (variable, weight 100 to 900, width 62 to 125), self-hosted under `docs/fonts/archivo/`, fallback system-ui.
**Body Font:** Archivo.
**Label/Mono Font:** Courier Prime (400 and 700), self-hosted under `docs/fonts/courier-prime/`, fallback Courier New.

**Character:** the sheet's lettering and its printout. Archivo's width axis does the work a second display face would do: the view title is set condensed at 75% width, section heads and labels at 85%, body at normal width. Courier Prime is the typewriter every figure went through, so numbers look typed rather than set.

### Hierarchy
- **Display** (800, `clamp(28px, 2.6vw, 34px)`, line 1, tracking .01em, width 75%, uppercase): the view title (the tournament on the Forecast, the view name elsewhere), one per view, on a rule.
- **Headline** (800, 15px, tracking .04em, width 85%, uppercase): section heads on the 2px rule (Milestones and History, Up Next), sheet titles, the top-bar subject.
- **Title** (700, 11px, tracking .08em, uppercase, muted): panel titles on a soft rule, KPI labels, table heads, field labels, tags.
- **Body** (400, 14px/1.45): prose, notes, table cells at 13px. The Ask and Audit columns are capped at 760px.
- **Label** (700, 13px, tracking .04em, width 85%, uppercase): buttons, nav items, segmented controls.
- **Figure** (Courier Prime 700, 28px, tabular, tracking -.02em): KPI values; 24px on phones and in Performance tiles. **Meta** (Courier Prime 400, 12px): datelines, T-minus, footers, keyboard hints.
- **Hero Figure** (Courier Prime 700, `clamp(52px, 6vw, 80px)`, tabular, tracking -.03em) on the highlighter: the forecast, one per page.

### Named Rules
**The Typed Figure Rule.** Every number that can be compared with another is Courier Prime with tabular figures: KPIs, table cells, deltas, T-minus, the range ends. A number inside running prose stays in Archivo.

**The Capitals Rule.** Headings, labels, buttons and nav are uppercase condensed Archivo with tracking; body and figures are never uppercase. AP Title Case is the source text, so the uppercase is a style, not the copy.

## Layout

One column of ruled sheet, at most 1400px wide, centred, with 28px side padding on desktop and 96px of room at the foot; phones use a 12px gutter. The top bar is sticky at 56px plus the safe-area inset, with a 2px rule under it; the subject (the selected tournament with its status pill and T-minus) sits in a ruled box in the bar and opens the picker. Desktop shows the four-item nav in the bar (Forecast, Season, Model, Tools); under 768px the same four move to a bottom bar of 58px plus the safe-area inset, and under 640px grouped views open a sheet from the foot.

Breakpoints, in order of weight: 640px splits phone from desktop (the compact top bar, sheets from the foot, swipe between views, single-column hero); 768px brings the nav into the top bar and opens two columns (panels side by side, the hero splits forecast from the week); 1024px opens three (the hero becomes forecast, last seven days, and KPIs with soft rules between, panels get 20px by 28px padding) and folds the brand name; 1280px shows the Updated meta. The Forecast stacks as top bar, notes, hero, chart, disclosures (Milestones and History open on desktop, Registration Curve and Fees and About This Model closed), Up Next as a three-card strip that scroll-snaps on phones, See the Full Season, footer.

Spacing is a seven-step scale (4, 8, 12, 16, 20, 28, 40px); panels pad 16px, sections sit 12px apart on a 2px rule, the hero pads 16px vertically. Controls are 36px tall; under a coarse pointer every control, field and segment grows to 44px. Tables are full-rule: a 2px rule under the head, a soft rule between rows, a minimum width of 640px with horizontal scroll and a sticky first column on phones rather than a stack of cards.

## Elevation & Depth

Flat. The sheet is one plane and depth is drawn with rules, not shadows: a 2px rule opens a section, a 1px rule closes a panel, a soft rule separates rows. Hover on a control is a change of stock (`{colors.paper-raised}`), not a lift. The single exception is a sheet held over the page.

### Shadow Vocabulary
- **Elevation** (`box-shadow: 0 8px 24px rgba(17, 17, 17, .14)`; charcoal `0 8px 24px rgba(0, 0, 0, .5)`): the picker, the group sheets, the search dialog and the back-to-top control, which are held above the wallchart. Nothing else casts one.
- **Scrim** (`color-mix(in srgb, ink 45%, transparent)`; charcoal `rgba(0, 0, 0, .6)`): under a sheet on phones and under the search dialog; a desktop popover keeps its scrim clear and only catches the click outside.

### Named Rules
**The Ruled Sheet Rule.** Depth is a rule. If a surface seems to need a shadow to separate it from the page, it needs a rule or a stock instead; only something physically lifted off the wall (a sheet) gets the elevation shadow.

## Shapes

Square. Every radius token is 0: panels, buttons, fields, pills, tags, sheets, chart bars and chart tooltips all have sharp corners, because the sheet is cut, not moulded. The only circles are things that are circles on a wallchart: the live dot (7px, pulsing), the milestone nodes, the compare series dots and the points on a line. Borders are 1px in the rule colour; the section head, the table head and the top bar carry 2px; a puzzle board carries a 2px ink border. Empty states are a 1px dashed rule. Disabled controls drop to 45% opacity rather than changing colour. Focus is a 2px outline in pen blue, offset 2px, and a field in focus doubles its rule to the pen with an inset 1px ring.

## Components

### Buttons
- **Shape:** square (0), 36px tall, 14px side padding, label typography.
- **Primary** (`.button`): pen blue fill, paper type, 1px pen-blue border; hover to the pressed blue. One per view at most, for the action the view is for (Add to Compare, Send, Copy).
- **Outline** (`.btn`, `button.secondary`): transparent, 1px ink rule, ink type; hover inverts to ink fill with paper type. Everything else.
- **Link** (`button.link`): inherits the text, underlined with a 3px offset, pen blue on hover.
- **Icon** (`.icon-button`): 36px square, no rule at rest, raised stock on hover; the theme toggle and dismissals.
- **Disabled:** 45% opacity, not-allowed cursor.

### Segmented Control
- **Style:** one ruled box; segments 30px tall, 12px padding, separated by 1px rules, ink 2 type; hover to the raised stock.
- **State:** the chosen segment is inked (ink fill, paper type). Used for the picker's status filters, the chart range (All, 90d, 30d) and the Performance year.

### Tags and Pills
- **Tag:** 1px rule, title typography, muted; `tag-signal` and `tag-ember` switch rule and type to the pen; `tag-ink` inks the type. Confidence, interim, adjusted.
- **Pill:** the status pill. Upcoming and live sit pen blue on blue stock with the pulsing dot; complete keeps a soft rule and muted type; historical sits muted on grey stock.

### Notes
- **Style:** a message in the flow, 1px rule, 12px by 16px padding, body type; the title in condensed capitals, the detail in ink 2.
- **Stock:** `note-signal` on blue stock (first run, good news), `note-amber` on yellow stock (on pace, stale data, warnings), `note-ember` on pink stock (tracking behind, errors). The pace note carries its delta as a figure in the pen.

### Panels and Sections
- **Panel:** 1px rule, 16px padding (20px by 28px from 1024px); a muted title in capitals on a soft rule. Cards are panels.
- **Section** (`details.sect`): a 2px rule with the name in condensed capitals and a caret; open by default on desktop where the plan says so (`data-open="wide"`), closed on phones; print opens all.
- **Tables:** full rules, muted capital heads, typed figures right-aligned, deltas in the pens, the current year's row on the highlighter.

### Fields
- **Style:** a ruled box on the sheet: 1px rule, sheet background, 14px Archivo, 36px tall, 6px by 10px padding; placeholders dim; the select draws its own caret from two 5px gradients.
- **Focus:** the rule turns pen blue and doubles with an inset 1px ring; no glow.
- **Phone:** 16px type so iOS does not zoom; 44px tall under a coarse pointer.

### Navigation
- **Top bar:** sheet background, 2px rule beneath, the mark and name at the left in condensed capitals, the subject box in the middle, Search (Ctrl K) and the theme toggle at the right.
- **Nav item:** 34px tall, label typography, ink 2 at rest, raised stock on hover, the highlighter with dark type when active. The group items (Model, Tools) show the highlighter while any grouped view is open.
- **Phone bar (under 768px):** the same four items with 20px icons over 11px names, fixed at the foot on a 2px rule; Model and Tools open a sheet listing their views as ruled rows, the open one on the highlighter.

### Sheets and Popovers
- **Sheet:** a ruled sheet with the elevation shadow, 20px padding, 420px wide at most on desktop and centred; from 640px a group or picker sheet anchors under its control as a popover with a clear scrim; under 640px it rises from the foot with a handle and a dark scrim.
- **Motion:** in with `sheetIn` over 250ms on the house ease (`cubic-bezier(.2, 0, 0, 1)`), out over 150ms the way it came; on phones a drag follows the finger, thins the scrim, and on release leaves at the finger's speed past a third of its height or springs back on the house spring (damping 1.0 to move, 0.8 to settle after a flick). Views swipe the same way, resisting at the ends. Reduced motion jumps to the end and drops the fades.

### Charts
- **Style:** Chart.js on the sheet: grid in the faint rule, ticks in muted Archivo 11px, tooltips square on the sheet colour with a rule.
- **Series:** actual in pen blue with a flat 8% tint under it, projected in ink dashed (6, 4), the likely range one flat 14% blue tint edged in a 30% blue hairline, historical traces in dim ink dashed and fading by age; the endpoint an ink dot with the figure beside it. History bars are flat dim ink at 35%, this year on the highlighter with an ink rule. Performance dots are blue within the range and red outside; the lead-time line is ink with a blue wash under the 10% target.

### The Hero Cell
The forecast is a wallchart cell: the label in muted capitals, the figure typed at up to 80px on the highlighter (padded .06em so the stroke sits inside the mark), the range as a bracket line with its ends typed, then the confidence tags. Beside it the last seven days as ruled bars in the pen, then Registered, Days to Event and 7-Day Pace as typed figures with their progress folded under them. A finished event drops the highlighter and sets the final count in ink.

## Do's and Don'ts

### Do:
- **Do** divide with rules: 1px in the rule colour between things, 2px to open a section or head a table.
- **Do** put every comparable number in Courier Prime with tabular figures.
- **Do** set headings, labels, buttons and nav in uppercase condensed Archivo with tracking, and leave body and figures in normal width.
- **Do** print a note on the stock its state calls for, with ink type on it, one stock per note.
- **Do** mark exactly one current thing per view with the highlighter.
- **Do** keep charts on the pens: blue actual, ink projected, flat tints, dim history, square tooltips.
- **Do** keep every control at 36px and grow it to 44px under a coarse pointer.
- **Do** run every colour through `docs/styles/tokens.css`; the colour-literal ceiling outside that file is zero and the suite enforces it.
- **Do** keep a cue that survives forced colours: every highlighter or ink fill that marks the current thing also carries an outline under `forced-colors: active`.
- **Do** reserve the height of what the data will fill (the hero, the pace note) so nothing below moves when the figures land.

### Don't:
- **Don't** introduce a third pen. Green, amber, purple and gold resolve to blue, ink or a stock; there is no state colour beyond blue and red.
- **Don't** round a corner. Radius is 0 everywhere; only dots and nodes are circles.
- **Don't** cast a shadow on anything that is not a sheet held over the page, and never use a glow, a colour gradient, or a coloured left border thicker than 1px. A hard-stop gradient that draws a caret or a dash rhythm is a pattern, not shading, and carries a comment saying so.
- **Don't** put coloured type on a stock that is not its own tint, and never stack one stock on another.
- **Don't** draw an icon with a glyph or an emoji; icons are inline SVG from `docs/icons.js`, and chess pieces are content.
- **Don't** add an eyebrow above the view title, a status banner, a version line or a "coming soon" label; the dateline sits under the title in meta type.
- **Don't** replace a phone table with a stack of cards; scroll it sideways with the first column held.
- **Don't** animate anything gesture-driven with a CSS transition; use the house spring in `docs/motion.js` and let reduced motion jump to the end.
