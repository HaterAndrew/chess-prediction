// chart_text_probe.js — injected before the page's scripts by
// scripts/check_chart_text.py. It records what every canvas draws, in device
// pixels through the current transform, and reports text a reader cannot
// read cleanly:
//   overlap  two labels' boxes overlap;
//   crossed  a line or mark drawn before a label passes through it, and the
//            label has no halo (an opaque box filled under it first);
//   covered  a line, mark or box drawn after a label passes through it;
//   clipped  a label runs off the canvas edge.
// A full-canvas clearRect starts a new frame, so only the last frame counts.
(() => {
  const P = CanvasRenderingContext2D.prototype;
  const S = new WeakMap();
  const state = ctx => {
    let s = S.get(ctx.canvas);
    if (!s) { s = { seq: 0, texts: [], marks: [], fills: [], path: [], clip: null, stack: [] }; S.set(ctx.canvas, s); }
    return s;
  };
  const dev = (ctx, x, y) => { const m = ctx.getTransform(); return [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]; };
  const box = pts => {
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    return { l: Math.min(...xs), t: Math.min(...ys), r: Math.max(...xs), b: Math.max(...ys) };
  };
  const alpha = c => {
    if (typeof c !== 'string') return 1;
    const m = /rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)/.exec(c);
    return m ? parseFloat(m[1]) : 1;
  };

  const oClear = P.clearRect;
  P.clearRect = function (x, y, w, h) {
    if (x <= 0 && y <= 0 && w >= this.canvas.width / 4 && h >= this.canvas.height / 4) {
      S.set(this.canvas, { seq: 0, texts: [], marks: [], fills: [], path: [], clip: null, stack: [] });
    }
    return oClear.apply(this, arguments);
  };
  const oBegin = P.beginPath;
  P.beginPath = function () { state(this).path = []; return oBegin.apply(this, arguments); };
  const oMove = P.moveTo;
  P.moveTo = function (x, y) { state(this).path.push({ k: 'M', p: dev(this, x, y) }); return oMove.apply(this, arguments); };
  const oLine = P.lineTo;
  P.lineTo = function (x, y) { state(this).path.push({ k: 'L', p: dev(this, x, y) }); return oLine.apply(this, arguments); };
  const oBez = P.bezierCurveTo;
  P.bezierCurveTo = function (a, b, c, d, x, y) {
    state(this).path.push({ k: 'B', c1: dev(this, a, b), c2: dev(this, c, d), p: dev(this, x, y) });
    return oBez.apply(this, arguments);
  };
  const oArc = P.arc;
  P.arc = function (x, y, r) {
    state(this).path.push({ k: 'A', box: box([dev(this, x - r, y - r), dev(this, x + r, y + r)]) });
    return oArc.apply(this, arguments);
  };
  const oRect = P.rect;
  P.rect = function (x, y, w, h) {
    state(this).path.push({ k: 'R', box: box([dev(this, x, y), dev(this, x + w, y + h)]) });
    return oRect.apply(this, arguments);
  };

  // Chart.js strokes its dataset lines through a cached Path2D, so a Path2D
  // keeps its own ops in local coordinates; stroke(path) and fill(path) map
  // them through the transform in force when they are drawn.
  const PP = Path2D.prototype;
  ['moveTo', 'lineTo', 'bezierCurveTo', 'arc', 'rect'].forEach(k => {
    const o = PP[k];
    PP[k] = function () { (this.__ops || (this.__ops = [])).push([k, [...arguments]]); return o.apply(this, arguments); };
  });
  function path2dOps(ctx, p2d) {
    return (p2d.__ops || []).map(([k, a]) => {
      if (k === 'moveTo') return { k: 'M', p: dev(ctx, a[0], a[1]) };
      if (k === 'lineTo') return { k: 'L', p: dev(ctx, a[0], a[1]) };
      if (k === 'bezierCurveTo') return { k: 'B', c1: dev(ctx, a[0], a[1]), c2: dev(ctx, a[2], a[3]), p: dev(ctx, a[4], a[5]) };
      if (k === 'arc') return { k: 'A', box: box([dev(ctx, a[0] - a[2], a[1] - a[2]), dev(ctx, a[0] + a[2], a[1] + a[2])]) };
      return { k: 'R', box: box([dev(ctx, a[0], a[1]), dev(ctx, a[0] + a[2], a[1] + a[3])]) };
    });
  }
  const opsFor = (ctx, args) => args[0] instanceof Path2D ? path2dOps(ctx, args[0]) : state(ctx).path;

  // Chart.js clips each dataset to its plot; a mark only counts inside the
  // clip in force when it was drawn (save and restore scope it).
  const meet = (a, b) => !a ? b : !b ? a : { l: Math.max(a.l, b.l), t: Math.max(a.t, b.t), r: Math.min(a.r, b.r), b: Math.min(a.b, b.b) };
  const oSave = P.save;
  P.save = function () { const s = state(this); s.stack.push(s.clip); return oSave.apply(this, arguments); };
  const oRestore = P.restore;
  P.restore = function () { const s = state(this); s.clip = s.stack.length ? s.stack.pop() : null; return oRestore.apply(this, arguments); };
  const oClip = P.clip;
  P.clip = function () {
    const s = state(this);
    opsFor(this, arguments).filter(op => op.k === 'R').forEach(op => { s.clip = meet(s.clip, op.box); });
    return oClip.apply(this, arguments);
  };

  // A path as marks: line segments (a curve by 12 samples) and dot boxes.
  function pathMarks(path) {
    const out = [];
    let cur = null;
    path.forEach(op => {
      if (op.k === 'M') { cur = op.p; return; }
      if (op.k === 'L' && cur) { out.push({ seg: [cur, op.p] }); cur = op.p; return; }
      if (op.k === 'B' && cur) {
        let prev = cur;
        for (let i = 1; i <= 12; i++) {
          const t = i / 12, u = 1 - t;
          const pt = [0, 1].map(j => u * u * u * cur[j] + 3 * u * u * t * op.c1[j] + 3 * u * t * t * op.c2[j] + t * t * t * op.p[j]);
          out.push({ seg: [prev, pt] });
          prev = pt;
        }
        cur = op.p;
        return;
      }
      if (op.k === 'A') out.push({ box: op.box });
      if (op.k === 'R') {
        // a stroked rectangle is its four edges, not its area
        const { l, t, r, b } = op.box;
        [[[l, t], [r, t]], [[r, t], [r, b]], [[r, b], [l, b]], [[l, b], [l, t]]].forEach(seg => out.push({ seg }));
      }
    });
    return out;
  }
  const oStroke = P.stroke;
  P.stroke = function () {
    const s = state(this);
    // A line covers half its width either side of its path.
    const t = this.getTransform(), w = this.lineWidth * Math.hypot(t.a, t.b);
    if (this.globalAlpha > 0.05) pathMarks(opsFor(this, arguments)).forEach(m => s.marks.push(Object.assign(m, { seq: ++s.seq, w, clip: s.clip })));
    return oStroke.apply(this, arguments);
  };
  const oFill = P.fill;
  P.fill = function () {
    const s = state(this);
    opsFor(this, arguments).filter(op => op.k === 'A' || op.k === 'R').forEach(op => {
      if (op.k === 'R') s.fills.push({ box: meet(s.clip, op.box), seq: ++s.seq, opaque: alpha(this.fillStyle) * this.globalAlpha >= 0.8 });
      else s.marks.push({ box: op.box, seq: ++s.seq, clip: s.clip });
    });
    return oFill.apply(this, arguments);
  };
  const oFillRect = P.fillRect;
  P.fillRect = function (x, y, w, h) {
    const s = state(this);
    s.fills.push({ box: meet(s.clip, box([dev(this, x, y), dev(this, x + w, y + h)])), seq: ++s.seq,
                   opaque: alpha(this.fillStyle) * this.globalAlpha >= 0.8 });
    return oFillRect.apply(this, arguments);
  };
  const oText = P.fillText;
  P.fillText = function (text, x, y) {
    const s = state(this);
    const m = this.measureText(text);
    const l = x - m.actualBoundingBoxLeft, r = x + m.actualBoundingBoxRight;
    const t = y - m.actualBoundingBoxAscent, b = y + m.actualBoundingBoxDescent;
    const bx = box([dev(this, l, t), dev(this, r, t), dev(this, l, b), dev(this, r, b)]);
    if (String(text).trim()) s.texts.push({ text: String(text), box: bx, seq: ++s.seq });
    return oText.apply(this, arguments);
  };

  const inter = (a, b, pad) => a.l + pad < b.r && b.l + pad < a.r && a.t + pad < b.b && b.t + pad < a.b;
  // Liang–Barsky: does the segment enter the box's interior?
  function segHits(seg, bx) {
    const [[x0, y0], [x1, y1]] = seg;
    let t0 = 0, t1 = 1;
    const dx = x1 - x0, dy = y1 - y0;
    const edges = [[-dx, x0 - bx.l], [dx, bx.r - x0], [-dy, y0 - bx.t], [dy, bx.b - y0]];
    for (const [p, q] of edges) {
      if (p === 0) { if (q < 0) return false; continue; }
      const r = q / p;
      if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; }
      else { if (r < t0) return false; if (r < t1) t1 = r; }
    }
    return t0 < t1;
  }
  const grow = (b, d) => ({ l: b.l - d, t: b.t - d, r: b.r + d, b: b.b + d });
  function hits(mark, bx) {
    const area = mark.clip ? meet(bx, mark.clip) : bx;
    if (area.l >= area.r || area.t >= area.b) return false;
    return mark.seg ? segHits(mark.seg, grow(area, (mark.w || 0) / 2)) : inter(mark.box, area, 0);
  }

  // Raw records for one canvas, for debugging the probe itself.
  window.__chartTextDump = id => S.get(document.getElementById(id));

  window.__chartTextReport = () => [...document.querySelectorAll('canvas')].map(cv => {
    const s = S.get(cv);
    if (!s || !cv.offsetParent) return null;
    const dpr = window.devicePixelRatio || 1;
    const problems = [];
    s.texts.forEach((a, i) => {
      const inner = a.box;
      s.texts.slice(i + 1).forEach(b => {
        if (inter(a.box, b.box, 1 * dpr)) problems.push(`overlap: "${a.text}" / "${b.text}"`);
      });
      const halo = s.fills.some(f => f.opaque && f.seq < a.seq && f.box.l <= a.box.l + 1 && f.box.r >= a.box.r - 1 &&
                                     f.box.t <= a.box.t + 1 && f.box.b >= a.box.b - 1);
      const before = s.marks.filter(m => m.seq < a.seq && hits(m, inner));
      if (before.length && !halo) problems.push(`crossed: "${a.text}" by ${before.length} earlier mark(s)`);
      const after = s.marks.filter(m => m.seq > a.seq && hits(m, inner)).length +
                    s.fills.filter(f => f.seq > a.seq && inter(f.box, inner, 0)).length;
      if (after) problems.push(`covered: "${a.text}" by ${after} later mark(s)`);
      if (a.box.l < 0 || a.box.t < 0 || a.box.r > cv.width || a.box.b > cv.height) problems.push(`clipped: "${a.text}" runs off the canvas`);
    });
    return { id: cv.id || '(no id)', texts: s.texts.length, problems: [...new Set(problems)] };
  }).filter(Boolean);
})();
