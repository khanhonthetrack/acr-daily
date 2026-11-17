// Live rallies: ACR Daily's own scheduled rallies, in the app only (as iRacing's official races, run as a real rally).
//
// Two series, each a car class (SERIES): a session every 2 hours, the series in turn (00:00 UTC the first, 02:00 the
// second...), so each series every 4 hours. Each series races in one country a week (Monday 00:00 UTC to the next; the
// two never in the same one), each session there on 3 stages drawn at its hour, with its weather and time of day: nobody
// can prepare them.
//
//   hour - 30 min   sign-up opens (the app: SIGN UP, with the car of the class)
//   hour            sign-up closes; the rally is drawn and the start list published (the dailies' rating, best first;
//                   the drivers without one after, by sign-up): the drivers press DRIVE (the app sets the game up)
//   hour + 5 min    car 1 starts SS1, then one every 30 s
//
// Each stage after SS1 is a queue: a driver who finishes a stage gets the next free 30-s slot on the next one at least
// LIVE.turnaroundMs after the finish, after everyone queued before them. On time: the stage clock starts from
// LIVE.earlyMs before the slot to LIVE.windowMs after it. Late (no start by then, LIVE.graceMs given for the start to
// reach the server): sent to the end of that stage's queue, no penalty (be kind, for now); missed LIVE.maxMoves + 1
// times: out (SS1: did not start; a later stage: DNF). Early: the seconds jumped are added to the stage as a penalty,
// so starting early never gains anything (a league_penalties row, by 'acr-daily').
//
// A session's rally is a league event of a hidden holder of kind 'live' (one a series), open to its entrants only
// (only_ids), as a cup match is: DRIVE, the judging, the official times, the DNFs and the standings are the leagues'
// (src/leaguesapi.js calls liveStarted on each stage's start). Not rated, for now: anyone can start a session alone.
// Ghost cars: the app joins the live relay in a room of the session's own (live/relay.py), so only its drivers see each
// other. Nothing runs in the cron: a session is published by the first request after its hour, and the late are moved
// on whenever the session is looked at (every entrant's app asks every LIVE.pollS).
//
//   GET  /api/liverallies                          the series, and their sessions from the one under way to 10 h on
//   GET  /api/liverallies/:series/:starts          a session: its sign-ups, then its rally, start list, queues, standings
//   POST /api/liverallies/:series/:starts/signup {car}    sign up (or change the car), in the 30 minutes before the hour
//   POST /api/liverallies/:series/:starts/withdraw        before the hour
//   POST /api/liverallies/:series/:starts/queue {no, finishedAt}   SS(no) finished the stage before: the slot on stage `no`
//   POST /api/liverallies/:series/:starts/dnf {no, reason}  a stage of it driven outside it: my entry a DNF (outRun)
//
// Every start on a session's stages counts (nobody prepares them): the leagues' DNFs (a restart, retiring, a stage
// started twice, settings changed once the rally runs, no official time from the game: the wrong mode) and, from the
// app, a run on one of its stages before the driver's start or outside the session's Rally Weekend (practice, the
// wrong mode, settings changed in the game's menus): a DNF, before the entry is made too (outRun).

import { CARS, carByName } from './cars.js';
import { TIMES } from './conditions.js';
import { drawStages } from './cups.js';
import { withTeams } from './drivers.js';
import { catalog, checkEvent, DEFAULT_RULES, entryState, newCode, OFFICIAL_OWNER, RALLIES, text } from './leagues.js';
import { eventOut, holderMemberStmt, matchRows, routesRows } from './leaguesapi.js';
import { drawWeather } from './officialleagues.js';

const MIN = 60000, HOUR = 3600000, WEEK = 7 * 24 * HOUR;
const MONDAY = Date.UTC(1970, 0, 5);          // (a Monday: the weeks start on Mondays, 00:00 UTC, as the time trial's)

export const LIVE = {
  everyMs: 2 * HOUR,           // a session every 2 hours, the series in turn: each series every 4 hours
  signupMs: 30 * MIN,          // sign-up opens this long before the hour
  firstStartMs: 5 * MIN,       // car 1 starts this long after the hour...
  gapMs: 30000,                // ...and one every 30 s (every slot on this grid)
  earlyMs: 5000,               // on time: the clock starts from this long before the slot...
  windowMs: 30000,             // ...to this long after it
  graceMs: 20000,              // a late start may still reach the server this long after the window; then: to the end
  turnaroundMs: 2 * MIN,       // from a stage's finish to the next stage's slot, at least (the results, the game's save, loading)
  requeueMs: MIN,              // sent to the end of the queue: the new slot at least this long from then
  maxMoves: 3,                 // sent to the end this many times and late again: out
  openMs: 105 * MIN,           // the session closes this long after the hour (unfinished: DNF)
  stages: 3,
  maxKm: 30,                   // the three stages within this many km when the rally has them
  stageGapMin: 20,             // SS2 and SS3 start this much later in the day than the stage before (time stands still)
  aheadMs: 10 * HOUR,          // GET /api/liverallies lists the sessions starting within this
  pollS: { running: 10, signup: 30, idle: 60 },   // how often the app asks again
};

