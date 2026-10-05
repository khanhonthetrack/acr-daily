// ACR Daily server: Cloudflare Worker + D1.
//
// Two dailies a day (slot 1 and 2): each its own stage, a random car, its own board.
// Public:  GET  /                         website (both dailies, live map, boards, past days)
//          GET  /api/challenges/today     today's two challenges (stage, car, route)
//          GET  /api/challenge?date=&slot= one daily (slot 1 by default; /api/challenge/today too)
//          GET  /api/leaderboard?date=&slot= best valid run per driver
//          GET  /api/live?date=&slot=     drivers on the stage right now (POST: the app's position, 1 s)
//          GET  /api/cars                 every car the random pick chooses from
//          GET  /api/commentary?date=&slot= the last live commentary lines (src/commentary.js)
//          GET  /api/runs/:id/trace       a finished run's trace (the app uses #1's for the live gap)
//          GET  /api/version              newest app version + download link
// Auth:    GET  /auth/steam/start?state=  -> Steam sign-in; /auth/steam/callback; GET /auth/poll?state=
//          POST /auth/logout
// Player:  POST /api/runs                 submit a run (Bearer token from sign-in)
// Admin:   (Bearer ADMIN_KEY) POST /api/admin/route | /api/admin/pool | /api/admin/schedule |
//          /api/admin/runs/:id/reject | /api/admin/ban, GET /api/admin/state

import { steamLoginUrl, steamProfile, verifySteam } from './steam.js';
import { PENALTY_MS, routeInfo, validateRun } from './validate.js';
import { sections, tempProfile, timesAt } from './realism.js';
import { sitePage } from './site.js';
import { viewerPage } from './viewer.js';
import { statsPage } from './statspage.js';
import { dailyStats } from './stats.js';
import { isoWeek, POINTS, weekDays, weekStandings, weekStart } from './week.js';
import { weekPage } from './weekpage.js';
import { guidePage } from './guidepage.js';
import { downloadUrl, latestVersion, releasePage, releaseSha256 } from './release.js';
import { CARS, carByName } from './cars.js';
import { countryCode } from './countries.js';
import { describe, pickConditions, stageParts, TIMES, WEATHER } from './conditions.js';
import { comment, fmtGap, fmtMs, recentLines } from './commentary.js';

const DAILIES = 2;                           // challenges per day
const MAX_BODY = 2_000_000;
const SPLITS = [0.25, 0.5, 0.75];          // split points, as fractions of the route (the finish is the 4th)
const MAX_RUNS_PER_DAY = 300;
const LATE_SUBMIT_MS = 30 * 60 * 1000;   // a run finished just before midnight may arrive a bit after

const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store', ...extra },
  });
const err = (msg, status = 400) => json({ error: msg }, status);
const html = (body, status = 200) => new Response(body, { status, headers: { 'Content-Type': 'text/html; charset=utf-8' } });

const dayOf = (ms) => new Date(ms).toISOString().slice(0, 10);
const dayStart = (date) => Date.parse(date + 'T00:00:00Z');
const dayNumber = (date) => Math.floor(dayStart(date) / 86400000);

async function sha256(text) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
}
function randomToken() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
}
function hashStr(s) {   // small stable hash for the daily picks (FNV-1a + a final mix, so neighbouring dates differ)
  let h = 2166136261;
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0;
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}

// ------------------------------------------------------------------ challenge

/** The day's two picks: two different stages from the pool, each with a random (or fixed) car.
 *  Slots already fixed for the day (schedule rows) are kept, and the others avoid their stages and cars. */
async function pickDay(env, date) {
  const { results } = await env.DB.prepare(
    'SELECT p.track, p.car FROM pool p JOIN routes r ON r.track = p.track WHERE p.enabled = 1').all();
  const fixedRows = (await env.DB.prepare('SELECT slot, track, car, weather, time FROM schedule WHERE date = ?')
    .bind(date).all()).results;
  const byTrack = new Map();
  for (const r of results) {
    if (!byTrack.has(r.track)) byTrack.set(r.track, []);
    if (r.car !== '*') byTrack.get(r.track).push(r.car);
  }
  const tracks = [...byTrack.keys()].sort((a, b) => hashStr(a) - hashStr(b));
  const d = dayNumber(date), picks = [];
  for (let slot = 1; slot <= DAILIES; slot++) {
    const done = fixedRows.find((r) => r.slot === slot);
    if (done) { picks.push(done); continue; }
    // rotate through the stages, skipping any already used today
    const used = new Set(fixedRows.map((r) => r.track).concat(picks.map((p) => p.track)));
    let track = null;
    for (let k = 0; k < tracks.length && !track; k++) {
      const t = tracks[(d * DAILIES + slot - 1 + k) % tracks.length];
      if (!used.has(t)) track = t;
    }
    if (!track) break;                    // fewer stages than dailies: no repeats on the same day
    const fixed = byTrack.get(track);
    let car;
    if (fixed.length) car = fixed[hashStr(date + slot) % fixed.length];
    else {
      let k = hashStr(date + '|' + slot + '|' + track) % CARS.length;
      while (picks.some((p) => p.car === CARS[k].name)) k = (k + 1) % CARS.length;   // two different cars a day
      car = CARS[k].name;
    }
    const cond = pickConditions(track, hashStr(date + '|w|' + slot), hashStr(date + '|t|' + slot));
    picks.push({ slot, track, car, weather: cond.weather, time: cond.time });
  }
  return picks;
}

