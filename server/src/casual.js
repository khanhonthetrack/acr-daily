// CASUAL (switched on with COPILOT_FROM, as src/copilot.js): a lobby of up to 4, the host driving a stage of their own
// choosing (any stage with the game's pacenotes), up to 3 co-drivers reading the notes. No results, no board, no tries a
// day, not tied to a day. The host picks the stage, car, weather, time of day, up to 3 languages, public or private (a
// 6-letter code); co-drivers join and press READY (only informational); the host presses START (any time, alone too);
// whoever is in the lobby then takes part, nobody joins after. Open lobbies are closed after CX.openMs, started ones
// finished after CX.liveMs. The app opens one direct voice link for each driver<->co-driver pair: each signal is
// addressed to one member (casual_signals: lobby, from, to).
//
// Someone without the game (next to the driver, or on Discord) reads the notes on a page, /n/<token> (src/casualpage.js),
// the link a QR code in the lobby: no login, valid while the lobby is on and CX.noteMs after.
//
// API (all JSON; 404 when COPILOT_FROM is off):
//   GET  /api/casual/options               what a lobby's creator may choose: stages, cars, weather, times
//   GET  /api/casual                       {on, lobbies: [public open + started], lobby: mine or null}
//   POST /api/casual/lobbies               {track, car, weather, time, langs, private} -> {ok, lobby}
//   POST /api/casual/join                  {id} or {code} -> {ok, lobby}
//   GET  /api/casual/lobbies/:id           a lobby, for its members
//   POST /api/casual/lobbies/:id/ready     {ready}
//   POST /api/casual/lobbies/:id/start     the host's
//   POST /api/casual/lobbies/:id/leave     the host: open -> closed, started -> finished; a member: out
//   POST /api/casual/lobbies/:id/signal    {to: <member's Steam id>, data} -> that member's signals[<my Steam id>]
//   GET  /api/n/<token>                    {stage, car, notes} (no login)

import { POOL_CARS, carByName } from './cars.js';
import { TIMES, WEATHER, describe, stageParts } from './conditions.js';
import { menuName } from './stages.js';
import { PACENOTES } from './pacenotes.js';
import { WEEKEND_RULES } from './weekend.js';
import { CP, copilotOn, firstDay, notesOf, parseLangs, stageOut } from './copilot.js';
import { notesGonePage, notesPage } from './casualpage.js';

export const CX = {
  max: 4,                       // people in a lobby, the host included
  openMs: 3 * 3600000,          // a lobby not started this long after it was made: closed
  liveMs: 3 * 3600000,          // a started lobby this long after it started: finished
  noteMs: 2 * 3600000,          // the notes page after the lobby has ended
  keepMs: 7 * 86400000,         // an ended lobby's rows kept this long
  listMax: 40,
  signalMax: CP.signalMax,
};
const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const TOKEN_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789';
const TOKEN_RE = /^[A-Za-z0-9_-]{12}$/;

const randomString = (chars, n) => {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return [...b].map((x) => chars[x % chars.length]).join('');
};

const carOut = (name) => {
  const c = carByName(name);
  return { id: c ? c.id : null, name: c ? c.name : String(name), cls: c ? c.cls : null };
};
const stageShort = (track, route) => {
  const parts = stageParts(track);
  return { track, stageName: parts.stageName, menuName: (route && menuName(route.stage_id)) || parts.stageName, rally: parts.rally,
    lengthM: route && route.length ? Math.round(route.length) : null };
};
const langsOf = (s) => { try { const a = JSON.parse(s); return Array.isArray(a) ? a : []; } catch { return []; } };
const labelOf = (weather, time) => {
  const d = describe(weather, time);
  return { weather: { code: weather, label: d.weatherLabel }, time: { code: time, label: d.timeLabel } };
};

// ------------------------------------------------------------------ what may be chosen