// "Something new and something old": Rally2 (2018-2022) and the 1970s Group 4 (H1: Stratos, 131 Abarth, Quattro Gr.4).
// turn: its place in the 2-hour rotation; shift: its country a week (RALLIES[(week + shift) % 4]: one apart, so the two
// are never in the same country, and with RALLIES' order never on the same surface)
export const SERIES = [
  { key: 'rally2', holder: 'liverly2', name: 'Rally2 Live', about: 'Modern Rally2 cars', carClass: 'Rally2/R5', turn: 0, shift: 0 },
  { key: 'classic', holder: 'livegrp4', name: 'Group 4 Classics Live', about: 'The 1970s legends', carClass: 'H1', turn: 1, shift: 1 },
];
const seriesOf = (key) => SERIES.find((s) => s.key === key) || null;
/** A session's event in /api/me/events (src/leaguesapi.js): its series' key and its hour, for the app. */
export const liveSessionOf = (ev) => {
  const s = SERIES.find((x) => x.holder === ev.league_id);
  return s ? { series: s.key, sessionStarts: ev.opens } : {};
};

/** For the testers only, for now: the app's test builds (a four-part version, User-Agent "ACR-Daily/0.1.5.32 public"),
 *  never a release, the website or anyone else, until LIVE_PUBLIC (wrangler.toml) is "1". The app shows LIVE in its test
 *  builds only too (client/acr_daily/liverally.py ON). */
export const testersOnly = (env, req) => env.LIVE_PUBLIC !== '1'
  && !/^ACR-Daily\/\d+\.\d+\.\d+\.\d+ /.test((req && req.headers && req.headers.get('User-Agent')) || '');

/** When live rallies start (LIVE_FROM in wrangler.toml, YYYY-MM-DD), in ms; null: off. */
export function liveFrom(env) {
  const t = env.LIVE_FROM ? Date.parse(`${env.LIVE_FROM}T00:00:00Z`) : NaN;
  return Number.isFinite(t) ? t : null;
}

/** The series whose session is at `starts` (an exact 2-hour mark), or null. */
export function seriesAt(starts) {
  if (!Number.isInteger(starts) || starts % LIVE.everyMs) return null;
  return SERIES.find((s) => s.turn === (starts / LIVE.everyMs) % SERIES.length) || null;
}

/** The sessions starting in [from, to]: [{series, starts}], in time order. */
export function sessionsBetween(from, to) {
  const out = [];
  for (let t = Math.ceil(from / LIVE.everyMs) * LIVE.everyMs; t <= to; t += LIVE.everyMs) out.push({ series: seriesAt(t), starts: t });
  return out;
}

/** The country a series races in the week of `t`. */
export const rallyOfWeek = (s, t) => RALLIES[(Math.floor((t - MONDAY) / WEEK) + s.shift) % RALLIES.length];

/** A session's times (ms). */
export const timesOf = (starts) => ({ signupOpens: starts - LIVE.signupMs, starts, firstStart: starts + LIVE.firstStartMs,
  closes: starts + LIVE.openMs });

/** upcoming (sign-up not open yet) / signup / running / over. */
export function phaseOf(starts, now) {
  const t = timesOf(starts);
  return now < t.signupOpens ? 'upcoming' : now < starts ? 'signup' : now < t.closes ? 'running' : 'over';
}

/** The first slot of the 30-s grid at or after t. */
export const gridUp = (t) => Math.ceil(t / LIVE.gapMs) * LIVE.gapMs;

