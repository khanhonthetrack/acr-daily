// COPILOT (COPILOT_FROM in wrangler.toml, the first day; empty = off): a daily for two, a driver and a co-driver (the
// user, 24 Nov 2026). Each day has one stage, car and weather of its own, kept hidden until you have driven it (as
// driver or as co-driver: "?" in the app until then). Hardcore Mode is on (COPILOT_RULES): damage, wear and failures
// at Realistic.
//
// You drive it once a day as the driver and once as the co-driver (copilot_tries: a row for each role, written as the
// stage starts; a start that never sends a result is a DNF). To start, a driver sets up a lobby and picks a role; the
// other joins (a private lobby: with its code, never listed); both press READY and the lobby starts: both apps are
// given the stage, the driver's app takes the game there to drive it, the co-driver's to watch the driver's car from
// inside it, with the stage's pacenotes (the game's own, from its files: src/pacenotes.js) to read out over voice. The
// game's own co-driver is off for both (the app and the game mod see to it).
//
// The driver's app sends the run as for a time trial stage (the game's own result: stage time + penalties); it goes on
// the day's board as the crew's (driver + co-driver). Not rated.
//
// API:  GET  /api/copilot?date=           the day: on, date, revealed (the stage, car, weather: only once you have
//                                         driven it, or the day is over), my tries, my lobby, the open lobbies
//       GET  /api/copilot/board?date=     the day's crews: finished ones by time, then the DNFs
//       GET  /api/copilot/ranking?month=  the month's drivers and co-drivers, apart: points for each day's place
//       POST /api/copilot/lobbies         {role: 'driver'|'codriver', private} -> a new lobby (its code if private)
//       POST /api/copilot/join            {id} or {code} -> joined
//       GET  /api/copilot/lobbies/:id     a lobby, for its two: once started, the stage (and the notes, for the
//                                         co-driver) and the other's link details (signal)
//       POST /api/copilot/lobbies/:id/ready   {ready}: both ready -> started
//       POST /api/copilot/lobbies/:id/leave   leave it (the host: closed); started: a DNF (the driver's)
//       POST /api/copilot/lobbies/:id/signal  {data}: my side's link details (the apps' direct link, copilotlink.py)
//       POST /api/copilot/runs            the driver's run ('cp:<date>/<lobby>'): finished (the game's result) or a DNF

import { POOL_CARS as CARS, carByName } from './cars.js';
import { describe, pickConditions, stageParts } from './conditions.js';
import { menuName } from './stages.js';
import { routeInfo, validateRun } from './validate.js';
import { timesAt } from './realism.js';
import { cached, dropCached } from './cache.js';
import { PACENOTES } from './pacenotes.js';

export const CP = {
  openMs: 30 * 60000,           // a lobby not started this long after it was made: closed
  driveMs: 90 * 60000,          // a started lobby with no run this long after it started: a DNF
  lateMs: 30 * 60000,           // a run finished just before midnight may arrive a bit after
  signalMax: 2000,              // a side's link details, at most (characters)
  listMax: 30,                  // open lobbies listed
};
// Hardcore Mode: the game locks damage, wear, failures and its penalties at Realistic (docs/hardcore-and-assists.md)
export const COPILOT_RULES = { penalty: 'realistic', respawn: true, damage: true, damageIntensity: 'realistic', wear: 'realistic',
  failures: 'realistic', hardcore: true };
export const ROLES = ['driver', 'codriver'];
const DAY = 86400000;
const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';   // (no 0 / O, 1 / I)

const dayOf = (ms) => new Date(ms).toISOString().slice(0, 10);
const dayStart = (date) => Date.parse(date + 'T00:00:00Z');
const isDate = (d) => /^\d{4}-\d{2}-\d{2}$/.test(String(d)) && dayOf(dayStart(d) || 0) === d;

/** COPILOT's first day (COPILOT_FROM), or null: off. */
export const firstDay = (env) => (env && isDate(env.COPILOT_FROM) ? env.COPILOT_FROM : null);
export const copilotOn = (env, date) => !!firstDay(env) && date >= firstDay(env);

/** 'cp:2026-11-25/12' -> {date, lobby}, else null. */
export function parseCpId(id) {
  const m = String(id || '').match(/^cp:(\d{4}-\d{2}-\d{2})\/(\d{1,9})$/);
  return m && isDate(m[1]) ? { date: m[1], lobby: +m[2] } : null;
}

// ------------------------------------------------------------------ the notes in words

