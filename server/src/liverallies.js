// Ranked rallies (the app's RANKED, its test builds only for now; "live rallies" in the code): ACR Daily's own scheduled
// rallies, in the app only, as iRacing's official races, run as a real rally: one car starting at a time.
//
// Two series, each a car class (SERIES): a session every 2 hours from LIVE_FROM, the series in turn, so each series
// every 4 hours. Each series races in one country a week (Monday 00:00 UTC to the next; the two never in the same one),
// each session there on 3 stages drawn at its hour, with its weather and time of day: nobody can prepare them.
//
//   hour - 30 min   registration opens (the app: REGISTER, with the car of the class)
//   hour            registration closes; the rally is drawn and the start list published (the dailies' rating, best
//                   first; the drivers without one after, by registration): the drivers press DRIVE (the app sets the
//                   game up)
//   hour + 5 min    the first turn: the top-ranked driver has LIVE.turnMs (20 s) to start SS1
//
// Turns, not slots: one driver's turn at a time. A turn opens when the turn before it ends: at its driver's start, or
// at the end of their 20 s without one. Missed (no start in the turn): to the end of that stage's queue (ready again
// from the turn's end; out after LIVE.maxMoves moves: SS1 did not start, a later stage DNF). Started before the turn
// (on red): the run counts, with the seconds jumped (to when the turn would have opened) added to the stage, so it
// gains nothing. A start whose time is before the turn's end, on its way to the server when the queue moved on, is
// taken as in its turn. After a stage, a LIVE.breakMs (3 min) break, then the driver joins the next stage's queue:
// whoever is ready first, first. The app shows each driver's place in a window over the game (red lights while they
// wait, green with 20 s on their turn); a start counts as the ranked run when the app follows the session on that
// stage (no button to press).
//
// A session's rally is a league event of a hidden holder of kind 'live' (one a series), open to its entrants only
// (only_ids), as a cup match is: DRIVE, the judging, the official times, the DNFs and the standings are the leagues'
// (src/leaguesapi.js calls liveStarted on each stage's start). Not rated, for now: anyone can start a session alone.
// Ghost cars: the app joins the live relay in a room of the session's own (live/relay.py), so only its drivers see each
// other. Nothing runs in the cron: a session is published by the first request after its hour, and the turns move on
// whenever the session is looked at (every entrant's app asks every 2 to 10 s, as near as its turn is).
//
//   GET  /api/liverallies                          the series, and their sessions from the one under way to 10 h on
//   GET  /api/liverallies/:series/:starts          a session: its registrations, then its rally, queues, standings,
//                                                  my next turn, whether the results are out
//   POST /api/liverallies/:series/:starts/signup {car}    register (or change the car), in the 30 minutes before the hour
//   POST /api/liverallies/:series/:starts/withdraw        before the hour
//   POST /api/liverallies/:series/:starts/queue {no, finishedAt}   stage `no` - 1 finished: in stage `no`'s queue after the break
//   POST /api/liverallies/:series/:starts/dnf {no, reason}  a stage of it driven outside it: my entry a DNF (outRun)
//
// Every start on a session's stages counts (nobody prepares them): the leagues' DNFs (a restart, retiring, a stage
// started twice, settings changed once the rally runs, no official time from the game: the wrong mode) and, from the
// app, a run on one of its stages before the driver's run on it that belongs to no mode (practice: not this session's,
// not a counted daily's, not the time trial's): a DNF, before the entry is made too (outRun).

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
  signupMs: 30 * MIN,          // registration opens this long before the hour
  firstStartMs: 5 * MIN,       // the first turn this long after the hour (time to start the game and get ready)
  turnMs: 20000,               // a driver's turn: this long to start (the app's green light)
  earlyMs: 2000,               // a start this much before its turn still counts as in it (the game's countdown, the clocks)
  breakMs: 3 * MIN,            // between stages: a driver joins the next stage's queue this long after their finish
  maxMoves: 3,                 // a turn missed, sent to the end this many times, and missed again: out
  writes: 30,                  // the turns written at most this many statements a look (D1's free plan: 50 queries a request)
  openMs: 105 * MIN,           // the session closes this long after the hour (unfinished: DNF)
  stages: 3,
  maxKm: 30,                   // the three stages within this many km when the rally has them
  stageGapMin: 20,             // SS2 and SS3 start this much later in the day than the stage before (time stands still)
  aheadMs: 10 * HOUR,          // GET /api/liverallies lists the sessions starting within this
  recentMs: 7 * 24 * HOUR,     // ...and the ones over within this, with their results (recent: the app's RESULTS)
  pollS: { turn: 2, wait: 5, running: 10, signup: 30, idle: 60 },   // how often the app asks again (2: my turn near)
};