const hhmmss = (ms) => new Date(ms).toISOString().slice(11, 19);
const hhmm = (min) => `${String(Math.floor(min / 60) % 24).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

/** A session's rally, drawn (the week's country; another one only if it hasn't the stages): its stages on as many
 *  roads as it has, one weather for the three, a time of day (the dailies' odds), a service park before SS1 only (the
 *  damage carries through), the class's cars. avoid: tracks left out (the dailies' and the time trial's: a driver who
 *  hasn't driven them yet would have to wait until after the session, liverallyui.lr_stage_clash), drawn only when
 *  the country hasn't the roads without them. -> checkEvent's value, or null. */
export function drawSession(s, starts, routes, rand = Math.random, avoid = new Set()) {
  const cat = catalog(routes);
  const home = rallyOfWeek(s, starts);
  const total = TIMES.reduce((a, x) => a + x.weight, 0);
  let r = rand() * total, tod = TIMES[TIMES.length - 1];
  for (const x of TIMES) { r -= x.weight; if (r < 0) { tod = x; break; } }
  const [h, m] = tod.hour.split(':').map(Number);
  for (const rally of [home, ...RALLIES.filter((x) => x !== home)]) {
    const weather = drawWeather(rally, rand);
    const template = Array.from({ length: LIVE.stages }, (_, k) => ({ day: 1, service: k === 0, weather,
      time: hhmm(h * 60 + m + k * LIVE.stageGapMin) }));
    const pool = (cat.rallies.find((x) => x.name === rally) || { stages: [] }).stages
      .map((x) => ({ track: x.track, stageId: x.stageId, lengthM: x.lengthM }));
    const stages = drawStages(pool.filter((p) => !avoid.has(p.track)), template, new Set(), LIVE.maxKm, rand, { twice: true })
      || drawStages(pool, template, avoid, LIVE.maxKm, rand, { twice: true });   // (avoided ones drawn last)
    if (!stages) continue;
    const c = checkEvent({ name: `${s.name} · ${rally} · ${hhmm(new Date(starts).getUTCHours() * 60)} UTC`, rally,
      carClass: s.carClass, rules: DEFAULT_RULES, stages, opens: starts, closes: starts + LIVE.openMs }, cat, starts);
    if (!c.error) return c.value;
  }
  return null;
}

const sessionRow = (env, key, starts) => env.DB.prepare('SELECT * FROM live_sessions WHERE series = ? AND starts = ?').bind(key, starts).first();

/** The series' holder (a hidden league of kind 'live', run by ACR Daily), made the first time. */
const holderStmt = (env, s, now) => env.DB.prepare(`INSERT OR IGNORE INTO leagues (id, name, about, owner, public, code, created, kind, official)
  VALUES (?, ?, ?, ?, 0, ?, ?, 'live', 1)`).bind(s.holder, s.name, s.about, OFFICIAL_OWNER.id, newCode(), now);

/** Publish a session at (or after) its hour, once: its rally drawn, its event made for the drivers signed up, SS1's start
 *  list. The first request after the hour does it (a claim on live_sessions: another one meanwhile sees it under way;
 *  one stalled for 30 s is taken over). -> its event id (0: nobody signed up, or no stages), or null: under way. */
export async function publish(env, s, starts, now, rand = Math.random, deps = {}) {
  const claim = await env.DB.prepare(`INSERT INTO live_sessions (series, starts, event_id, created) VALUES (?, ?, NULL, ?)
    ON CONFLICT(series, starts) DO UPDATE SET created = excluded.created
      WHERE live_sessions.event_id IS NULL AND live_sessions.created < ?`).bind(s.key, starts, now, now - 30000).run();
  if (!claim.meta.changes) return ((await sessionRow(env, s.key, starts)) || {}).event_id ?? null;
  const done = (id) => env.DB.prepare('UPDATE live_sessions SET event_id = ? WHERE series = ? AND starts = ?').bind(id, s.key, starts).run();
  // the start list: the dailies' rating, best first (as a real rally's seeds), the drivers without one after (by sign-up)
  const { results: ups } = await env.DB.prepare(`SELECT u.steam_id, u.car FROM live_signups u JOIN players p ON p.steam_id = u.steam_id
      LEFT JOIN ratings r ON r.steam_id = u.steam_id
    WHERE u.series = ? AND u.starts = ? AND COALESCE(p.banned, 0) = 0
    ORDER BY r.rating IS NULL, r.rating DESC, u.at, u.steam_id`).bind(s.key, starts).all();
  const avoid = ups.length && deps.avoid ? await deps.avoid(starts) : new Set();
  const spec = ups.length ? drawSession(s, starts, await routesRows(env), rand, avoid) : null;
  if (!spec) {
    await done(0);
    return 0;
  }
  const only = ups.map((u) => u.steam_id);
  // all or nothing, in one batch (a D1 batch is one transaction): the event (once: a publish taken over after a stall
  // finds it made), SS1's start list and the session's event, so a publish cut short leaves nothing half made
  const evId = `(SELECT id FROM league_events WHERE league_id = ?1 AND opens = ?2 ORDER BY id LIMIT 1)`;
  await env.DB.batch([
    holderStmt(env, s, now),
    ...only.map((sid) => holderMemberStmt(env, s.holder, sid, now)),
    env.DB.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, rules, stages, opens, closes,
        created, only_ids, hide)
      SELECT ?1, NULL, ?3, ?4, ?5, ?6, ?7, ?8, ?2, ?9, ?10, ?11, NULL
      WHERE NOT EXISTS (SELECT 1 FROM league_events WHERE league_id = ?1 AND opens = ?2)`)
      .bind(s.holder, starts, text(spec.name, 60), spec.rally, spec.car, spec.car_class, JSON.stringify(spec.rules),
        JSON.stringify(spec.stages), starts + LIVE.openMs, now, JSON.stringify(only)),
    env.DB.prepare(`INSERT OR IGNORE INTO live_slots (event_id, stage_no, steam_id, slot_at, created)
      SELECT ${evId}, 0, j.value, ?3 + j.key * ?4, ?5 FROM json_each(?6) j`)
      .bind(s.holder, starts, starts + LIVE.firstStartMs, LIVE.gapMs, now, JSON.stringify(only)),
    env.DB.prepare(`UPDATE live_sessions SET event_id = ${evId} WHERE series = ?3 AND starts = ?2 AND event_id IS NULL`)
      .bind(s.holder, starts, s.key),
  ]);
  return ((await sessionRow(env, s.key, starts)) || {}).event_id ?? null;
}