async function challengeFor(env, date, slot = 1) {
  const q = 'SELECT track, car, weather, time FROM schedule WHERE date = ? AND slot = ?';
  let pick = await env.DB.prepare(q).bind(date, slot).first();
  if (!pick) {
    const picks = await pickDay(env, date);
    pick = picks.find((p) => p.slot === slot);
    if (!pick) return null;
    // once a day has started its challenges are fixed, so changing the pool never swaps a running day
    if (date <= dayOf(Date.now())) {
      await env.DB.batch(picks.filter((p) => p.weather !== undefined).map((p) => env.DB.prepare(
        'INSERT OR IGNORE INTO schedule (date, slot, track, car, weather, time) VALUES (?, ?, ?, ?, ?, ?)')
        .bind(date, p.slot, p.track, p.car, p.weather, p.time)));
      pick = await env.DB.prepare(q).bind(date, slot).first();
    }
  }
  const route = await env.DB.prepare('SELECT points, length, stage_id FROM routes WHERE track = ?').bind(pick.track).first();
  const start = dayStart(date);
  const car = carByName(pick.car);
  return {
    startTempK: await startTemp(env, date, slot),   // the app checks the game's time/weather against it
    id: `${date}/${slot}`,
    date,
    slot,
    track: pick.track,
    ...stageParts(pick.track),                         // rally, stageName, surface
    stageId: route ? route.stage_id || null : null,   // the game's id, for the app's "Drive daily" set-up
    car: pick.car,
    carId: car ? car.id : null,
    carClass: car ? car.cls : null,
    carAliases: car ? car.aliases || [] : [],
    ...describe(pick.weather, pick.time),     // conditions: weather, weatherLabel, time, timeLabel
    penaltyMs: PENALTY_MS,
    splits: SPLITS,
    startsAt: start,
    endsAt: start + 86400000,
    lengthM: route ? Math.round(route.length) : null,
    route: route ? JSON.parse(route.points) : null,
  };
}

/** Air temperature (kelvin) at the start of this daily, from the drivers who finished it (median of their first
 *  tenth of the stage), or null before anyone has. Same time of day + weather = same air, so the app can tell
 *  a driver whose game is set up differently. */
async function startTemp(env, date, slot) {
  const { results } = await env.DB.prepare(
    `SELECT temps FROM runs WHERE date = ? AND slot = ? AND status = 'finished' AND temps IS NOT NULL
      ORDER BY id DESC LIMIT 25`).bind(date, slot).all();
  const vals = results.map((r) => { try { return JSON.parse(r.temps)[0]; } catch { return null; } })
    .filter((v) => typeof v === 'number' && v > 150 && v < 350).sort((a, b) => a - b);
  return vals.length ? Math.round(vals[Math.floor(vals.length / 2)] * 100) / 100 : null;
}

async function challengesFor(env, date) {
  const out = [];
  for (let slot = 1; slot <= DAILIES; slot++) {
    const c = await challengeFor(env, date, slot);
    if (c) out.push(c);
  }
  return out;
}

/** "2026-10-05/2" -> {date, slot}; a bare date (apps before 0.4) means daily 1. */
function parseChallengeId(id) {
  const m = String(id || '').match(/^(\d{4}-\d{2}-\d{2})(?:\/([12]))?$/);
  return m ? { date: m[1], slot: m[2] ? +m[2] : 1 } : null;
}

const ATTEMPT_MATCH_MS = 120000;     // the counted run must have started within 2 min of the first attempt
const ABANDONED_MS = 60 * 60000;     // started and no result after an hour = DNF

/** Each driver's counted run for a daily: the FIRST one. -> Map steamId -> {run|null, dnf: reason|null} */
async function countedRuns(env, date, slot, now = Date.now()) {
  const { results: runs } = await env.DB.prepare(
    `SELECT id, steam_id, status, started_at, created FROM runs WHERE date = ? AND slot = ?
      ORDER BY COALESCE(started_at, created) ASC, id ASC`).bind(date, slot).all();
  const { results: atts } = await env.DB.prepare('SELECT steam_id, started FROM attempts WHERE date = ? AND slot = ?')
    .bind(date, slot).all();
  const firstStart = new Map(atts.map((a) => [a.steam_id, a.started]));
  const byPlayer = new Map();
  for (const r of runs) {
    if (!byPlayer.has(r.steam_id)) byPlayer.set(r.steam_id, []);
    byPlayer.get(r.steam_id).push(r);
  }
  const out = new Map();
  for (const sid of new Set([...byPlayer.keys(), ...firstStart.keys()])) {
    const list = byPlayer.get(sid) || [];
    const a = firstStart.get(sid);
    const first = list[0];
    const firstAt = first ? first.started_at || first.created : null;
    // the first run counts, unless there was an earlier start that never produced a result
    if (first && (a == null || a >= firstAt - ATTEMPT_MATCH_MS)) { out.set(sid, { run: first, dnf: null }); continue; }
    // that earlier start: DNF once a later run exists or an hour has passed (until then: still on stage)
    if (first || now - a > ABANDONED_MS) out.set(sid, { run: null, dnf: 'abandoned' });
  }
  return out;
}

