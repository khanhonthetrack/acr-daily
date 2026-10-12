// Driver pages: every driver's page (/d/<steamId>: their rating and world rank, results, career numbers, leagues, cups,
// 1V1s), a name and a picture of their own, and teams (a coloured tag by their drivers' names, as in Trackmania). The
// pages are src/driverpages.js; the rating and the kept results src/rating.js.
//
//   GET  /api/drivers/<steamId>              a driver's page
//   GET  /api/ranking?country=&page=         the world ranking (src/rating.js)
//   POST /api/me/name {name}                 my own name (null / '': my Steam name again); one change a week
//   POST /api/me/avatar                      my own picture (its bytes; {"remove": true}: Steam's again)
//   GET  /avatar/<steamId>?v=                a driver's own picture
//   GET  /api/teams                          every team
//   GET  /api/teams/<id>                     a team (its invite code for its members)
//   POST /api/teams {name, tag, color}       a new team (I am its captain)
//   POST /api/teams/join {code}
//   POST /api/teams/<id>/leave | code | edit {name, tag, color} | kick {steamId} | captain {steamId}
//
// A driver's own name is unique (folded: case, spaces and . _ - ' don't count, so nobody can pose as someone else) and
// can't be another driver's name; the Steam id stays who they are. Names and pictures can be reset by the site's admins
// (POST /api/admin/driver). Everything a driver writes is put in pages with textContent, never as HTML.

import { stageParts } from './conditions.js';
import { newCode, newLeagueId, normCode, showCode, sniffImage, text } from './leagues.js';
import { RANK_SQL, rankingPage, rankOut } from './rating.js';
import { ACHIEVEMENTS } from './achievements.js';
import { cached } from './cache.js';
import { LOOK_COLS, lookJoin, lookOfRow } from './shop.js';
import { tmPlain, tmStyled } from './tmtext.js';

export const NAME = { min: 3, max: 20, everyDays: 7 };
export const AVATAR = { maxBytes: 60_000, min: 64, max: 512 };
export const TEAM = {
  nameMin: 3, nameMax: 30, maxMembers: 20,
  fmtMax: { tag: 60, name: 160 },     // the most a tag / a name can be with its $ codes (src/tmtext.js)
  colors: ['#F4F4F5', '#E30613', '#FF9F43', '#FFD60A', '#7BE07B', '#4CD6C0', '#3DD5F3', '#5BA8FF', '#B48CFF', '#FF7AB6'],
};
const RESERVED = ['acrdaily', 'admin', 'administrator', 'moderator', 'mod', 'steward', 'system', 'support', 'staff'];