// "Something new and something old": Rally2 (2018-2022) and the 1970s Group 4 (H1: Stratos, 131 Abarth, Quattro Gr.4).
// turn: its place in the 2-hour rotation; shift: its country a week (RALLIES[(week + shift) % 4]: one apart, so the two
// are never in the same country, and with RALLIES' order never on the same surface)
export const SERIES = [
  { key: 'rally2', holder: 'liverly2', name: 'Rally2', about: 'Modern Rally2 cars', carClass: 'Rally2/R5', turn: 0, shift: 0 },
  { key: 'classic', holder: 'livegrp4', name: 'Group 4 Classics', about: 'The 1970s legends', carClass: 'H1', turn: 1, shift: 1 },
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
  const v = String(env.LIVE_FROM || '');
  const t = v ? Date.parse(v.includes('T') ? v : `${v}T00:00:00Z`) : NaN;   // (a day, or the first session's time)
  return Number.isFinite(t) ? t : null;
}

/** The series whose session is at `starts` (an exact 2-hour mark), or null. */
export function seriesAt(starts, anchor = 0) {
  if (!Number.isInteger(starts) || (starts - anchor) % LIVE.everyMs) return null;
  const k = Math.round((starts - anchor) / LIVE.everyMs);
  return SERIES.find((s) => s.turn === ((k % SERIES.length) + SERIES.length) % SERIES.length) || null;
}

/** The sessions starting in [from, to] on the grid from anchor (LIVE_FROM: the first session, Rally2's; every
 *  LIVE.everyMs from it, the series in turn): [{series, starts}], in time order. */
export function sessionsBetween(from, to, anchor = 0) {
  const out = [];
  for (let t = anchor + Math.ceil((from - anchor) / LIVE.everyMs) * LIVE.everyMs; t <= to; t += LIVE.everyMs) {
    out.push({ series: seriesAt(t, anchor), starts: t });
  }
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

const hhmmss = (ms) => new Date(ms).toISOString().slice(11, 19);
const hhmm = (min) => `${String(Math.floor(min / 60) % 24).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

/** A session's rally, drawn (the week's country; another one only if it hasn't the stages): its stages on as many
 *  roads as it has, one weather for the three, a time of day (the dailies' odds), a service park before SS1 only (the
 *  damage carries through), the class's cars. Any stage of the country, a daily's or the time trial's too: the app tells
 *  each run's mode apart (START SSn for ranked, START OFFICIAL RALLY for a daily). -> checkEvent's value, or null. */
export function drawSession(s, starts, routes, rand = Math.random) {
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
    const stages = drawStages(pool, template, new Set(), LIVE.maxKm, rand, { twice: true });
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
export async function publish(env, s, starts, now, rand = Math.random) {
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
  const spec = ups.length ? drawSession(s, starts, await routesRows(env), rand) : null;
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
      SELECT ${evId}, 0, j.value, ?3, ?4 FROM json_each(?5) j ORDER BY j.key`)     // (in the start list's order: the turns')
      .bind(s.holder, starts, starts + LIVE.firstStartMs, now, JSON.stringify(only)),
    env.DB.prepare(`UPDATE live_sessions SET event_id = ${evId} WHERE series = ?3 AND starts = ?2 AND event_id IS NULL`)
      .bind(s.holder, starts, s.key),
  ]);
  return ((await sessionRow(env, s.key, starts)) || {}).event_id ?? null;
}

/** When the turn a queue row had ended (null: none ended yet): a missed turn's (or the turn it was taken out in) at
 *  its moved_at; a started row whose turn came: its start, or its turn's opening when it started before it (on red). */
function endsOf(r) {
  let t = r.moved_at ?? null;
  if (r.turn_at != null && r.started != null) {
    const e = r.started >= r.turn_at - LIVE.earlyMs ? Math.max(r.turn_at, r.started) : r.turn_at;
    t = t == null ? e : Math.max(t, e);
  }
  return t;
}