async function leaderboard(env, date, slot = 1) {
  const counted = await countedRuns(env, date, slot);
  const ids = [...counted.values()].filter((c) => c.run).map((c) => c.run.id);
  const rows = ids.length ? (await env.DB.prepare(
    `SELECT r.id AS runId, r.steam_id AS steamId, p.name, p.avatar, p.country, r.status, r.reason, r.total_ms AS totalMs,
            r.clock_ms AS clockMs, r.resets, r.created, r.flags, r.splits,
            (SELECT COUNT(*) FROM reports WHERE run_id = r.id) AS reports
       FROM runs r JOIN players p ON p.steam_id = r.steam_id
      WHERE r.id IN (${ids.map(() => '?').join(',')}) AND p.banned = 0`).bind(...ids).all()).results : [];
  const finished = rows.filter((r) => r.status === 'finished').sort((a, b) => a.totalMs - b.totalMs || a.created - b.created);
  const entries = [];
  for (const r of finished) {
    const { flags, reports, splits, reason, ...e } = r;
    entries.push({ ...e, rank: entries.length + 1, splits: splits ? JSON.parse(splits) : null,
      review: JSON.parse(flags || '[]').length > 0 || reports >= REVIEW_REPORTS });
  }
  const leader = entries[0] ? entries[0].totalMs : null;
  for (const e of entries) e.gapMs = e.totalMs - leader;
  // DNF / invalid first runs, and starts that never finished, at the bottom (no rank)
  for (const r of rows.filter((x) => x.status !== 'finished' && x.status !== 'rejected')) {
    entries.push({ runId: r.runId, steamId: r.steamId, name: r.name, avatar: r.avatar, country: r.country,
      status: 'dnf', reason: r.reason, rank: null, totalMs: null, gapMs: null, resets: r.resets, splits: null, review: false });
  }
  const abandoned = [...counted.entries()].filter(([, c]) => c.dnf).map(([sid]) => sid);
  if (abandoned.length) {
    const { results: ps } = await env.DB.prepare(
      `SELECT steam_id, name, avatar, country FROM players WHERE banned = 0 AND steam_id IN (${abandoned.map(() => '?').join(',')})`)
      .bind(...abandoned).all();
    for (const p of ps) {
      entries.push({ runId: null, steamId: p.steam_id, name: p.name, avatar: p.avatar, country: p.country,
        status: 'dnf', reason: 'did not finish', rank: null, totalMs: null, gapMs: null, resets: 0, splits: null, review: false });
    }
  }
  const stats = await env.DB.prepare(
    `SELECT COUNT(*) AS attempts, COUNT(DISTINCT steam_id) AS drivers,
            COALESCE(SUM(CASE WHEN status = 'dnf' THEN 1 ELSE 0 END), 0) AS dnfs
       FROM runs WHERE date = ? AND slot = ?`).bind(date, slot).first();
  stats.dnfs = entries.filter((e) => e.status === 'dnf').length;   // DNFs on the board (first runs only)
  stats.drivers = entries.length;
  return { date, slot, entries, stats };
}

// ------------------------------------------------------------------ weekly hall of fame

const FIRST_WEEK = '2026-09-28';   // the week ACR Daily started (no navigation before it)

async function weekData(env, date) {
  const start = weekStart(date), today = dayOf(Date.now());
  const days = weekDays(start), stages = [];
  for (const d of days) {
    for (let slot = 1; slot <= DAILIES; slot++) {
      if (d > today) { stages.push({ date: d, slot, future: true, board: null }); continue; }
      const ch = await challengeFor(env, d, slot);
      if (!ch) { stages.push({ date: d, slot, board: [] }); continue; }
      const b = await leaderboard(env, d, slot);
      stages.push({ date: d, slot, stageName: ch.stageName || ch.track, rally: ch.rally, car: ch.car, board: b.entries });
    }
  }
  const standings = weekStandings(stages);
  return {
    start, end: days[6], week: isoWeek(start), today, points: POINTS,
    prev: start > FIRST_WEEK ? weekStart(new Date(Date.parse(start) - 86400000).toISOString().slice(0, 10)) : null,
    next: days[6] < today ? weekStart(new Date(Date.parse(days[6]) + 86400000).toISOString().slice(0, 10)) : null,
    stages: stages.map(({ board, ...s }) => ({ ...s, drivers: board ? board.length : 0 })),
    standings,
  };
}

// ------------------------------------------------------------------ stats page

async function stageStats(env, date, slot) {
  const ch = await challengeFor(env, date, slot);
  if (!ch || !ch.route) return null;
  const board = await leaderboard(env, date, slot);
  const ids = board.entries.filter((e) => e.status === 'finished').slice(0, 200).map((e) => e.runId);
  const runs = [];
  for (let i = 0; i < ids.length; i += 50) {   // D1 limits bound parameters per query
    const part = ids.slice(i, i + 50);
    const { results } = await env.DB.prepare(
      `SELECT r.id, r.total_ms, r.clock_ms, r.resets, r.trace, r.sections, r.jumps, p.name, p.country
         FROM runs r JOIN players p ON p.steam_id = r.steam_id WHERE r.id IN (${part.map(() => '?').join(',')})`).bind(...part).all();
    for (const r of results) {
      runs.push({ runId: r.id, name: r.name, country: r.country, totalMs: r.total_ms, clockMs: r.clock_ms, resets: r.resets,
        trace: r.trace ? JSON.parse(r.trace) : [], sections: r.sections ? JSON.parse(r.sections) : null,
        jumps: r.jumps ? JSON.parse(r.jumps) : null });
    }
  }
  return { challenge: ch, ...dailyStats(ch.route, runs, board.entries) };
}

// ------------------------------------------------------------------ live positions

const LIVE_STALE_MS = 15000;      // a driver disappears from the map 15 s after their last update
const LIVE_KEEP_DONE_MS = 60000;  // a finish / DNF stays on the map for a minute

async function postLive(req, env, ctx) {
  const player = await playerFrom(req, env);
  if (!player) return err('sign in with Steam first', 401);
  const b = await req.json().catch(() => null);
  const c = b && parseChallengeId(b.challengeId);
  if (!c || c.date !== dayOf(Date.now())) return err('bad challenge');
  const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  const state = ['live', 'finished', 'dnf'].includes(b.state) ? b.state : 'live';
  let first = false;
  if (state === 'live') {   // the first start of this daily: the run that started then is the one that counts
    const ins = await env.DB.prepare('INSERT OR IGNORE INTO attempts (steam_id, date, slot, started) VALUES (?, ?, ?, ?)')
      .bind(player.steam_id, c.date, c.slot, startedMs(b.startedAt, Date.now())).run();
    first = ins.meta.changes > 0;
  }
  if (b.country) await setCountry(env, player.steam_id, b.country);
  const prev = await env.DB.prepare('SELECT progress, resets, state FROM live WHERE steam_id = ? AND date = ? AND slot = ?')
    .bind(player.steam_id, c.date, c.slot).first();
  if (state === 'live' && ctx) {
    ctx.waitUntil(liveEvents(env, player, c, b, prev, first).catch((e) => console.error('live events', e)));
  }
  await env.DB.prepare(
    `INSERT INTO live (steam_id, date, slot, x, z, progress, total_ms, resets, state, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (steam_id, date, slot) DO UPDATE SET x = excluded.x, z = excluded.z, progress = excluded.progress,
       total_ms = excluded.total_ms, resets = excluded.resets, state = excluded.state, updated = excluded.updated`)
    .bind(player.steam_id, c.date, c.slot, n(b.x), n(b.z), Math.max(0, Math.min(1, n(b.progress))),
      Math.round(n(b.totalMs)), n(b.resets) | 0, state, Date.now()).run();
  return json({ ok: true });
}