const WORDS = {
  And: 'and', Into: 'into', Long: 'long', VeryLong: 'very long', Short: 'short', Late: 'late', Opens: 'opens',
  OpensLate: 'opens late', Widens: 'widens', Narrows: 'narrows', NarrowsOutside: 'narrows outside', Tightens: 'tightens',
  TightensLate: 'tightens late', Caution: 'caution', Brake: 'brake', HeavyBrake: 'heavy brake', SlowDown: 'slow down',
  DontCut: "don't cut", Cut: 'cut', SmallCut: 'small cut', BigCut: 'big cut', KeepIn: 'keep in', KeepOut: 'keep out',
  KeepLeft: 'keep left', KeepRight: 'keep right', KeepMiddle: 'keep middle', OverCrest: 'over crest', Crest: 'crest',
  OverJump: 'over jump', OverJumpSmall: 'over small jump', OverBigJump: 'over big jump', Jump: 'jump', JumpBig: 'big jump',
  JumpSmall: 'small jump', JumpMaybe: 'jump maybe', Over: 'over', OverBridge: 'over bridge', OverBump: 'over bump',
  OverBumps: 'over bumps', Bumps: 'bumps', Dip: 'dip', IntoDip: 'into dip', Sudden: 'sudden', BadCamber: 'bad camber',
  DitchInside: 'ditch inside', DitchOutside: 'ditch outside', LogsInside: 'logs inside', LogsOutside: 'logs outside',
  Inside: 'inside', OnAsphalt: 'on tarmac', OnGravel: 'on gravel', Slippery: 'slippery', UpHill: 'uphill',
  Downhill: 'downhill', Junction: 'junction', AtJunction: 'at junction', AtTheJunction: 'at the junction',
  AfterJunction: 'after junction', AtTheHouse: 'at the house', ThroughGate: 'through gate', ThroughTunnel: 'through tunnel',
  GoLeft: 'go left', GoRight: 'go right', GoStraight: 'straight on', Finish: 'finish', StopAtMarshals: 'stop at marshals',
  AfterEnd: 'after the end', AfterFinish: 'after the finish', Kinks: 'kinks', KinksStartingLeft: 'kinks starting left',
  KinksStartingRight: 'kinks starting right', RightChicane: 'right chicane', RightChicaneEntry: 'right chicane entry',
  LeftChicane: 'left chicane',
};

/** One token in the co-driver's words: 'Right3' -> 'right 3', 'Dist60' -> '60', 'LeftHP' -> 'left hairpin', a pause
 *  ('Pause0.5s_Reset': how the game's voice times its calls) -> '' (not read out). */
export function tokenWord(t) {
  t = String(t || '');
  if (/^Pause/.test(t)) return '';
  if (WORDS[t]) return WORDS[t];
  let m = t.match(/^Dist(\d+)$/);
  if (m) return m[1];
  m = t.match(/^Tighten(\d)$/);
  if (m) return 'tightens ' + m[1];
  m = t.match(/^(Left|Right)(\d|HP|AcuteHP|OpenHP|Square|Flat|Kink)$/);
  if (m) {
    const side = m[1].toLowerCase();
    return { HP: `${side} hairpin`, AcuteHP: `${side} acute hairpin`, OpenHP: `${side} open hairpin`, Square: `${side} square`,
      Flat: `flat ${side}`, Kink: `kink ${side}` }[m[2]] || `${side} ${m[2]}`;
  }
  return t.replace(/([a-z])([A-Z0-9])/g, '$1 $2').toLowerCase();   // (one not known yet: its own name in words)
}

/** A note's tokens ('Right3 Long Narrows') -> its words ('right 3 long narrows'). */
export const noteText = (tokens) => String(tokens || '').split(' ').map(tokenWord).filter(Boolean).join(' ');

/** A stage's notes for the co-driver: [{n, at (m from the first), len, text, link (read with the next one)}], or null. */
export function notesOf(stageId) {
  const rows = PACENOTES[stageId];
  if (!rows) return null;
  return rows.map(([at, len, toks], i) => ({ n: i + 1, at, len, text: noteText(toks) })).filter((x) => x.text);
}

// ------------------------------------------------------------------ the day's stage

/** The day's pick: a stage with the game's notes, from the dailies' pool (deps.pool), not one of the day's dailies'
 *  stage + car, its car and conditions from the date's hash. -> {track, car, weather, time} or null. */
export function pickCopilot({ byTrack, tracks }, stageOf, date, dailies, hash) {
  const withNotes = tracks.filter((t) => PACENOTES[stageOf.get(t)]);
  if (!withNotes.length) return null;
  const used = new Set(dailies.map((d) => d.track));
  const free = withNotes.filter((t) => !used.has(t));
  const list = free.length ? free : withNotes;
  const track = list[hash(date + '|copilot') % list.length];
  const fixed = byTrack.get(track) || [];
  let car;
  if (fixed.length) car = fixed[hash(date + '|cp-car') % fixed.length];
  else {
    let k = hash(date + '|cp-car|' + track) % CARS.length;
    for (let i = 0; i < CARS.length && dailies.some((d) => d.track === track && d.car === CARS[k].name); i++) k = (k + 1) % CARS.length;
    car = CARS[k].name;
  }
  const cond = pickConditions(track, hash(date + '|cp-w'), hash(date + '|cp-t'));
  return { track, car, weather: cond.weather, time: cond.time };
}