/** One stage's queue at `now`, as its turns go (pure; see the top). rows: [{steam_id, rid (made in this order), slot_at
 *  (ready from), turn_at, started, moved, moved_at, prev_at, out, penalty_ms, entry (its league entry's status or null)}];
 *  first: when the stage's first turn opens (SS1: the hour + 5 min; null for a later stage: each driver's when ready);
 *  stage: 0.. A turn opens when the turn before it ended (endsOf) and its driver is ready (slot_at), to the first in the
 *  queue (slot_at, rid); it ends at its driver's start or LIVE.turnMs on. A row is on its turn while its turn_at is set
 *  and it has not started (one at a time).
 *  -> {rows, each with state ('turn', 'waiting', 'break' (not ready yet), 'started', its out), turnAt, deadline, estAt
 *  (the latest its turn should open), ahead (turns before it); ops: what changed, in order, for settle: {op: 'retire',
 *  row, at} (an entry over: out of the queue; at: its turn ended then), {op: 'turn', row, at} (its turn opened),
 *  {op: 'miss', row, turnAt, from, at} (missed: to the end, ready again from the turn's end), {op: 'out', row, out,
 *  turnAt, at} (missed too often), {op: 'jump', row, ms} (started on red: the seconds jumped)}. */
export function turnsOf(input, first, now, stage = 0) {
  const rows = input.map((r) => ({ ...r, turn_at: r.turn_at ?? null, moved_at: r.moved_at ?? null,
    moved: r.moved || 0, penalty_ms: r.penalty_ms || 0, state: null, turnAt: null, deadline: null, estAt: null, ahead: 0 }));
  const ops = [];
  const byQueue = (a, b) => a.slot_at - b.slot_at || a.rid - b.rid;
  const onTurn = () => rows.find((r) => r.turn_at != null && r.started == null && !r.out);
  const lastEnd = () => rows.reduce((t, r) => Math.max(t, endsOf(r) ?? -Infinity), first == null ? -Infinity : first);
  for (const r of rows) {                              // an entry over before this stage (a DNF before it, a DSQ)
    if (!r.out && r.started == null && r.entry && r.entry !== 'running') {
      const at = r.turn_at != null ? now : null;
      Object.assign(r, { out: 'retired', moved_at: at ?? r.moved_at });
      ops.push({ op: 'retire', row: r, at });
    }
  }
  for (let n = 0; n < 5000; n++) {
    const cur = onTurn();
    if (cur) {
      const deadline = cur.turn_at + LIVE.turnMs;
      if (now < deadline) break;                       // its turn
      if (cur.moved >= LIVE.maxMoves) {                // missed once too often: out
        const out = stage ? 'dnf' : 'dns';
        ops.push({ op: 'out', row: cur, out, turnAt: cur.turn_at, at: deadline });
        Object.assign(cur, { out, prev_at: cur.slot_at, moved_at: deadline });
      } else {                                         // missed: to the end, ready again from its turn's end
        ops.push({ op: 'miss', row: cur, turnAt: cur.turn_at, from: cur.slot_at, at: deadline });
        Object.assign(cur, { prev_at: cur.slot_at, slot_at: deadline, moved: cur.moved + 1, moved_at: deadline, turn_at: null });
      }
      continue;
    }
    const head = rows.filter((r) => r.turn_at == null && !r.out).sort(byQueue)[0];
    if (!head) break;
    const open = Math.max(lastEnd(), head.slot_at);
    if (now < open) break;                             // (the next turn not open yet: a break)
    head.turn_at = open;                               // (one already started: its turn goes by at once)
    ops.push({ op: 'turn', row: head, at: open });
  }
  for (const r of rows) {                              // the starts before their turns, now they came
    if (r.turn_at != null && r.started != null && r.started < r.turn_at - LIVE.earlyMs && !r.penalty_ms) {
      r.penalty_ms = Math.ceil((r.turn_at - r.started) / 1000) * 1000;
      ops.push({ op: 'jump', row: r, ms: r.penalty_ms });
    }
  }
  // the view: the turn, then the queue (each at the latest a turn would take: LIVE.turnMs each, a started one none)
  const cur = onTurn();
  let est = lastEnd(), ahead = 0;
  if (cur) {
    Object.assign(cur, { state: 'turn', turnAt: cur.turn_at, deadline: cur.turn_at + LIVE.turnMs, estAt: cur.turn_at });
    est = cur.deadline;
    ahead = 1;
  }
  for (const r of rows.filter((x) => x.turn_at == null && !x.out && x.started == null).sort(byQueue)) {
    const at = Math.max(est, r.slot_at);
    Object.assign(r, { state: now < r.slot_at ? 'break' : 'waiting', estAt: at, ahead });
    if (!ahead) Object.assign(r, { turnAt: at, deadline: at + LIVE.turnMs });
    est = at + LIVE.turnMs;
    ahead += 1;
  }
  for (const r of rows) if (!r.state) Object.assign(r, { state: r.out || 'started', turnAt: r.turn_at });
  rows.sort((a, b) => (a.turn_at ?? Infinity) - (b.turn_at ?? Infinity) || byQueue(a, b));
  return { rows, ops };
}

