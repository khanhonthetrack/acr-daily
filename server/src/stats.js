// Statistics of one daily, from the counted (first) runs' telemetry.
// Trace sample: [clockMs, x, z, kmh, resets, wallMs, physicsPackets, throttle, brake, steer, gear, rpm, airK]

const SEGMENTS = 80;   // the speed map: the route cut into this many pieces

function along(route) {
  const cum = [0];
  for (let i = 1; i < route.length; i++) cum.push(cum[i - 1] + Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]));
  return cum;
}

/** For each trace sample: distance along the route (m), moving forwards, ignoring samples far off the road. */
function project(trace, route, cum) {
  const out = [];
  let idx = 0;
  for (const s of trace) {
    let bi = idx, bd = Infinity;
    for (let j = Math.max(0, idx - 10); j < Math.min(route.length, idx + 80); j++) {
      const d = (route[j][0] - s[1]) ** 2 + (route[j][1] - s[2]) ** 2;
      if (d < bd) { bd = d; bi = j; }
    }
    if (bd > 3600) continue;
    idx = bi;
    out.push({ d: cum[bi], s });
  }
  return out;
}

const median = (xs) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

/** What the stats need from one run's trace, worked out once when the run arrives (about 1 KB as JSON, where the trace
 *  is ~100 KB, and reading every finisher's trace for each stats page costs more CPU than Workers Free allows):
 *  seg = per piece of the route [sum of km/h, samples, top km/h]; top = top speed {kmh, km}; flat = the longest
 *  flat-out stretch (throttle >= 98 %) {ms of stage clock, km where it started}. */
export function runProfile(trace, route) {
  const cum = along(route);
  const L = cum[cum.length - 1] || 1;
  const seg = Array.from({ length: SEGMENTS }, () => [0, 0, 0]);
  let top = null, flat = null, runStart = null;
  const pts = project(trace || [], route, cum);
  for (let i = 0; i < pts.length; i++) {
    const { d, s } = pts[i];
    const k = Math.min(SEGMENTS - 1, Math.floor((d / L) * SEGMENTS));
    seg[k][0] += s[3]; seg[k][1]++;
    if (s[3] > seg[k][2]) seg[k][2] = s[3];
    if (!top || s[3] > top.kmh) top = { kmh: s[3], km: d / 1000 };
    const full = s.length > 7 && s[7] >= 0.98;
    if (full && runStart == null) runStart = i;
    if ((!full || i === pts.length - 1) && runStart != null) {
      const ms = s[0] - pts[runStart].s[0];   // stage-clock time spent flat out
      if (!flat || ms > flat.ms) flat = { ms, km: pts[runStart].d / 1000 };
      runStart = null;
    }
  }
  const r1 = (v) => Math.round(v * 10) / 10;
  return { seg: seg.map(([sum, n, max]) => [r1(sum), n, r1(max)]), top: top && { kmh: r1(top.kmh), km: top.km }, flat };
}

/** runs: [{runId, name, country, totalMs, clockMs, resets, profile (runProfile) or else trace, sections, jumps}],
 *  board: leaderboard entries */