/** The day's stage as stored; today's (or an earlier day's) picked and stored the first time it is asked for. */
export async function dayPick(env, date, deps, now = Date.now()) {
  const row = await env.DB.prepare('SELECT track, car, weather, time FROM copilot_days WHERE date = ?').bind(date).first();
  if (row || date > dayOf(now) || !copilotOn(env, date)) return row || null;
  const pool = await deps.pool();
  const { results } = await env.DB.prepare(`SELECT track, stage_id FROM routes WHERE track IN (SELECT value FROM json_each(?))`)
    .bind(JSON.stringify(pool.tracks)).all();
  const { results: dailies } = await env.DB.prepare('SELECT track, car FROM schedule WHERE date = ?').bind(date).all();
  const p = pickCopilot(pool, new Map(results.map((r) => [r.track, r.stage_id])), date, dailies, deps.hash);
  if (!p) return null;
  await env.DB.prepare('INSERT OR IGNORE INTO copilot_days (date, track, car, weather, time) VALUES (?, ?, ?, ?, ?)')
    .bind(date, p.track, p.car, p.weather, p.time).run();
  return env.DB.prepare('SELECT track, car, weather, time FROM copilot_days WHERE date = ?').bind(date).first();
}

/** The stage as the app takes it (a time trial stage's shape: src/timetrial.js stageOut), for a lobby's run. */
export function stageOut(date, lobbyId, p, route, deps) {
  const car = carByName(p.car), parts = stageParts(p.track);
  return {
    id: `cp:${date}/${lobbyId}`, kind: 'copilot', date, lobby: lobbyId, slot: 0,
    track: p.track, ...parts,
    menuName: (route && menuName(route.stage_id)) || parts.stageName,
    stageId: route ? route.stage_id || null : null,
    car: p.car, carId: car ? car.id : null, carClass: car ? car.cls : null,
    carAliases: car ? [car.telemetry, ...(car.aliases || [])].filter(Boolean) : [],
    ...describe(p.weather, p.time),
    mode: 'weekend', weekend: COPILOT_RULES, penaltyMs: 0, hardcore: true,
    splits: deps.splits, timing: deps.timing,
    startsAt: dayStart(date), endsAt: dayStart(date) + DAY,
    lengthM: route ? Math.round(route.length) : null,
    ...(route && route.points ? { route: JSON.parse(route.points) } : {}),
  };
}

/** The day's stage in short (the board, a revealed day): {track, stageName, menuName, rally, car, weatherLabel...}. */
function revealOut(p, route) {
  if (!p) return null;
  const parts = stageParts(p.track);
  return { track: p.track, ...parts, menuName: (route && menuName(route.stage_id)) || parts.stageName, stageId: route ? route.stage_id : null,
    car: p.car, ...describe(p.weather, p.time), lengthM: route ? Math.round(route.length) : null };
}

// ------------------------------------------------------------------ lobbies

const LOBBY_COLS = `l.id, l.date, l.code, l.host, l.host_role, l.guest, l.host_ready, l.guest_ready, l.state, l.created,
  l.started, l.host_signal, l.guest_signal,
  hp.name AS host_name, hp.avatar AS host_avatar, hp.country AS host_country,
  gp.name AS guest_name, gp.avatar AS guest_avatar, gp.country AS guest_country`;
const LOBBY_FROM = `copilot_lobbies l JOIN players hp ON hp.steam_id = l.host LEFT JOIN players gp ON gp.steam_id = l.guest`;

export const otherRole = (r) => (r === 'driver' ? 'codriver' : 'driver');
/** A lobby's driver and co-driver (Steam ids; null: not joined yet). */
export function crewOf(l) {
  return l.host_role === 'driver' ? { driver: l.host, codriver: l.guest } : { driver: l.guest, codriver: l.host };
}

/** A lobby as the app shows it. me: my Steam id (a member sees its code, its state's details, the other's signal). */
export function lobbyOut(l, me) {
  const mine = me && (l.host === me || l.guest === me);
  const side = (who) => (who === 'host'
    ? { steamId: l.host, name: l.host_name, avatar: l.host_avatar || null, country: l.host_country || null, role: l.host_role, ready: !!l.host_ready }
    : l.guest ? { steamId: l.guest, name: l.guest_name, avatar: l.guest_avatar || null, country: l.guest_country || null,
      role: otherRole(l.host_role), ready: !!l.guest_ready } : null);
  const out = { id: l.id, date: l.date, private: !!l.code, state: l.state, created: l.created, started: l.started || null,
    host: side('host'), guest: side('guest'), wants: l.guest ? null : otherRole(l.host_role) };
  if (mine) {
    const host = l.host === me;
    Object.assign(out, { me: host ? 'host' : 'guest', myRole: host ? l.host_role : otherRole(l.host_role),
      ...(l.code ? { code: l.code } : {}), signal: (host ? l.guest_signal : l.host_signal) || null });
  }
  return out;
}

async function lobbyRow(env, id) {
  return env.DB.prepare(`SELECT ${LOBBY_COLS} FROM ${LOBBY_FROM} WHERE l.id = ?`).bind(id).first();
}

/** Lobbies left open too long are closed; started ones whose run never came are a DNF (copilot_runs). Lazy (on the
 *  calls that list them) and from the cron. */