/** The turns of an event's stages moved on (turnsOf) and written, in one batch, each change guarded to the row as it was
 *  (two looks at the same moment write it once; a start that came in between is not moved): turns opened, the ones who
 *  missed theirs to the end of the queue or out (a later stage's entry then a DNF), a jump start's seconds on that stage
 *  (a league_penalties row by ACR Daily), the entries over taken out. At most LIVE.writes statements a look (the rest the
 *  next look: the turns come out the same from what was written). -> [per stage: turnsOf's rows] for the view. */
export async function settle(env, ev, now) {
  const { results: all } = await env.DB.prepare(`SELECT s.rowid AS rid, s.*, e.status AS entry FROM live_slots s
      LEFT JOIN league_entries e ON e.event_id = s.event_id AND e.steam_id = s.steam_id
    WHERE s.event_id = ? ORDER BY s.stage_no, s.slot_at, s.rowid`).bind(ev.id).all();
  const n = JSON.parse(ev.stages).length;
  const out = [], stmts = [];
  let full = now > ev.closes;                          // (over: nothing moves any more)
  for (let no = 0; no < n; no++) {
    const q = turnsOf(all.filter((r) => r.stage_no === no), no === 0 ? ev.opens + LIVE.firstStartMs : null,
      Math.min(now, ev.closes), no);
    out.push(q.rows);
    const key = (r) => [ev.id, no, r.steam_id];
    // (a turn opened and missed in this same look: written as the miss alone)
    const ops = q.ops.filter((o, i) => !(o.op === 'turn' && q.ops.slice(i + 1).some((x) => x.row === o.row && x.turnAt === o.at)));
    for (const o of ops) {
      if (full) break;
      const add = [];
      if (o.op === 'turn') {
        add.push(env.DB.prepare(`UPDATE live_slots SET turn_at = ? WHERE event_id = ? AND stage_no = ? AND steam_id = ?
          AND turn_at IS NULL AND out IS NULL AND slot_at = ?`).bind(o.at, ...key(o.row), o.row.slot_at));
      } else if (o.op === 'miss') {
        add.push(env.DB.prepare(`UPDATE live_slots SET slot_at = ?1, moved = moved + 1, moved_at = ?1, prev_at = ?2, turn_at = NULL
          WHERE event_id = ?3 AND stage_no = ?4 AND steam_id = ?5 AND started IS NULL AND out IS NULL AND slot_at = ?2
            AND COALESCE(turn_at, ?6) = ?6`).bind(o.at, o.from, ...key(o.row), o.turnAt));
      } else if (o.op === 'out') {
        add.push(env.DB.prepare(`UPDATE live_slots SET out = ?1, moved_at = ?2, prev_at = slot_at, turn_at = ?3 WHERE event_id = ?4
          AND stage_no = ?5 AND steam_id = ?6 AND started IS NULL AND out IS NULL AND COALESCE(turn_at, ?3) = ?3`)
          .bind(o.out, o.at, o.turnAt, ...key(o.row)));
        if (no) {
          add.push(env.DB.prepare(`UPDATE league_entries SET status = 'dnf', reason = ?, updated = ? WHERE event_id = ? AND steam_id = ?
            AND status = 'running'`).bind(`did not start SS${no + 1}`, now, ev.id, o.row.steam_id));
        }
      } else if (o.op === 'retire') {
        add.push(env.DB.prepare(`UPDATE live_slots SET out = 'retired', moved_at = COALESCE(?, moved_at), prev_at = slot_at
          WHERE event_id = ? AND stage_no = ? AND steam_id = ? AND started IS NULL AND out IS NULL`).bind(o.at, ...key(o.row)));
      } else if (o.op === 'jump') {
        add.push(env.DB.prepare(`UPDATE live_slots SET penalty_ms = ? WHERE event_id = ? AND stage_no = ? AND steam_id = ?
          AND penalty_ms = 0`).bind(o.ms, ...key(o.row)));
        add.push(env.DB.prepare(`INSERT INTO league_penalties (event_id, steam_id, stage_no, ms, reason, by, created)
          SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7 WHERE NOT EXISTS (SELECT 1 FROM league_penalties WHERE event_id = ?1 AND steam_id = ?2
            AND stage_no = ?3 AND by = ?6)`).bind(ev.id, o.row.steam_id, no, o.ms,
          `jump start: SS${no + 1} started ${o.ms / 1000} s before the turn`, OFFICIAL_OWNER.id, now));
      }
      if (stmts.length + add.length > LIVE.writes) { full = true; break; }
      stmts.push(...add);
    }
  }
  if (stmts.length) await env.DB.batch(stmts);
  return out;
}

