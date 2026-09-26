// motion.js — the house motion. A sheet of paper does not bounce: every
// animation is a critically damped spring by default, with a little bounce
// only after a flick, and every animation starts from where the thing is
// now and can be re-aimed mid-flight. The maths is pure (springs by damping
// ratio and response, momentum projection, rubber-banding) and exported for
// node; the driver at the end runs a spring on requestAnimationFrame and
// jumps straight to the target under prefers-reduced-motion.

// The two designer parameters (damping ratio and response, in seconds) and
// the house values for the interactions that use them.
const MOTION = {
  move: { response: 0.4, damping: 1 },     // a reposition: no overshoot
  settle: { response: 0.3, damping: 1 },   // a spring back to rest
  throw: { response: 0.3, damping: 0.8 },  // something flicked away
  decelerationRate: 0.998,                 // the scroll-view feel
  epsilon: 0.05,                           // px and px/s: close enough to rest
};

// Damping ratio and response to the physics pair, for unit mass.
function springParams(response, dampingRatio) {
  const omega = (2 * Math.PI) / Math.max(response, 0.001);
  return { stiffness: omega * omega, damping: 2 * dampingRatio * omega };
}

// A one-dimensional spring, stepped in fixed sub-steps so a long frame
// cannot blow it up. retarget() keeps the current value and velocity, which
// is what makes an interrupted animation continue instead of jumping.
class Spring {
  constructor(opts) {
    const o = opts || {};
    this.value = o.from || 0;
    this.target = o.to || 0;
    this.velocity = o.velocity || 0;
    const p = springParams(o.response || MOTION.move.response,
      o.damping == null ? MOTION.move.damping : o.damping);
    this.stiffness = p.stiffness;
    this.damping = p.damping;
    this.epsilon = o.epsilon || MOTION.epsilon;
  }

  retarget(to, velocity) {
    this.target = to;
    if (velocity != null) this.velocity += velocity;
  }

  // Advance by dt seconds; returns the new value.
  step(dt) {
    let remaining = Math.min(Math.max(dt, 0), 1 / 15);
    const h = 1 / 240;
    while (remaining > 0) {
      const d = Math.min(h, remaining);
      const accel = -this.stiffness * (this.value - this.target) - this.damping * this.velocity;
      this.velocity += accel * d;
      this.value += this.velocity * d;
      remaining -= d;
    }
    if (this.done) { this.value = this.target; this.velocity = 0; }
    return this.value;
  }

  get done() {
    return Math.abs(this.velocity) < this.epsilon && Math.abs(this.value - this.target) < this.epsilon;
  }
}

// Where a flick would come to rest on its own (the scroll view's own
// deceleration curve). velocity in px/s; the answer is a distance in px.
function projectMomentum(velocity, decelerationRate) {
  const rate = decelerationRate || MOTION.decelerationRate;
  return (velocity / 1000) * rate / (1 - rate);
}

// Past an edge the thing follows the finger less and less: the further past
// the bound, the more it resists, and it never travels more than the
// dimension times the constant.
function rubberBand(overshoot, dimension, constant) {
  const c = constant == null ? 0.55 : constant;
  const sign = overshoot < 0 ? -1 : 1;
  const x = Math.abs(overshoot);
  return sign * (x * dimension * c) / (dimension + c * x);
}

// The nearest of several resting points to where the momentum lands.
function nearestSnap(projected, points) {
  let best = points[0];
  for (const p of points) if (Math.abs(p - projected) < Math.abs(best - projected)) best = p;
  return best;
}

// A short position history gives the release velocity: the finger's speed
// over the last hundred milliseconds, not the last two events.
class VelocityTracker {
  constructor() { this.samples = []; }
  reset() { this.samples.length = 0; }
  push(value, time) {
    this.samples.push({ value, time });
    while (this.samples.length && time - this.samples[0].time > 100) this.samples.shift();
    if (this.samples.length > 12) this.samples.shift();
  }
  // px/s over the window; 0 when the finger paused before release.
  velocity() {
    const s = this.samples;
    if (s.length < 2) return 0;
    const a = s[0], b = s[s.length - 1];
    const dt = b.time - a.time;
    if (dt < 8) return 0;
    return (b.value - a.value) / dt * 1000;
  }
}

function motionReduced() {
  return typeof window !== 'undefined' && !!window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// Run a spring on the frame clock. Returns a handle: retarget(to, velocity)
// re-aims it from the live value, cancel() stops it where it is, value is
// the current position. Under reduced motion the target is set at once.
function animateSpring(opts) {
  const spring = new Spring(opts);
  const onUpdate = opts.onUpdate || function () {};
  const onDone = opts.onDone || function () {};
  const handle = { spring, active: true, get value() { return spring.value; } };
  if (motionReduced() || typeof requestAnimationFrame === 'undefined') {
    spring.value = spring.target;
    handle.active = false;
    onUpdate(spring.value);
    onDone();
    handle.retarget = function () {};
    handle.cancel = function () {};
    return handle;
  }
  let last = null;
  let frame = 0;
  function tick(now) {
    if (!handle.active) return;
    const dt = last == null ? 1 / 60 : (now - last) / 1000;
    last = now;
    onUpdate(spring.step(dt));
    if (spring.done) { handle.active = false; onDone(); return; }
    frame = requestAnimationFrame(tick);
  }
  handle.retarget = function (to, velocity) {
    spring.retarget(to, velocity);
    if (!handle.active) { handle.active = true; last = null; frame = requestAnimationFrame(tick); }
  };
  handle.cancel = function () {
    handle.active = false;
    if (frame) cancelAnimationFrame(frame);
  };
  frame = requestAnimationFrame(tick);
  return handle;
}

// ── node export tail: tests/js/motion_driver.js requires the pure parts ──
if (typeof module !== 'undefined') {
  module.exports = { MOTION, springParams, Spring, projectMomentum, rubberBand, nearestSnap, VelocityTracker };
}
