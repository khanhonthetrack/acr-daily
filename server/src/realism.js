// "Does this look like a real car driven in the real game?" Checks on a run's trace.
// Trace sample: [clockMs, x, z, kmh, resets, wallMs, physicsPackets, throttle, brake, steer, gear, rpm]
//
// Limits were set from real runs (Wales/Mini with a crash and a reset, Obersteigen/208 clean):
//   stage clock vs PC clock      1.000 (+-0.2 %)          physics packets  333 per second
//   reported vs measured speed   median error 0.4-0.5 %
//   acceleration p99 0.4-0.5 g,  braking p99 ~1 g (crashes peak higher),  cornering p95 0.6-1.1 g
// Hard limits ("fail") sit far outside anything a real run produces; "flag" marks runs for a human to look at.
// validate.js turns a "fail" into a flag too: no realism check can DNF a run on its own.

export const LIMITS = {
  clockRate: { fail: [0.97, 1.03] },          // stage clock per real second
  packetRate: { fail: [316, 350], flag: [326, 340] },   // steps per second of stage clock: fixed by the game
  speedError: { flag: 0.03, fail: 0.08 },      // median |measured - reported| / reported
  accel: { flag: 0.8, fail: 1.3 },             // g, 99th percentile
  braking: { flag: 1.8, fail: 2.6 },           // g, 99th percentile
  lateral: { flag: 1.7, fail: 2.4 },           // g, 95th percentile
  noThrottleAccel: { flag: 0.35 },             // share of strong accelerations with no throttle
  rpmSpeed: { flag: 0.4 },                     // correlation of rpm with speed within a gear (real: 0.66 gravel, 0.91 tarmac)
};

const G = 9.81;
const dist = (a, b) => Math.hypot(a[1] - b[1], a[2] - b[2]);
const pct = (xs, p) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(s.length * p))];
};
const median = (xs) => pct(xs, 0.5);
const round = (v, d = 3) => (v == null ? null : Math.round(v * 10 ** d) / 10 ** d);

/** Indices of samples within `ms` of a reset jump (crash + teleport moments are not normal driving). */
function nearResets(tr, ms = 3000) {
  const bad = new Set();
  for (let i = 1; i < tr.length; i++) {
    if ((tr[i][4] | 0) !== (tr[i - 1][4] | 0) || dist(tr[i - 1], tr[i]) > 15 + (Math.max(tr[i - 1][3], tr[i][3]) / 3.6) * ((tr[i][0] - tr[i - 1][0]) / 1000) * 1.5) {
      for (let j = 0; j < tr.length; j++) if (Math.abs(tr[j][0] - tr[i][0]) <= ms) bad.add(j);
    }
  }
  return bad;
}

