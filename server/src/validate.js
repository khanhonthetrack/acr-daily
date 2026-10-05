// Server-side checks of a submitted run. Same rules as the app (client/acr_daily/judge.py), re-run on the
// uploaded trace, so a modified app cannot just send a made-up time.

import { judgeRealism } from './realism.js';

export const PENALTY_MS = 60000;
const CHECKPOINT_EVERY_M = 100;
const CHECKPOINT_RADIUS_M = 45;
const MIN_CHECKPOINTS = 0.9;
const START_NEAR_M = 60;
const END_NEAR_M = 120;
const MAX_SAMPLE_GAP_MS = 3000;
const MAX_KMH = 300;

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

export function routeInfo(points) {
  const cum = [0];
  for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + dist(points[i - 1], points[i]));
  const length = cum[cum.length - 1] || 0;
  const checkpoints = [];
  let next = CHECKPOINT_EVERY_M;
  for (let i = 0; i < cum.length; i++) {
    if (cum[i] >= next && length - cum[i] > CHECKPOINT_EVERY_M / 2) {
      checkpoints.push(points[i]);
      next = cum[i] + CHECKPOINT_EVERY_M;
    }
  }
  return { points, length, checkpoints };
}

// same as the app: a jump no car could drive
export function teleported(d, dtS, kmh) {
  return d > 15 + (kmh / 3.6) * Math.max(dtS, 0) * 1.5;
}

const num = (v) => typeof v === 'number' && Number.isFinite(v);

/**
 * sub: the app's result ({status, clockMs, resets, totalMs, trace, ...}); route: routeInfo(...).
 * Returns {ok, status, reason, clockMs, resets, totalMs, flags}. ok=false means "refuse the upload".
 */
export function validateRun(sub, route, penaltyMs = PENALTY_MS) {
  const flags = [];
  const fail = (reason) => ({ ok: false, reason });
  if (!sub || typeof sub !== 'object') return fail('empty run');
  const status = sub.status;
  if (!['finished', 'dnf', 'invalid'].includes(status)) return fail('bad status');
  const resets = sub.resets | 0;
  const clockMs = sub.clockMs | 0;
  if (resets < 0 || resets > 99 || clockMs < 0 || clockMs > 4 * 3600 * 1000) return fail('bad numbers');
  if (status !== 'finished') {
    // DNFs and invalid runs only count as attempts
    return { ok: true, status, reason: String(sub.reason || '').slice(0, 200), clockMs, resets, totalMs: null, flags };
  }

  const tr = sub.trace;
  if (!Array.isArray(tr) || tr.length < 10) return fail('trace missing');
  for (const s of tr) {
    if (!Array.isArray(s) || s.length < 12 || !s.slice(0, 12).every(num)) return fail('trace malformed (update the app)');
  }
  let jumps = 0;
  for (let i = 1; i < tr.length; i++) {
    const a = tr[i - 1], b = tr[i];
    const dt = b[0] - a[0];
    if (dt < 0) return fail('clock went backwards');
    if (dt > MAX_SAMPLE_GAP_MS) return fail('gap in the trace');
    if (b[3] > MAX_KMH) return fail('impossible speed');
    const d = dist([a[1], a[2]], [b[1], b[2]]);
    if (teleported(d, dt / 1000, Math.max(a[3], b[3]) + 10)) jumps++;
  }
  if (tr[0][0] > 3000) return fail('trace does not start at the start');
  if (Math.abs(tr[tr.length - 1][0] - clockMs) > 50) return fail('trace does not match the time');
  if (jumps > resets) return fail('resets in the trace that were not counted');
  const lastResets = tr[tr.length - 1].length > 4 ? tr[tr.length - 1][4] | 0 : resets;
  if (lastResets !== resets) return fail('reset count does not match the trace');

  const first = [tr[0][1], tr[0][2]], last = [tr[tr.length - 1][1], tr[tr.length - 1][2]];
  if (dist(first, route.points[0]) > START_NEAR_M) return fail('did not start at the stage start');
  if (dist(last, route.points[route.points.length - 1]) > END_NEAR_M) return fail('did not reach the finish');

  let hit = 0;
  for (const c of route.checkpoints) {
    if (tr.some((s) => (s[1] - c[0]) ** 2 + (s[2] - c[1]) ** 2 <= CHECKPOINT_RADIUS_M ** 2)) hit++;
  }
  const need = Math.ceil(route.checkpoints.length * MIN_CHECKPOINTS);
  if (hit < need) return fail(`missed part of the stage (${hit} of ${route.checkpoints.length} checkpoints)`);

  // the stage cannot be done faster than at an average of 200 km/h
  if (clockMs < (route.length / (200 / 3.6)) * 1000) return fail('impossibly fast');
  const avgKmh = route.length / 1000 / (clockMs / 3600000);
  if (avgKmh > 140) flags.push(`average ${avgKmh.toFixed(0)} km/h`);
  if (jumps < resets) flags.push(`${resets - jumps} reset(s) not visible in the trace`);

  const totalMs = clockMs + resets * penaltyMs;
  if (num(sub.totalMs) && Math.abs(sub.totalMs - totalMs) > 5) return fail('total does not add up');

  // does it look like a real car in the real game? (timing, physics, inputs)
  const real = judgeRealism(tr);
  if (real.fail) return fail(real.fail);
  flags.push(...real.flags);
  return { ok: true, status: 'finished', reason: '', clockMs, resets, totalMs, flags, checks: real.m };
}