/** The stages a lobby may use: the dailies' pool's, those with the game's notes. -> [{track, route}] sorted. */
async function stagePool(env, deps) {
  const pool = await deps.pool();
  const { results } = await env.DB.prepare(`SELECT track, length, stage_id FROM routes WHERE track IN (SELECT value FROM json_each(?))`)
    .bind(JSON.stringify(pool.tracks)).all();
  return results.filter((r) => PACENOTES[r.stage_id]).map((r) => ({ track: r.track, route: r }));
}

export async function optionsOut(env, deps) {
  const stages = (await stagePool(env, deps)).map((s) => stageShort(s.track, s.route))
    .sort((a, b) => String(a.rally).localeCompare(String(b.rally)) || String(a.menuName).localeCompare(String(b.menuName)));
  return {
    stages,
    cars: POOL_CARS.map((c) => ({ id: c.id, name: c.name, cls: c.cls })),
    weather: Object.entries(WEATHER).map(([code, w]) => ({ code, label: w.label })),
    times: TIMES.map((t) => ({ code: t.id, label: `${t.label} (${t.hour})` })),
  };
}

// ------------------------------------------------------------------ lobbies

/** A lobby as the app shows it. l: the lobby's row + members (rows: steam_id, name, avatar, country, seat, ready), route
 *  (track, length, stage_id) and signals (the ones for me: {from_id, data}). me: my Steam id, or null. */
export function lobbyOut(l, me) {
  const members = (l.members || []).slice().sort((a, b) => a.seat - b.seat).map((m) => ({ steamId: m.steam_id, name: m.name,
    avatar: m.avatar || null, country: m.country || null, role: m.seat === 0 ? 'driver' : 'codriver', seat: m.seat, ready: !!m.ready }));
  const host = members.find((m) => m.seat === 0) || null;
  const out = {
    id: l.id, private: !!l.code, state: l.state, created: l.created, started: l.started || null, max: CX.max,
    langs: langsOf(l.langs), stage: stageShort(l.track, l.route), car: carOut(l.car), ...labelOf(l.weather, l.time),
    host: host && { steamId: host.steamId, name: host.name, avatar: host.avatar, country: host.country },
    members, count: members.length, free: Math.max(0, CX.max - members.length),
  };
  const mine = me && members.find((m) => m.steamId === me);
  if (mine) {
    out.me = { steamId: mine.steamId, role: mine.role, seat: mine.seat };
    if (l.code) out.code = l.code;
    out.notesUrl = '/n/' + l.token;
    out.signals = {};
    for (const s of l.signals || []) out.signals[s.from_id] = s.data;
  }
  return out;
}

/** Lobby rows (casual_lobbies.*) -> lobbyOut for each, with members, routes, and the signals to me: one batch. */
async function hydrate(env, rows, me) {
  if (!rows.length) return [];
  const ids = JSON.stringify(rows.map((r) => r.id));
  const tracks = JSON.stringify([...new Set(rows.map((r) => r.track))]);
  const stmts = [
    env.DB.prepare(`SELECT m.lobby_id, m.steam_id, m.seat, m.ready, p.name, p.avatar, p.country FROM casual_members m
      JOIN players p ON p.steam_id = m.steam_id WHERE m.lobby_id IN (SELECT value FROM json_each(?))`).bind(ids),
    env.DB.prepare(`SELECT track, length, stage_id FROM routes WHERE track IN (SELECT value FROM json_each(?))`).bind(tracks),
  ];
  if (me) stmts.push(env.DB.prepare(`SELECT lobby_id, from_id, data FROM casual_signals WHERE to_id = ? AND lobby_id IN (SELECT value FROM json_each(?))`).bind(me, ids));
  const [ms, rs, ss] = await env.DB.batch(stmts);
  const route = new Map(rs.results.map((r) => [r.track, r]));
  return rows.map((r) => lobbyOut({ ...r, route: route.get(r.track) || null,
    members: ms.results.filter((m) => m.lobby_id === r.id), signals: ss ? ss.results.filter((s) => s.lobby_id === r.id) : [] }, me));
}