/** All measurements, no verdicts. */
export function measure(tr) {
  const m = {};
  const full = tr.every((s) => s.length >= 12);
  m.hasInputs = full;

  // ---- 1. timing: stage clock vs PC clock vs game physics steps (pauses left out)
  if (full) {
    let dc = 0, dw = 0, dp = 0, fastSeg = 0;
    const windows = [];
    let win = [0, 0];
    for (let i = 1; i < tr.length; i++) {
      const c = tr[i][0] - tr[i - 1][0], w = tr[i][5] - tr[i - 1][5], p = tr[i][6] - tr[i - 1][6];
      if (c <= 0 || w <= 0) continue;
      if (w > c + 1000) continue;                 // paused (time passed, clock didn't)
      if (c > w * 1.2 + 200) fastSeg++;           // clock ran ahead of real time
      dc += c; dw += w; dp += p;
      win[0] += c; win[1] += p;
      if (win[0] >= 5000) { windows.push(win[1] / win[0] * 1000); win = [0, 0]; }
    }
    m.clockRate = dw ? dc / dw : null;
    m.packetRate = dc ? (dp / dc) * 1000 : null;
    m.clockAheadSegments = fastSeg;
    const pr = median(windows);
    m.packetRateSpread = windows.length ? Math.max(...windows.map((w) => Math.abs(w - pr) / pr)) : null;
  }

  // ---- 2. physics
  const skip = nearResets(tr);
  const speedErr = [], acc = [], brk = [], lat = [], accNoThrottle = [];
  const ratios = {};
  for (let i = 2; i + 2 < tr.length; i++) {
    if (skip.has(i)) continue;
    const a = tr[i - 2], b = tr[i], c = tr[i + 2];
    const dt = (c[0] - a[0]) / 1000;
    if (dt < 0.3 || dt > 2) continue;
    const v = b[3] / 3.6;
    // reported speed vs how far the car really moved
    const moved = dist(a, b) + dist(b, c);
    const vAvg = (a[3] + b[3] + c[3]) / 3 / 3.6;
    if (vAvg > 6) speedErr.push(Math.abs(moved / dt - vAvg) / vAvg);
    // longitudinal: from the speed readings
    const g = (c[3] - a[3]) / 3.6 / dt / G;
    if (g >= 0) acc.push(g); else brk.push(-g);
    if (full && g > 0.15) accNoThrottle.push(((a[7] + b[7] + c[7]) / 3) < 0.1 ? 1 : 0);
    // lateral: speed x turn rate (heading from positions)
    if (v > 8) {
      const h1 = Math.atan2(b[2] - a[2], b[1] - a[1]), h2 = Math.atan2(c[2] - b[2], c[1] - b[1]);
      const dh = ((h2 - h1 + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
      lat.push(Math.abs((v * dh) / (dt / 2)) / G);
    }
    // engine: speed per rpm is fixed within a gear (when driving, not slipping the clutch)
    if (full && b[11] > 1500 && b[3] > 25 && b[7] > 0.3) (ratios[b[10]] = ratios[b[10]] || []).push([b[3], b[11]]);
  }
  m.speedError = median(speedErr);
  m.accel = pct(acc, 0.99);
  m.braking = pct(brk, 0.99);
  m.lateral = pct(lat, 0.95);

  // ---- 3. inputs
  if (full) {
    m.noThrottleAccel = accNoThrottle.length >= 10 ? accNoThrottle.reduce((x, y) => x + y, 0) / accNoThrottle.length : null;
    // within a gear rpm must rise with speed (wheelspin on gravel blurs it, but never breaks the link)
    const corr = Object.values(ratios).filter((r) => r.length >= 12).map((pairs) => {
      const xs = pairs.map((p) => p[0]), ys = pairs.map((p) => p[1]);
      const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length;
      let sxy = 0, sxx = 0, syy = 0;
      for (let k = 0; k < xs.length; k++) { sxy += (xs[k] - mx) * (ys[k] - my); sxx += (xs[k] - mx) ** 2; syy += (ys[k] - my) ** 2; }
      return sxx && syy ? sxy / Math.sqrt(sxx * syy) : 0;
    });
    m.rpmSpeed = corr.length ? median(corr) : null;
    m.maxThrottle = Math.max(...tr.map((s) => s[7]));
    const steer = tr.map((s) => s[9]);
    const mean = steer.reduce((x, y) => x + y, 0) / steer.length;
    m.steerStd = Math.sqrt(steer.reduce((x, y) => x + (y - mean) ** 2, 0) / steer.length);
  }
  for (const k of Object.keys(m)) if (typeof m[k] === 'number') m[k] = round(m[k], 4);
  return m;
}

/** Verdict: {fail: reason|null, flags: [..], m: measurements} */
export function judgeRealism(tr) {
  const m = measure(tr);
  const L = LIMITS;
  const flags = [];
  let fail = null;
  const out = (v, [lo, hi]) => v != null && (v < lo || v > hi);
  if (!m.hasInputs) fail = 'trace is missing timing/input data (old app?)';
  else if (out(m.clockRate, L.clockRate.fail)) fail = `stage clock ran at ${(m.clockRate * 100).toFixed(1)} % of real time`;
  else if (m.clockAheadSegments > 2) fail = 'stage clock jumped ahead of real time';
  else if (out(m.packetRate, L.packetRate.fail)) fail = `game physics ran at ${m.packetRate.toFixed(0)} steps/s (normal 333)`;
  else if (m.speedError != null && m.speedError > L.speedError.fail) fail = 'speed readings do not match the car\'s movement';
  else if (m.accel != null && m.accel > L.accel.fail) fail = `impossible acceleration (${m.accel.toFixed(2)} g)`;
  else if (m.braking != null && m.braking > L.braking.fail) fail = `impossible braking (${m.braking.toFixed(2)} g)`;
  else if (m.lateral != null && m.lateral > L.lateral.fail) fail = `impossible cornering (${m.lateral.toFixed(2)} g)`;
  else if (m.maxThrottle < 0.3) fail = 'no throttle input';

  if (out(m.packetRate, L.packetRate.flag)) flags.push(`physics rate ${m.packetRate.toFixed(0)}/s`);
  if (m.packetRateSpread != null && m.packetRateSpread > 0.15) flags.push('uneven physics rate');
  if (m.speedError != null && m.speedError > L.speedError.flag) flags.push(`speed error ${(m.speedError * 100).toFixed(1)} %`);
  if (m.accel != null && m.accel > L.accel.flag) flags.push(`acceleration ${m.accel.toFixed(2)} g`);
  if (m.braking != null && m.braking > L.braking.flag) flags.push(`braking ${m.braking.toFixed(2)} g`);
  if (m.lateral != null && m.lateral > L.lateral.flag) flags.push(`cornering ${m.lateral.toFixed(2)} g`);
  if (m.noThrottleAccel != null && m.noThrottleAccel > L.noThrottleAccel.flag) flags.push('speeds up without throttle');
  if (m.rpmSpeed != null && m.rpmSpeed < L.rpmSpeed.flag) flags.push('rpm does not follow speed');
  if (m.steerStd != null && m.steerStd < 0.01) flags.push('no steering input');
  return { fail, flags, m };
}

// ------------------------------------------------------------------ 4. comparison with the field

/** Stage clock when the run first passed 10 %, 20 % ... 100 % of the route. */
export function sections(tr, route, parts = 10) {
  return timesAt(tr, route, Array.from({ length: parts }, (_, k) => (k + 1) / parts), 0);
}

/** Time (stage clock + penaltyMs per reset so far) when the run first passed each fraction of the route. */
export function timesAt(tr, route, fracs, penaltyMs) {
  const pts = route.points, cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = cum[cum.length - 1];
  const parts = fracs.length;
  const out = new Array(parts).fill(null);
  let idx = 0, best = 0, prevBest = 0, prevT = null;
  for (const s of tr) {
    // nearest route point, searching forward from the last one
    let bi = idx, bd = Infinity;
    for (let j = Math.max(0, idx - 10); j < Math.min(pts.length, idx + 80); j++) {
      const d = (pts[j][0] - s[1]) ** 2 + (pts[j][1] - s[2]) ** 2;
      if (d < bd) { bd = d; bi = j; }
    }
    if (bd > 60 * 60) continue;
    idx = bi;
    best = Math.max(best, cum[bi] / total);
    const t = s[0] + (s[4] | 0) * penaltyMs;
    for (let k = 0; k < parts; k++) {
      // the finish (100 %) gets a little slack: the route's last point can sit just past where the clock stops
      if (out[k] != null || best < (fracs[k] >= 0.999 ? fracs[k] - 0.004 : fracs[k])) continue;
      // between two samples: estimate the moment the fraction was crossed (samples are 250 ms apart)
      out[k] = prevT != null && best > prevBest && fracs[k] > prevBest
        ? Math.round(prevT + ((Math.min(fracs[k], best) - prevBest) / (best - prevBest)) * (t - prevT))
        : t;
    }
    prevBest = best;
    prevT = t;
  }
  return out;
}

// ------------------------------------------------------------------ 5. conditions (weather + time of day)

/** Median air temperature (kelvin, trace column 12) over each tenth of the route. null where there's no data. */
export function tempProfile(tr, route, parts = 10) {
  if (!tr.length || tr[0].length < 13) return null;
  const pts = route.points, cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = cum[cum.length - 1];
  const bins = Array.from({ length: parts }, () => []);
  let idx = 0;
  for (const s of tr) {
    let bi = idx, bd = Infinity;
    for (let j = Math.max(0, idx - 10); j < Math.min(pts.length, idx + 80); j++) {
      const d = (pts[j][0] - s[1]) ** 2 + (pts[j][1] - s[2]) ** 2;
      if (d < bd) { bd = d; bi = j; }
    }
    if (bd > 60 * 60) continue;
    idx = bi;
    if (s[12] > 150 && s[12] < 350) bins[Math.min(parts - 1, Math.floor((cum[bi] / total) * parts))].push(s[12]);
  }
  return bins.map((b) => (b.length ? round(median(b), 2) : null));
}

export const TEMP_FLAG_K = 2.5;   // a run this much warmer/colder than the field (same points) looks like other conditions

/** mine / others: tempProfile()s. Flag when the run's temperatures differ from the field's at the same points. */
export function compareTemps(mine, others) {
  if (!mine) return { flags: [], diff: null };
  const usable = others.filter(Boolean);
  if (usable.length < 2) return { flags: [], diff: null };
  const diffs = [];
  for (let i = 0; i < mine.length; i++) {
    const vals = usable.map((o) => o[i]).filter((v) => v != null);
    if (mine[i] != null && vals.length >= 2) diffs.push(mine[i] - median(vals));
  }
  if (diffs.length < 5) return { flags: [], diff: null };
  const diff = median(diffs);
  const flags = Math.abs(diff) > TEMP_FLAG_K
    ? [`conditions differ: ${Math.abs(diff).toFixed(1)} °C ${diff > 0 ? 'warmer' : 'colder'} than the other drivers`] : [];
  return { flags, diff: round(diff, 2) };
}

const durations = (cs) => cs.map((c, i) => (c == null || (i && cs[i - 1] == null) ? null : c - (i ? cs[i - 1] : 0)));

/**
 * mine: section clock times of this run; others: [[...], ...] from other drivers' best runs today;
 * prevBestMs: this driver's best clock on the same stage+car before today (or null).
 */
export function compareField(mine, others, clockMs, prevBestMs) {
  const flags = [];
  const md = durations(mine);
  if (others.length >= 3) {
    const od = others.map(durations);
    let fastestEverywhere = true, n = 0;
    const logs = [];
    for (let i = 0; i < md.length; i++) {
      const vals = od.map((o) => o[i]).filter((v) => v != null);
      if (md[i] == null || vals.length < 3) continue;
      n++;
      if (md[i] >= Math.min(...vals)) fastestEverywhere = false;
      logs.push(Math.log(md[i] / median(vals)));
    }
    if (n >= 8 && fastestEverywhere) flags.push('fastest of everyone in every section');
    if (logs.length >= 8) {
      const mean = logs.reduce((a, b) => a + b, 0) / logs.length;
      const sd = Math.sqrt(logs.reduce((a, b) => a + (b - mean) ** 2, 0) / logs.length);
      if (mean < -0.05 && sd < 0.015) flags.push(`evenly ${((1 - Math.exp(mean)) * 100).toFixed(0)} % faster than the field in every section`);
    }
  }
  if (prevBestMs && clockMs < prevBestMs * 0.85) {
    flags.push(`${((1 - clockMs / prevBestMs) * 100).toFixed(0)} % faster than own previous best`);
  }
  return flags;
}