export async function tidy(env, now) {
  const res = await env.DB.batch([
    env.DB.prepare(`UPDATE copilot_lobbies SET state = 'closed', updated = ? WHERE state = 'open' AND created < ?`).bind(now, now - CP.openMs),
    env.DB.prepare(`INSERT OR IGNORE INTO copilot_runs (date, lobby_id, driver, codriver, status, reason, created)
      SELECT date, id, CASE host_role WHEN 'driver' THEN host ELSE guest END, CASE host_role WHEN 'driver' THEN guest ELSE host END,
        'dnf', 'no result from the driver', ? FROM copilot_lobbies WHERE state = 'started' AND started < ?`).bind(now, now - CP.driveMs),
    env.DB.prepare(`UPDATE copilot_lobbies SET state = 'dnf', updated = ? WHERE state = 'started' AND started < ?`).bind(now, now - CP.driveMs),
  ]);
  if (res[1].meta.changes) {             // (new DNFs: the boards of today and yesterday built again)
    await dropCached(env, [boardKey(dayOf(now)), boardKey(dayOf(now - DAY))]);
  }
}

function newCode() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  return [...b].map((x) => CODE_CHARS[x % CODE_CHARS.length]).join('');
}

/** My tries today: {driver: lobby id or null, codriver: ...}. */
async function triesOf(env, date, me) {
  const { results } = await env.DB.prepare('SELECT role, lobby_id FROM copilot_tries WHERE date = ? AND steam_id = ?').bind(date, me).all();
  const out = { driver: null, codriver: null };
  for (const r of results) out[r.role] = r.lobby_id;
  return out;
}

async function createLobby(env, me, b, now, deps) {
  const { json, err } = deps;
  const date = dayOf(now);
  if (!ROLES.includes(b.role)) return err('role: driver or codriver');
  const tries = await triesOf(env, date, me.steam_id);
  if (tries[b.role]) return err(`you have driven today's CODRIVER as ${b.role === 'driver' ? 'the driver' : 'the co-driver'} already`, 409);
  if (!(await dayPick(env, date, deps, now))) return err('no CODRIVER stage today', 409);
  const code = b.private ? newCode() : null;
  // (one lobby at a time: any other open one of mine is closed, or left)
  const res = await env.DB.batch([
    env.DB.prepare(`UPDATE copilot_lobbies SET state = 'closed', updated = ? WHERE state = 'open' AND host = ?`).bind(now, me.steam_id),
    env.DB.prepare(`UPDATE copilot_lobbies SET guest = NULL, guest_ready = 0, host_ready = 0, guest_signal = NULL, updated = ?
      WHERE state = 'open' AND guest = ?`).bind(now, me.steam_id),
    env.DB.prepare(`INSERT INTO copilot_lobbies (date, code, host, host_role, state, created, updated) VALUES (?, ?, ?, ?, 'open', ?, ?)`)
      .bind(date, code, me.steam_id, b.role, now, now),
  ]);
  const id = res[2].meta.last_row_id;
  return json({ ok: true, lobby: lobbyOut(await lobbyRow(env, id), me.steam_id) });
}

async function joinLobby(env, me, b, now, deps) {
  const { json, err } = deps;
  const date = dayOf(now);
  await tidy(env, now);
  const code = typeof b.code === 'string' ? b.code.trim().toUpperCase() : '';
  // (by its id from the list, a private one with its code too; or by the code alone)
  const l = b.id ? await env.DB.prepare(`SELECT * FROM copilot_lobbies WHERE id = ? AND state = 'open'`).bind(+b.id || 0).first()
    : code ? await env.DB.prepare(`SELECT * FROM copilot_lobbies WHERE code = ? AND date = ? AND state = 'open'`).bind(code, date).first()
      : null;
  if (!l) return err(code && !b.id ? 'no open lobby with that code' : 'that lobby is gone', 404);
  if (l.code && l.code !== code) return err(code ? 'wrong code' : 'a private lobby: join it with its code', 403);
  if (l.date !== date) return err('that lobby was for another day', 409);
  if (l.host === me.steam_id) return json({ ok: true, lobby: lobbyOut(await lobbyRow(env, l.id), me.steam_id) });
  if (l.guest && l.guest !== me.steam_id) return err('that lobby is full', 409);
  const role = otherRole(l.host_role);
  const tries = await triesOf(env, date, me.steam_id);
  if (tries[role]) return err(`you have driven today's CODRIVER as ${role === 'driver' ? 'the driver' : 'the co-driver'} already`, 409);
  const res = await env.DB.batch([
    env.DB.prepare(`UPDATE copilot_lobbies SET state = 'closed', updated = ? WHERE state = 'open' AND host = ?`).bind(now, me.steam_id),
    env.DB.prepare(`UPDATE copilot_lobbies SET guest = NULL, guest_ready = 0, host_ready = 0, guest_signal = NULL, updated = ?
      WHERE state = 'open' AND guest = ? AND id != ?`).bind(now, me.steam_id, l.id),
    env.DB.prepare(`UPDATE copilot_lobbies SET guest = ?, guest_ready = 0, host_ready = 0, updated = ? WHERE id = ? AND state = 'open'
      AND (guest IS NULL OR guest = ?)`).bind(me.steam_id, now, l.id, me.steam_id),
  ]);
  if (!res[2].meta.changes) return err('that lobby is full', 409);
  return json({ ok: true, lobby: lobbyOut(await lobbyRow(env, l.id), me.steam_id) });
}

