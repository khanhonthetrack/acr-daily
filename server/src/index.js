// ACR Daily server: Cloudflare Worker + D1 (+ R2 for the run traces, src/traces.js).
//
// Two dailies a day (slot 1 and 2): each its own stage, a random car, its own board.
// Public:  GET  /                         website (both dailies, live map, boards, past days)
//          GET  /api/challenges/today     today's two challenges (stage, car, route)
//          GET  /api/challenge?date=&slot= one daily (slot 1 by default; /api/challenge/today too)
//          GET  /api/leaderboard?date=&slot= best valid run per driver
//          GET  /api/live?date=&slot=     drivers on the stage right now (slot=all: both dailies; POST: the app's position, 2 s)
//          GET  /api/cars                 every car the random pick chooses from
//          GET  /api/runs/:id/trace       a finished run's trace (the app uses #1's for the live gap)
//          GET  /api/version              newest app version + download link
//          GET  /discord                  -> the Discord invite (the server widget's, else DISCORD_URL)
//          GET  /brand/acr-daily-icon-512.png  the logo as a PNG (the Discord bot's avatar)
// Auth:    GET  /auth/steam/start?state=  -> Steam sign-in; /auth/steam/callback; GET /auth/poll?state=
//          POST /auth/logout
// Player:  POST /api/runs                 submit a run (Bearer token from sign-in)
// Admin:   (Bearer ADMIN_KEY) POST /api/admin/route | /api/admin/pool | /api/admin/schedule |
//          /api/admin/runs/:id/reject | /api/admin/runs/:id/fix | /api/admin/discord |
//          /api/admin/ban | /api/admin/move-traces, GET /api/admin/state
// Discord: a webhook bot keeps a live board and posts each day's results + report (src/discord.js; cron every minute)
// Runs, live positions and routes only come from apps >= MIN_APP_VERSION (wrangler.toml); older ones get 426.
// Boards, the week and the stage stats are built once and kept for a while (src/cache.js), not built per request.

import { steamLoginUrl, steamProfile, verifySteam } from './steam.js';
import { PENALTY_MS, routeInfo, validateRun } from './validate.js';
import { sections, tempProfile, timesAt } from './realism.js';
import { sitePage } from './site.js';
import { viewerPage } from './viewer.js';
import { statsPage } from './statspage.js';
import { dailyStats, runProfile } from './stats.js';
import { isoWeek, POINTS, weekDays, weekStandings, weekStart } from './week.js';
import { weekPage } from './weekpage.js';
import { guidePage } from './guidepage.js';
import { labMapPage } from './labmap.js';
import { discordInvite, downloadUrl, latestVersion, releasePage, releaseSha256 } from './release.js';
import { ICON_PNG } from './brandpng.js';
import { CARS, carByName } from './cars.js';
import { countryCode } from './countries.js';
import { describe, pickConditions, stageParts, TIMES, WEATHER } from './conditions.js';
import { menuName } from './stages.js';
import { cached, dropCached, dropExpired } from './cache.js';
import { getTrace, packTrace, putTrace, traceText, trimTraces } from './traces.js';
import { boardMessage, dayMessage, webhook } from './discord.js';
import { eventsApi, syncEvents } from './discordevents.js';
import { faqApi, syncFaq } from './discordfaq.js';
import { FAVICON, logoSvg } from './logo.js';
import { officialDay, WEEKEND_RULES } from './weekend.js';

const DAILIES = 2;                           // challenges per day
const MAX_BODY = 2_000_000;
const SPLITS = [0.25, 0.5, 0.75];          // split points, as fractions of the route (the finish is the 4th)
const MAX_RUNS_PER_DAY = 300;
const LATE_SUBMIT_MS = 30 * 60 * 1000;   // a run finished just before midnight may arrive a bit after

/** How often the app (0.15.1 on) sends its position and asks for others' positions and the boards, in seconds:
 *  wrangler.toml vars, so the requests a day can be tuned without a new app (Workers Free allows 100,000 a day).
 *  liveSendS: own position while on stage; livePollS: others' while on the daily's stage (start line, results);
 *  liveIdleS: others' anywhere else; boardS / boardIdleS: today's boards with the game running / not running. */
function timing(env) {
  const n = (v, d) => (Number(v) >= 1 ? Number(v) : d);
  return { liveSendS: n(env.LIVE_SEND_S, 5), livePollS: n(env.LIVE_POLL_S, 5), liveIdleS: n(env.LIVE_IDLE_S, 15),
    boardS: n(env.BOARD_S, 120), boardIdleS: n(env.BOARD_IDLE_S, 300) };
}

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
  const parts = stageParts(pick.track);
  const official = officialDay(env, date);
  return {
    id: `${date}/${slot}`,
    date,
    slot,
    track: pick.track,                                 // the game's telemetry name (the app matches runs on it)
    ...parts,                                          // rally, stageName (short: "La Bollène"), surface
    menuName: (route && menuName(route.stage_id)) || parts.stageName,   // "La Bollène-Vésubie - Peïra Cava"
    stageId: route ? route.stage_id || null : null,   // the game's id, for the app's "Drive daily" set-up
    car: pick.car,
    carId: car ? car.id : null,
    carClass: car ? car.cls : null,
    carAliases: car ? [car.telemetry, ...(car.aliases || [])].filter(Boolean) : [],   // the name the game reports first
    ...describe(pick.weather, pick.time),     // conditions: weather, weatherLabel, time, timeLabel
    mode: official ? 'weekend' : 'single',     // the game mode the app sets up (weekend: the game's own result counts)
    ...(official ? { weekend: WEEKEND_RULES } : {}),
    penaltyMs: official ? 0 : PENALTY_MS,      // per reset the app counts
    splits: SPLITS,
    timing: timing(env),
    startsAt: start,
    endsAt: start + 86400000,
    lengthM: route ? Math.round(route.length) : null,
    route: route ? JSON.parse(route.points) : null,
  };
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