/** When a stage's start was, in server time: the app's (its PC clock set by the server's, b.serverAt) when it is
 *  plausible (from the event's opening to now: a start sent late, from the app's queue, keeps its time), else now. */
function startTime(b, ev, now) {
  const at = Math.round(+b.serverAt);
  return Number.isFinite(at) && at >= ev.opens && at <= now + 5000 ? Math.min(at, now) : now;
}

/** A ranked session's stage started (src/leaguesapi.js, after the leagues' own checks: SS1's start, a later stage's
 *  begin): its time kept on its queue row (the turns judge it: settle, turnsOf; a start on red gets the seconds jumped
 *  once the turn it jumped is known). A stage with no queue row (an app that didn't queue): one made, started. ->
 *  {startedAt} for the app. */
export async function liveStarted(env, ev, steamId, no, b, now) {
  const at = startTime(b, ev, now);
  await env.DB.batch([
    env.DB.prepare(`INSERT OR IGNORE INTO live_slots (event_id, stage_no, steam_id, slot_at, created) VALUES (?, ?, ?, ?, ?)`)
      .bind(ev.id, no, steamId, at, now),
    // (made before the queue moved it on, still on its way to the server: in the turn it missed, back in the queue if
    // that took it out)
    env.DB.prepare(`UPDATE live_slots SET started = ?1,
        turn_at = CASE WHEN turn_at IS NULL AND moved_at IS NOT NULL AND ?1 < moved_at THEN moved_at - ?2 ELSE turn_at END,
        out = CASE WHEN out IN ('dns', 'dnf') AND moved_at IS NOT NULL AND ?1 < moved_at THEN NULL ELSE out END
      WHERE event_id = ?3 AND stage_no = ?4 AND steam_id = ?5 AND started IS NULL`).bind(at, LIVE.turnMs, ev.id, no, steamId),
  ]);
  return { startedAt: at };
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
    // (out of the queues; on its turn: the turn ends now)
    env.DB.prepare(`UPDATE live_slots SET out = 'dnf', moved_at = CASE WHEN turn_at IS NOT NULL THEN ? ELSE moved_at END,
      prev_at = slot_at WHERE event_id = ? AND steam_id = ? AND started IS NULL AND out IS NULL`).bind(now, ev.id, steamId),
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
  return `did not start: missed the turn ${slot.moved + 1} times`;
}

/** A driver who finished the stage before (`no` >= 1) in stage `no`'s queue, ready LIVE.breakMs after the finish (then
 *  their turn comes as the queue goes: whoever is ready first, first). Once: asked again, the same. -> the queue row,
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
  await env.DB.prepare(`INSERT OR IGNORE INTO live_slots (event_id, stage_no, steam_id, slot_at, created) VALUES (?, ?, ?, ?, ?)`)
    .bind(ev.id, no, steamId, fin + LIVE.breakMs, now).run();
  return env.DB.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = ? AND steam_id = ?').bind(ev.id, no, steamId).first();
}

// ------------------------------------------------------------------ what the app gets

const seriesOut = (s, now) => ({ key: s.key, name: s.name, about: s.about, carClass: s.carClass,
  cars: CARS.filter((c) => c.cls === s.carClass).map((c) => ({ name: c.name, id: c.id })),
  rally: rallyOfWeek(s, now), nextRally: rallyOfWeek(s, now + WEEK), everyHours: LIVE.everyMs * SERIES.length / HOUR });

const slotOut = (r) => (r ? { no: r.stage_no, state: r.state || null, at: r.turnAt ?? r.estAt ?? r.slot_at, readyAt: r.slot_at,
  turnAt: r.turnAt ?? null, deadline: r.deadline ?? null, estAt: r.estAt ?? null, ahead: r.ahead ?? 0, moved: r.moved,
  started: r.started, penaltyMs: r.penalty_ms, out: r.out } : null);

/** GET /api/liverallies: the series and their sessions, from the one under way to LIVE.aheadMs on, with how many
 *  signed up and whether I did; the ones over in the last LIVE.recentMs with drivers (recent: their results). A session past its hour with sign-ups is published here too. */