/** READY (or not): with both ready the lobby starts, at once and once: a try for each (one a role a day: copilot_tries'
 *  key), the lobby 'started', in one batch; a try already used (the same driver's other lobby) and nothing starts. */
async function setReady(env, me, id, b, now, deps) {
  const { json, err } = deps;
  const l = await env.DB.prepare('SELECT * FROM copilot_lobbies WHERE id = ?').bind(id).first();
  if (!l || (l.host !== me.steam_id && l.guest !== me.steam_id)) return err('not your lobby', 404);
  if (l.state !== 'open') return json({ ok: true, lobby: await lobbyFor(env, id, me, deps) });
  const col = l.host === me.steam_id ? 'host_ready' : 'guest_ready';
  await env.DB.prepare(`UPDATE copilot_lobbies SET ${col} = ?, updated = ? WHERE id = ? AND state = 'open'`).bind(b.ready === false ? 0 : 1, now, id).run();
  const after = await env.DB.prepare('SELECT * FROM copilot_lobbies WHERE id = ?').bind(id).first();
  if (after.host_ready && after.guest_ready && after.guest && after.state === 'open') {
    if (after.date !== dayOf(now)) {
      await env.DB.prepare(`UPDATE copilot_lobbies SET state = 'closed', updated = ? WHERE id = ?`).bind(now, id).run();
      return err('the day is over: set up a new lobby', 409);
    }
    const { driver, codriver } = crewOf(after);
    const res = await env.DB.batch([
      env.DB.prepare(`INSERT OR IGNORE INTO copilot_tries (date, steam_id, role, lobby_id, created) VALUES (?, ?, 'driver', ?, ?)`)
        .bind(after.date, driver, id, now),
      env.DB.prepare(`INSERT OR IGNORE INTO copilot_tries (date, steam_id, role, lobby_id, created) VALUES (?, ?, 'codriver', ?, ?)`)
        .bind(after.date, codriver, id, now),
      env.DB.prepare(`UPDATE copilot_lobbies SET state = 'started', started = ?, updated = ? WHERE id = ? AND state = 'open'
        AND (SELECT COUNT(*) FROM copilot_tries WHERE lobby_id = ?) = 2`).bind(now, now, id, id),
      // (a try already used: the other row of this lobby taken back, nothing started)
      env.DB.prepare(`DELETE FROM copilot_tries WHERE lobby_id = ? AND NOT EXISTS (SELECT 1 FROM copilot_lobbies WHERE id = ? AND state = 'started')`)
        .bind(id, id),
    ]);
    if (!res[2].meta.changes) {
      await env.DB.prepare(`UPDATE copilot_lobbies SET host_ready = 0, guest_ready = 0, updated = ? WHERE id = ? AND state = 'open'`).bind(now, id).run();
      return err('one of you has driven today\'s CODRIVER in that role already', 409);
    }
  }
  return json({ ok: true, lobby: await lobbyFor(env, id, me, deps) });
}

async function leaveLobby(env, me, id, now, deps) {
  const { json, err } = deps;
  const l = await env.DB.prepare('SELECT * FROM copilot_lobbies WHERE id = ?').bind(id).first();
  if (!l || (l.host !== me.steam_id && l.guest !== me.steam_id)) return err('not your lobby', 404);
  if (l.state === 'open') {
    if (l.host === me.steam_id) {
      await env.DB.prepare(`UPDATE copilot_lobbies SET state = 'closed', updated = ? WHERE id = ?`).bind(now, id).run();
    } else {
      await env.DB.prepare(`UPDATE copilot_lobbies SET guest = NULL, guest_ready = 0, host_ready = 0, guest_signal = NULL, updated = ?
        WHERE id = ? AND guest = ?`).bind(now, id, me.steam_id).run();
    }
  } else if (l.state === 'started' && crewOf(l).driver === me.steam_id) {
    // (the driver gives up: a DNF now; a co-driver leaving leaves the driver to finish alone)
    await endRun(env, l, { status: 'dnf', reason: 'the driver left', clockMs: null, resets: 0, totalMs: null }, null, now);
  }
  return json({ ok: true });
}

async function setSignal(env, me, id, b, now, deps) {
  const { json, err } = deps;
  const data = typeof b.data === 'string' ? b.data : JSON.stringify(b.data || null);
  if (data.length > CP.signalMax) return err('too long', 413);
  const res = await env.DB.prepare(`UPDATE copilot_lobbies SET host_signal = CASE WHEN host = ?1 THEN ?2 ELSE host_signal END,
      guest_signal = CASE WHEN guest = ?1 THEN ?2 ELSE guest_signal END, updated = ?3 WHERE id = ?4 AND (host = ?1 OR guest = ?1)
      AND state IN ('open', 'started')`).bind(me.steam_id, data, now, id).run();
  if (!res.meta.changes) return err('not your lobby', 404);
  return json({ ok: true });
}