/** What a started lobby gives its members: the stage as the app takes it (ch) and the stage's notes. */
async function addStage(env, out, row, deps) {
  if (!out.me || out.state !== 'started') return out;
  const route = await env.DB.prepare('SELECT points, length, stage_id FROM routes WHERE track = ?').bind(row.track).first();
  const day = new Date(row.started || row.created).toISOString().slice(0, 10);
  out.ch = {
    ...stageOut(day, row.id, { track: row.track, car: row.car, weather: row.weather, time: row.time }, route, deps),
    id: `cx:${row.id}`, kind: 'casual', lobby: row.id, mode: 'weekend', weekend: { ...WEEKEND_RULES, hardcore: false }, hardcore: false,
    penaltyMs: 0, startsAt: row.started || row.created, endsAt: (row.started || row.created) + CX.liveMs,
  };
  out.notes = notesOf(out.ch.stageId) || [];
  return out;
}

async function lobbyFor(env, id, me, deps) {
  const row = await env.DB.prepare('SELECT * FROM casual_lobbies WHERE id = ?').bind(id).first();
  if (!row) return null;
  const [out] = await hydrate(env, [row], me.steam_id);
  return addStage(env, out, row, deps);
}

/** Lobbies left open too long are closed, started ones finished, old ended ones' rows dropped (lazy, and the cron). */
export async function tidy(env, now) {
  await env.DB.batch([
    env.DB.prepare(`UPDATE casual_lobbies SET state = 'closed', updated = ? WHERE state = 'open' AND created < ?`).bind(now, now - CX.openMs),
    env.DB.prepare(`UPDATE casual_lobbies SET state = 'finished', updated = ? WHERE state = 'started' AND started < ?`).bind(now, now - CX.liveMs),
    env.DB.prepare(`DELETE FROM casual_signals WHERE lobby_id IN (SELECT id FROM casual_lobbies WHERE state IN ('finished', 'closed') AND updated < ?)`)
      .bind(now - CX.noteMs),
    env.DB.prepare(`DELETE FROM casual_members WHERE lobby_id IN (SELECT id FROM casual_lobbies WHERE state IN ('finished', 'closed') AND updated < ?)`)
      .bind(now - CX.keepMs),
    env.DB.prepare(`DELETE FROM casual_lobbies WHERE state IN ('finished', 'closed') AND updated < ?`).bind(now - CX.keepMs),
  ]);
}

/** Statements that take me out of any other lobby: mine as the host is closed (open) or finished (started), as a member
 *  I am removed (with the signals to and from me). One lobby at a time. */
function leaveOthers(env, me, exceptId, now) {
  const live = `SELECT id FROM casual_lobbies WHERE state IN ('open', 'started') AND id != ?2`;
  return [
    env.DB.prepare(`UPDATE casual_lobbies SET state = 'closed', updated = ?1 WHERE state = 'open' AND host = ?3 AND id != ?2`).bind(now, exceptId, me),
    env.DB.prepare(`UPDATE casual_lobbies SET state = 'finished', updated = ?1 WHERE state = 'started' AND host = ?3 AND id != ?2`).bind(now, exceptId, me),
    env.DB.prepare(`DELETE FROM casual_signals WHERE (from_id = ?3 OR to_id = ?3) AND lobby_id IN (${live})`).bind(now, exceptId, me),
    env.DB.prepare(`DELETE FROM casual_members WHERE steam_id = ?3 AND lobby_id IN (${live})`).bind(now, exceptId, me),
  ];
}