async function overview(env, me, now, rand) {
  const from = Math.max(now - LIVE.openMs, liveFrom(env)), to = now + LIVE.aheadMs;
  const list = sessionsBetween(from, to, liveFrom(env));
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
      await publish(env, x.series, x.starts, now, rand);
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
  // the sessions over in the last LIVE.recentMs that had drivers: their results (newest first, whether I drove)
  const { results: past } = await env.DB.prepare(`SELECT s.series, s.starts, s.event_id, e.only_ids, e.stages FROM live_sessions s
      JOIN league_events e ON e.id = s.event_id
    WHERE s.event_id > 0 AND s.starts >= ? AND s.starts < ? ORDER BY s.starts DESC LIMIT 20`)
    .bind(Math.max(now - LIVE.recentMs, liveFrom(env)), from).all();
  const recent = past.map((r) => {
    const s = SERIES.find((x) => x.key === r.series), only = JSON.parse(r.only_ids || '[]');
    return s ? { series: s.key, starts: r.starts, rally: rallyOfWeek(s, r.starts), eventId: r.event_id, drivers: only.length,
      mine: !!sid && only.includes(sid) } : null;
  }).filter(Boolean);
  return { now, on: true, series: SERIES.map((s) => seriesOut(s, now)), sessions, recent, live: LIVE_RULES, pollS: LIVE.pollS.idle };
}

/** What the app says about the rules (and works out the countdowns with). */
const LIVE_RULES = { signupMin: LIVE.signupMs / MIN, firstStartMin: LIVE.firstStartMs / MIN, turnS: LIVE.turnMs / 1000,
  earlyS: LIVE.earlyMs / 1000, breakS: LIVE.breakMs / 1000, maxMoves: LIVE.maxMoves, stages: LIVE.stages };

/** One session: before its hour its sign-ups; from then its rally (as /api/me/events gives an event: the app drives it
 *  through the leagues' DRIVE), each stage's queue (start list on SS1), the standings and my next slot. */