/** A lobby for one of its two: once started, the stage (with its route) and, for the co-driver, the notes. */
async function lobbyFor(env, id, me, deps) {
  const l = await lobbyRow(env, id);
  if (!l) return null;
  const out = lobbyOut(l, me.steam_id);
  if (out.me && l.state !== 'open' && l.state !== 'closed') {
    const p = await env.DB.prepare('SELECT track, car, weather, time FROM copilot_days WHERE date = ?').bind(l.date).first();
    const route = p ? await env.DB.prepare('SELECT points, length, stage_id FROM routes WHERE track = ?').bind(p.track).first() : null;
    if (p) {
      out.ch = stageOut(l.date, l.id, p, route, deps);
      if (out.myRole === 'codriver') out.notes = notesOf(out.ch.stageId) || [];
    }
    const run = await env.DB.prepare('SELECT status, reason, total_ms, clock_ms FROM copilot_runs WHERE lobby_id = ?').bind(id).first();
    if (run) out.result = { status: run.status, reason: run.reason || null, totalMs: run.total_ms, clockMs: run.clock_ms };
  }
  return out;
}

// ------------------------------------------------------------------ runs and the board

export const boardKey = (date) => `cpboard:${date}`;

/** The day's crews: finished ones by time (ties: who finished first), then the DNFs. */
export async function buildBoard(env, date) {
  const { results } = await env.DB.prepare(`SELECT r.id AS runId, r.status, r.reason, r.total_ms AS totalMs, r.clock_ms AS clockMs,
      r.created, r.driver, r.codriver, d.name AS dName, d.avatar AS dAvatar, d.country AS dCountry,
      c.name AS cName, c.avatar AS cAvatar, c.country AS cCountry
    FROM copilot_runs r JOIN players d ON d.steam_id = r.driver JOIN players c ON c.steam_id = r.codriver
    WHERE r.date = ? AND d.banned = 0 AND c.banned = 0
    ORDER BY CASE r.status WHEN 'finished' THEN 0 ELSE 1 END, r.total_ms, r.created, r.id`).bind(date).all();
  const lead = results.find((r) => r.status === 'finished');
  let rank = 0;
  const entries = results.map((r) => ({
    runId: r.runId, status: r.status, reason: r.status === 'finished' ? null : r.reason || 'did not finish',
    rank: r.status === 'finished' ? ++rank : null, totalMs: r.totalMs, clockMs: r.clockMs,
    gapMs: r.status === 'finished' && lead ? r.totalMs - lead.totalMs : null, created: r.created,
    driver: { steamId: r.driver, name: r.dName, avatar: r.dAvatar || null, country: r.dCountry || null },
    codriver: { steamId: r.codriver, name: r.cName, avatar: r.cAvatar || null, country: r.cCountry || null },
  }));
  return { date, entries, crews: entries.length, finished: rank };
}

export const board = (env, date, now = Date.now()) =>
  cached(env, boardKey(date), now - dayStart(date) < DAY + 2 * 3600000 ? 2 * 60000 : 30 * DAY, () => buildBoard(env, date));

// ------------------------------------------------------------------ the ranking

/** Points for a day's place among the crews that finished (a rally's: 25, 18, 15...); any other finish 1. */
export const POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
export const pointsFor = (place) => (place >= 1 && place <= POINTS.length ? POINTS[place - 1] : place > 0 ? 1 : 0);
export const rankingKey = (month) => `cprank:${month}`;
const isMonth = (m) => /^\d{4}-(0[1-9]|1[0-2])$/.test(String(m));

/** A month's ranking (YYYY-MM): each day's finished crews placed by time, points for each place, summed for each
 *  driver (as the driver) and each co-driver (as the co-driver), apart. -> {month, drivers: [{rank, steamId, name,
 *  avatar, country, points, days, wins, best}], codrivers: [...]} (best: their best place). */
export async function buildRanking(env, month) {
  const { results } = await env.DB.prepare(`SELECT r.date, r.driver, r.codriver,
      ROW_NUMBER() OVER (PARTITION BY r.date ORDER BY r.total_ms, r.created, r.id) AS place
    FROM copilot_runs r JOIN players d ON d.steam_id = r.driver JOIN players c ON c.steam_id = r.codriver
    WHERE r.date BETWEEN ? AND ? AND r.status = 'finished' AND d.banned = 0 AND c.banned = 0`)
    .bind(month + '-01', month + '-31').all();
  const tally = (role) => {
    const by = new Map();
    for (const r of results) {
      const sid = r[role];
      const t = by.get(sid) || { steamId: sid, points: 0, days: 0, wins: 0, best: null, first: r.date };
      if (r.date < t.first) t.first = r.date;
      t.points += pointsFor(r.place);
      t.days += 1;
      if (r.place === 1) t.wins += 1;
      t.best = t.best == null ? r.place : Math.min(t.best, r.place);
      by.set(sid, t);
    }
    // (all even: whoever scored first, then the Steam id: never an order that changes from one look to the next)
    return [...by.values()].sort((a, b) => b.points - a.points || b.wins - a.wins || a.best - b.best || b.days - a.days ||
      a.first.localeCompare(b.first) || a.steamId.localeCompare(b.steamId)).map(({ first, ...x }) => x);
  };
  const drivers = tally('driver'), codrivers = tally('codriver');
  const ids = [...new Set([...drivers, ...codrivers].map((x) => x.steamId))];
  const who = new Map();
  for (let i = 0; i < ids.length; i += 90) {
    const part = ids.slice(i, i + 90);
    const { results: ps } = await env.DB.prepare(`SELECT steam_id, name, avatar, country FROM players
      WHERE steam_id IN (${part.map(() => '?').join(',')})`).bind(...part).all();
    for (const p of ps) who.set(p.steam_id, p);
  }
  const out = (list) => list.map((x, i) => {
    const p = who.get(x.steamId) || {};
    return { rank: i + 1, ...x, name: p.name || '?', avatar: p.avatar || null, country: p.country || null };
  });
  return { month, drivers: out(drivers), codrivers: out(codrivers) };
}

