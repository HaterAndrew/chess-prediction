// Node driver for docs/motion.js — exercised by tests/test_motion_js.py.
// Runs the pure motion maths (springs, projection, rubber-banding, the
// velocity tracker) and prints one JSON blob; the pytest side asserts on it.
const path = require('path');
const M = require(path.join(__dirname, '..', '..', 'docs', 'motion.js'));

function run(spring, seconds, dt) {
  const trace = [];
  const step = dt || 1 / 60;
  for (let t = 0; t < seconds; t += step) trace.push(spring.step(step));
  return trace;
}

const out = {};

// A critically damped spring settles at its target without crossing it.
{
  const s = new M.Spring({ from: 0, to: 100, response: 0.4, damping: 1 });
  const trace = run(s, 2);
  out.critical = { final: s.value, done: s.done, max: Math.max(...trace), settledAt: trace.findIndex(v => Math.abs(v - 100) < 0.5) / 60 };
}

// An underdamped spring overshoots, then settles.
{
  const s = new M.Spring({ from: 0, to: 100, response: 0.3, damping: 0.6 });
  const trace = run(s, 2);
  out.bouncy = { final: s.value, done: s.done, max: Math.max(...trace) };
}

// Re-aiming mid-flight continues from the live value: no jump between the
// last frame before and the first frame after the retarget.
{
  const s = new M.Spring({ from: 0, to: 100, response: 0.4, damping: 1 });
  const before = run(s, 0.15);
  const last = before[before.length - 1];
  s.retarget(0);
  const first = s.step(1 / 60);
  const after = run(s, 2);
  out.retarget = { last, first, jump: Math.abs(first - last), final: s.value, done: s.done };
}

// A long frame is sub-stepped: the value after one 100 ms step equals the
// value after the same time in short steps, and nothing explodes.
{
  const a = new M.Spring({ from: 0, to: 100, response: 0.3, damping: 1 });
  const b = new M.Spring({ from: 0, to: 100, response: 0.3, damping: 1 });
  a.step(0.05); a.step(0.05);
  for (let i = 0; i < 12; i++) b.step(0.1 / 12);
  out.substep = { longFrames: a.value, shortFrames: b.value, diff: Math.abs(a.value - b.value) };
}

// Momentum projection: the exponential-decay form, not v^2/2a.
out.project = {
  atRate998: M.projectMomentum(1000, 0.998),
  atRate99: M.projectMomentum(1000, 0.99),
  negative: M.projectMomentum(-500),
  zero: M.projectMomentum(0),
  defaultRate: M.MOTION.decelerationRate,
};

// Rubber-banding: monotonic, bounded by dimension times the constant, and
// symmetric in sign.
{
  const dim = 400;
  const samples = [0, 20, 50, 100, 200, 400, 800, 1600, 5000].map(x => M.rubberBand(x, dim, 0.55));
  const monotonic = samples.every((v, i) => i === 0 || v > samples[i - 1]);
  out.rubber = { samples, monotonic, mirror: M.rubberBand(-100, dim, 0.55), small: M.rubberBand(1, dim, 0.55) };
}

// The nearest resting point to where the momentum lands.
out.snap = { a: M.nearestSnap(140, [0, 300, 600]), b: M.nearestSnap(170, [0, 300, 600]), c: M.nearestSnap(-50, [0, 300]) };

// The velocity tracker: speed over the last hundred milliseconds, zero after
// a pause, zero with one sample.
{
  const v = new M.VelocityTracker();
  v.push(0, 0); v.push(10, 16); v.push(20, 32); v.push(30, 48);
  const moving = v.velocity();
  v.push(30, 200); v.push(30, 216);
  const paused = v.velocity();
  const single = new M.VelocityTracker();
  single.push(5, 0);
  out.tracker = { moving, paused, single: single.velocity() };
}

// The physics pair from the designer pair.
out.params = M.springParams(0.4, 1);

console.log(JSON.stringify(out));