async function sessionView(env, s, starts, me, now, rand) {
  const t = timesOf(starts);
  let row = await sessionRow(env, s.key, starts);
  if (now >= starts && now < t.closes && (!row || row.event_id == null)) {
    await publish(env, s, starts, now, rand);
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
  const turns = await settle(env, ev, now);
  const [{ results: people }, standings, routes, mineEntry] = await Promise.all([
    env.DB.prepare(`SELECT p.steam_id, p.name, p.country, p.avatar, u.car FROM json_each(?) j JOIN players p ON p.steam_id = j.value
        LEFT JOIN live_signups u ON u.series = ? AND u.starts = ? AND u.steam_id = p.steam_id`)
      .bind(ev.only_ids || '[]', s.key, starts).all(),
    matchRows(env, ev.id, now),
    routesRows(env),
    sid ? env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, sid).first() : null,
  ]);
  const only = JSON.parse(ev.only_ids || '[]');
  const who = new Map(people.map((p) => [p.steam_id, p]));
  const byDriver = new Map(standings.map((r) => [r.steamId, r]));
  // each stage's queue as its turns go: the turns gone by (finished: their time; on stage; DNF), the driver whose turn
  // it is, the waiting (each with the latest its turn should open), the ones on their break, the out
  const queues = turns.map((rows, no) => rows.map((x) => {
    const st = byDriver.get(x.steam_id), p = who.get(x.steam_id) || {};
    const done = st && st.stages && st.stages[no] && st.stages[no].totalMs != null ? st.stages[no] : null;
    const state = x.state === 'started' ? (done ? 'done' : st && st.status === 'dnf' && (st.done || 0) <= no ? 'dnf' : 'driving')
      : x.state;
    return { steamId: x.steam_id, name: p.name || 'Driver', country: p.country || null, avatar: p.avatar || null,
      car: (st && st.car) || p.car || null, at: x.started ?? x.turnAt ?? x.estAt ?? x.slot_at, readyAt: x.slot_at,
      turnAt: x.turnAt, deadline: x.deadline, estAt: x.estAt, ahead: x.ahead, moved: x.moved, started: x.started,
      penaltyMs: x.penalty_ms, state, timeMs: done ? done.totalMs : null };
  }));
  const slots = turns.flatMap((rows, no) => rows.map((x) => ({ ...x, stage_no: no })));
  const o = eventOut(ev, routes, now);
  o.kind = 'live';
  o.league = s.name;
  o.series = s.key;
  o.sessionStarts = starts;
  o.drivers = only.length;
  o.entry = mineEntry ? { car: mineEntry.car, ...entryState(mineEntry, ev, now), done: mineEntry.done, totalMs: mineEntry.total_ms,
    started: mineEntry.started } : null;
  // my next turn: my earliest queue row not started and still in the queue
  const next = sid ? slots.find((x) => x.steam_id === sid && ['turn', 'waiting', 'break'].includes(x.state)) || null : null;
  const myCar = sid ? (who.get(sid) || {}).car || (mineEntry && mineEntry.car) || null : null;
  // the results are out once every driver is done (finished, DNF, DSQ, or out before starting) or the session is over
  const doneOf = (id) => ['finished', 'dnf', 'dsq'].includes((byDriver.get(id) || {}).status) ||
    slots.some((x) => x.steam_id === id && x.stage_no === 0 && x.out);
  const resultsOut = phase === 'over' || (only.length > 0 && only.every(doneOf));
  const near = next && (next.state === 'turn' || (next.state === 'waiting' && next.ahead <= 3) || next.estAt - now < MIN);
  Object.assign(out, { eventId: ev.id, event: o, entrants: only.length, queues, standings, resultsOut,
    me: { signedIn: !!me, signedUp: only.includes(sid), car: myCar, next: slotOut(next),
      out: sid ? slotOut(slots.find((x) => x.steam_id === sid && x.out && x.out !== 'retired')) : null },
    pollS: phase !== 'running' || !only.includes(sid) ? LIVE.pollS.signup : near ? LIVE.pollS.turn
      : next ? LIVE.pollS.wait : LIVE.pollS.running });
  if (phase === 'over' || resultsOut) out.pollS = LIVE.pollS.idle;
  return withTeams(env, out);
}

// ------------------------------------------------------------------ the API

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' } });
const err = (msg, status = 400) => json({ error: msg }, status);
async function readBody(req) {
  try { const b = await req.json(); return b && typeof b === 'object' ? b : {}; } catch { return {}; }
}

/** /api/liverallies... (see the top; /api/live is the dailies' live positions). me: the signed-in player row or null.
 *  -> a Response, or null (not ours). */
export async function liveApi(req, env, path, me, now = Date.now(), rand = Math.random) {
  if (path !== '/api/liverallies' && !path.startsWith('/api/liverallies/')) return null;
  const post = req.method === 'POST';
  const from = liveFrom(env);
  if (testersOnly(env, req)) return path === '/api/liverallies' && !post ? json({ now, on: false, series: [], sessions: [] })
    : err('not found', 404);                          // (as if there were none: nothing said to anyone else)
  if (from === null || now < from - LIVE.aheadMs) return json({ now, on: false, series: [], sessions: [] });
  if (path === '/api/liverallies') return post ? err('not found', 404) : json(await withTeams(env, await overview(env, me, now, rand)));
  const m = path.match(/^\/api\/liverallies\/([a-z0-9]+)\/(\d{13})(?:\/([a-z]+))?$/);
  const s = m && seriesOf(m[1]);
  const starts = m ? +m[2] : NaN;
  if (!s || seriesAt(starts, from) !== s || starts < from) return err('no such session', 404);
  const action = m[3] || '';
  if (!post) return action ? err('not found', 404) : json(await sessionView(env, s, starts, me, now, rand));
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
    return json(await sessionView(env, s, starts, me, now, rand));
  }
  if (action === 'withdraw') {
    if (now >= starts) return err('the start list is out: just don\'t start', 409);
    await env.DB.prepare('DELETE FROM live_signups WHERE series = ? AND starts = ? AND steam_id = ?').bind(s.key, starts, me.steam_id).run();
    return json(await sessionView(env, s, starts, me, now, rand));
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