/** Each driver's counted run for a daily: the FIRST one.
 *  -> {counted: Map steamId -> {run|null, dnf: reason|null}, runCount: every run of the daily, practice too} */
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
  return { counted: out, runCount: runs.length };
}

// ------------------------------------------------------------------ kept copies (src/cache.js)
// A new run, a first start, a report or an admin action drops the copies it changes, so a copy only has to expire for
// what changes by itself: a start that never finishes becomes a DNF after an hour, a driver's name or flag. While a
// day can still change, a board is kept 5 minutes, the week 15 and the stage stats 10; a closed day's copies 30 days.

const FRESH_MS = 26 * 3600000;   // late runs arrive until 00:30, abandoned starts settle by 01:00
const keepFor = (date, ms) => (Date.now() - dayStart(date) < FRESH_MS ? ms : 30 * 86400000);
const boardKey = (date, slot) => `board:${date}/${slot}`;
const statsKey = (date, slot) => `stats:${date}/${slot}`;
const weekKey = (date) => `week:${weekStart(date)}@${dayOf(Date.now())}`;   // today in it: "future" days come in
/** Only days ACR Daily had are kept: any other date asked for is built (empty) each time, never stored. */
const keep = (env, date, key, ms, build) =>
  (date >= FIRST_WEEK && date <= dayOf(Date.now()) ? cached(env, key, ms, build) : build());

/** A daily's board: best valid run per driver (buildLeaderboard), from the kept copy when there is one. */
const leaderboard = (env, date, slot = 1) =>
  keep(env, date, boardKey(date, slot), keepFor(date, 5 * 60000), () => buildLeaderboard(env, date, slot));
/** The week's hall of fame that the date is in. */
const weekCached = (env, date) =>
  keep(env, date, weekKey(date), keepFor(weekDays(weekStart(date))[6], 15 * 60000), () => weekData(env, date));
/** A daily's stage statistics (null: no stage). */
const statsCached = (env, date, slot) =>
  keep(env, date, statsKey(date, slot), keepFor(date, 10 * 60000), () => stageStats(env, date, slot));
/** A daily's runs changed: its board and the week are built again on the next request (its stats in their time;
 *  withStats: now). */
const dropDaily = (env, date, slot, withStats = false) =>
  dropCached(env, [boardKey(date, slot), weekKey(date), ...(withStats ? [statsKey(date, slot)] : [])]);

async function buildLeaderboard(env, date, slot = 1) {
  const { counted, runCount } = await countedRuns(env, date, slot);
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
  const stats = { attempts: runCount, drivers: entries.length,
    dnfs: entries.filter((e) => e.status === 'dnf').length };   // DNFs on the board (first runs only)
  return { date, slot, entries, stats };
}

// ------------------------------------------------------------------ weekly hall of fame

const FIRST_WEEK = '2026-09-28';   // the week ACR Daily started (no navigation before it)

/** The week's hall of fame; with `until`, as it stood at the end of that day (the Discord bot's day wrap-up).
 *  The dailies' stages and cars come from the schedule in two queries for the whole week (Workers Free allows 50
 *  queries a request), their boards from the kept copies. */