async function createLobby(env, me, b, now, deps) {
  const { json, err } = deps;
  const lg = parseLangs(b.langs);
  if (lg.error) return err(lg.error);
  const stage = (await stagePool(env, deps)).find((s) => s.track === b.track);
  if (typeof b.track !== 'string' || !stage) return err('track: a stage with pacenotes from /api/casual/options');
  const car = typeof b.car === 'string' ? carByName(b.car) : null;
  if (!car || !POOL_CARS.includes(car)) return err('car: one from /api/casual/options');
  if (typeof b.weather !== 'string' || !Object.hasOwn(WEATHER, b.weather)) return err('weather: one from /api/casual/options');
  if (typeof b.time !== 'string' || !TIMES.some((t) => t.id === b.time)) return err('time: one from /api/casual/options');
  const token = randomString(TOKEN_CHARS, 12);
  const code = b.private ? randomString(CODE_CHARS, 6) : null;
  await env.DB.batch([
    // (the new lobby's id isn't known yet: the others are left from the ones that exist, then it is inserted)
    ...leaveOthers(env, me.steam_id, 0, now),
    env.DB.prepare(`INSERT INTO casual_lobbies (token, code, host, track, car, weather, time, langs, state, created, updated)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)`)
      .bind(token, code, me.steam_id, stage.track, car.name, b.weather, b.time, lg.langs.length ? JSON.stringify(lg.langs) : null, now, now),
    env.DB.prepare(`INSERT INTO casual_members (lobby_id, steam_id, seat, ready, joined)
      VALUES ((SELECT id FROM casual_lobbies WHERE token = ?), ?, 0, 0, ?)`).bind(token, me.steam_id, now),
  ]);
  const row = await env.DB.prepare('SELECT * FROM casual_lobbies WHERE token = ?').bind(token).first();
  return json({ ok: true, lobby: await lobbyFor(env, row.id, me, deps) });
}

async function joinLobby(env, me, b, now, deps) {
  const { json, err } = deps;
  await tidy(env, now);
  const code = typeof b.code === 'string' ? b.code.trim().toUpperCase() : '';
  const l = b.id ? await env.DB.prepare('SELECT * FROM casual_lobbies WHERE id = ?').bind(+b.id || 0).first()
    : code ? await env.DB.prepare('SELECT * FROM casual_lobbies WHERE code = ? ORDER BY id DESC').bind(code).first() : null;
  if (!l || (l.state !== 'open' && l.state !== 'started')) return err(code && !b.id ? 'no open lobby with that code' : 'that lobby is gone', 404);
  if (l.code && l.code !== code) return err(code ? 'wrong code' : 'a private lobby: join it with its code', 403);
  const members = (await env.DB.prepare('SELECT steam_id, seat FROM casual_members WHERE lobby_id = ?').bind(l.id).all()).results;
  if (members.some((m) => m.steam_id === me.steam_id)) return json({ ok: true, lobby: await lobbyFor(env, l.id, me, deps) });
  if (l.state !== 'open') return err('that lobby has already started', 409);
  if (members.length >= CX.max) return err('that lobby is full', 409);
  try {
    const res = await env.DB.batch([
      ...leaveOthers(env, me.steam_id, l.id, now),
      // (the lowest free seat, 1..3; none free or the lobby no longer open: nothing inserted or the constraint refuses)
      env.DB.prepare(`INSERT INTO casual_members (lobby_id, steam_id, seat, ready, joined)
        SELECT ?1, ?2, (SELECT MIN(s) FROM (SELECT 1 AS s UNION ALL SELECT 2 UNION ALL SELECT 3)
          WHERE s NOT IN (SELECT seat FROM casual_members WHERE lobby_id = ?1)), 0, ?3
        WHERE EXISTS (SELECT 1 FROM casual_lobbies WHERE id = ?1 AND state = 'open')`).bind(l.id, me.steam_id, now),
    ]);
    if (!res[res.length - 1].meta.changes) return err('that lobby has already started', 409);
  } catch {
    return err('that lobby is full', 409);
  }
  return json({ ok: true, lobby: await lobbyFor(env, l.id, me, deps) });
}

async function memberRow(env, id, steamId) {
  return env.DB.prepare(`SELECT l.*, m.seat FROM casual_lobbies l JOIN casual_members m ON m.lobby_id = l.id
    WHERE l.id = ? AND m.steam_id = ?`).bind(id, steamId).first();
}

async function setReady(env, me, id, b, now, deps) {
  const { json, err } = deps;
  const l = await memberRow(env, id, me.steam_id);
  if (!l) return err('not your lobby', 404);
  if (l.state === 'open') {
    await env.DB.prepare(`UPDATE casual_members SET ready = ? WHERE lobby_id = ? AND steam_id = ?`).bind(b.ready === false ? 0 : 1, id, me.steam_id).run();
  }
  return json({ ok: true, lobby: await lobbyFor(env, id, me, deps) });
}