/** The late on an event's queues moved on (see the top): each slot whose start window (and grace) is over without a
 *  start goes to the end of its stage's queue, or out after LIVE.maxMoves moves; a driver whose entry has ended (a DNF on
 *  the stage before) leaves the queue. One batch, in slot order (each move sees the ones before it). */
export async function settle(env, ev, now) {
  if (now > ev.closes) return 0;
  const { results: late } = await env.DB.prepare(`SELECT s.stage_no, s.steam_id, s.slot_at, s.moved, e.status AS entry
      FROM live_slots s LEFT JOIN league_entries e ON e.event_id = s.event_id AND e.steam_id = s.steam_id
    WHERE s.event_id = ? AND s.started IS NULL AND s.out IS NULL AND s.slot_at < ?
    ORDER BY s.stage_no, s.slot_at`).bind(ev.id, now - LIVE.windowMs - LIVE.graceMs).all();
  if (!late.length) return 0;
  const stmts = [];
  const out = (r, why) => env.DB.prepare(`UPDATE live_slots SET out = ?, moved_at = ?, prev_at = slot_at WHERE event_id = ?
    AND stage_no = ? AND steam_id = ? AND started IS NULL AND out IS NULL`).bind(why, now, ev.id, r.stage_no, r.steam_id);
  for (const r of late) {
    if (r.stage_no > 0 && r.entry !== 'running') {
      stmts.push(out(r, 'retired'));
    } else if (r.moved >= LIVE.maxMoves) {
      stmts.push(out(r, r.stage_no ? 'dnf' : 'dns'));
      if (r.stage_no) {
        stmts.push(env.DB.prepare(`UPDATE league_entries SET status = 'dnf', reason = ?, updated = ? WHERE event_id = ? AND steam_id = ?
          AND status = 'running'`).bind(`did not start SS${r.stage_no + 1}`, now, ev.id, r.steam_id));
      }
    } else {
      stmts.push(env.DB.prepare(`UPDATE live_slots SET moved = moved + 1, moved_at = ?7, prev_at = slot_at,
          slot_at = MAX(?1, (SELECT MAX(x.slot_at) FROM live_slots x WHERE x.event_id = ?2 AND x.stage_no = ?3) + ?4)
        WHERE event_id = ?2 AND stage_no = ?3 AND steam_id = ?5 AND started IS NULL AND slot_at = ?6`)
        .bind(gridUp(now + LIVE.requeueMs), ev.id, r.stage_no, LIVE.gapMs, r.steam_id, r.slot_at, now));
    }
  }
  await env.DB.batch(stmts);
  return late.length;
}

/** When a stage's start was, in server time: the app's (its PC clock set by the server's, b.serverAt) when it is
 *  plausible (from the event's opening to now: a start sent late, from the app's queue, keeps its time), else now. */
function startTime(b, ev, now) {
  const at = Math.round(+b.serverAt);
  return Number.isFinite(at) && at >= ev.opens && at <= now + 5000 ? Math.min(at, now) : now;
}

/** A live session's stage started (src/leaguesapi.js, after the leagues' own checks: SS1's start, a later stage's
 *  begin): kept against its slot. Early by more than LIVE.earlyMs: the seconds jumped as a penalty on that stage. Late:
 *  taken as it is (be kind). A stage with no slot (an app that didn't queue): on time. -> {slotAt, startedAt, penaltyMs,
 *  late} for the app. */