/** Commentary events from a live position update of the counted run: start, splits (25 / 50 / 75 %), resets. */
async function liveEvents(env, player, c, b, prev, first) {
  const ch = await challengeFor(env, c.date, c.slot);
  if (!ch) return;
  const base = { driver: player.name, stage: ch.stageName || ch.track, rally: ch.rally || null, car: ch.car,
    conditions: [ch.weatherLabel, ch.timeLabel].filter(Boolean).join(', ') || null };
  if (first) {
    const others = await env.DB.prepare('SELECT COUNT(*) AS n FROM attempts WHERE date = ? AND slot = ?').bind(c.date, c.slot).first();
    await comment(env, c.date, c.slot, { kind: 'start', ...base, driverNumberToday: others.n }, player.steam_id);
    return;
  }
  // only the counted run (the first start) gets commentary, not practice runs
  const att = await env.DB.prepare('SELECT started FROM attempts WHERE steam_id = ? AND date = ? AND slot = ?')
    .bind(player.steam_id, c.date, c.slot).first();
  if (!att || Math.abs(startedMs(b.startedAt, Date.now()) - att.started) > ATTEMPT_MATCH_MS) return;
  if (!prev || prev.state !== 'live') return;
  const prog = Number(b.progress) || 0, my = Math.round(Number(b.totalMs) || 0);
  for (let k = 0; k < SPLITS.length; k++) {
    if (prev.progress < SPLITS[k] && prog >= SPLITS[k]) {
      const board = await leaderboard(env, c.date, c.slot);
      const times = board.entries.filter((e) => e.status === 'finished' && e.steamId !== player.steam_id && e.splits && e.splits[k] != null)
        .map((e) => ({ name: e.name, t: e.splits[k] })).sort((a, z) => a.t - z.t);
      const place = 1 + times.filter((x) => x.t < my).length;
      const lead = times[0];
      await comment(env, c.date, c.slot, { kind: 'split', ...base, split: k + 1, ofSplits: SPLITS.length, time: fmtMs(my),
        place: times.length ? place : null, of: times.length + 1, leader: lead && lead.t <= my ? lead.name : null,
        gapToLeader: lead && lead.t <= my ? fmtGap(my - lead.t) : null,
        aheadOfBestBy: lead && my < lead.t ? fmtGap(my - lead.t) : null, resetsSoFar: Number(b.resets) | 0 }, player.steam_id);
    }
  }
  if ((Number(b.resets) | 0) > (prev.resets | 0)) {
    await comment(env, c.date, c.slot, { kind: 'reset', ...base, at: `${Math.round(prog * 100)} % into the stage`,
      resetsSoFar: Number(b.resets) | 0, penalty: '+60 s each' }, player.steam_id);
  }
}

async function getLive(env, date, slot) {
  const now = Date.now();
  const { results } = await env.DB.prepare(
    `SELECT l.steam_id AS steamId, p.name, p.country, p.avatar, l.x, l.z, l.progress, l.total_ms AS totalMs, l.resets, l.state, l.updated
       FROM live l JOIN players p ON p.steam_id = l.steam_id
      WHERE l.date = ? AND l.slot = ? AND p.banned = 0
        AND ((l.state = 'live' AND l.updated > ?) OR (l.state != 'live' AND l.updated > ?))
      ORDER BY l.progress DESC`).bind(date, slot, now - LIVE_STALE_MS, now - LIVE_KEEP_DONE_MS).all();
  return { date, slot, now, drivers: results };
}

// ------------------------------------------------------------------ auth

async function playerFrom(req, env) {
  const m = (req.headers.get('Authorization') || '').match(/^Bearer\s+([0-9a-f]{64})$/);
  if (!m) return null;
  return env.DB.prepare(
    'SELECT p.* FROM sessions s JOIN players p ON p.steam_id = s.steam_id WHERE s.token_hash = ?')
    .bind(await sha256(m[1])).first();
}

function isAdmin(req, env) {
  const key = (env.ADMIN_KEY || '').trim();   // a pasted secret often carries a stray newline
  return key.length >= 24 && req.headers.get('Authorization') === `Bearer ${key}`;
}

async function completeLogin(env, state, steamId, devName) {
  const prof = devName ? { name: devName, avatar: null } : await steamProfile(steamId, env);
  const now = Date.now();
  await env.DB.prepare(
    `INSERT INTO players (steam_id, name, avatar, created) VALUES (?, ?, ?, ?)
     ON CONFLICT (steam_id) DO UPDATE SET name = excluded.name, avatar = excluded.avatar`)
    .bind(steamId, prof.name, prof.avatar, now).run();
  const token = randomToken();
  await env.DB.batch([
    env.DB.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, ?)').bind(await sha256(token), steamId, now),
    env.DB.prepare('UPDATE logins SET token = ?, steam_id = ?, name = ? WHERE state = ?').bind(token, steamId, prof.name, state),
  ]);
  return prof;
}