async function startLobby(env, me, id, now, deps) {
  const { json, err } = deps;
  const l = await memberRow(env, id, me.steam_id);
  if (!l) return err('not your lobby', 404);
  if (l.host !== me.steam_id) return err('only the host starts the lobby', 403);
  if (l.state === 'open') {
    await env.DB.prepare(`UPDATE casual_lobbies SET state = 'started', started = ?, updated = ? WHERE id = ? AND state = 'open'`).bind(now, now, id).run();
  } else if (l.state !== 'started') return err('that lobby is over', 409);
  return json({ ok: true, lobby: await lobbyFor(env, id, me, deps) });
}

async function leaveLobby(env, me, id, now, deps) {
  const { json, err } = deps;
  const l = await memberRow(env, id, me.steam_id);
  if (!l) return err('not your lobby', 404);
  if (l.host === me.steam_id) {
    await env.DB.batch([
      env.DB.prepare(`UPDATE casual_lobbies SET state = 'closed', updated = ? WHERE id = ? AND state = 'open'`).bind(now, id),
      env.DB.prepare(`UPDATE casual_lobbies SET state = 'finished', updated = ? WHERE id = ? AND state = 'started'`).bind(now, id),
    ]);
  } else if (l.state === 'open' || l.state === 'started') {
    await env.DB.batch([
      env.DB.prepare(`DELETE FROM casual_signals WHERE lobby_id = ?1 AND (from_id = ?2 OR to_id = ?2)`).bind(id, me.steam_id),
      env.DB.prepare(`DELETE FROM casual_members WHERE lobby_id = ? AND steam_id = ?`).bind(id, me.steam_id),
    ]);
  }
  return json({ ok: true });
}

async function setSignal(env, me, id, b, now, deps) {
  const { json, err } = deps;
  const l = await memberRow(env, id, me.steam_id);
  if (!l || (l.state !== 'open' && l.state !== 'started')) return err('not your lobby', 404);
  const to = typeof b.to === 'string' ? b.to : '';
  if (!to || to === me.steam_id) return err('to: another member of the lobby');
  const data = typeof b.data === 'string' ? b.data : JSON.stringify(b.data == null ? null : b.data);
  if (data.length > CX.signalMax) return err('too long', 413);
  const res = await env.DB.prepare(`INSERT INTO casual_signals (lobby_id, from_id, to_id, data, updated)
    SELECT ?1, ?2, ?3, ?4, ?5 WHERE EXISTS (SELECT 1 FROM casual_members WHERE lobby_id = ?1 AND steam_id = ?3)
    ON CONFLICT (lobby_id, from_id, to_id) DO UPDATE SET data = excluded.data, updated = excluded.updated`)
    .bind(id, me.steam_id, to, data, now).run();
  if (!res.meta.changes) return err('to: another member of the lobby', 404);
  return json({ ok: true });
}

// ------------------------------------------------------------------ the notes page

/** A lobby by its notes token, while it is on and CX.noteMs after: {stage, car, notes}, or null. */
export async function notesFor(env, token, now) {
  if (!TOKEN_RE.test(String(token || ''))) return null;
  const l = await env.DB.prepare(`SELECT * FROM casual_lobbies WHERE token = ? AND (state IN ('open', 'started') OR updated > ?)`)
    .bind(token, now - CX.noteMs).first();
  if (!l) return null;
  const route = await env.DB.prepare('SELECT length, stage_id FROM routes WHERE track = ?').bind(l.track).first();
  return { stage: stageShort(l.track, route), car: carOut(l.car), notes: (route && notesOf(route.stage_id)) || [] };
}

/** /n/<token> -> {status, body}: the page, or a small friendly one (404). */
export async function casualPage(env, token, now = Date.now()) {
  const info = firstDay(env) && copilotOn(env, new Date(now).toISOString().slice(0, 10)) ? await notesFor(env, token, now) : null;
  return info ? { status: 200, body: notesPage(token, info) } : { status: 404, body: notesGonePage() };
}