export async function liveStarted(env, ev, steamId, no, b, now) {
  const at = startTime(b, ev, now);
  const slot = await env.DB.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = ? AND steam_id = ?')
    .bind(ev.id, no, steamId).first();
  if (slot && slot.started != null) return { slotAt: slot.slot_at, startedAt: slot.started, penaltyMs: slot.penalty_ms, late: false };
  if (!slot) {
    await env.DB.prepare(`INSERT OR IGNORE INTO live_slots (event_id, stage_no, steam_id, slot_at, started, created)
      VALUES (?, ?, ?, ?, ?, ?)`).bind(ev.id, no, steamId, Math.floor(at / LIVE.gapMs) * LIVE.gapMs, at, now).run();
    return { slotAt: Math.floor(at / LIVE.gapMs) * LIVE.gapMs, startedAt: at, penaltyMs: 0, late: false };
  }
  // a start made before the slot was last moved (or taken out of the queue), and still on its way to the server then:
  // judged against the slot it had at the time (late: no penalty), not the new one it would be early for
  const ref = slot.moved_at != null && at < slot.moved_at && slot.prev_at != null ? slot.prev_at : slot.slot_at;
  const jumped = ref - at;
  const penaltyMs = jumped > LIVE.earlyMs ? Math.ceil(jumped / 1000) * 1000 : 0;
  const stmts = [env.DB.prepare(`UPDATE live_slots SET started = ?, penalty_ms = ?, out = NULL WHERE event_id = ? AND stage_no = ?
    AND steam_id = ? AND started IS NULL`).bind(at, penaltyMs, ev.id, no, steamId)];
  if (penaltyMs) {
    stmts.push(env.DB.prepare(`INSERT INTO league_penalties (event_id, steam_id, stage_no, ms, reason, by, created)
      VALUES (?, ?, ?, ?, ?, ?, ?)`).bind(ev.id, steamId, no, penaltyMs,
      `jump start: SS${no + 1} started ${penaltyMs / 1000} s before its slot (${hhmmss(ref)} UTC)`, OFFICIAL_OWNER.id, now));
  }
  await env.DB.batch(stmts);
  return { slotAt: ref, startedAt: at, penaltyMs, late: at - ref > LIVE.windowMs };
}

/** A later stage's start (src/leaguesapi.js begin) for an entry the queue made a DNF (settle: SS(no) not started after
 *  the last move): when this start was made before that, still on its way to the server then, the DNF is undone and the
 *  start goes on as any other. -> true when undone. */
export async function liveRevived(env, ev, entry, no, b, now) {
  if (!Number.isInteger(no) || no < 1 || entry.done !== no || entry.reason !== `did not start SS${no + 1}`) return false;
  const slot = await env.DB.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = ? AND steam_id = ?')
    .bind(ev.id, no, entry.steam_id).first();
  if (!slot || slot.out !== 'dnf' || slot.moved_at == null || startTime(b, ev, now) >= slot.moved_at) return false;
  const r = await env.DB.prepare(`UPDATE league_entries SET status = 'running', reason = NULL, updated = ? WHERE event_id = ?
    AND steam_id = ? AND status = 'dnf' AND reason = ?`).bind(now, ev.id, entry.steam_id, entry.reason).run();
  return r.meta.changes > 0;
}

/** A stage of the session driven outside it (the app saw it: before the driver's start, in another mode, or with the
 *  session's settings changed in the game): the entry a DNF, made if not started yet (with the car signed up with), and
 *  out of every queue. Once: an entry already over stays as it is. -> {status, reason}. */