const page = (title, text) => html(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACR Daily</title><body style="background:#0A0A0C;color:#FFFFFF;font:18px system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;padding:16px;border-top:4px solid #FFD100"><h1 style="margin:16px 0 8px">${title}</h1><p style="color:#D8D8DE">${text}</p></div>`);

const escapeHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ------------------------------------------------------------------ handlers

async function submitRun(req, env, ctx) {
  const player = await playerFrom(req, env);
  if (!player) return err('sign in with Steam first', 401);
  if (player.banned) return err('this account is banned', 403);
  const len = +(req.headers.get('Content-Length') || 0);
  if (len > MAX_BODY) return err('run too big', 413);
  let sub;
  try { sub = await req.json(); } catch { return err('bad json'); }
  const now = Date.now();
  const cid = parseChallengeId(sub.challengeId);
  if (!cid) return err('missing challenge');
  const { date, slot } = cid;
  const today = dayOf(now);
  if (date !== today && !(date === dayOf(now - LATE_SUBMIT_MS) && now - dayStart(today) < LATE_SUBMIT_MS)) {
    return err('too late: that challenge is over', 409);
  }
  const ch = await challengeFor(env, date, slot);
  if (!ch || !ch.route) return err('no challenge for that day', 409);
  if (sub.track !== ch.track || sub.car !== ch.car) return err('invalid: not the challenge stage/car', 422);
  const count = await env.DB.prepare('SELECT COUNT(*) AS n FROM runs WHERE steam_id = ? AND date = ?')
    .bind(player.steam_id, date).first();
  if (count.n >= MAX_RUNS_PER_DAY) return err('too many runs today', 429);

  const v = validateRun(sub, routeInfo(ch.route), ch.penaltyMs);
  const status = v.ok ? v.status : 'invalid';
  const reason = v.reason;
  let secs = null, splits = null, temps = null;
  const flags = [...(v.flags || [])];
  if (status === 'finished') {   // for the split standings and the stats page (no checks)
    splits = timesAt(v.trace, { points: ch.route }, SPLITS, ch.penaltyMs);
    secs = sections(v.trace, { points: ch.route });
    temps = tempProfile(v.trace, { points: ch.route });
  }
  const res = await env.DB.prepare(
    `INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, total_ms, flags, app_version, created,
                       started_at, trace, sections, checks, splits, temps, jumps)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(date, slot, player.steam_id, ch.track, ch.car, status, reason, v.ok ? v.clockMs : sub.clockMs | 0,
      v.ok ? v.resets : sub.resets | 0, v.ok ? v.totalMs : null, JSON.stringify(flags),
      String(sub.appVersion || '').slice(0, 20), now, startedMs(sub.startedAt, now),
      status === 'finished' ? JSON.stringify(v.trace) : null,
      secs ? JSON.stringify(secs) : null, v.checks ? JSON.stringify(v.checks) : null,
      splits ? JSON.stringify(splits) : null, temps ? JSON.stringify(temps) : null,
      status === 'finished' ? JSON.stringify(cleanJumps(sub.jumps, v.clockMs, routeInfo(ch.route).length)) : null)
    .run();
  await setCountry(env, player.steam_id, sub.country);
  const id = res.meta.last_row_id;
  const mine = (await countedRuns(env, date, slot)).get(player.steam_id);
  const counted = !!(mine && mine.run && mine.run.id === id);
  const base = { driver: player.name, stage: ch.stageName || ch.track, rally: ch.rally || null, car: ch.car };
  if (counted && status !== 'finished' && ctx) {
    ctx.waitUntil(comment(env, date, slot, { kind: 'dnf', ...base, reason: reason || 'did not finish',
      progressNote: sub.clockMs ? `after ${fmtMs(sub.clockMs | 0)} on the stage clock` : null }, player.steam_id)
      .catch((e) => console.error('commentary', e)));
  }
  if (!v.ok) return err('invalid: ' + v.reason + (counted ? '' : ' (practice run)'), 422);
  let rank = null;
  if (counted && status === 'finished') {
    const b = await leaderboard(env, date, slot);
    const me = b.entries.find((e) => e.runId === id);
    rank = me ? me.rank : null;
    if (ctx) {
      const done = b.entries.filter((e) => e.status === 'finished');
      const lead = done[0], next = done[1];
      ctx.waitUntil(comment(env, date, slot, { kind: 'finish', ...base, time: fmtMs(v.totalMs), stageClock: fmtMs(v.clockMs),
        resets: v.resets, place: rank, of: done.length,
        leader: rank > 1 && lead ? lead.name : null, gapToLeader: rank > 1 && lead ? fmtGap(v.totalMs - lead.totalMs) : null,
        newLeaderAheadOf: rank === 1 && next ? next.name : null, marginToSecond: rank === 1 && next ? fmtGap(next.totalMs - v.totalMs) : null },
      player.steam_id).catch((e) => console.error('commentary', e)));
    }
  }
  return json({ ok: true, id, status, totalMs: v.totalMs, rank, counted, review: flags.length > 0 });
}

/** A run's jumps, kept only when plausible: [[clockMs, airtimeMs, routeM, kmh], ...] (null when none sent). */
function cleanJumps(j, clockMs, lengthM) {
  if (!Array.isArray(j)) return null;
  const out = [];
  for (const x of j.slice(0, 300)) {
    if (!Array.isArray(x) || x.length < 4 || !x.every((v) => Number.isFinite(v))) continue;
    const [t, dur, m, kmh] = x;
    if (dur < 150 || dur > 3000 || t < 0 || t > clockMs || m < 0 || m > lengthM + 50 || kmh < 0 || kmh > 300) continue;
    out.push([Math.round(t), Math.round(dur), Math.round(m), Math.round(kmh * 10) / 10]);
  }
  return out;
}