// ------------------------------------------------------------------ the API

/** /api/casual..., /api/n/<token>: a Response, or null when the path isn't one. deps: as copilotApi's. */
export async function casualApi(req, env, path, url, me, sameOrigin, now, deps) {
  const nm = path.match(/^\/api\/n\/([^/]+)$/);
  if (path !== '/api/casual' && !path.startsWith('/api/casual/') && !nm) return null;
  const { json, err } = deps;
  const post = req.method === 'POST';
  if (!firstDay(env) || !copilotOn(env, new Date(now).toISOString().slice(0, 10))) return err('CASUAL is off on this server', 404);

  if (nm) {
    if (post) return err('not found', 404);
    const info = await notesFor(env, nm[1], now);
    return info ? json(info) : err('these pacenotes are no longer available', 404);
  }
  if (path === '/api/casual/options' && !post) return json(await optionsOut(env, deps));
  if (path === '/api/casual' && !post) {
    await tidy(env, now);
    const meId = me ? me.steam_id : '';
    const [open, mine] = await env.DB.batch([
      env.DB.prepare(`SELECT l.* FROM casual_lobbies l WHERE l.state IN ('open', 'started')
        AND (l.code IS NULL OR l.id IN (SELECT lobby_id FROM casual_members WHERE steam_id = ?1)) ORDER BY l.created DESC, l.id DESC LIMIT ?2`)
        .bind(meId, CX.listMax),
      env.DB.prepare(`SELECT l.* FROM casual_lobbies l JOIN casual_members m ON m.lobby_id = l.id
        WHERE m.steam_id = ? AND l.state IN ('open', 'started') ORDER BY l.created DESC LIMIT 1`).bind(meId),
    ]);
    const rows = open.results.slice();
    const myRow = mine.results[0] || null;
    if (myRow && !rows.some((r) => r.id === myRow.id)) rows.push(myRow);
    const outs = await hydrate(env, rows, me ? me.steam_id : null);
    const lobby = myRow ? await addStage(env, outs[rows.findIndex((r) => r.id === myRow.id)], myRow, deps) : null;
    const listed = outs.slice(0, open.results.length).map((o) => (o.me ? { ...o, mine: true } : o))
      .map((o) => { const { signals, notesUrl, code, ...pub } = o; return pub; });
    return json({ on: true, signedIn: !!me, lobbies: listed, lobby });
  }
  const lm = path.match(/^\/api\/casual\/lobbies\/(\d+)(?:\/(ready|start|leave|signal))?$/);
  if (lm && !post && !lm[2]) {
    if (!me) return err('sign in with Steam first', 401);
    const l = await lobbyFor(env, +lm[1], me, deps);
    return l && l.me ? json({ lobby: l }) : err('not your lobby', 404);
  }
  if (!post) return err('not found', 404);
  if (!me) return err('sign in with Steam first', 401);
  if (me.banned) return err('this account is banned', 403);
  if (!sameOrigin) return err('refused: not from this site', 403);
  const body = async () => { const b = await req.json().catch(() => ({})); return b && typeof b === 'object' ? b : {}; };
  if (path === '/api/casual/lobbies') return createLobby(env, me, await body(), now, deps);
  if (path === '/api/casual/join') return joinLobby(env, me, await body(), now, deps);
  if (lm && lm[2] === 'ready') return setReady(env, me, +lm[1], await body(), now, deps);
  if (lm && lm[2] === 'start') return startLobby(env, me, +lm[1], now, deps);
  if (lm && lm[2] === 'leave') return leaveLobby(env, me, +lm[1], now, deps);
  if (lm && lm[2] === 'signal') return setSignal(env, me, +lm[1], await body(), now, deps);
  return err('not found', 404);
}

/** The cron: stale lobbies closed or finished. */
export async function casualTick(env, now) {
  if (!firstDay(env)) return null;
  await tidy(env, now);
  return { ok: true };
}