export async function outRun(env, s, starts, ev, steamId, no, reason, now) {
  const entry = await env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, steamId).first();
  if (entry && entry.status !== 'running') return { status: entry.status, reason: entry.reason || '' };
  const why = text(reason, 120) || `SS${no + 1} driven outside the rally`;
  const up = await env.DB.prepare('SELECT car FROM live_signups WHERE series = ? AND starts = ? AND steam_id = ?')
    .bind(s.key, starts, steamId).first();
  const car = (entry && entry.car) || (up && up.car) || (CARS.find((c) => c.cls === s.carClass) || {}).name;
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, reason, done, on_stage, total_ms, started, updated)
        VALUES (?, ?, ?, 'dnf', ?, 0, NULL, 0, ?, ?)
      ON CONFLICT(event_id, steam_id) DO UPDATE SET status = 'dnf', reason = excluded.reason, updated = excluded.updated
        WHERE league_entries.status = 'running'`).bind(ev.id, steamId, car, why, now, now),
    env.DB.prepare(`UPDATE live_slots SET out = 'dnf', moved_at = ?, prev_at = slot_at WHERE event_id = ? AND steam_id = ?
      AND started IS NULL AND out IS NULL`).bind(now, ev.id, steamId),
  ]);
  return { status: 'dnf', reason: why };
}

/** SS1's start refused (src/leaguesapi.js, before the entry is made): the driver missed their start too often and is out
 *  of the session (did not start), unless this start was made before they were taken out (on its way to the server
 *  then). -> why, or null (it may start). */
export async function liveRefused(env, ev, steamId, b, now) {
  const slot = await env.DB.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = 0 AND steam_id = ?')
    .bind(ev.id, steamId).first();
  if (!slot || slot.out !== 'dns' || (slot.moved_at != null && startTime(b, ev, now) < slot.moved_at)) return null;
  return `did not start: missed the start ${slot.moved + 1} times`;
}

/** A stage's slot for a driver who finished the stage before (`no` >= 1): the next free one on the 30-s grid at least
 *  LIVE.turnaroundMs after the finish, after everyone queued before them. Once: asked again, the same. -> the slot row,
 *  or {error, status}. */
export async function queueFor(env, ev, steamId, no, finishedAt, now) {
  const n = JSON.parse(ev.stages).length;
  if (!(Number.isInteger(no) && no >= 1 && no < n)) return { error: 'which stage?', status: 400 };
  // (refused for good, 410: the app stops asking; 409: not yet, it asks again shortly)
  if (now >= ev.closes) return { error: 'the session is over', status: 410 };
  const entry = await env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, steamId).first();
  if (!entry) return { error: 'not started', status: 409 };
  if (entry.status !== 'running' && !(entry.status === 'finished' && entry.done >= no)) return { error: `this entry is ${entry.status}`, status: 410 };
  if (!(entry.done >= no || entry.on_stage === no - 1)) return { error: `SS${no} not driven yet`, status: 409 };
  const fin = Number.isFinite(+finishedAt) ? Math.max(now - 2 * MIN, Math.min(now, Math.round(+finishedAt))) : now;
  await env.DB.prepare(`INSERT INTO live_slots (event_id, stage_no, steam_id, slot_at, created)
    SELECT ?1, ?2, ?3, MAX(?4, COALESCE((SELECT MAX(slot_at) FROM live_slots WHERE event_id = ?1 AND stage_no = ?2) + ?5, 0)), ?6
    WHERE NOT EXISTS (SELECT 1 FROM live_slots WHERE event_id = ?1 AND stage_no = ?2 AND steam_id = ?3)`)
    .bind(ev.id, no, steamId, gridUp(fin + LIVE.turnaroundMs), LIVE.gapMs, now).run();
  return env.DB.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = ? AND steam_id = ?').bind(ev.id, no, steamId).first();
}

// ------------------------------------------------------------------ what the app gets

const seriesOut = (s, now) => ({ key: s.key, name: s.name, about: s.about, carClass: s.carClass,
  cars: CARS.filter((c) => c.cls === s.carClass).map((c) => ({ name: c.name, id: c.id })),
  rally: rallyOfWeek(s, now), nextRally: rallyOfWeek(s, now + WEEK), everyHours: LIVE.everyMs * SERIES.length / HOUR });

const slotOut = (r) => (r ? { no: r.stage_no, at: r.slot_at, moved: r.moved, started: r.started, penaltyMs: r.penalty_ms, out: r.out } : null);

/** GET /api/liverallies: the series and their sessions, from the one under way to LIVE.aheadMs on, with how many
 *  signed up and whether I did. A session past its hour with sign-ups is published here too. */
async function overview(env, me, now, rand, deps) {
  const from = Math.max(now - LIVE.openMs, liveFrom(env)), to = now + LIVE.aheadMs;
  const list = sessionsBetween(from, to);
  const sid = me ? me.steam_id : '';
  const [{ results: counts }, { results: rows }] = await Promise.all([
    env.DB.prepare(`SELECT series, starts, COUNT(*) AS n, MAX(steam_id = ?1) AS mine, MAX(CASE WHEN steam_id = ?1 THEN car END) AS car
      FROM live_signups WHERE starts >= ?2 AND starts <= ?3 GROUP BY series, starts`).bind(sid, from, to).all(),
    env.DB.prepare('SELECT * FROM live_sessions WHERE starts >= ? AND starts <= ?').bind(from, to).all(),
  ]);
  const key = (k, t) => `${k}:${t}`;
  const count = new Map(counts.map((c) => [key(c.series, c.starts), c]));
  const pub = new Map(rows.map((r) => [key(r.series, r.starts), r]));
  for (const x of list) {                              // (an hour gone by with sign-ups and nobody asked yet)
    const k = key(x.series.key, x.starts);
    if (now >= x.starts && now < timesOf(x.starts).closes && count.has(k) && !pub.has(k)) {
      await publish(env, x.series, x.starts, now, rand, deps);
      pub.set(k, await sessionRow(env, x.series.key, x.starts));
    }
  }
  const evIds = [...pub.values()].map((r) => r.event_id).filter(Boolean);
  const mine = sid && evIds.length ? new Map((await env.DB.prepare(`SELECT event_id, status, done FROM league_entries WHERE steam_id = ?
    AND event_id IN (SELECT value FROM json_each(?))`).bind(sid, JSON.stringify(evIds)).all()).results.map((e) => [e.event_id, e])) : new Map();
  const sessions = list.map(({ series: s, starts }) => {
    const c = count.get(key(s.key, starts)) || {}, p = pub.get(key(s.key, starts)) || null;
    let phase = phaseOf(starts, now);
    if (phase === 'running' && p && p.event_id === 0) phase = 'empty';
    const e = p && p.event_id ? mine.get(p.event_id) : null;
    return { series: s.key, starts, ...timesOf(starts), phase, rally: rallyOfWeek(s, starts), signups: c.n || 0,
      signedUp: !!c.mine, car: c.car || null, eventId: (p && p.event_id) || null,
      entry: e ? { status: e.status, done: e.done } : null };
  });
  return { now, on: true, series: SERIES.map((s) => seriesOut(s, now)), sessions, live: LIVE_RULES, pollS: LIVE.pollS.idle };
}

/** What the app says about the rules (and works out the countdowns with). */
const LIVE_RULES = { signupMin: LIVE.signupMs / MIN, firstStartMin: LIVE.firstStartMs / MIN, gapS: LIVE.gapMs / 1000,
  earlyS: LIVE.earlyMs / 1000, windowS: LIVE.windowMs / 1000, graceS: LIVE.graceMs / 1000, turnaroundS: LIVE.turnaroundMs / 1000,
  maxMoves: LIVE.maxMoves, stages: LIVE.stages };

/** One session: before its hour its sign-ups; from then its rally (as /api/me/events gives an event: the app drives it
 *  through the leagues' DRIVE), each stage's queue (start list on SS1), the standings and my next slot. */
async function sessionView(env, s, starts, me, now, rand, deps) {
  const t = timesOf(starts);
  let row = await sessionRow(env, s.key, starts);
  if (now >= starts && now < t.closes && (!row || row.event_id == null)) {
    await publish(env, s, starts, now, rand, deps);
    row = await sessionRow(env, s.key, starts);
  }
  const sid = me ? me.steam_id : null;
  const phase = phaseOf(starts, now);
  const out = { now, series: seriesOut(s, starts), starts, ...t, phase, rally: rallyOfWeek(s, starts), live: LIVE_RULES };
  if (!row || row.event_id == null) {                  // sign-up (or being published, or an hour gone by with nobody)
    const { results: ups } = await env.DB.prepare(`SELECT u.steam_id, u.car, u.at, p.name, p.country, p.avatar FROM live_signups u
      JOIN players p ON p.steam_id = u.steam_id WHERE u.series = ? AND u.starts = ? ORDER BY u.at`).bind(s.key, starts).all();
    const mine = ups.find((u) => u.steam_id === sid);
    Object.assign(out, { publishing: now >= starts && now < t.closes,
      entrants: ups.map((u) => ({ steamId: u.steam_id, name: u.name, country: u.country || null, avatar: u.avatar || null, car: u.car })),
      me: { signedIn: !!me, signedUp: !!mine, car: mine ? mine.car : null },
      pollS: phase === 'signup' || now >= starts ? LIVE.pollS.signup : LIVE.pollS.idle });
    if (out.publishing) out.pollS = 2;
    return withTeams(env, out);
  }
  if (row.event_id === 0) {                            // nobody signed up
    return Object.assign(out, { phase: phase === 'running' ? 'empty' : phase, entrants: [], queues: [], standings: [],
      me: { signedIn: !!me, signedUp: false }, pollS: LIVE.pollS.idle });
  }
  const ev = await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(row.event_id).first();
  await settle(env, ev, now);
  const [{ results: slots }, standings, routes, mineEntry] = await Promise.all([
    env.DB.prepare(`SELECT x.*, p.name, p.country, p.avatar, u.car FROM live_slots x JOIN players p ON p.steam_id = x.steam_id
        LEFT JOIN live_signups u ON u.series = ? AND u.starts = ? AND u.steam_id = x.steam_id
      WHERE x.event_id = ? ORDER BY x.stage_no, x.slot_at`).bind(s.key, starts, ev.id).all(),
    matchRows(env, ev.id, now),
    routesRows(env),
    sid ? env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, sid).first() : null,
  ]);
  const only = JSON.parse(ev.only_ids || '[]');
  const n = JSON.parse(ev.stages).length;
  const byDriver = new Map(standings.map((r) => [r.steamId, r]));
  const queues = Array.from({ length: n }, () => []);
  for (const x of slots) {
    const st = byDriver.get(x.steam_id);
    const done = st && st.stages && st.stages[x.stage_no] && st.stages[x.stage_no].totalMs != null ? st.stages[x.stage_no] : null;
    const state = x.out || (x.started == null ? (now > x.slot_at + LIVE.windowMs ? 'late' : 'waiting')
      : done ? 'done' : st && st.status === 'dnf' && (st.done || 0) <= x.stage_no ? 'dnf' : 'driving');
    queues[x.stage_no].push({ steamId: x.steam_id, name: x.name, country: x.country || null, avatar: x.avatar || null,
      car: (st && st.car) || x.car || null, at: x.slot_at, moved: x.moved, started: x.started, penaltyMs: x.penalty_ms, state,
      timeMs: done ? done.totalMs : null });
  }
  const o = eventOut(ev, routes, now);
  o.kind = 'live';
  o.league = s.name;
  o.series = s.key;
  o.sessionStarts = starts;
  o.drivers = only.length;
  o.entry = mineEntry ? { car: mineEntry.car, ...entryState(mineEntry, ev, now), done: mineEntry.done, totalMs: mineEntry.total_ms,
    started: mineEntry.started } : null;
  // my next start: my earliest slot not started and still queued
  const next = sid ? slots.filter((x) => x.steam_id === sid && x.started == null && !x.out).sort((a, b) => a.slot_at - b.slot_at)[0] : null;
  const myCar = sid ? (slots.find((x) => x.steam_id === sid && x.car) || {}).car || (mineEntry && mineEntry.car) || null : null;
  const waitingSoon = next && next.slot_at - now < 10 * MIN;
  Object.assign(out, { eventId: ev.id, event: o, entrants: only.length, queues, standings,
    me: { signedIn: !!me, signedUp: only.includes(sid), car: myCar, next: slotOut(next), out: sid ? slotOut(slots.find((x) => x.steam_id === sid && x.out)) : null },
    pollS: phase === 'running' && only.includes(sid) ? (waitingSoon ? LIVE.pollS.running : LIVE.pollS.signup) : LIVE.pollS.signup });
  if (phase === 'over') out.pollS = LIVE.pollS.idle;
  return withTeams(env, out);
}

// ------------------------------------------------------------------ the API

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' } });
const err = (msg, status = 400) => json({ error: msg }, status);
async function readBody(req) {
  try { const b = await req.json(); return b && typeof b === 'object' ? b : {}; } catch { return {}; }
}

/** /api/liverallies... (see the top; /api/live is the dailies' live positions). me: the signed-in player row or null;
 *  deps: {avoid(starts) -> Set of tracks} (src/index.js: the dailies' and the time trial's stages). -> a Response, or
 *  null (not ours). */
export async function liveApi(req, env, path, me, now = Date.now(), rand = Math.random, deps = {}) {
  if (path !== '/api/liverallies' && !path.startsWith('/api/liverallies/')) return null;
  const post = req.method === 'POST';
  const from = liveFrom(env);
  if (testersOnly(env, req)) return path === '/api/liverallies' && !post ? json({ now, on: false, series: [], sessions: [] })
    : err('not found', 404);                          // (as if there were none: nothing said to anyone else)
  if (from === null || now < from - LIVE.aheadMs) return json({ now, on: false, series: [], sessions: [] });
  if (path === '/api/liverallies') return post ? err('not found', 404) : json(await withTeams(env, await overview(env, me, now, rand, deps)));
  const m = path.match(/^\/api\/liverallies\/([a-z0-9]+)\/(\d{13})(?:\/([a-z]+))?$/);
  const s = m && seriesOf(m[1]);
  const starts = m ? +m[2] : NaN;
  if (!s || seriesAt(starts) !== s || starts < from) return err('no such session', 404);
  const action = m[3] || '';
  if (!post) return action ? err('not found', 404) : json(await sessionView(env, s, starts, me, now, rand, deps));
  if (!me) return err('sign in first', 401);
  if (me.banned) return err('banned', 403);
  const b = await readBody(req);
  const t = timesOf(starts);
  if (action === 'signup') {
    if (now < t.signupOpens) return err(`sign-up opens at ${hhmmss(t.signupOpens).slice(0, 5)} UTC, 30 minutes before the start`, 409);
    if (now >= starts) return err('sign-up closed at the start', 409);
    const car = carByName(b.car) || CARS.find((c) => c.id === b.car);
    if (!car || car.cls !== s.carClass) return err(`pick a ${s.carClass} car`, 422);
    await env.DB.batch([
      env.DB.prepare(`INSERT INTO live_signups (series, starts, steam_id, car, at) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(series, starts, steam_id) DO UPDATE SET car = excluded.car`).bind(s.key, starts, me.steam_id, car.name, now),
      holderStmt(env, s, now),
      holderMemberStmt(env, s.holder, me.steam_id, now),
    ]);
    return json(await sessionView(env, s, starts, me, now, rand, deps));
  }
  if (action === 'withdraw') {
    if (now >= starts) return err('the start list is out: just don\'t start', 409);
    await env.DB.prepare('DELETE FROM live_signups WHERE series = ? AND starts = ? AND steam_id = ?').bind(s.key, starts, me.steam_id).run();
    return json(await sessionView(env, s, starts, me, now, rand, deps));
  }
  if (action === 'queue' || action === 'dnf') {
    const row = await sessionRow(env, s.key, starts);
    const ev = row && row.event_id ? await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(row.event_id).first() : null;
    if (!ev || !JSON.parse(ev.only_ids || '[]').includes(me.steam_id)) return err('not in this session', 403);
    if (action === 'dnf') {
      const no = Math.round(+b.no);
      if (!(no >= 0 && no < JSON.parse(ev.stages).length)) return err('which stage?');
      return json(await outRun(env, s, starts, ev, me.steam_id, no, b.reason, now));
    }
    const q = await queueFor(env, ev, me.steam_id, Math.round(+b.no), b.finishedAt, now);
    if (q.error) return err(text(q.error, 120), q.status);
    return json({ now, slot: slotOut(q) });
  }
  return err('not found', 404);
}