/** The app sends time.time() seconds; older apps nothing (then the arrival time stands in). */
function startedMs(v, now) {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return now;
  const ms = n < 1e11 ? Math.round(n * 1000) : Math.round(n);
  return Math.abs(ms - now) < 6 * 3600000 ? ms : now;
}

async function setCountry(env, steamId, name) {
  const code = countryCode(name);
  if (code) await env.DB.prepare('UPDATE players SET country = ? WHERE steam_id = ? AND (country IS NULL OR country != ?)')
    .bind(code, steamId, code).run();
}

const REVIEW_REPORTS = 3;   // this many reports put a run "under review" too

async function runDetail(env, id) {
  const r = await env.DB.prepare(
    `SELECT r.*, p.name, p.avatar, p.country, (SELECT COUNT(*) FROM reports WHERE run_id = r.id) AS reports
       FROM runs r JOIN players p ON p.steam_id = r.steam_id WHERE r.id = ? AND r.status IN ('finished', 'rejected')`)
    .bind(id).first();
  if (!r) return null;
  const board = await leaderboard(env, r.date, r.slot || 1);
  const me = board.entries.find((e) => e.runId === r.id);
  // compare with the day's #1 (or #2 when this run is #1)
  const other = board.entries.find((e) => e.status === 'finished' && e.runId !== r.id && e.steamId !== r.steam_id);
  let compare = null;
  if (other) {
    const o = await env.DB.prepare('SELECT trace, sections FROM runs WHERE id = ?').bind(other.runId).first();
    compare = { id: other.runId, name: other.name, rank: other.rank, totalMs: other.totalMs, resets: other.resets,
      trace: JSON.parse(o.trace), sections: o.sections ? JSON.parse(o.sections) : null };
  }
  const ch = await challengeFor(env, r.date, r.slot || 1);
  return {
    id: r.id, date: r.date, slot: r.slot || 1, name: r.name, country: r.country, avatar: r.avatar, steamId: r.steam_id, track: r.track, car: r.car,
    status: r.status, reason: r.reason, clockMs: r.clock_ms, resets: r.resets, totalMs: r.total_ms,
    rank: me ? me.rank : null, flags: JSON.parse(r.flags || '[]'), reports: r.reports,
    review: JSON.parse(r.flags || '[]').length > 0 || r.reports >= REVIEW_REPORTS,
    checks: r.checks ? JSON.parse(r.checks) : null, sections: r.sections ? JSON.parse(r.sections) : null,
    trace: JSON.parse(r.trace), route: ch ? ch.route : null, penaltyMs: PENALTY_MS, compare,
  };
}

async function reportRun(req, env, id) {
  const run = await env.DB.prepare("SELECT id FROM runs WHERE id = ? AND status = 'finished'").bind(id).first();
  if (!run) return err('not found', 404);
  const body = await req.json().catch(() => ({}));
  const ip = req.headers.get('CF-Connecting-IP') || 'local';
  const who = await sha256(ip + '|' + (env.ADMIN_KEY || ''));
  await env.DB.prepare('INSERT OR IGNORE INTO reports (run_id, who, reason, created) VALUES (?, ?, ?, ?)')
    .bind(id, who, String(body.reason || '').slice(0, 300), Date.now()).run();
  const c = await env.DB.prepare('SELECT COUNT(*) AS n FROM reports WHERE run_id = ?').bind(id).first();
  return json({ ok: true, reports: c.n });
}

// ------------------------------------------------------------------ routes from players
// The app records every clean run (no resets) of a stage. If that stage has no route yet, the first one
// that passes these checks becomes its route and the stage joins the daily rotation (random car).

async function listRoutes(env) {
  const { results } = await env.DB.prepare('SELECT track, stage_id AS stageId, length FROM routes ORDER BY track').all();
  return results.map((r) => ({ ...r, length: Math.round(r.length) }));
}

/** Checks on a contributed route; returns an error message or null. */
export function checkContribution(b) {
  if (!b || typeof b.track !== 'string' || !/^[\p{L}\p{N} '.\-]{3,60}$/u.test(b.track.trim())) return 'bad stage name';
  const pts = b.points;
  if (!Array.isArray(pts) || pts.length < 200 || pts.length > 20000) return 'route too short';
  let len = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    if (!Array.isArray(p) || p.length < 2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) return 'bad points';
    if (i) {
      const d = Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]);
      if (d > 40) return 'the route has a jump (reset?)';
      len += d;
    }
  }
  if (len < 1500 || len > 30000) return 'stage length not plausible';
  const clock = Number(b.clockMs);
  if (!Number.isFinite(clock) || clock <= 0) return 'missing stage time';
  const kmh = len / 1000 / (clock / 3600000);
  if (kmh < 25 || kmh > 170) return 'average speed not plausible';
  if (b.stageId != null && !/^[A-Za-z0-9]{6,60}$/.test(b.stageId)) return 'bad stage id';
  return null;
}

async function contributeRoute(req, env) {
  const player = await playerFrom(req, env);
  if (!player) return err('sign in with Steam first', 401);
  if (player.banned) return err('this account is banned', 403);
  const b = await req.json().catch(() => null);
  const bad = checkContribution(b);
  if (bad) return err('route refused: ' + bad, 422);
  const track = b.track.trim();
  const info = routeInfo(b.points);
  const res = await env.DB.prepare(
    `INSERT OR IGNORE INTO routes (track, points, length, updated, stage_id, contributed_by) VALUES (?, ?, ?, ?, ?, ?)`)
    .bind(track, JSON.stringify(b.points), info.length, Date.now(), b.stageId || null, player.steam_id).run();
  if (!res.meta.changes) return json({ ok: true, added: false, reason: 'this stage already has a route' });
  await env.DB.prepare("INSERT OR IGNORE INTO pool (track, car, enabled) VALUES (?, '*', 1)").bind(track).run();
  return json({ ok: true, added: true, track, length: Math.round(info.length) });
}