/** A name folded for comparing: 'Ann B' = 'ann_b' = 'ANN.B'. */
export const nameKey = (s) => String(s).normalize('NFKC').toLowerCase().replace(/[\s._'’-]+/g, '');
// the same in SQL (for names already there; SQLite's lower() folds A-Z only)
const KEY_SQL = (col) => `lower(replace(replace(replace(replace(replace(${col}, ' ', ''), '.', ''), '_', ''), '-', ''), '''', ''))`;

/** A name a driver gives themselves: -> {value, key} or {error}. */
export function checkName(v) {
  const s = String(v == null ? '' : v).normalize('NFKC').replace(/\s+/g, ' ').trim();
  if (s.length < NAME.min || s.length > NAME.max) return { error: `a name of ${NAME.min} to ${NAME.max} characters` };
  if (!/^[\p{L}\p{N}][\p{L}\p{N} ._'-]*$/u.test(s)) return { error: 'letters, digits, spaces and . _ - \' only, starting with a letter or a digit' };
  const key = nameKey(s);
  if (key.length < NAME.min) return { error: `a name of ${NAME.min} to ${NAME.max} characters` };
  if (RESERVED.includes(key) || key.startsWith('acrdaily')) return { error: 'that name is kept for the site' };
  return { value: s, key };
}

/** A team from a form: -> {value: {name, tag, color, nameFmt, tagFmt}} or {error}. The name and the tag can carry
 *  Trackmania's $ codes (src/tmtext.js): the rules are on what they read as (name, tag), the codes kept apart (nameFmt,
 *  tagFmt: null without any). */
export function checkTeam(b) {
  const raw = (v, max) => String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, max);
  const nameRaw = raw(b && b.name, TEAM.fmtMax.name), tagRaw = raw(b && b.tag, TEAM.fmtMax.tag);
  const name = text(tmPlain(nameRaw), TEAM.nameMax + 1);
  if (name.length < TEAM.nameMin || name.length > TEAM.nameMax) return { error: `the team's name: ${TEAM.nameMin} to ${TEAM.nameMax} characters` };
  const tag = tmPlain(tagRaw).trim();
  if (!/^[A-Za-z0-9]{2,4}$/.test(tag)) return { error: 'the tag: 2 to 4 letters or digits' };
  if (RESERVED.some((r) => r.toUpperCase() === tag.toUpperCase()) || tag.toUpperCase() === 'ACR') return { error: 'that tag is kept for the site' };
  const color = TEAM.colors.includes(b && b.color) ? b.color : null;
  if (!color) return { error: 'pick the tag\'s colour' };
  // a plain tag is in capitals; a styled one reads as written ($t for capitals)
  const tagFmt = tmStyled(tagRaw) ? tagRaw : null;
  return { value: { name, tag: tagFmt ? tag : tag.toUpperCase(), color, nameFmt: tmStyled(nameRaw) ? nameRaw : null, tagFmt } };
}

/** A driver's own picture from its bytes: -> {value: {type}} or {error, status}. */
export function checkAvatar(bytes) {
  if (bytes.length > AVATAR.maxBytes) return { status: 413, error: `the picture is ${Math.round(bytes.length / 1000)} KB: ${AVATAR.maxBytes / 1000} KB at most` };
  const img = sniffImage(bytes);
  if (!img) return { status: 415, error: 'a PNG, JPEG or WebP picture, please' };
  const r = img.w / img.h;
  if (img.w < AVATAR.min || img.w > AVATAR.max || img.h < AVATAR.min || img.h > AVATAR.max || r < 0.9 || r > 1.1) {
    return { status: 422, error: `a square picture, ${AVATAR.min} to ${AVATAR.max} pixels (it is ${img.w} x ${img.h})` };
  }
  return { value: img };
}

const bytesOf = (d) => (d instanceof ArrayBuffer ? new Uint8Array(d)
  : ArrayBuffer.isView(d) ? new Uint8Array(d.buffer, d.byteOffset, d.byteLength) : Uint8Array.from(d));

/** GET /avatar/<steamId>: a driver's own picture, kept by browsers for good when asked for with its version. */
export async function avatarResponse(env, sid, version) {
  const r = await env.DB.prepare('SELECT type, data, updated FROM player_avatars WHERE steam_id = ?').bind(sid).first();
  if (!r) return new Response('no picture', { status: 404, headers: { 'Cache-Control': 'no-store' } });
  return new Response(bytesOf(r.data), { headers: {
    'Content-Type': r.type, 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'",
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': String(r.updated) === version ? 'public, max-age=31536000, immutable' : 'public, max-age=60' } });
}

const teamOut = (t) => (t ? { id: t.id, name: t.name, tag: t.tag, color: t.color, nameFmt: t.name_fmt || null, tagFmt: t.tag_fmt || null } : null);

/** The API (paths above). -> a Response, or null when the path is not one of these. site: the website's address (a
 *  picture's address in players.avatar is a full one: the app and Discord show it too); namesChanged(): drop the kept
 *  timing sheets (names, pictures and tags are in them). */
export async function driversApi(req, env, path, url, me, sameOrigin, now, { json, err, site, namesChanged }) {
  const post = req.method === 'POST';
  let m = path.match(/^\/api\/drivers\/(\d{17})$/);
  // the app asks for the driver strip only (its rating and name, every 15 minutes): the light answer, not the whole page
  if (m && !post) return driverPage(env, m[1], me, json, err, /^ACR-Daily\//.test(req.headers.get('User-Agent') || '') || url.searchParams.has('lite'));
  if (path === '/api/ranking' && !post) {
    const country = /^[a-z]{2}$/.test(url.searchParams.get('country') || '') ? url.searchParams.get('country') : null;
    const page = Math.max(1, Math.min(1000, Math.round(+url.searchParams.get('page') || 1)));
    const [r, countries, mine] = await Promise.all([
      rankingPage(env, { country, page }),
      env.DB.prepare(`SELECT p.country, COUNT(*) AS n FROM ratings r JOIN players p ON p.steam_id = r.steam_id
        WHERE p.banned = 0 AND p.country IS NOT NULL GROUP BY p.country ORDER BY n DESC`).all(),
      me ? env.DB.prepare(RANK_SQL).bind(me.steam_id).first() : null,
    ]);
    return json({ ...r, country, countries: countries.results.map((c) => ({ code: c.country, drivers: c.n })),
      me: me ? { steamId: me.steam_id, ...(rankOut(mine) || {}) } : null, ratingOn: !!env.RATING_FROM, ratingFrom: env.RATING_FROM || null });
  }
  if (path === '/api/teams' && !post) {
    const [{ results }, mine] = await Promise.all([
      env.DB.prepare(`SELECT t.*, COUNT(m.steam_id) AS members, AVG(r.rating) AS rating FROM teams t
        JOIN team_members m ON m.team_id = t.id LEFT JOIN ratings r ON r.steam_id = m.steam_id
        GROUP BY t.id ORDER BY members DESC, t.created LIMIT 200`).all(),
      me ? env.DB.prepare('SELECT team_id FROM team_members WHERE steam_id = ?').bind(me.steam_id).first() : null,
    ]);
    return json({ teams: results.map((t) => ({ ...teamOut(t), members: t.members, rating: t.rating == null ? null : Math.round(t.rating) })),
      mine: mine ? mine.team_id : null, colors: TEAM.colors });
  }
  m = path.match(/^\/api\/teams\/([a-z0-9]{8})$/);
  if (m && !post) return teamPage(env, m[1], me, json, err);

  if (!(path.startsWith('/api/me/') || path.startsWith('/api/teams')) || !post) return null;
  if (!me) return err('sign in with Steam first', 401);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (me.banned) return err('this account is banned', 403);

  if (path === '/api/me/avatar') return setAvatar(env, req, me, now, { json, err, site, namesChanged });
  const b = await req.json().catch(() => ({})) || {};
  if (path === '/api/me/name') {
    const until = (me.name_set || 0) + NAME.everyDays * 86400000;
    if (me.name_set && now < until) return err(`one name change a week: the next from ${new Date(until).toISOString().slice(0, 10)}`, 429);
    if (b.name == null || String(b.name).trim() === '') {           // my Steam name again
      await env.DB.prepare(`UPDATE players SET custom_name = NULL, name_key = NULL, name = COALESCE(steam_name, name), name_set = ?
        WHERE steam_id = ?`).bind(now, me.steam_id).run();
      await namesChanged();
      return json({ name: (await env.DB.prepare('SELECT name FROM players WHERE steam_id = ?').bind(me.steam_id).first()).name, custom: false });
    }
    const c = checkName(b.name);
    if (c.error) return err(c.error);
    if (me.name_key === c.key && me.custom_name === c.value) return json({ name: c.value, custom: true });
    try {
      const r = await env.DB.prepare(`UPDATE players SET custom_name = ?1, name_key = ?2, name = ?1, name_set = ?3 WHERE steam_id = ?4
          AND NOT EXISTS (SELECT 1 FROM players o WHERE o.steam_id != ?4 AND (o.name_key = ?2 OR ${KEY_SQL('o.name')} = ?2))`)
        .bind(c.value, c.key, now, me.steam_id).run();
      if (!r.meta.changes) return err('another driver has that name', 409);
    } catch (e) {
      if (/UNIQUE|constraint/i.test(String(e && e.message))) return err('another driver has that name', 409);
      throw e;
    }
    await namesChanged();
    return json({ name: c.value, custom: true });
  }

  // ---- teams
  const inTeam = async () => env.DB.prepare('SELECT m.team_id, t.captain FROM team_members m JOIN teams t ON t.id = m.team_id WHERE m.steam_id = ?')
    .bind(me.steam_id).first();
  if (path === '/api/teams') {                            // a new team
    if (await inTeam()) return err('leave your team first', 409);
    const c = checkTeam(b);
    if (c.error) return err(c.error);
    for (let tries = 0; tries < 5; tries++) {
      const id = newLeagueId();
      try {
        await env.DB.batch([
          env.DB.prepare(`INSERT INTO teams (id, name, tag, tag_key, color, captain, code, created, name_fmt, tag_fmt)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
            .bind(id, c.value.name, c.value.tag, c.value.tag.toUpperCase(), c.value.color, me.steam_id, newCode(), now, c.value.nameFmt, c.value.tagFmt),
          env.DB.prepare('INSERT INTO team_members (steam_id, team_id, joined) VALUES (?, ?, ?)').bind(me.steam_id, id, now),
        ]);
        await namesChanged();
        return json({ id });
      } catch (e) {
        const s = String(e && e.message);
        if (/tag_key/.test(s)) return err('another team has that tag', 409);
        if (/team_members/.test(s)) return err('leave your team first', 409);
        if (!/UNIQUE|constraint/i.test(s)) throw e;           // (an id or a code taken: again)
      }
    }
    return err('try again', 503);
  }
  if (path === '/api/teams/join') {
    const code = normCode(b.code);
    const t = code && await env.DB.prepare('SELECT * FROM teams WHERE code = ?').bind(code).first();
    if (!t) return err('no team has that code (it may have been renewed)', 404);
    if (await inTeam()) return err('leave your team first', 409);
    const r = await env.DB.prepare(`INSERT OR IGNORE INTO team_members (steam_id, team_id, joined) SELECT ?1, ?2, ?3
      WHERE (SELECT COUNT(*) FROM team_members WHERE team_id = ?2) < ?4`).bind(me.steam_id, t.id, now, TEAM.maxMembers).run();
    if (!r.meta.changes) return err(`the team is full (${TEAM.maxMembers} drivers)`, 409);
    await namesChanged();
    return json({ id: t.id });
  }
  m = path.match(/^\/api\/teams\/([a-z0-9]{8})\/(leave|code|edit|kick|captain)$/);
  if (!m) return err('not found', 404);
  const t = await env.DB.prepare('SELECT * FROM teams WHERE id = ?').bind(m[1]).first();
  const mine = await inTeam();
  if (!t || !mine || mine.team_id !== t.id) return err('you are not in this team', 403);
  const captain = t.captain === me.steam_id;
  if (m[2] === 'leave') {
    const { results: rest } = await env.DB.prepare('SELECT steam_id FROM team_members WHERE team_id = ? AND steam_id != ? ORDER BY joined, steam_id')
      .bind(t.id, me.steam_id).all();
    await env.DB.batch([
      env.DB.prepare('DELETE FROM team_members WHERE steam_id = ? AND team_id = ?').bind(me.steam_id, t.id),
      // the last one out closes the team; a captain leaving hands it to whoever has been in it longest
      ...(!rest.length ? [env.DB.prepare('DELETE FROM teams WHERE id = ?').bind(t.id)]
        : captain ? [env.DB.prepare('UPDATE teams SET captain = ? WHERE id = ?').bind(rest[0].steam_id, t.id)] : []),
    ]);
    await namesChanged();
    return json({ left: true, closed: !rest.length });
  }
  if (!captain) return err('only the team\'s captain can do that', 403);
  if (m[2] === 'code') {
    const code = newCode();
    await env.DB.prepare('UPDATE teams SET code = ? WHERE id = ?').bind(code, t.id).run();
    return json({ code: showCode(code) });
  }
  if (m[2] === 'edit') {
    const c = checkTeam({ name: b.name == null ? t.name_fmt || t.name : b.name, tag: b.tag == null ? t.tag_fmt || t.tag : b.tag,
      color: b.color == null ? t.color : b.color });
    if (c.error) return err(c.error);
    try {
      await env.DB.prepare('UPDATE teams SET name = ?, tag = ?, tag_key = ?, color = ?, name_fmt = ?, tag_fmt = ? WHERE id = ?')
        .bind(c.value.name, c.value.tag, c.value.tag.toUpperCase(), c.value.color, c.value.nameFmt, c.value.tagFmt, t.id).run();
    } catch (e) {
      if (/UNIQUE|constraint/i.test(String(e && e.message))) return err('another team has that tag', 409);
      throw e;
    }
    await namesChanged();
    return json(c.value);
  }
  const sid = String(b.steamId || '');
  if (sid === me.steam_id || !await env.DB.prepare('SELECT 1 AS x FROM team_members WHERE steam_id = ? AND team_id = ?').bind(sid, t.id).first()) {
    return err('no such driver in the team', 404);
  }
  if (m[2] === 'kick') {
    await env.DB.prepare('DELETE FROM team_members WHERE steam_id = ? AND team_id = ?').bind(sid, t.id).run();
    await namesChanged();
    return json({ removed: sid });
  }
  await env.DB.prepare('UPDATE teams SET captain = ? WHERE id = ?').bind(sid, t.id).run();   // captain: hand it over
  return json({ captain: sid });
}

async function setAvatar(env, req, me, now, { json, err, site, namesChanged }) {
  const type = (req.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (type === 'application/json') {                    // {remove: true}: Steam's picture again
    const b = await req.json().catch(() => ({})) || {};
    if (!b.remove) return err('send a picture, or {"remove": true}');
    await env.DB.batch([
      env.DB.prepare('DELETE FROM player_avatars WHERE steam_id = ?').bind(me.steam_id),
      env.DB.prepare('UPDATE players SET avatar = steam_avatar, avatar_set = NULL WHERE steam_id = ?').bind(me.steam_id),
    ]);
    await namesChanged();
    return json({ avatar: (await env.DB.prepare('SELECT avatar FROM players WHERE steam_id = ?').bind(me.steam_id).first()).avatar || null });
  }
  if (me.avatar_set && now - me.avatar_set < 60000) return err('one new picture a minute', 429);
  if (+(req.headers.get('Content-Length') || 0) > AVATAR.maxBytes) return err(`${AVATAR.maxBytes / 1000} KB at most`, 413);
  const bytes = new Uint8Array(await req.arrayBuffer());
  const c = checkAvatar(bytes);
  if (c.error) return err(c.error, c.status);
  const url = `${site}/avatar/${me.steam_id}?v=${now}`;
  await env.DB.batch([
    env.DB.prepare('INSERT OR REPLACE INTO player_avatars (steam_id, type, data, updated) VALUES (?, ?, ?, ?)')
      .bind(me.steam_id, c.value.type, bytes.buffer, now),
    env.DB.prepare('UPDATE players SET avatar = ?, avatar_set = ? WHERE steam_id = ?').bind(url, now, me.steam_id),
  ]);
  await namesChanged();
  return json({ avatar: url });
}

/** An admin of the site puts a driver's own name and / or picture back to Steam's (POST /api/admin/driver). */
export async function adminResetDriver(env, sid, { name = true, avatar = true } = {}) {
  await env.DB.batch([
    ...(name ? [env.DB.prepare('UPDATE players SET custom_name = NULL, name_key = NULL, name = COALESCE(steam_name, name) WHERE steam_id = ?').bind(sid)] : []),
    ...(avatar ? [env.DB.prepare('DELETE FROM player_avatars WHERE steam_id = ?').bind(sid),
      env.DB.prepare('UPDATE players SET avatar = steam_avatar, avatar_set = NULL WHERE steam_id = ?').bind(sid)] : []),
  ]);
}

/** An admin of the site closes a team (an offensive name or tag): POST /api/admin/team-delete. */
export async function adminDeleteTeam(env, id) {
  await env.DB.batch([env.DB.prepare('DELETE FROM team_members WHERE team_id = ?').bind(id),
    env.DB.prepare('DELETE FROM teams WHERE id = ?').bind(id)]);
}

// ------------------------------------------------------------------ the pages' data

async function driverPage(env, sid, me, json, err, lite = false) {
  const mine = !!me && me.steam_id === sid;
  const q = (sql, ...b) => env.DB.prepare(sql).bind(...b);
  if (lite) {                                          // the app's driver strip, every 15 minutes: the name and the rating
    const [pl, rk] = await env.DB.batch([
      q(`SELECT p.*, ${LOOK_COLS}, lkt.id AS team_id, lkt.name AS team_name FROM players p ${lookJoin('p.steam_id')} WHERE p.steam_id = ?`, sid),
      q(RANK_SQL, sid)]);
    const p = pl.results[0];
    if (!p || (p.banned && !mine)) return err('no such driver', 404);
    return json({ steamId: p.steam_id, name: p.name, avatar: p.avatar || null, country: p.country || null, look: lookOfRow(p),
      team: p.team_id ? { id: p.team_id, name: p.team_name, tag: p.look_tag, color: p.look_tag_color, tagFmt: p.look_tag_fmt || null } : null,
      rating: rankOut(rk.results[0]), ratingOn: !!env.RATING_FROM, lite: true });
  }
  const [pl, rk, hist, agg, recent, distance, cars, tracks, leagues, cups, duels, ach] = await env.DB.batch([
    q(`SELECT p.*, ${LOOK_COLS}, lkt.id AS team_id, lkt.name AS team_name, lkt.name_fmt AS team_name_fmt, lkt.captain AS team_captain
       FROM players p ${lookJoin('p.steam_id')} WHERE p.steam_id = ?`, sid),
    q(RANK_SQL, sid),
    q('SELECT ref, delta, after, created FROM rating_history WHERE steam_id = ? ORDER BY created DESC, ref DESC LIMIT 60', sid),
    q(`SELECT COUNT(*) AS dailies, SUM(status = 'finished') AS finishes, SUM(place = 1) AS wins, SUM(place <= 3) AS podiums,
         MIN(place) AS best FROM daily_results WHERE steam_id = ?`, sid),
    q('SELECT * FROM daily_results WHERE steam_id = ? ORDER BY date DESC, slot DESC LIMIT 20', sid),
    q(`SELECT COUNT(*) AS runs, SUM(CASE WHEN r.status = 'finished' THEN COALESCE(ro.length, 0) ELSE 0 END) AS metres
         FROM runs r LEFT JOIN routes ro ON ro.track = r.track WHERE r.steam_id = ?`, sid),
    q('SELECT car, COUNT(*) AS n FROM runs WHERE steam_id = ? GROUP BY car ORDER BY n DESC LIMIT 3', sid),
    q('SELECT track, COUNT(*) AS n FROM runs WHERE steam_id = ? GROUP BY track', sid),
    q(`SELECT l.id, l.name, l.public, m.role FROM league_members m JOIN leagues l ON l.id = m.league_id
        WHERE m.steam_id = ? AND l.kind = 'league' ORDER BY m.joined DESC LIMIT 30`, sid),
    q(`SELECT c.id, c.name, c.status, c.size, c.starts, e.place, (SELECT COUNT(*) FROM cup_entries x WHERE x.cup_id = c.id) AS drivers
         FROM cup_entries e JOIN cups c ON c.id = e.cup_id WHERE e.steam_id = ? AND c.status != 'cancelled' ORDER BY c.starts DESC LIMIT 10`, sid),
    q(`SELECT SUM(winner = ?1) AS won, SUM(winner IS NOT NULL AND winner != ?1) AS lost, SUM(winner IS NULL) AS drawn
         FROM h2h WHERE status = 'settled' AND (challenger = ?1 OR opponent = ?1)`, sid),
    q('SELECT id, at FROM achievements WHERE steam_id = ?', sid),
  ]);
  // how rare each achievement is (of the drivers who have signed in): counted once an hour, not for every page
  const rarity = await cached(env, 'ach-rarity', 3600000, async () => {
    const [rare, drivers] = await env.DB.batch([q('SELECT id, COUNT(*) AS n FROM achievements GROUP BY id'),
      q('SELECT COUNT(*) AS n FROM players WHERE banned = 0')]);
    const total = Math.max(1, drivers.results[0].n);
    return Object.fromEntries(rare.results.map((r) => [r.id, Math.round(1000 * r.n / total) / 10]));
  });
  const p = pl.results[0];
  if (!p || (p.banned && !mine)) return err('no such driver', 404);
  const rallies = new Map();
  for (const t of tracks.results) { const r = stageParts(t.track).rally; rallies.set(r, (rallies.get(r) || 0) + t.n); }
  const favRally = [...rallies].sort((a, b) => b[1] - a[1])[0];
  const a = agg.results[0] || {};
  const d = duels.results[0] || {};
  return json({
    steamId: p.steam_id, name: p.name, steamName: p.custom_name ? p.steam_name : null, avatar: p.avatar || null,
    country: p.country || null, since: p.created, look: lookOfRow(p),
    team: p.team_id ? { id: p.team_id, name: p.team_name, tag: p.look_tag, color: p.look_tag_color, tagFmt: p.look_tag_fmt || null,
      nameFmt: p.team_name_fmt || null, captain: p.team_captain === sid } : null,
    rating: rankOut(rk.results[0]), history: hist.results.reverse().map((h) => ({ ref: h.ref, delta: h.delta, rating: Math.round(h.after), at: h.created })),
    ratingOn: !!env.RATING_FROM,
    achievements: (() => {
      const got = new Map(ach.results.map((a) => [a.id, a.at]));
      return ACHIEVEMENTS.map((a) => ({ id: a.id, at: got.get(a.id) || null, rarity: rarity[a.id] || 0 }));
    })(),
    stats: { dailies: a.dailies || 0, finishes: a.finishes || 0, wins: a.wins || 0, podiums: a.podiums || 0, best: a.best || null,
      runs: distance.results[0].runs || 0, km: Math.round((distance.results[0].metres || 0) / 100) / 10,
      cars: cars.results.map((c) => ({ car: c.car, runs: c.n })), rally: favRally ? favRally[0] : null,
      oneVone: { won: d.won || 0, lost: d.lost || 0, drawn: d.drawn || 0 } },
    recent: recent.results.map((r) => ({ date: r.date, slot: r.slot, place: r.place, field: r.field, status: r.status, totalMs: r.total_ms,
      gapMs: r.gap_ms, runId: r.run_id, stage: r.track ? stageParts(r.track).stageName : null, rally: r.track ? stageParts(r.track).rally : null,
      car: r.car, delta: r.delta })),
    leagues: leagues.results.filter((l) => l.public || mine).map((l) => ({ id: l.id, name: l.name, role: l.role, public: !!l.public })),
    cups: cups.results.map((c) => ({ id: c.id, name: c.name, status: c.status, place: c.place, drivers: c.drivers, starts: c.starts })),
    me: mine ? { customName: p.custom_name || null, steamName: p.steam_name || p.name, steamAvatar: p.steam_avatar || null,
      ownAvatar: !!p.avatar_set, nameSet: p.name_set || null,
      nextNameChange: p.name_set ? p.name_set + NAME.everyDays * 86400000 : null } : null,
    signedIn: !!me,
  });
}

async function teamPage(env, id, me, json, err) {
  const [t, mem] = await env.DB.batch([
    env.DB.prepare('SELECT * FROM teams WHERE id = ?').bind(id),
    env.DB.prepare(`SELECT m.steam_id, m.joined, p.name, p.avatar, p.country, r.rating, r.races FROM team_members m
        JOIN players p ON p.steam_id = m.steam_id LEFT JOIN ratings r ON r.steam_id = m.steam_id
       WHERE m.team_id = ? ORDER BY r.rating DESC, m.joined`).bind(id),
  ]);
  const team = t.results[0];
  if (!team) return err('no such team', 404);
  const member = !!me && mem.results.some((x) => x.steam_id === me.steam_id);
  const rated = mem.results.filter((x) => x.rating != null);
  return json({ ...teamOut(team), captain: team.captain, created: team.created,
    rating: rated.length ? Math.round(rated.reduce((s, x) => s + x.rating, 0) / rated.length) : null,
    members: mem.results.map((x) => ({ steamId: x.steam_id, name: x.name, avatar: x.avatar || null, country: x.country || null,
      rating: x.rating == null ? null : Math.round(x.rating), races: x.races || 0, joined: x.joined, captain: x.steam_id === team.captain })),
    code: member ? showCode(team.code) : null, maxMembers: TEAM.maxMembers, colors: TEAM.colors,
    me: me ? { steamId: me.steam_id, member, captain: team.captain === me.steam_id } : null });
}