async function weekData(env, date, until = null) {
  const start = weekStart(date), today = dayOf(Date.now());
  const last = until && until < today ? until : today;
  const days = weekDays(start), stages = [];
  const { results: picks } = await env.DB.prepare('SELECT date, slot, track, car FROM schedule WHERE date BETWEEN ? AND ?')
    .bind(days[0], days[6]).all();
  const stageIds = new Map((await env.DB.prepare('SELECT track, stage_id FROM routes').all()).results
    .map((r) => [r.track, r.stage_id]));
  for (const d of days) {
    for (let slot = 1; slot <= DAILIES; slot++) {
      if (d > last) { stages.push({ date: d, slot, future: true, board: null }); continue; }
      let pick = picks.find((p) => p.date === d && p.slot === slot);
      if (!pick) {   // nobody asked for that daily on its day: its pick is made (and stored) now
        const ch = await challengeFor(env, d, slot);
        pick = ch && { track: ch.track, car: ch.car };
      }
      if (!pick) { stages.push({ date: d, slot, board: [] }); continue; }
      const parts = stageParts(pick.track);
      const b = await leaderboard(env, d, slot);
      stages.push({ date: d, slot, stageName: menuName(stageIds.get(pick.track)) || parts.stageName || pick.track,
        rally: parts.rally, car: pick.car, board: b.entries });
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
    // each run's profile (src/stats.js runProfile, stored when it arrived); only runs from before have to be read
    // from their trace, which costs far more CPU
    const { results } = await env.DB.prepare(
      `SELECT r.id, r.total_ms, r.clock_ms, r.resets, r.profile, CASE WHEN r.profile IS NULL THEN r.trace END AS trace,
              r.sections, r.jumps, p.name, p.country
         FROM runs r JOIN players p ON p.steam_id = r.steam_id WHERE r.id IN (${part.map(() => '?').join(',')})`).bind(...part).all();
    const traces = await Promise.all(results.map((r) => (r.profile ? null : getTrace(env, r))));
    results.forEach((r, i) => {
      runs.push({ runId: r.id, name: r.name, country: r.country, totalMs: r.total_ms, clockMs: r.clock_ms, resets: r.resets,
        profile: r.profile ? JSON.parse(r.profile) : null, trace: traces[i] || [],
        sections: r.sections ? JSON.parse(r.sections) : null, jumps: r.jumps ? JSON.parse(r.jumps) : null });
    });
  }
  return { challenge: ch, ...dailyStats(ch.route, runs, board.entries) };
}

// ------------------------------------------------------------------ Discord bot (src/discord.js)

/** Each daily's heading for Discord, without loading its route: stage (menu name), car, conditions. */
async function dailyHeads(env, date) {
  const out = [];
  for (let slot = 1; slot <= DAILIES; slot++) {
    let s = await env.DB.prepare('SELECT track, car, weather, time FROM schedule WHERE date = ? AND slot = ?').bind(date, slot).first();
    if (!s) {   // the day's picks are stored by the first request for them
      const ch = await challengeFor(env, date, slot);
      if (!ch) continue;
      s = { track: ch.track, car: ch.car, weather: ch.weather, time: ch.time };
    }
    const r = await env.DB.prepare('SELECT stage_id, length FROM routes WHERE track = ?').bind(s.track).first();
    const parts = stageParts(s.track);
    out.push({ slot, track: s.track, car: s.car, menuName: (r && menuName(r.stage_id)) || parts.stageName,
      rally: parts.rally, surface: parts.surface, lengthM: r ? Math.round(r.length) : null,
      ...describe(s.weather, s.time) });
  }
  return out;
}

const discordGet = (env, key) => env.DB.prepare('SELECT message_id AS id, hash, date, updated FROM discord WHERE key = ?').bind(key).first();
const discordSet = (env, key, id, hash, date) => env.DB.prepare(
  'INSERT OR REPLACE INTO discord (key, message_id, hash, date, updated) VALUES (?, ?, ?, ?, ?)').bind(key, id, hash, date, Date.now()).run();

// the day before is wrapped up at 01:05 UTC: by then late runs (30 min) and abandoned starts (1 h) are settled
const WRAP_AFTER_MS = 65 * 60000;

/** One minute of the bot: the day before's wrap-up once it is settled, then today's live board (edited in place,
 *  re-posted below anything new). -> what it did, for the logs and the admin endpoint. */
async function discordTick(env, now = Date.now(), force = false) {
  const hook = webhook(env.DISCORD_WEBHOOK_URL, fetch, env.DEV_LOGIN === '1');
  if (!hook) return { skipped: 'DISCORD_WEBHOOK_URL is not set (or not a Discord webhook URL)' };
  const site = (env.SITE_URL || '').replace(/\/+$/, '');
  const today = dayOf(now), yday = dayOf(now - 86400000);
  const board = await discordGet(env, 'board');
  let moveBoard = !board || !board.id || board.date !== today;
  const did = {};
  if (now - dayStart(today) > WRAP_AFTER_MS && !await discordGet(env, 'day:' + yday)) {
    const stages = [];
    for (const head of await dailyHeads(env, yday)) {
      stages.push({ slot: head.slot, head, board: (await leaderboard(env, yday, head.slot)).entries });
    }
    let id = null;
    if (stages.some((s) => s.board.length)) {
      const r = await hook.post(dayMessage({ date: yday, stages, week: await weekData(env, yday, yday), site }));
      if (!r.ok) return { error: `posting the ${yday} results: Discord answered ${r.status}` };
      id = r.id;
      moveBoard = true;
      did.wrapped = yday;
    }
    await discordSet(env, 'day:' + yday, id, null, yday);
  }
  const stages = [];
  for (const head of await dailyHeads(env, today)) {
    stages.push({ slot: head.slot, head, board: (await leaderboard(env, today, head.slot)).entries,
      live: (await getLive(env, today, head.slot)).drivers });
  }
  const msg = boardMessage({ date: today, stages, site });
  const hash = await sha256(JSON.stringify(msg));
  if (!moveBoard && board.hash === hash && !force) return { ...did, board: 'unchanged' };   // force: re-send (a deleted board is re-posted)
  if (!moveBoard) {
    const r = await hook.edit(board.id, msg);
    if (r.ok) {
      await discordSet(env, 'board', board.id, hash, today);
      return { ...did, board: 'edited' };
    }
    if (r.status !== 404) return { ...did, error: `editing the live board: Discord answered ${r.status}` };
  } else if (board && board.id) {
    await hook.remove(board.id);   // the live board moves below what was just posted
  }
  const r = await hook.post(msg);
  if (!r.ok || !r.id) return { ...did, error: `posting the live board: Discord answered ${r.status}` };
  await discordSet(env, 'board', r.id, hash, today);
  return { ...did, board: 'posted' };
}

/** The Discord server Events for the two dailies (src/discordevents.js); off until DISCORD_BOT_TOKEN is set. */
async function discordEvents(env, now = Date.now()) {
  const api = eventsApi(env.DISCORD_BOT_TOKEN, env.DISCORD_GUILD_ID);
  if (!api) return { skipped: 'DISCORD_BOT_TOKEN (or DISCORD_GUILD_ID) is not set' };
  return syncEvents({ api, now, site: (env.SITE_URL || '').replace(/\/+$/, ''), image: 'data:image/png;base64,' + ICON_PNG,
    heads: (date) => dailyHeads(env, date),
    store: { get: (key) => discordGet(env, key), set: (key, id, state, date) => discordSet(env, key, id, state, date) } });
}

/** The FAQ message in #faq (src/discordfaq.js), as the bot; off until DISCORD_BOT_TOKEN is set. */
async function discordFaq(env) {
  const api = faqApi(env.DISCORD_BOT_TOKEN, env.DISCORD_GUILD_ID);
  if (!api) return { skipped: 'DISCORD_BOT_TOKEN (or DISCORD_GUILD_ID) is not set' };
  return syncFaq({ api, site: (env.SITE_URL || '').replace(/\/+$/, ''), hashOf: sha256,
    store: { get: (key) => discordGet(env, key), set: (key, id, hash) => discordSet(env, key, id, hash, dayOf(Date.now())) } });
}

// ------------------------------------------------------------------ live positions

const LIVE_STALE_MS = 15000;      // a driver disappears from the map 15 s after their last update
const LIVE_KEEP_DONE_MS = 60000;  // a finish / DNF stays on the map for a minute

async function postLive(req, env) {
  const player = await playerFrom(req, env);
  if (!player) return err('sign in with Steam first', 401);
  const b = await req.json().catch(() => null);
  const c = b && parseChallengeId(b.challengeId);
  if (!c || c.date !== dayOf(Date.now())) return err('bad challenge');
  // an old app's start would be recorded as the daily's first attempt, and its run then refused
  const old = tooOld(env, req, null, c.date);
  if (old) return old;
  const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  const state = ['live', 'finished', 'dnf'].includes(b.state) ? b.state : 'live';
  if (state === 'live') {   // the first start of this daily: the run that started then is the one that counts
    const ins = await env.DB.prepare('INSERT OR IGNORE INTO attempts (steam_id, date, slot, started) VALUES (?, ?, ?, ?)')
      .bind(player.steam_id, c.date, c.slot, startedMs(b.startedAt, Date.now())).run();
    if (ins.meta.changes) await dropCached(env, [boardKey(c.date, c.slot)]);   // a start that never ends is a DNF on it
  }
  if (b.country) await setCountry(env, player.steam_id, b.country);
  await env.DB.prepare(
    `INSERT INTO live (steam_id, date, slot, x, z, progress, total_ms, resets, state, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (steam_id, date, slot) DO UPDATE SET x = excluded.x, z = excluded.z, progress = excluded.progress,
       total_ms = excluded.total_ms, resets = excluded.resets, state = excluded.state, updated = excluded.updated`)
    .bind(player.steam_id, c.date, c.slot, n(b.x), n(b.z), Math.max(0, Math.min(1, n(b.progress))),
      Math.round(n(b.totalMs)), n(b.resets) | 0, state, Date.now()).run();
  // an app showing the others on its displays gets them with its own position: one request, not two
  return json(b.others ? { ok: true, drivers: (await getLive(env, c.date, c.slot)).drivers } : { ok: true });
}

/** Who is on a daily's stage right now; slot null = both dailies in one go (the website), each driver with their slot. */
async function getLive(env, date, slot = null) {
  const now = Date.now();
  const bySlot = slot == null ? [] : [slot];
  const { results } = await env.DB.prepare(
    `SELECT l.steam_id AS steamId, l.slot, p.name, p.country, p.avatar, l.x, l.z, l.progress, l.total_ms AS totalMs, l.resets,
            l.state, l.updated
       FROM live l JOIN players p ON p.steam_id = l.steam_id
      WHERE l.date = ?${bySlot.length ? ' AND l.slot = ?' : ''} AND p.banned = 0
        AND ((l.state = 'live' AND l.updated > ?) OR (l.state != 'live' AND l.updated > ?))
      ORDER BY l.progress DESC`).bind(date, ...bySlot, now - LIVE_STALE_MS, now - LIVE_KEEP_DONE_MS).all();
  return { date, slot, now, drivers: results };
}

// ------------------------------------------------------------------ app versions
// The board only takes runs judged the same way: from MIN_APP_VERSION of the app on (for dailies from MIN_APP_FROM on,
// so a day already under way keeps the apps it started with). Older apps get 426 and their UPDATE bar.
// Public builds (0.0.1 on) say "public" in their User-Agent ("ACR-Daily/0.0.1 public"). The test builds before them
// were numbered 0.1.0 to 0.15.1, above the public ones, so they are told apart by that and refused like old apps.

const verParts = (v) => String(v || '').split('.').map((x) => parseInt(x, 10) || 0);

/** '0.14.1' < '0.14.2' < '0.15' (missing parts count as 0). */
export function olderThan(v, min) {
  const a = verParts(v), b = verParts(min);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) < (b[i] || 0);
  }
  return false;
}