async function admin(req, env, path) {
  if (!isAdmin(req, env)) return err('not allowed', 403);
  const body = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  if (path === '/api/admin/route') {
    const pts = body.points;
    if (!body.track || !Array.isArray(pts) || pts.length < 20) return err('need track and points');
    const info = routeInfo(pts);
    const sid = body.stageId && /^[A-Za-z0-9]{6,60}$/.test(body.stageId) ? body.stageId : null;
    await env.DB.prepare(
      `INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, ?, ?)
       ON CONFLICT (track) DO UPDATE SET points = excluded.points, length = excluded.length, updated = excluded.updated,
         stage_id = COALESCE(excluded.stage_id, routes.stage_id)`)
      .bind(body.track, JSON.stringify(pts), info.length, Date.now(), sid).run();
    return json({ ok: true, track: body.track, length: Math.round(info.length), checkpoints: info.checkpoints.length });
  }
  if (path === '/api/admin/stage-id') {
    if (!body.track || !/^[A-Za-z0-9]{6,60}$/.test(body.stageId || '')) return err('need track and stageId (e.g. AlsaceS4SaverneFullForward)');
    const r = await env.DB.prepare('UPDATE routes SET stage_id = ? WHERE track = ?').bind(body.stageId, body.track).run();
    return r.meta.changes ? json({ ok: true }) : err('no route for that track', 404);
  }
  if (path === '/api/admin/pool') {
    if (!body.track) return err('need track');
    const car = body.car || '*';   // '*' = a random car each time
    if (car !== '*' && !carByName(car)) return err('unknown car (see /api/cars)');
    await env.DB.prepare(
      `INSERT INTO pool (track, car, enabled) VALUES (?, ?, ?)
       ON CONFLICT (track, car) DO UPDATE SET enabled = excluded.enabled`)
      .bind(body.track, car, body.enabled === false ? 0 : 1).run();
    return json({ ok: true });
  }
  if (path === '/api/admin/schedule') {
    const slot = +(body.slot || 1);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(body.date || '') || ![1, 2].includes(slot)) return err('need date and slot 1 or 2');
    if (body.remove) await env.DB.prepare('DELETE FROM schedule WHERE date = ? AND slot = ?').bind(body.date, slot).run();
    else {
      if (!body.track || !body.car) return err('need track and car');
      const car = carByName(body.car);
      if (!car) return err('unknown car (see /api/cars)');
      if (body.weather && !WEATHER[body.weather]) return err('weather: ' + Object.keys(WEATHER).join(', '));
      if (body.time && !TIMES.some((t) => t.id === body.time)) return err('time: ' + TIMES.map((t) => t.id).join(', '));
      const auto = pickConditions(body.track, hashStr(body.date + '|w|' + slot), hashStr(body.date + '|t|' + slot));
      await env.DB.prepare('INSERT OR REPLACE INTO schedule (date, slot, track, car, weather, time) VALUES (?, ?, ?, ?, ?, ?)')
        .bind(body.date, slot, body.track, car.name, body.weather || auto.weather, body.time || auto.time).run();
    }
    return json({ ok: true });
  }
  let m = path.match(/^\/api\/admin\/runs\/(\d+)\/reject$/);
  if (m) {
    await env.DB.prepare("UPDATE runs SET status = 'rejected', reason = ? WHERE id = ?").bind(String(body.reason || 'rejected by admin'), +m[1]).run();
    return json({ ok: true });
  }
  if (path === '/api/admin/ban') {
    await env.DB.prepare('UPDATE players SET banned = ? WHERE steam_id = ?').bind(body.banned === false ? 0 : 1, String(body.steamId)).run();
    return json({ ok: true });
  }
  if (path === '/api/admin/state') {
    const routes = (await env.DB.prepare('SELECT track, length, updated, stage_id FROM routes ORDER BY track').all()).results;
    const pool = (await env.DB.prepare('SELECT * FROM pool ORDER BY track, car').all()).results;
    const next = [];
    for (let i = 0; i < 7; i++) {
      const d = dayOf(Date.now() + i * 86400000);
      for (const c of await challengesFor(env, d)) {
        next.push({ date: d, slot: c.slot, track: c.track, car: c.car, weather: c.weatherLabel, time: c.timeLabel });
      }
    }
    const flagged = (await env.DB.prepare(
      `SELECT r.id, r.date, r.steam_id, r.total_ms, r.flags, COUNT(rp.run_id) AS reports
         FROM runs r LEFT JOIN reports rp ON rp.run_id = r.id
        WHERE r.status = 'finished'
        GROUP BY r.id HAVING r.flags != '[]' OR COUNT(rp.run_id) > 0
        ORDER BY r.id DESC LIMIT 50`).all()).results;
    return json({ routes, pool, next, flagged });
  }
  return err('not found', 404);
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';
    try {
      if (req.method === 'OPTIONS') {
        return new Response(null, { headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Authorization, Content-Type', 'Access-Control-Allow-Methods': 'GET, POST' } });
      }
      if (path === '/' && req.method === 'GET') return html(sitePage(env));

      const qDate = url.searchParams.get('date') || dayOf(Date.now());
      const qSlot = +(url.searchParams.get('slot') || 1);
      if (path === '/api/challenges/today' || path === '/api/challenges') {
        const date = path.endsWith('today') ? dayOf(Date.now()) : qDate;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return err('bad date');
        if (date > dayOf(Date.now())) return err('no peeking', 403);
        return json({ date, challenges: await challengesFor(env, date) });
      }
      if (path === '/api/challenge/today' || path === '/api/challenge') {   // one daily (default daily 1)
        const date = path.endsWith('today') ? dayOf(Date.now()) : qDate;
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || ![1, 2].includes(qSlot)) return err('bad date or slot');
        if (date > dayOf(Date.now())) return err('no peeking', 403);
        const ch = await challengeFor(env, date, qSlot);
        return ch ? json(ch) : err('no challenge yet', 404);
      }
      if (path === '/api/leaderboard') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || ![1, 2].includes(qSlot)) return err('bad date or slot');
        return json(await leaderboard(env, qDate, qSlot));
      }
      if (path === '/api/live') {
        if (req.method === 'POST') return postLive(req, env, ctx);
        if (![1, 2].includes(qSlot)) return err('bad slot');
        return json(await getLive(env, qDate, qSlot));
      }
      if (path === '/api/cars') return json(CARS);
      if (path === '/api/commentary') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || ![1, 2].includes(qSlot)) return err('bad date or slot');
        return json({ date: qDate, slot: qSlot, lines: await recentLines(env, qDate, qSlot) });
      }
      if (path === '/api/stats') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || ![1, 2].includes(qSlot) || qDate > dayOf(Date.now())) return err('bad date or slot');
        const st = await stageStats(env, qDate, qSlot);
        return st ? json(st) : err('no stage', 404);
      }
      if (path === '/api/week') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || qDate > dayOf(Date.now())) return err('bad date');
        return json(await weekData(env, qDate));
      }
      if (path === '/week') return html(weekPage());
      if (path === '/guide') return html(guidePage(env));
      const sm = path.match(/^\/stage\/(\d{4}-\d{2}-\d{2})\/([12])$/);
      if (sm) return html(statsPage(sm[1], +sm[2]));
      if (path === '/api/routes' && req.method === 'GET') return json(await listRoutes(env));
      if (path === '/api/routes/contribute' && req.method === 'POST') return contributeRoute(req, env);
      let rm = path.match(/^\/api\/runs\/(\d+)$/);
      if (rm) {
        const d = await runDetail(env, +rm[1]);
        return d ? json(d) : err('not found', 404);
      }
      rm = path.match(/^\/api\/runs\/(\d+)\/report$/);
      if (rm && req.method === 'POST') return reportRun(req, env, +rm[1]);
      rm = path.match(/^\/run\/(\d+)$/);
      if (rm) return html(viewerPage(+rm[1]));
      let m = path.match(/^\/api\/runs\/(\d+)\/trace$/);
      if (m) {
        const r = await env.DB.prepare("SELECT id, track, car, total_ms, trace FROM runs WHERE id = ? AND status = 'finished'").bind(+m[1]).first();
        return r ? json({ id: r.id, track: r.track, car: r.car, totalMs: r.total_ms, trace: JSON.parse(r.trace) }) : err('not found', 404);
      }
      if (path === '/api/version') {
        return json({ latest: latestVersion(env), url: downloadUrl(env), sha256: await releaseSha256(env, ctx),
                      release: releasePage(env) });
      }
      // old links to the download on this server go to the current GitHub release
      if ((path === '/download/ACR-Daily.exe' || path === '/download/ACR-Daily.exe.sha256') && /^https:/.test(downloadUrl(env))) {
        return Response.redirect(downloadUrl(env) + (path.endsWith('.sha256') ? '.sha256' : ''), 302);
      }
      if (path === '/api/runs' && req.method === 'POST') return submitRun(req, env, ctx);
      if (path.startsWith('/api/admin/')) return admin(req, env, path);

      // ---- Steam sign-in
      if (path === '/auth/steam/start') {
        const state = url.searchParams.get('state') || '';
        if (!/^[\w-]{16,64}$/.test(state)) return err('bad state');
        await env.DB.prepare('DELETE FROM logins WHERE created < ?').bind(Date.now() - 600000).run();
        await env.DB.prepare('INSERT OR IGNORE INTO logins (state, created) VALUES (?, ?)').bind(state, Date.now()).run();
        return Response.redirect(steamLoginUrl(url.origin, state), 302);
      }
      if (path === '/auth/steam/callback') {
        const state = url.searchParams.get('state') || '';
        const pending = await env.DB.prepare('SELECT state FROM logins WHERE state = ? AND token IS NULL').bind(state).first();
        if (!pending) return page('Sign-in expired', 'Start again from the ACR Daily app.');
        const steamId = await verifySteam(url);
        if (!steamId) return page('Steam sign-in failed', 'Please try again from the app.');
        const prof = await completeLogin(env, state, steamId);
        return page(`Signed in as ${escapeHtml(prof.name)}`, 'You can close this tab and go back to ACR Daily.');
      }
      if (path === '/auth/dev' && env.DEV_LOGIN === '1') {   // local testing only (wrangler dev)
        const state = url.searchParams.get('state') || '';
        await env.DB.prepare('INSERT OR IGNORE INTO logins (state, created) VALUES (?, ?)').bind(state, Date.now()).run();
        const prof = await completeLogin(env, state, url.searchParams.get('steamId') || '76561190000000001',
          url.searchParams.get('name') || 'Dev Driver');
        return page(`Signed in as ${escapeHtml(prof.name)}`, 'dev login');
      }
      if (path === '/auth/poll') {
        const state = url.searchParams.get('state') || '';
        const row = await env.DB.prepare('SELECT * FROM logins WHERE state = ? AND token IS NOT NULL').bind(state).first();
        if (!row) return json({ waiting: true });
        await env.DB.prepare('DELETE FROM logins WHERE state = ?').bind(state).run();
        return json({ token: row.token, steamId: row.steam_id, name: row.name });
      }
      if (path === '/auth/logout' && req.method === 'POST') {
        const m2 = (req.headers.get('Authorization') || '').match(/^Bearer\s+([0-9a-f]{64})$/);
        if (m2) await env.DB.prepare('DELETE FROM sessions WHERE token_hash = ?').bind(await sha256(m2[1])).run();
        return json({ ok: true });
      }
      return err('not found', 404);
    } catch (e) {
      console.error(e);
      return err('server error', 500);
    }
  },
};