export function dailyStats(route, runs, board) {
  const cum = along(route);
  const L = cum[cum.length - 1] || 1;
  const finished = board.filter((e) => e.status === 'finished');
  const totals = finished.map((e) => e.totalMs);
  const seg = Array.from({ length: SEGMENTS }, () => ({ sum: 0, n: 0, max: 0, maxBy: null }));
  let top = null, longestFull = null;
  const clean = runs.filter((r) => !r.resets).length;
  for (const r of runs) {
    const p = r.profile && r.profile.seg && r.profile.seg.length === SEGMENTS ? r.profile : runProfile(r.trace, route);
    p.seg.forEach(([sum, n, max], k) => {
      seg[k].sum += sum; seg[k].n += n;
      if (max > seg[k].max) { seg[k].max = max; seg[k].maxBy = r.name; }
    });
    if (p.top && (!top || p.top.kmh > top.kmh)) top = { ...p.top, name: r.name, country: r.country, runId: r.runId };
    if (p.flat && (!longestFull || p.flat.ms > longestFull.ms)) longestFull = { ...p.flat, name: r.name, country: r.country };
  }
  // sections: who was fastest in each tenth, and the ideal run from everyone's best sections
  const parts = 10, best = Array(parts).fill(null);
  const table = [];
  for (const r of runs) {
    if (!r.sections) continue;
    const durs = r.sections.map((c, i) => (c == null || (i && r.sections[i - 1] == null) ? null : c - (i ? r.sections[i - 1] : 0)));
    table.push({ name: r.name, country: r.country, runId: r.runId, totalMs: r.totalMs, durs });
    durs.forEach((v, i) => { if (v != null && (!best[i] || v < best[i].ms)) best[i] = { ms: v, name: r.name, country: r.country }; });
  }
  table.sort((a, b) => a.totalMs - b.totalMs);
  // jumps (apps from 0.11): the longest, the most airtime in one run, and the stage's jump spots
  const withJumps = runs.filter((r) => Array.isArray(r.jumps));
  let longestJump = null, mostAir = null;
  const spots = new Map();   // ~60 m buckets along the route
  for (const r of withJumps) {
    let sum = 0;
    for (const [, ms, m, kmh] of r.jumps) {
      sum += ms;
      if (!longestJump || ms > longestJump.ms) longestJump = { ms, name: r.name, country: r.country, km: m / 1000, kmh };
      const key = Math.round(m / 60);
      const s = spots.get(key) || { m: 0, n: 0, sum: 0, drivers: new Set(), best: null };
      s.m += m; s.n++; s.sum += ms; s.drivers.add(r.runId);
      if (!s.best || ms > s.best.ms) s.best = { ms, name: r.name, country: r.country, kmh };
      spots.set(key, s);
    }
    if (r.jumps.length && (!mostAir || sum > mostAir.ms)) mostAir = { ms: sum, count: r.jumps.length, name: r.name, country: r.country };
  }
  const jumpSpots = [...spots.values()]
    .map((s) => ({ m: Math.round(s.m / s.n), drivers: s.drivers.size, avgMs: Math.round(s.sum / s.n), best: s.best }))
    .filter((s) => s.avgMs >= 200)
    .sort((a, b) => b.drivers * b.avgMs - a.drivers * a.avgMs)
    .slice(0, 6);
  const ideal = best.every(Boolean) ? best.reduce((a, b) => a + b.ms, 0) : null;
  return {
    lengthM: Math.round(L),
    field: {
      drivers: board.length, finishers: finished.length, dnfs: board.filter((e) => e.status === 'dnf').length,
      cleanRuns: clean, avgMs: mean(totals), medianMs: median(totals),
      fastestMs: totals.length ? Math.min(...totals) : null, slowestMs: totals.length ? Math.max(...totals) : null,
      totals: finished.map((e) => ({ name: e.name, country: e.country, totalMs: e.totalMs, resets: e.resets, rank: e.rank })),
    },
    records: {
      fastest: finished[0] ? { name: finished[0].name, country: finished[0].country, totalMs: finished[0].totalMs, runId: finished[0].runId } : null,
      topSpeed: top && { ...top, kmh: Math.round(top.kmh * 10) / 10, km: Math.round(top.km * 100) / 100 },
      avgSpeed: finished[0] ? Math.round((L / 1000) / (finished[0].clockMs / 3600000) * 10) / 10 : null,
      longestFlatOut: longestFull && { ...longestFull, ms: Math.round(longestFull.ms), km: Math.round(longestFull.km * 100) / 100 },
      ideal: ideal && { ms: ideal, gainMs: finished[0] ? finished[0].clockMs - ideal : null },
    },
    sections: { best, table: table.slice(0, 15) },
    air: {
      runsWithData: withJumps.length,
      longestJump: longestJump && { ...longestJump, km: Math.round(longestJump.km * 100) / 100 },
      mostAirtime: mostAir,
      spots: jumpSpots,
    },
    speedMap: seg.map((x, i) => ({ from: (i / SEGMENTS) * L, to: ((i + 1) / SEGMENTS) * L, avg: x.n ? x.sum / x.n : null, max: x.max || null, maxBy: x.maxBy })),
  };
}
