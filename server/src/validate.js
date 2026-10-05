// A submitted run, as the server stores it. The app (client/acr_daily/judge.py) applies the stage rules;
// the server does not re-check runs (its anti-cheat checks DNF'd and flagged real runs, so they were removed).

export const PENALTY_MS = 60000;
const CHECKPOINT_EVERY_M = 100;

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

  // No checks on finished runs: the app's own result counts as sent (clock + penalty per reset).
  // The trace is kept only for display (splits, maps, the run viewer), without the samples that can't be drawn.
  const trace = (Array.isArray(sub.trace) ? sub.trace : [])
    .filter((s) => Array.isArray(s) && s.length >= 4 && s.slice(0, 4).every(num));
  return { ok: true, status: 'finished', reason: '', clockMs, resets, totalMs: clockMs + resets * penaltyMs, flags, trace };
}