/** The app's version: the one in the run, else its User-Agent ("ACR-Daily/0.0.1 public"); null if neither. */
export function appVersionOf(req, body) {
  if (body && typeof body.appVersion === 'string' && /^\d+(\.\d+)*$/.test(body.appVersion)) return body.appVersion;
  const m = (req.headers.get('User-Agent') || '').match(/ACR-Daily\/(\d+(?:\.\d+)*)/);
  return m ? m[1] : null;
}

/** A public build of the app (0.0.1 on), not one of the test builds before it. */
export const publicBuild = (req) => /^ACR-Daily\/[\d.]+ public\b/.test(req.headers.get('User-Agent') || '');

/** The 426 answer for an app too old to send this (date = the daily's, null = anything else), or null if it may. */
export function tooOld(env, req, body, date) {
  const min = env.MIN_APP_VERSION;
  if (!min || (date && env.MIN_APP_FROM && date < env.MIN_APP_FROM)) return null;
  const v = appVersionOf(req, body);
  // "invalid" makes the test builds up to 0.14.1 drop the run from their retry queue (it would never be taken)
  if (!publicBuild(req)) {
    return err(`invalid run: this ACR Daily (${v || 'unknown version'}) is a test build from before the public release. ` +
      `Download the app at ${(env.SITE_URL || '').replace(/^https?:\/\//, '') || 'the website'}.`, 426);
  }
  if (v && !olderThan(v, min)) return null;
  return err(`invalid run: ACR Daily ${v || '(unknown version)'} is too old for the leaderboard. ` +
    `Update to ${min} or newer (UPDATE button in the app, or the website).`, 426);
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
<title>ACR Daily</title><link rel="icon" href="${FAVICON}"><style>.brandmark{display:block;height:96px;width:auto;margin:12px auto 4px}</style>
<body style="background:#0A0A0C;color:#FFFFFF;font:18px system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;padding:16px;border-top:4px solid #E30613">${logoSvg()}<h1 style="margin:16px 0 8px">${title}</h1><p style="color:#D8D8DE">${text}</p></div>`);

const escapeHtml = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ------------------------------------------------------------------ handlers

async function submitRun(req, env) {
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
  const old = tooOld(env, req, sub, date);
  if (old) return old;
  const ch = await challengeFor(env, date, slot);
  if (!ch || !ch.route) return err('no challenge for that day', 409);
  if (sub.track !== ch.track || sub.car !== ch.car) return err('invalid: not the challenge stage/car', 422);
  const count = await env.DB.prepare('SELECT COUNT(*) AS n FROM runs WHERE steam_id = ? AND date = ?')
    .bind(player.steam_id, date).first();
  if (count.n >= MAX_RUNS_PER_DAY) return err('too many runs today', 429);

  const v = validateRun(sub, routeInfo(ch.route), ch.penaltyMs, ch.mode === 'weekend');
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
                       started_at, sections, checks, splits, temps, jumps)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(date, slot, player.steam_id, ch.track, ch.car, status, reason, v.ok ? v.clockMs : sub.clockMs | 0,
      v.ok ? v.resets : sub.resets | 0, v.ok ? v.totalMs : null, JSON.stringify(flags),
      String(sub.appVersion || '').slice(0, 20), now, startedMs(sub.startedAt, now),
      secs ? JSON.stringify(secs) : null, v.checks ? JSON.stringify(v.checks) : null,
      splits ? JSON.stringify(splits) : null, temps ? JSON.stringify(temps) : null,
      status === 'finished' ? JSON.stringify(cleanJumps(sub.jumps, v.clockMs, routeInfo(ch.route).length)) : null)
    .run();
  const id = res.meta.last_row_id;
  await setCountry(env, player.steam_id, sub.country);
  await dropDaily(env, date, slot);     // a first run goes on the board; any run changes its run count
  const mine = (await countedRuns(env, date, slot)).counted.get(player.steam_id);
  const counted = !!(mine && mine.run && mine.run.id === id);
  // only a counted run keeps its trace and its profile for the stats page: practice runs are on no board, and the
  // database has 500 MB on the free plan (a trace is ~100 KB)
  if (counted && status === 'finished') {
    await storeTrace(env, id, JSON.stringify(v.trace), { profile: JSON.stringify(runProfile(v.trace, ch.route)) });
  }
  if (!v.ok) return err('invalid: ' + v.reason + (counted ? '' : ' (practice run)'), 422);
  let rank = null;
  if (counted && status === 'finished') {
    const me = (await leaderboard(env, date, slot)).entries.find((e) => e.runId === id);
    rank = me ? me.rank : null;
  }
  return json({ ok: true, id, status, totalMs: v.totalMs, rank, counted, review: flags.length > 0 });
}

/** Keep a run's trace (JSON text): in R2 when there is a bucket, else (or if R2 fails) gzipped in its row
 *  (src/traces.js). profile: its stats profile, stored with it. fromRow: the row held the trace before (an older run,
 *  move-traces, fix-run): that copy is replaced. -> true when the trace went to R2. */
async function storeTrace(env, id, text, { profile, fromRow = false } = {}) {
  let inRow = null;
  if (env.TRACES) {
    try {
      await putTrace(env, id, text);
    } catch (e) {
      console.error('trace to R2', id, e);
      inRow = await packTrace(text);
    }
  } else inRow = await packTrace(text);
  if (inRow != null || fromRow || profile !== undefined) {
    const sets = ['trace = ?'], args = [inRow];
    if (profile !== undefined) { sets.push('profile = ?'); args.push(profile); }
    await env.DB.prepare(`UPDATE runs SET ${sets.join(', ')} WHERE id = ?`).bind(...args, id).run();
  }
  return inRow == null;
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
    const o = await env.DB.prepare('SELECT id, trace, sections FROM runs WHERE id = ?').bind(other.runId).first();
    compare = { id: other.runId, name: other.name, rank: other.rank, totalMs: other.totalMs, resets: other.resets,
      trace: (await getTrace(env, o)) || [], sections: o.sections ? JSON.parse(o.sections) : null };
  }
  const ch = await challengeFor(env, r.date, r.slot || 1);
  return {
    id: r.id, date: r.date, slot: r.slot || 1, name: r.name, country: r.country, avatar: r.avatar, steamId: r.steam_id, track: r.track,
    menuName: ch ? ch.menuName : null, car: r.car,
    status: r.status, reason: r.reason, clockMs: r.clock_ms, resets: r.resets, totalMs: r.total_ms,
    rank: me ? me.rank : null, flags: JSON.parse(r.flags || '[]'), reports: r.reports,
    review: JSON.parse(r.flags || '[]').length > 0 || r.reports >= REVIEW_REPORTS,
    checks: r.checks ? JSON.parse(r.checks) : null, sections: r.sections ? JSON.parse(r.sections) : null,
    trace: (await getTrace(env, r)) || [], route: ch ? ch.route : null, penaltyMs: ch ? ch.penaltyMs : PENALTY_MS,
    official: !!(ch && ch.mode === 'weekend'), compare,
  };
}

async function reportRun(req, env, id) {
  const run = await env.DB.prepare("SELECT id, date, slot FROM runs WHERE id = ? AND status = 'finished'").bind(id).first();
  if (!run) return err('not found', 404);
  const body = await req.json().catch(() => ({}));
  const ip = req.headers.get('CF-Connecting-IP') || 'local';
  const who = await sha256(ip + '|' + (env.ADMIN_KEY || ''));
  await env.DB.prepare('INSERT OR IGNORE INTO reports (run_id, who, reason, created) VALUES (?, ?, ?, ?)')
    .bind(id, who, String(body.reason || '').slice(0, 300), Date.now()).run();
  await dropCached(env, [boardKey(run.date, run.slot || 1)]);   // enough reports mark it UNDER REVIEW on the board
  const c = await env.DB.prepare('SELECT COUNT(*) AS n FROM reports WHERE run_id = ?').bind(id).first();
  return json({ ok: true, reports: c.n });
}

// ------------------------------------------------------------------ routes from players
// The app records every clean run (no resets) of a stage. If that stage has no route yet, the first one
// that passes these checks becomes its route and the stage joins the daily rotation (random car).

async function listRoutes(env) {
  const { results } = await env.DB.prepare('SELECT track, stage_id AS stageId, length, contributed_by FROM routes ORDER BY track').all();
  // estimated = taken from the game's files; the app still sends its first clean run of those stages
  return results.map(({ contributed_by, ...r }) => ({ ...r, length: Math.round(r.length), estimated: contributed_by === 'game-files' }));
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

/** The route already stored for the stage a contribution was driven on, whatever name the game reported: the same
 *  start line and finish (variants share a start or a finish, never both) and about the same length. The game's
 *  stage id only breaks a tie: it comes from the save, which can still hold the set-up of another stage. */
export function sameStage(b, routes) {
  const pts = b.points, len = routeInfo(pts).length;
  const near = (p, q, m) => Math.hypot(p[0] - q[0], p[1] - q[1]) <= m;
  const hits = routes.filter((r) => {
    const rp = JSON.parse(r.points);
    return near(pts[0], rp[0], 60) && near(pts[pts.length - 1], rp[rp.length - 1], 400) && Math.abs(r.length - len) <= 0.15 * r.length;
  });
  return hits.find((r) => b.stageId && r.stage_id === b.stageId) || hits[0] || null;
}

async function contributeRoute(req, env) {
  const player = await playerFrom(req, env);
  if (!player) return err('sign in with Steam first', 401);
  if (player.banned) return err('this account is banned', 403);
  const old = tooOld(env, req, null, null);     // older apps miss small resets: their line could include one
  if (old) return old;
  const b = await req.json().catch(() => null);
  const bad = checkContribution(b);
  if (bad) return err('route refused: ' + bad, 422);
  let track = b.track.trim();
  const info = routeInfo(b.points);
  // a stage whose telemetry name was only guessed (route from the game's files) is reported under another name:
  // the run still goes to that stage, under the name the dailies already use
  const { results: all } = await env.DB.prepare('SELECT track, points, length, stage_id, contributed_by FROM routes').all();
  if (!all.some((r) => r.track === track)) {
    const same = sameStage(b, all);
    if (same) track = same.track;
  }
  const res = await env.DB.prepare(
    `INSERT OR IGNORE INTO routes (track, points, length, updated, stage_id, contributed_by) VALUES (?, ?, ?, ?, ?, ?)`)
    .bind(track, JSON.stringify(b.points), info.length, Date.now(), b.stageId || null, player.steam_id).run();
  if (!res.meta.changes) {
    // a route taken from the game's files (start line to stop control) gives way to the first driven one,
    // which ends exactly where the stage clock stops
    const up = await env.DB.prepare(
      `UPDATE routes SET points = ?, length = ?, updated = ?, contributed_by = ?, stage_id = COALESCE(stage_id, ?)
        WHERE track = ? AND contributed_by = 'game-files'`)
      .bind(JSON.stringify(b.points), info.length, Date.now(), player.steam_id, b.stageId || null, track).run();
    if (up.meta.changes) return json({ ok: true, added: true, replaced: 'estimated route', track, length: Math.round(info.length) });
    return json({ ok: true, added: false, reason: 'this stage already has a route' });
  }
  await env.DB.prepare("INSERT OR IGNORE INTO pool (track, car, enabled) VALUES (?, '*', 1)").bind(track).run();
  return json({ ok: true, added: true, track, length: Math.round(info.length) });
}

/** A finished run with its resets corrected (e.g. ones an older app missed). body: {resets, at?, dryRun?}
 *  at = the stage clock (ms) of each reset: the trace's reset count and the split times then include them
 *  too; without it only the total changes. Section times are stage clock only, so they stay. */
export function fixedRun(run, route, body) {
  const resets = Number(body.resets);
  if (!Number.isInteger(resets) || resets < 0 || resets > 99) return { error: 'resets: a whole number from 0 to 99' };
  const at = body.at == null ? null : body.at;
  if (at != null && (!Array.isArray(at) || at.length !== resets || !at.every((t) => Number.isFinite(t) && t >= 0 && t <= run.clock_ms))) {
    return { error: 'at: the stage clock (ms) of each reset, one per reset, within the run' };
  }
  const out = { resets, total_ms: run.clock_ms + resets * PENALTY_MS };
  if (at) {
    const trace = JSON.parse(run.trace || '[]'), when = [...at].sort((a, b) => a - b);
    for (const s of trace) s[4] = when.filter((t) => t <= s[0]).length;
    out.trace = JSON.stringify(trace);
    if (route) out.splits = JSON.stringify(timesAt(trace, { points: route }, SPLITS, PENALTY_MS));
  }
  return out;
}

async function fixRun(env, id, body) {
  const run = await env.DB.prepare("SELECT id, date, slot, clock_ms, resets, total_ms, splits, trace FROM runs WHERE id = ? AND status = 'finished'")
    .bind(id).first();
  if (!run) return err('no finished run with that id', 404);
  const ch = await challengeFor(env, run.date, run.slot || 1);
  if (ch && ch.mode === 'weekend') return err('this daily counts the game\'s own result: its resets add no time', 409);
  const inRow = !!run.trace;
  if (body.at != null) {   // only reset times change the trace
    run.trace = await traceText(env, run);
    if (!run.trace) return err('this run has no trace (practice runs, and after 14 days all but the top 3, keep none): '
      + 'give the number of resets without their times', 409);
  }
  const f = fixedRun(run, ch ? ch.route : null, body);
  if (f.error) return err(f.error);
  const before = { resets: run.resets, totalMs: run.total_ms, splits: run.splits ? JSON.parse(run.splits) : null };
  const after = { resets: f.resets, totalMs: f.total_ms, splits: f.splits ? JSON.parse(f.splits) : before.splits };
  if (!body.dryRun) {
    const cols = ['resets', 'total_ms', 'splits'].filter((k) => f[k] !== undefined);
    await env.DB.prepare(`UPDATE runs SET ${cols.map((k) => k + ' = ?').join(', ')} WHERE id = ?`)
      .bind(...cols.map((k) => f[k]), id).run();
    if (f.trace !== undefined) await storeTrace(env, id, f.trace, { fromRow: inRow });
    await dropDaily(env, run.date, run.slot || 1, true);
  }
  // its place on the day's board with the new total (null for a practice run, which is not on the board)
  const b = await leaderboard(env, run.date, run.slot || 1);
  const counted = b.entries.some((e) => e.runId === id);
  const rank = counted ? 1 + b.entries.filter((e) => e.status === 'finished' && e.runId !== id && e.totalMs < f.total_ms).length : null;
  return json({ ok: true, id, dryRun: !!body.dryRun, before, after, rank });
}

// admin calls that change nothing the kept boards, week and stats are built from, or drop just their day's copies
const KEEPS_CACHE = /^\/api\/admin\/(discord|move-traces|runs\/\d+\/(reject|fix))$/;

async function admin(req, env, path) {
  if (!isAdmin(req, env)) return err('not allowed', 403);
  const res = await adminCall(req, env, path);
  // a route, the schedule, a ban... can show on any of them: all built again on the next request
  if (req.method === 'POST' && res.ok && !KEEPS_CACHE.test(path)) await dropCached(env);
  return res;
}

async function adminCall(req, env, path) {
  const body = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  if (path === '/api/admin/move-traces') {
    // traces kept in rows: to R2 when there is a bucket, else gzipped where they are (older runs hold plain JSON);
    // a few runs per call (admin.py move-traces calls until none are left)
    const where = env.TRACES ? 'trace IS NOT NULL' : "trace IS NOT NULL AND trace NOT LIKE 'gz:%'";
    const { results } = await env.DB.prepare(`SELECT id, trace FROM runs WHERE ${where} LIMIT ?`)
      .bind(Math.min(Math.max(Number(body.limit) || 20, 1), 40)).all();
    let moved = 0;
    for (const r of results) {
      const toR2 = await storeTrace(env, r.id, await traceText(env, r), { fromRow: true });
      if (toR2 || !env.TRACES) moved++;
    }
    const left = await env.DB.prepare(`SELECT COUNT(*) AS n FROM runs WHERE ${where}`).first();
    return json({ ok: true, moved, left: left.n, to: env.TRACES ? 'R2' : 'the database, gzipped' });
  }
  if (path === '/api/admin/route') {
    const pts = body.points;
    if (!body.track || !Array.isArray(pts) || pts.length < 20) return err('need track and points');
    const info = routeInfo(pts);
    const sid = body.stageId && /^[A-Za-z0-9]{6,60}$/.test(body.stageId) ? body.stageId : null;
    // source 'game-files': a route taken from the game's own data (the first driven clean run replaces it)
    const source = body.source === 'game-files' ? 'game-files' : null;
    await env.DB.prepare(
      `INSERT INTO routes (track, points, length, updated, stage_id, contributed_by) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT (track) DO UPDATE SET points = excluded.points, length = excluded.length, updated = excluded.updated,
         stage_id = COALESCE(excluded.stage_id, routes.stage_id), contributed_by = excluded.contributed_by`)
      .bind(body.track, JSON.stringify(pts), info.length, Date.now(), sid, source).run();
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
  if (path === '/api/admin/discord') {   // run the Discord bot's minute now (it runs every minute anyway)
    const at = Number(body.now);          // tests: as if it were that time (ms)
    const when = Number.isFinite(at) && at > 0 ? at : Date.now();
    return json({ ...await discordTick(env, when, body.force === true), events: await discordEvents(env, when),
      faq: await discordFaq(env) });
  }
  let m = path.match(/^\/api\/admin\/runs\/(\d+)\/fix$/);
  if (m) return fixRun(env, +m[1], body);
  m = path.match(/^\/api\/admin\/runs\/(\d+)\/reject$/);
  if (m) {
    const run = await env.DB.prepare("UPDATE runs SET status = 'rejected', reason = ? WHERE id = ? RETURNING date, slot")
      .bind(String(body.reason || 'rejected by admin'), +m[1]).first();
    if (run) await dropDaily(env, run.date, run.slot || 1, true);
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
        if (req.method === 'POST') return postLive(req, env);
        if (url.searchParams.get('slot') === 'all') return json(await getLive(env, qDate, null));
        if (![1, 2].includes(qSlot)) return err('bad slot');
        return json(await getLive(env, qDate, qSlot));
      }
      if (path === '/api/cars') return json(CARS);
      if (path === '/api/stats') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || ![1, 2].includes(qSlot) || qDate > dayOf(Date.now())) return err('bad date or slot');
        const st = await statsCached(env, qDate, qSlot);
        return st ? json(st) : err('no stage', 404);
      }
      if (path === '/api/week') {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(qDate) || qDate > dayOf(Date.now())) return err('bad date');
        return json(await weekCached(env, qDate));
      }
      if (path === '/week') return html(weekPage());
      if (path === '/guide') return html(guidePage(env));
      if (path === '/discord') {   // every Discord link (website, app) comes here, so the invite can change any time
        const invite = await discordInvite(env);
        return invite ? Response.redirect(invite, 302) : page('Discord', 'The ACR Daily Discord opens soon.');
      }
      if (path === '/brand/acr-daily-icon-512.png') {   // the logo as a PNG (the Discord bot's avatar)
        return new Response(Uint8Array.from(atob(ICON_PNG), (c) => c.charCodeAt(0)),
          { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' } });
      }
      const sm = path.match(/^\/stage\/(\d{4}-\d{2}-\d{2})\/([12])$/);
      if (sm) return html(statsPage(sm[1], +sm[2]));
      if (path === '/api/routes' && req.method === 'GET') return json(await listRoutes(env));
      if (path === '/api/route' && req.method === 'GET') {   // one stage's route (the lab map's stage picker)
        const r = await env.DB.prepare('SELECT track, points FROM routes WHERE track = ?').bind(url.searchParams.get('track') || '').first();
        return r ? json({ track: r.track, route: JSON.parse(r.points) }) : err('not found', 404);
      }
      if (path === '/lab/map') return html(labMapPage());   // EXPERIMENTAL: the stages on satellite imagery
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
        const trace = r && await getTrace(env, r);
        return trace ? json({ id: r.id, track: r.track, car: r.car, totalMs: r.total_ms, trace }) : err('not found', 404);
      }
      if (path === '/api/version') {
        return json({ latest: latestVersion(env), url: downloadUrl(env), sha256: await releaseSha256(env, ctx),
                      release: releasePage(env) });
      }
      // old links to the download on this server go to the current GitHub release
      if ((path === '/download/ACR-Daily.exe' || path === '/download/ACR-Daily.exe.sha256') && /^https:/.test(downloadUrl(env))) {
        return Response.redirect(downloadUrl(env) + (path.endsWith('.sha256') ? '.sha256' : ''), 302);
      }
      if (path === '/api/runs' && req.method === 'POST') return submitRun(req, env);
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

  // cron (wrangler.toml [triggers]): every minute, the Discord bot, and live positions not updated for 2 minutes go
  // (the live map only shows the last minute: the table holds just who is on a stage, so reading it stays cheap);
  // once an hour the kept copies past their time, once a day (03:20 UTC) the old traces (trimTraces)
  async scheduled(event, env, ctx) {
    const t = event.scheduledTime, at = new Date(t);
    ctx.waitUntil(env.DB.prepare('DELETE FROM live WHERE updated < ?').bind(t - 2 * 60000).run()
      .catch((e) => console.error('live cleanup', e)));
    if (at.getUTCMinutes() === 30) ctx.waitUntil(dropExpired(env, t).catch((e) => console.error('cache cleanup', e)));
    if (at.getUTCHours() === 3 && at.getUTCMinutes() === 20) ctx.waitUntil(trimTraces(env, t).catch((e) => console.error('trace trim', e)));
    ctx.waitUntil(discordTick(env, event.scheduledTime).then((r) => { if (r.error) console.error('discord', r.error); })
      .catch((e) => console.error('discord', e)));
    ctx.waitUntil(discordEvents(env, event.scheduledTime).then((r) => {
      for (const [k, v] of Object.entries(r)) if (String(v).startsWith('error')) console.error('discord events', k, v);
    }).catch((e) => console.error('discord events', e)));
    ctx.waitUntil(discordFaq(env).then((r) => { if (r && r.error) console.error('discord faq', r.error); })
      .catch((e) => console.error('discord faq', e)));
  },
};