export const ranking = (env, month, now = Date.now()) =>
  cached(env, rankingKey(month), month >= dayOf(now - DAY).slice(0, 7) ? 2 * 60000 : 30 * DAY, () => buildRanking(env, month));

/** A started lobby's run in: on the board (once: a lobby has one run), the lobby over. */
async function endRun(env, l, v, splits, now, appVersion = '', startedAt = null) {
  const { driver, codriver } = crewOf(l);
  const res = await env.DB.batch([
    env.DB.prepare(`INSERT OR IGNORE INTO copilot_runs (date, lobby_id, driver, codriver, status, reason, clock_ms, resets, total_ms,
        splits, app_version, started_at, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(l.date, l.id, driver, codriver, v.status === 'finished' ? 'finished' : 'dnf', v.status === 'finished' ? null : String(v.reason || 'DNF').slice(0, 200),
        v.clockMs ?? null, v.resets || 0, v.totalMs ?? null, splits ? JSON.stringify(splits) : null, String(appVersion).slice(0, 20), startedAt, now),
    env.DB.prepare(`UPDATE copilot_lobbies SET state = ?, updated = ? WHERE id = ? AND state = 'started'`)
      .bind(v.status === 'finished' ? 'finished' : 'dnf', now, l.id),
  ]);
  await dropCached(env, [boardKey(l.date), rankingKey(l.date.slice(0, 7))]);
  return res[0].meta.changes > 0;
}

/** The driver's run ('cp:<date>/<lobby>'): finished with the game's result, or a DNF. Only the lobby's driver's, on its
 *  day's stage and car, once. */
async function submit(req, env, me, now, deps) {
  const { json, err } = deps;
  let sub;
  try { sub = await req.json(); } catch { return err('bad json'); }
  const id = parseCpId(sub && sub.challengeId);
  if (!id) return err('invalid run: not a CODRIVER stage');
  const old = deps.tooOld(req, sub);
  if (old) return old;
  const l = await env.DB.prepare('SELECT * FROM copilot_lobbies WHERE id = ? AND date = ?').bind(id.lobby, id.date).first();
  if (!l) return err('invalid run: no such CODRIVER lobby', 409);
  if (crewOf(l).driver !== me.steam_id) return err('invalid run: only the lobby\'s driver sends its run', 403);
  if (l.state !== 'started') {
    const had = await env.DB.prepare('SELECT status, total_ms FROM copilot_runs WHERE lobby_id = ?').bind(l.id).first();
    return had ? json({ ok: true, already: true, status: had.status, totalMs: had.total_ms }) : err('invalid run: that lobby never started', 409);
  }
  if (now >= dayStart(id.date) + DAY + CP.lateMs) return err('too late: that day is over', 409);
  const p = await env.DB.prepare('SELECT track, car, weather, time FROM copilot_days WHERE date = ?').bind(id.date).first();
  const route = p ? await env.DB.prepare('SELECT points, length, stage_id FROM routes WHERE track = ?').bind(p.track).first() : null;
  if (!p || !route) return err('no CODRIVER stage', 409);
  if (sub.track !== p.track || sub.car !== p.car) return err('invalid: not the CODRIVER stage/car', 422);
  const v = validateRun(sub, routeInfo(JSON.parse(route.points)), 0, true);
  if (!v.ok) return err('invalid: ' + v.reason, 422);
  const splits = v.status === 'finished' && v.trace && v.trace.length ? timesAt(v.trace, { points: JSON.parse(route.points) }, deps.splits, 0) : null;
  await endRun(env, l, v, splits, now, sub.appVersion || '', deps.startedMs(sub.startedAt, now));
  const b = await buildBoard(env, id.date);
  const mine = b.entries.find((e) => e.runId && e.driver.steamId === me.steam_id && e.codriver.steamId === crewOf(l).codriver);
  return json({ ok: true, status: v.status === 'finished' ? 'finished' : 'dnf', counted: true, totalMs: v.totalMs ?? null,
    rank: mine ? mine.rank : null, drivers: b.finished, crews: b.crews });
}

// ------------------------------------------------------------------ the API

/** /api/copilot...: a Response, or null when the path isn't one. deps: as the time trial's (index.js ttDeps). */
export async function copilotApi(req, env, path, url, me, sameOrigin, now, deps) {
  if (path !== '/api/copilot' && !path.startsWith('/api/copilot/')) return null;
  const { json, err } = deps;
  const post = req.method === 'POST';
  const today = dayOf(now);
  if (!firstDay(env)) return path === '/api/copilot' && !post ? json({ on: false }) : err('CODRIVER is off on this server', 404);

  if (path === '/api/copilot' && !post) {
    const date = url.searchParams.get('date') || today;
    if (!isDate(date)) return err('bad date');
    if (date > today) return err('no peeking', 403);
    if (!copilotOn(env, date)) return json({ on: false, date, startsAt: dayStart(firstDay(env)) });
    await tidy(env, now);
    const p = await dayPick(env, date, deps, now);
    const tries = me ? await triesOf(env, date, me.steam_id) : { driver: null, codriver: null };
    let revealed = date < today;
    if (!revealed && me && (tries.driver || tries.codriver)) {
      const ended = await env.DB.prepare(`SELECT 1 AS x FROM copilot_lobbies WHERE id IN (?, ?) AND state IN ('finished', 'dnf')`)
        .bind(tries.driver || 0, tries.codriver || 0).first();
      revealed = !!ended;
    }
    const route = revealed && p ? await env.DB.prepare('SELECT length, stage_id FROM routes WHERE track = ?').bind(p.track).first() : null;
    // the lobby browser: every lobby of the day still on (waiting, full, on the stage), private ones too (locked: joined
    // with their code, never shown); the ones with room first
    const [open, mine] = await env.DB.batch([
      env.DB.prepare(`SELECT ${LOBBY_COLS} FROM ${LOBBY_FROM} WHERE l.date = ? AND l.state IN ('open', 'started')
        ORDER BY CASE WHEN l.state = 'open' AND l.guest IS NULL THEN 0 WHEN l.state = 'open' THEN 1 ELSE 2 END, l.created DESC
        LIMIT ?`).bind(date, CP.listMax),
      env.DB.prepare(`SELECT l.id FROM copilot_lobbies l WHERE l.date = ?1 AND (l.host = ?2 OR l.guest = ?2)
        AND l.state IN ('open', 'started') ORDER BY l.created DESC LIMIT 1`).bind(date, me ? me.steam_id : ''),
    ]);
    const myLobby = mine.results[0] ? await lobbyFor(env, mine.results[0].id, me, deps) : null;
    return json({ on: true, date, startsAt: dayStart(date), endsAt: dayStart(date) + DAY, signedIn: !!me, rules: COPILOT_RULES,
      ready: !!p, revealed, ...(revealed ? { stage: revealOut(p, route) } : {}), tries,
      lobby: myLobby, lobbies: open.results.map((l) => ({ ...lobbyOut(l, null),
        ...(me && (l.host === me.steam_id || l.guest === me.steam_id) ? { mine: true } : {}) })) });
  }
  if (path === '/api/copilot/board' && !post) {
    const date = url.searchParams.get('date') || today;
    if (!isDate(date) || date > today) return err('bad date');
    const b = await board(env, date, now);
    const mine = me ? b.entries.some((e) => e.driver.steamId === me.steam_id || e.codriver.steamId === me.steam_id) : false;
    if (date < today || mine) {
      const p = await env.DB.prepare('SELECT track, car, weather, time FROM copilot_days WHERE date = ?').bind(date).first();
      const route = p ? await env.DB.prepare('SELECT length, stage_id FROM routes WHERE track = ?').bind(p.track).first() : null;
      return json({ ...b, stage: revealOut(p, route) });
    }
    return json(b);
  }
  if (path === '/api/copilot/ranking' && !post) {
    const month = url.searchParams.get('month') || today.slice(0, 7);
    if (!isMonth(month) || month > today.slice(0, 7)) return err('bad month: YYYY-MM');
    return json(await ranking(env, month, now));
  }
  const lm = path.match(/^\/api\/copilot\/lobbies\/(\d+)(?:\/(ready|leave|signal))?$/);
  if (lm && !post && !lm[2]) {
    if (!me) return err('sign in with Steam first', 401);
    const l = await lobbyFor(env, +lm[1], me, deps);
    return l && l.me ? json({ lobby: l }) : err('not your lobby', 404);
  }
  if (!post) return err('not found', 404);
  if (!me) return err('sign in with Steam first', 401);
  if (me.banned) return err('this account is banned', 403);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (!copilotOn(env, today)) return err('no CODRIVER today', 409);
  const body = async () => (await req.json().catch(() => ({}))) || {};
  if (path === '/api/copilot/lobbies') return createLobby(env, me, await body(), now, deps);
  if (path === '/api/copilot/join') return joinLobby(env, me, await body(), now, deps);
  if (path === '/api/copilot/runs') return submit(req, env, me, now, deps);
  if (lm && lm[2] === 'ready') return setReady(env, me, +lm[1], await body(), now, deps);
  if (lm && lm[2] === 'leave') return leaveLobby(env, me, +lm[1], now, deps);
  if (lm && lm[2] === 'signal') return setSignal(env, me, +lm[1], await body(), now, deps);
  return err('not found', 404);
}

/** The cron: today's stage picked as the day starts, old lobbies tidied. */
export async function copilotTick(env, now, deps) {
  if (!firstDay(env)) return null;
  const date = dayOf(now);
  if (copilotOn(env, date)) await dayPick(env, date, deps, now);
  await tidy(env, now);
  return { date };
}
