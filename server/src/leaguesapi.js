// The leagues' API (the rules and standings: src/leagues.js). The website signs in with a session cookie, the app with
// its Bearer token. Who may do what: anyone signed in can make a league and join public ones (or private ones with
// their code); members drive its events; admins (and the owner) run events and seasons, the invite code, the members
// (remove, ban) and the stewarding (time penalties, disqualifications); only the owner changes the league's settings,
// banner and Discord posts, makes or unmakes admins, and deletes it.
//
//   GET  /api/catalog                         what an event can be made of
//   GET  /api/me                              who is signed in on the website
//   GET  /api/me/events                       the app: events of my leagues, open or coming, with my entry
//   GET  /api/leagues                         public leagues, and mine
//   POST /api/leagues                         a new league
//   POST /api/leagues/join {code}             join with an invite code
//   GET  /api/leagues/code?code=              the invite page: which league a code opens
//   GET  /api/leagues/:id                     a league: members, events, seasons and their standings
//   POST /api/leagues/:id/<action>            join, leave, edit, banner, discord, code, remove, unban, role, delete,
//                                             events (a new event), seasons (a new season)
//   POST /api/seasons/:id/edit | delete       a season's settings
//   GET  /api/events/:id                      an event: itinerary, standings, the stewards' decisions
//   POST /api/events/:id/<action>             edit, delete, penalty, dsq (staff); start, begin, stage, dnf (the app)
// GET /l/:id/banner (the picture) and the cron's leagueDiscordTick are called from src/index.js.

import { CARS, carByName } from './cars.js';
import { stageParts, SURFACE, WEATHER } from './conditions.js';
import { webhook } from './discord.js';
import { BANNER, bannerUrl, catalog, checkBanner, checkEvent, checkLeague, checkPenalty, checkSeason,
  DEFAULT_SEASON, describeSeason, entryState, eventStandings, eventStatus, LIMITS, newCode, newLeagueId,
  normCode, seasonStandings, showCode, text } from './leagues.js';
import { duePosts, openMessage, reminderMessage, resultsMessage, testMessage } from './leaguediscord.js';
import { menuName } from './stages.js';

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' } });
const err = (msg, status = 400) => json({ error: msg }, status);
const verParts = (v) => String(v || '').split('.').map((x) => parseInt(x, 10) || 0);
function older(v, min) {
  const a = verParts(v), b = verParts(min);
  for (let i = 0; i < Math.max(a.length, b.length); i++) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) < (b[i] || 0);
  return false;
}
/** The app's version (User-Agent "ACR-Daily/0.0.5 public"), or null for a browser. */
const appVersion = (req) => ((req.headers.get('User-Agent') || '').match(/^ACR-Daily\/([\d.]+)/) || [])[1] || null;
const hookOf = (env, url, fetchFn = fetch) => webhook(url, fetchFn, env.DEV_LOGIN === '1');   // (a local stand-in in tests)

async function readBody(req) {
  try { return await req.json(); } catch { return null; }
}

async function routesRows(env) {
  const { results } = await env.DB.prepare('SELECT track, stage_id, length FROM routes WHERE stage_id IS NOT NULL').all();
  return results;
}

/** An event row -> what the website and the app get: its stages with names, lengths, the game's ids and weathers. */
function eventOut(ev, routes, now) {
  const stages = JSON.parse(ev.stages);
  const rt = new Map(routes.map((r) => [r.track, r]));
  const car = ev.car ? carByName(ev.car) : null;
  const cars = car ? [car] : CARS.filter((c) => c.cls === ev.car_class);
  const out = stages.map((s, k) => {
    const r = rt.get(s.track) || {};
    const [hh, mm] = s.time.split(':').map(Number);
    const w = WEATHER[s.weather] || {};
    return { no: k + 1, day: s.day, service: s.service, track: s.track, stageId: r.stage_id || null,
      name: (r.stage_id && menuName(r.stage_id)) || stageParts(s.track).stageName, lengthM: Math.round(r.length || 0),
      weather: s.weather, weatherLabel: w.label || s.weather, weatherGame: w.game || null, time: s.time, startSeconds: hh * 3600 + mm * 60 };
  });
  return {
    id: ev.id, leagueId: ev.league_id, seasonId: ev.season_id || null, name: ev.name, rally: ev.rally, surface: SURFACE[ev.rally] || null,
    car: ev.car, carClass: ev.car_class,
    cars: cars.map((c) => ({ name: c.name, id: c.id, cls: c.cls, telemetry: c.telemetry, aliases: [c.telemetry, ...(c.aliases || [])].filter(Boolean) })),
    rules: JSON.parse(ev.rules), stages: out, days: stages.length ? stages[stages.length - 1].day : 0,
    lengthM: out.reduce((a, s) => a + s.lengthM, 0), opens: ev.opens, closes: ev.closes, status: eventStatus(ev, now),
  };
}

const leagueRow = (env, id) => env.DB.prepare('SELECT * FROM leagues WHERE id = ?').bind(id).first();
const seasonOut = (s) => ({ id: s.id, name: s.name, points: JSON.parse(s.points), power: JSON.parse(s.power), drop: s.drop_worst });

/** Someone's place in a league: 'owner', 'admin', 'member' or null. */
async function roleIn(env, l, me) {
  if (!me) return null;
  if (me.steam_id === l.owner) return 'owner';
  const m = await env.DB.prepare('SELECT role FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, me.steam_id).first();
  return m ? (m.role === 'admin' ? 'admin' : 'member') : null;
}
const isStaff = (role) => role === 'owner' || role === 'admin';

/** The entries, stage times and penalties of one event, or of every event of a league: Map eventId -> {entries,
 *  times, penalties}. Three queries, whatever the number of events. */
async function resultsOf(env, { leagueId = null, eventId = null }) {
  const one = eventId != null;
  const where = (col) => (one ? `${col} = ?` : `${col} IN (SELECT id FROM league_events WHERE league_id = ?)`);
  const key = one ? eventId : leagueId;
  const [en, ti, pe] = await env.DB.batch([
    env.DB.prepare(`SELECT e.*, p.name, p.country, p.avatar, s.name AS dsq_by_name FROM league_entries e
      LEFT JOIN players p ON p.steam_id = e.steam_id LEFT JOIN players s ON s.steam_id = e.dsq_by WHERE ${where('e.event_id')}`).bind(key),
    env.DB.prepare(`SELECT * FROM league_stage_times WHERE ${where('event_id')}`).bind(key),
    env.DB.prepare(`SELECT x.*, s.name AS by_name, d.name AS driver_name FROM league_penalties x
      LEFT JOIN players s ON s.steam_id = x.by LEFT JOIN players d ON d.steam_id = x.steam_id WHERE ${where('x.event_id')}
      ORDER BY x.created`).bind(key),
  ]);
  const out = new Map();
  const of = (id) => { if (!out.has(id)) out.set(id, { entries: [], times: [], penalties: [] }); return out.get(id); };
  for (const r of en.results) of(r.event_id).entries.push(r);
  for (const r of ti.results) of(r.event_id).times.push(r);
  for (const r of pe.results) of(r.event_id).penalties.push(r);
  return out;
}
const EMPTY = { entries: [], times: [], penalties: [] };
const standingsOf = (ev, res, now) => eventStandings({ stages: JSON.parse(ev.stages), opens: ev.opens, closes: ev.closes },
  res.entries, res.times, now, res.penalties);

/** The stewards' decisions on an event, as everyone sees them. */
function decisions(res, nStages) {
  const out = res.penalties.map((p) => ({ id: p.id, kind: 'time', steamId: p.steam_id, driver: p.driver_name || 'Driver',
    stage: p.stage_no != null && p.stage_no < nStages ? p.stage_no + 1 : null, ms: p.ms, reason: p.reason, by: p.by_name || 'a steward', at: p.created }));
  for (const e of res.entries) {
    if (e.dsq) out.push({ id: null, kind: 'dsq', steamId: e.steam_id, driver: e.name || 'Driver', stage: null, ms: 0, reason: e.dsq, by: e.dsq_by_name || 'a steward', at: e.dsq_at });
  }
  return out.sort((a, b) => (a.at || 0) - (b.at || 0));
}

const LIST_SQL = `SELECT l.id, l.name, l.about, l.public, l.owner, l.banner, p.name AS owner_name,
    (SELECT COUNT(*) FROM league_members m WHERE m.league_id = l.id) AS members,
    (SELECT COUNT(*) FROM league_events e WHERE e.league_id = l.id) AS events,
    (SELECT COUNT(*) FROM league_events e WHERE e.league_id = l.id AND e.opens <= ?1 AND e.closes > ?1) AS open_events,
    (SELECT MIN(e.opens) FROM league_events e WHERE e.league_id = l.id AND e.opens > ?1) AS next_opens
  FROM leagues l LEFT JOIN players p ON p.steam_id = l.owner`;
const leagueListItem = (r) => ({ id: r.id, name: r.name, about: r.about, public: !!r.public, owner: r.owner_name,
  banner: bannerUrl(r.id, r.banner), members: r.members, events: r.events, openEvents: r.open_events, nextOpens: r.next_opens });

async function addMember(env, leagueId, steamId, now) {
  const ban = await env.DB.prepare('SELECT reason FROM league_bans WHERE league_id = ? AND steam_id = ?').bind(leagueId, steamId).first();
  if (ban) return err('you can\'t join this league' + (ban.reason ? ` (${ban.reason})` : ''), 403);
  const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_members WHERE league_id = ?').bind(leagueId).first();
  if (n.n >= LIMITS.members) return err(`this league is full (${LIMITS.members} drivers)`, 409);
  await env.DB.prepare('INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, ?, \'member\')')
    .bind(leagueId, steamId, now).run();
  return json({ id: leagueId, joined: true });
}

/** A season for a new or edited event: null (a one-off), 'new' (made now: "Season N", the default points) or the
 *  id of one of the league's seasons. -> {id} or {error}. */
async function seasonFor(env, l, sid, now) {
  if (sid == null || sid === '') return { id: null };
  if (sid === 'new') {
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = ?').bind(l.id).first();
    if (n.n >= LIMITS.seasonsPerLeague) return { error: `at most ${LIMITS.seasonsPerLeague} seasons in a league` };
    const r = await env.DB.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created)
      VALUES (?, ?, ?, ?, ?, ?)`).bind(l.id, `Season ${n.n + 1}`, JSON.stringify(DEFAULT_SEASON.points),
      JSON.stringify(DEFAULT_SEASON.power), DEFAULT_SEASON.drop, now).run();
    return { id: r.meta.last_row_id };
  }
  const s = await env.DB.prepare('SELECT id FROM league_seasons WHERE id = ? AND league_id = ?').bind(Math.round(+sid), l.id).first();
  return s ? { id: s.id } : { error: 'no such season in this league' };
}

// ------------------------------------------------------------------ banners

/** GET /l/:id/banner: the picture. Kept by browsers for good when asked for with its current version. */
export async function bannerResponse(env, id, version) {
  const r = await env.DB.prepare('SELECT type, data, updated FROM league_banners WHERE league_id = ?').bind(id).first();
  if (!r) return new Response('no banner', { status: 404, headers: { 'Cache-Control': 'no-store' } });
  const d = r.data;
  const bytes = d instanceof ArrayBuffer ? new Uint8Array(d)
    : ArrayBuffer.isView(d) ? new Uint8Array(d.buffer, d.byteOffset, d.byteLength) : Uint8Array.from(d);
  return new Response(bytes, { headers: {
    'Content-Type': r.type, 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'",
    'Cache-Control': String(r.updated) === version ? 'public, max-age=31536000, immutable' : 'public, max-age=60' } });
}

async function setBanner(env, l, req, now) {
  const type = (req.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (type === 'application/json') {                    // {remove: true}
    const b = await readBody(req) || {};
    if (!b.remove) return err('send a picture, or {"remove": true}');
    await removeBanner(env, l.id);
    return json({ banner: null });
  }
  if (+(req.headers.get('Content-Length') || 0) > BANNER.maxBytes) return err(`${BANNER.maxBytes / 1000} KB at most`, 413);
  const bytes = new Uint8Array(await req.arrayBuffer());
  const c = checkBanner(bytes);
  if (c.error) return err(c.error, c.status);
  await env.DB.batch([
    env.DB.prepare('INSERT OR REPLACE INTO league_banners (league_id, type, data, updated) VALUES (?, ?, ?, ?)')
      .bind(l.id, c.value.type, bytes.buffer, now),
    env.DB.prepare('UPDATE leagues SET banner = ? WHERE id = ?').bind(now, l.id)]);
  return json({ banner: bannerUrl(l.id, now) });
}

/** Take a league's banner down (its owner, or an admin of the site: POST /api/admin/league-banner). */
export async function removeBanner(env, id) {
  await env.DB.batch([env.DB.prepare('DELETE FROM league_banners WHERE league_id = ?').bind(id),
    env.DB.prepare('UPDATE leagues SET banner = NULL WHERE id = ?').bind(id)]);
}

// ------------------------------------------------------------------ the routes

/** -> a Response, or null when the path is not one of the leagues'. me: the signed-in player (or null); sameOrigin:
 *  false for a signed-in browser request from another site (refused for anything that changes data). */
export async function leaguesApi(req, env, path, url, me, sameOrigin = true, now = Date.now(), fetchFn = fetch) {
  if (!path.startsWith('/api/leagues') && !path.startsWith('/api/events') && !path.startsWith('/api/seasons') &&
      path !== '/api/catalog' && path !== '/api/me' && path !== '/api/me/events') return null;
  const post = req.method === 'POST';
  const site = env.SITE_URL || url.origin;
  const need = () => (!me ? err('sign in with Steam first', 401) : me.banned ? err('this account is banned', 403)
    : post && !sameOrigin ? err('refused: not from this site', 403) : null);

  if (path === '/api/catalog') return json(catalog(await routesRows(env)));
  if (path === '/api/me') return json(me ? { signedIn: true, steamId: me.steam_id, name: me.name, avatar: me.avatar } : { signedIn: false });

  if (path === '/api/leagues' && !post) {
    const { results: pub } = await env.DB.prepare(`${LIST_SQL} WHERE l.public = 1 ORDER BY members DESC, l.created DESC LIMIT 200`)
      .bind(now).all();
    let mine = [];
    if (me) {
      mine = (await env.DB.prepare(`${LIST_SQL} JOIN league_members m ON m.league_id = l.id AND m.steam_id = ?2
        ORDER BY l.created DESC`).bind(now, me.steam_id).all()).results;
    }
    return json({ public: pub.map(leagueListItem), mine: mine.map(leagueListItem) });
  }
  if (path === '/api/leagues' && post) {
    const no = need(); if (no) return no;
    const c = checkLeague(await readBody(req) || {});
    if (c.error) return err(c.error);
    const owned = await env.DB.prepare('SELECT COUNT(*) AS n FROM leagues WHERE owner = ?').bind(me.steam_id).first();
    if (owned.n >= LIMITS.leaguesPerOwner) return err(`you run ${LIMITS.leaguesPerOwner} leagues already`, 409);
    for (let tries = 0; tries < 5; tries++) {
      const id = newLeagueId(), code = newCode();
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO leagues (id, name, about, owner, public, code, created)
        VALUES (?, ?, ?, ?, ?, ?, ?)`).bind(id, c.value.name, c.value.about, me.steam_id, c.value.public, code, now).run();
      if (r.meta.changes) {
        await env.DB.prepare('INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, ?, \'member\')')
          .bind(id, me.steam_id, now).run();
        return json({ id, code: showCode(code) });
      }
    }
    return err('try again', 503);
  }
  if (path === '/api/leagues/join' && post) {          // with an invite code (any league, private ones only this way)
    const no = need(); if (no) return no;
    const b = await readBody(req) || {};
    const code = normCode(b.code);
    const l = code && await env.DB.prepare('SELECT id FROM leagues WHERE code = ?').bind(code).first();
    if (!l) return err('no league with that code (an owner can make a new one: ask for the new link)', 404);
    return addMember(env, l.id, me.steam_id, now);
  }
  if (path === '/api/leagues/code' && !post) {           // the invite page: which league a code opens
    const code = normCode(url.searchParams.get('code'));
    const l = code && await env.DB.prepare(`SELECT l.id, l.name, l.about, l.public, l.banner,
      (SELECT COUNT(*) FROM league_members m WHERE m.league_id = l.id) AS members FROM leagues l WHERE l.code = ?`).bind(code).first();
    if (!l) return err('this invite link no longer works: ask for a new one', 404);
    const member = !!me && !!await env.DB.prepare('SELECT 1 AS x FROM league_members WHERE league_id = ? AND steam_id = ?')
      .bind(l.id, me.steam_id).first();
    return json({ id: l.id, name: l.name, about: l.about, public: !!l.public, banner: bannerUrl(l.id, l.banner),
      members: l.members, member });
  }

  let m = path.match(/^\/api\/leagues\/([a-z0-9]{8})(?:\/([a-z]+))?$/);
  if (m) {
    const l = await leagueRow(env, m[1]);
    if (!l) return err('no such league', 404);
    const role = await roleIn(env, l, me);
    const action = m[2] || '';
    if (!action && !post) return leagueOut(env, l, role, me, url, now);
    if (!post) return err('not found', 404);
    const no = need(); if (no) return no;
    return leagueAction(env, l, role, me, action, req, now, site, fetchFn);
  }

  m = path.match(/^\/api\/seasons\/(\d+)\/(edit|delete)$/);
  if (m && post) {
    const no = need(); if (no) return no;
    const s = await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(+m[1]).first();
    if (!s) return err('no such season', 404);
    if (!isStaff(await roleIn(env, await leagueRow(env, s.league_id), me))) return err('only the league\'s owner and admins can do that', 403);
    if (m[2] === 'delete') {                              // its events become one-offs; their results stay
      await env.DB.batch([env.DB.prepare('UPDATE league_events SET season_id = NULL WHERE season_id = ?').bind(s.id),
        env.DB.prepare('DELETE FROM league_seasons WHERE id = ?').bind(s.id)]);
      return json({ deleted: true });
    }
    const c = checkSeason(await readBody(req) || {});
    if (c.error) return err(c.error);
    await env.DB.prepare('UPDATE league_seasons SET name = ?, points = ?, power = ?, drop_worst = ? WHERE id = ?')
      .bind(c.value.name, JSON.stringify(c.value.points), JSON.stringify(c.value.power), c.value.drop, s.id).run();
    return json({ ok: true });
  }

  if (path === '/api/me/events') {                       // the app: events of my leagues, open or coming, with my entry
    const no = need(); if (no) return no;
    const { results: evs } = await env.DB.prepare(`SELECT e.*, l.name AS league_name FROM league_events e
      JOIN leagues l ON l.id = e.league_id JOIN league_members m ON m.league_id = e.league_id AND m.steam_id = ?
      WHERE e.closes > ? AND e.opens < ? ORDER BY e.closes`).bind(me.steam_id, now - 86400000, now + 14 * 86400000).all();
    const routes = await routesRows(env);
    const { results: mine } = await env.DB.prepare(`SELECT * FROM league_entries WHERE steam_id = ? AND event_id IN
      (SELECT e.id FROM league_events e JOIN league_members m ON m.league_id = e.league_id AND m.steam_id = ?1 WHERE e.closes > ?2)`)
      .bind(me.steam_id, now - 86400000).all();
    const out = [];
    for (const ev of evs) {
      const entry = mine.find((x) => x.event_id === ev.id);
      const o = eventOut(ev, routes, now);
      o.league = ev.league_name;
      o.entry = entry ? { car: entry.car, ...entryState(entry, ev, now), done: entry.done, totalMs: entry.total_ms, started: entry.started } : null;
      out.push(o);
    }
    return json({ now, events: out });
  }

  m = path.match(/^\/api\/events\/(\d+)(?:\/([a-z]+))?$/);
  if (m) {
    const ev = await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(+m[1]).first();
    if (!ev) return err('no such event', 404);
    const l = await leagueRow(env, ev.league_id);
    const role = await roleIn(env, l, me);
    const action = m[2] || '';
    if (!action && !post) return eventView(env, ev, l, role, me, now);
    if (!post) return err('not found', 404);
    const no = need(); if (no) return no;
    return eventAction(env, ev, l, role, me, action, req, now);
  }
  return null;
}

// ------------------------------------------------------------------ a league

async function leagueOut(env, l, role, me, url, now) {
  const code = normCode(url.searchParams.get('code'));
  if (!l.public && !role && code !== l.code) return err('no such league', 404);   // private: members and invitees only
  const staff = isStaff(role);
  const [mem, evs, sea, bans] = await env.DB.batch([
    env.DB.prepare(`SELECT m.steam_id, m.joined, m.role, p.name, p.country, p.avatar FROM league_members m
      LEFT JOIN players p ON p.steam_id = m.steam_id WHERE m.league_id = ? ORDER BY m.joined`).bind(l.id),
    env.DB.prepare('SELECT * FROM league_events WHERE league_id = ? ORDER BY opens, id').bind(l.id),
    env.DB.prepare('SELECT * FROM league_seasons WHERE league_id = ? ORDER BY created, id').bind(l.id),
    env.DB.prepare(`SELECT b.steam_id, b.reason, b.created, p.name FROM league_bans b LEFT JOIN players p ON p.steam_id = b.steam_id
      WHERE b.league_id = ? ORDER BY b.created DESC`).bind(l.id),
  ]);
  const routes = await routesRows(env);
  const res = await resultsOf(env, { leagueId: l.id });
  const events = evs.results.map((ev) => {
    const st = standingsOf(ev, res.get(ev.id) || EMPTY, now);
    const o = eventOut(ev, routes, now);
    const win = st.rows.find((r) => r.rank === 1);
    return { id: ev.id, name: ev.name, seasonId: ev.season_id || null, rally: ev.rally, car: ev.car, carClass: ev.car_class,
      stages: o.stages.length, days: o.days, lengthM: o.lengthM, opens: ev.opens, closes: ev.closes, status: o.status,
      entries: st.rows.length, finished: st.rows.filter((r) => r.status === 'finished').length, winner: win ? win.name : null,
      _st: st };
  });
  const seasons = sea.results.map((s) => {
    const so = seasonOut(s);
    const mine = events.filter((e) => e.seasonId === s.id);
    so.about = describeSeason(so);
    so.events = mine.map((e) => e.id);
    so.standings = seasonStandings(so, mine.map((e) => ({ id: e.id, status: e.status, rows: e._st.rows, stages: e._st.stages })));
    return so;
  });
  for (const e of events) delete e._st;
  const ownerName = (mem.results.find((x) => x.steam_id === l.owner) || {}).name || null;
  return json({
    id: l.id, name: l.name, about: l.about, public: !!l.public, created: l.created, banner: bannerUrl(l.id, l.banner),
    owner: { steamId: l.owner, name: ownerName },
    code: staff || l.public ? showCode(l.code) : null,
    discord: role === 'owner' ? (l.discord ? { set: true, hint: l.discord.slice(-4) } : { set: false }) : undefined,
    members: mem.results.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver', country: x.country, avatar: x.avatar,
      joined: x.joined, role: x.steam_id === l.owner ? 'owner' : x.role === 'admin' ? 'admin' : 'member' })),
    bans: staff ? bans.results.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver', reason: x.reason, at: x.created })) : undefined,
    events, seasons,
    me: { signedIn: !!me, member: !!role, owner: role === 'owner', role, staff },
  });
}

async function leagueAction(env, l, role, me, action, req, now, site, fetchFn) {
  const owner = role === 'owner', staff = isStaff(role);
  if (action === 'banner') return owner ? setBanner(env, l, req, now) : err('only the league\'s owner can do that', 403);
  const b = await readBody(req) || {};
  if (action === 'join') {                                // a public league, from its page
    if (!l.public && normCode(b.code) !== l.code) return err('this league is private: join with its invite link', 403);
    return addMember(env, l.id, me.steam_id, now);
  }
  if (action === 'leave') {
    if (owner) return err('the owner can\'t leave their league (delete it instead)', 409);
    await env.DB.prepare('DELETE FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, me.steam_id).run();
    return json({ left: true });
  }
  if (!staff) return err('only the league\'s owner and admins can do that', 403);

  if (action === 'code') {                                // a new invite code: the old links stop working
    for (let tries = 0; tries < 5; tries++) {
      const r = await env.DB.prepare('UPDATE OR IGNORE leagues SET code = ? WHERE id = ?').bind(newCode(), l.id).run();
      if (r.meta.changes) return json({ code: showCode((await leagueRow(env, l.id)).code) });
    }
    return err('try again', 503);
  }
  if (action === 'remove') {                              // take a member out, and with ban: true keep them out
    const sid = String(b.steamId || '');
    if (sid === l.owner) return err('the owner can\'t be removed', 409);
    if (sid === me.steam_id) return err('that is you: leave the league instead', 409);
    const target = await env.DB.prepare('SELECT role FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, sid).first();
    if (target && target.role === 'admin' && !owner) return err('only the owner can remove an admin', 403);
    const reason = text(b.reason, LIMITS.reason);
    const stmts = [env.DB.prepare('DELETE FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, sid),
      // their events under way end there (their results so far stay)
      env.DB.prepare(`UPDATE league_entries SET status = 'dnf', reason = 'removed from the league', updated = ? WHERE steam_id = ?
        AND status = 'running' AND event_id IN (SELECT id FROM league_events WHERE league_id = ?)`).bind(now, sid, l.id)];
    if (b.ban) {
      stmts.push(env.DB.prepare('INSERT OR REPLACE INTO league_bans (league_id, steam_id, reason, by, created) VALUES (?, ?, ?, ?, ?)')
        .bind(l.id, sid, reason, me.steam_id, now));
    }
    await env.DB.batch(stmts);
    return json({ removed: true, banned: !!b.ban });
  }
  if (action === 'unban') {
    await env.DB.prepare('DELETE FROM league_bans WHERE league_id = ? AND steam_id = ?').bind(l.id, String(b.steamId || '')).run();
    return json({ unbanned: true });
  }
  if (action === 'seasons') {                             // a new season
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = ?').bind(l.id).first();
    if (n.n >= LIMITS.seasonsPerLeague) return err(`at most ${LIMITS.seasonsPerLeague} seasons in a league`, 409);
    const c = checkSeason(b);
    if (c.error) return err(c.error);
    const r = await env.DB.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created)
      VALUES (?, ?, ?, ?, ?, ?)`).bind(l.id, c.value.name, JSON.stringify(c.value.points), JSON.stringify(c.value.power),
      c.value.drop, now).run();
    return json({ id: r.meta.last_row_id });
  }
  if (action === 'events') {                              // a new event
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_events WHERE league_id = ?').bind(l.id).first();
    if (n.n >= LIMITS.eventsPerLeague) return err(`at most ${LIMITS.eventsPerLeague} events in a league`, 409);
    const c = checkEvent(b, catalog(await routesRows(env)), now);
    if (c.error) return err(c.error);
    const se = await seasonFor(env, l, b.seasonId, now);
    if (se.error) return err(se.error);
    const v = c.value;
    const r = await env.DB.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, rules, stages,
      opens, closes, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(l.id, se.id, v.name, v.rally, v.car, v.car_class,
      JSON.stringify(v.rules), JSON.stringify(v.stages), v.opens, v.closes, now).run();
    return json({ id: r.meta.last_row_id, seasonId: se.id });
  }
  if (!owner) return err('only the league\'s owner can do that', 403);

  if (action === 'edit') {
    const c = checkLeague({ ...b, name: b.name == null ? l.name : b.name });
    if (c.error) return err(c.error);
    await env.DB.prepare('UPDATE leagues SET name = ?, about = ?, public = ? WHERE id = ?')
      .bind(c.value.name, b.about == null ? l.about : c.value.about, b.public == null ? l.public : c.value.public, l.id).run();
    return json({ ok: true });
  }
  if (action === 'role') {                                // make an admin, or a member again
    const sid = String(b.steamId || '');
    if (!['admin', 'member'].includes(b.role)) return err('the role is admin or member');
    if (sid === l.owner) return err('the owner is the owner', 409);
    const r = await env.DB.prepare('UPDATE league_members SET role = ? WHERE league_id = ? AND steam_id = ?').bind(b.role, l.id, sid).run();
    return r.meta.changes ? json({ role: b.role }) : err('not a member of this league', 404);
  }
  if (action === 'discord') {                             // the league's own Discord posts: a webhook of one of its channels
    if (b.remove) {
      await env.DB.prepare('UPDATE leagues SET discord = NULL WHERE id = ?').bind(l.id).run();
      return json({ discord: { set: false } });
    }
    if (b.test) {
      const hook = l.discord && hookOf(env, l.discord, fetchFn);
      if (!hook) return err('no Discord webhook set', 409);
      const r = await hook.post(testMessage(l, site));
      return r.ok ? json({ sent: true }) : err(`Discord answered ${r.status || 'nothing'}: check the webhook (Channel settings › Integrations)`, 502);
    }
    const hookUrl = String(b.webhook || '').trim();
    if (!hookOf(env, hookUrl, fetchFn)) return err('paste the webhook\'s address: https://discord.com/api/webhooks/…');
    // events already over aren't announced: the posts start from now on
    await env.DB.batch([env.DB.prepare('UPDATE leagues SET discord = ? WHERE id = ?').bind(hookUrl, l.id),
      env.DB.prepare(`UPDATE league_events SET posted_open = COALESCE(posted_open, ?1), posted_24h = COALESCE(posted_24h, ?1),
        posted_results = COALESCE(posted_results, ?1) WHERE league_id = ?2 AND closes + ?3 <= ?1`).bind(now, l.id, LIMITS.graceMs)]);
    return json({ discord: { set: true, hint: hookUrl.slice(-4) } });
  }
  if (action === 'delete') {
    if (b.confirm !== l.name) return err('type the league\'s name to delete it');
    const inLeague = 'event_id IN (SELECT id FROM league_events WHERE league_id = ?)';
    await env.DB.batch([
      env.DB.prepare(`DELETE FROM league_stage_times WHERE ${inLeague}`).bind(l.id),
      env.DB.prepare(`DELETE FROM league_entries WHERE ${inLeague}`).bind(l.id),
      env.DB.prepare(`DELETE FROM league_penalties WHERE ${inLeague}`).bind(l.id),
      env.DB.prepare('DELETE FROM league_events WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_seasons WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_members WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_bans WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_banners WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM leagues WHERE id = ?').bind(l.id),
    ]);
    return json({ deleted: true });
  }
  return err('not found', 404);
}

// ------------------------------------------------------------------ an event

async function eventView(env, ev, l, role, me, now) {
  if (!l.public && !role) return err('no such event', 404);
  const o = eventOut(ev, await routesRows(env), now);
  const res = (await resultsOf(env, { eventId: ev.id })).get(ev.id) || EMPTY;
  const st = standingsOf(ev, res, now);
  const season = ev.season_id && await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(ev.season_id).first();
  o.league = { id: l.id, name: l.name, public: !!l.public, banner: bannerUrl(l.id, l.banner) };
  o.season = season ? { id: season.id, name: season.name, ...seasonOut(season), about: describeSeason(seasonOut(season)) } : null;
  o.standings = st.rows;
  o.stageResults = st.stages;
  o.decisions = decisions(res, o.stages.length);
  const mine = me && st.rows.find((r) => r.steamId === me.steam_id);
  o.me = { signedIn: !!me, member: !!role, owner: role === 'owner', role, staff: isStaff(role), entry: mine || null };
  return json(o);
}

async function eventAction(env, ev, l, role, me, action, req, now) {
  const staff = isStaff(role);
  const b = await readBody(req) || {};
  const nStages = JSON.parse(ev.stages).length;
  if (['edit', 'delete', 'penalty', 'dsq'].includes(action) && !staff) return err('only the league\'s owner and admins can do that', 403);
  if (action === 'delete') {
    await env.DB.batch([env.DB.prepare('DELETE FROM league_stage_times WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_entries WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_penalties WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_events WHERE id = ?').bind(ev.id)]);
    return json({ deleted: true });
  }
  if (action === 'edit') {
    let seasonId = ev.season_id;
    if ('seasonId' in b) {                               // the season can change at any time (the standings follow)
      const se = await seasonFor(env, l, b.seasonId, now);
      if (se.error) return err(se.error);
      seasonId = se.id;
    }
    const started = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_entries WHERE event_id = ?').bind(ev.id).first();
    if (started.n) {                                     // once someone has started: only the name, the season and a later close
      const name = text(b.name == null ? ev.name : b.name, LIMITS.name);
      const closes = b.closes == null ? ev.closes : Math.round(+b.closes);
      if (name.length < 3) return err('give the event a name (3 to 60 characters)');
      if (!(closes >= ev.closes) || closes - ev.opens > LIMITS.windowDays * 86400000) {
        return err('drivers have started it: only its name and season can change, and it can only close later');
      }
      await env.DB.prepare('UPDATE league_events SET name = ?, closes = ?, season_id = ? WHERE id = ?').bind(name, closes, seasonId, ev.id).run();
      return json({ ok: true, limited: true });
    }
    const c = checkEvent(b, catalog(await routesRows(env)), now);
    if (c.error) return err(c.error);
    const v = c.value;
    await env.DB.prepare(`UPDATE league_events SET name = ?, rally = ?, car = ?, car_class = ?, rules = ?, stages = ?, opens = ?, closes = ?,
      season_id = ? WHERE id = ?`).bind(v.name, v.rally, v.car, v.car_class, JSON.stringify(v.rules), JSON.stringify(v.stages), v.opens,
      v.closes, seasonId, ev.id).run();
    return json({ ok: true });
  }
  if (action === 'penalty') {                             // a steward's time penalty, or {remove: id} to take one back
    if (b.remove != null) {
      const r = await env.DB.prepare('DELETE FROM league_penalties WHERE id = ? AND event_id = ?').bind(Math.round(+b.remove), ev.id).run();
      return r.meta.changes ? json({ removed: true }) : err('no such penalty', 404);
    }
    const entry = await env.DB.prepare('SELECT 1 AS x FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, String(b.steamId || '')).first();
    if (!entry) return err('that driver has not started this event', 404);
    const c = checkPenalty(b, nStages);
    if (c.error) return err(c.error);
    const r = await env.DB.prepare(`INSERT INTO league_penalties (event_id, steam_id, stage_no, ms, reason, by, created)
      VALUES (?, ?, ?, ?, ?, ?, ?)`).bind(ev.id, String(b.steamId), c.value.stage, c.value.ms, c.value.reason, me.steam_id, now).run();
    return json({ id: r.meta.last_row_id });
  }
  if (action === 'dsq') {                                 // disqualify an entry, or {remove: true} to reinstate it
    const sid = String(b.steamId || '');
    const reason = b.remove ? null : text(b.reason, LIMITS.reason);
    if (!b.remove && reason.length < 3) return err('give a reason: everyone sees it');
    const r = await env.DB.prepare('UPDATE league_entries SET dsq = ?, dsq_by = ?, dsq_at = ? WHERE event_id = ? AND steam_id = ?')
      .bind(reason, b.remove ? null : me.steam_id, b.remove ? null : now, ev.id, sid).run();
    return r.meta.changes ? json({ dsq: reason }) : err('that driver has not started this event', 404);
  }

  if (!role) return err('join the league first', 403);

  // the app: a driver's run through the event
  const v = appVersion(req);
  const min = env.LEAGUES_MIN_APP || '0.0.5';
  if (!v || older(v, min)) return err(`leagues need ACR Daily ${min} or newer`, 426);
  const entry = await env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, me.steam_id).first();
  // Each stage's first start counts, as a daily's: a stage started a second time without finishing it (the app
  // closed during it, then the stage driven again) ends the entry.
  const again = async (no) => {
    const reason = `SS${no + 1} started again`;
    await env.DB.prepare('UPDATE league_entries SET status = \'dnf\', reason = ?, updated = ? WHERE event_id = ? AND steam_id = ?')
      .bind(reason, now, ev.id, me.steam_id).run();
    return json({ status: 'dnf', reason });
  };
  if (action === 'start') {                               // SS1 started: the entry
    if (now < ev.opens) return err('the event is not open yet', 409);
    if (now >= ev.closes) return err('the event is closed', 409);
    if (entry && entry.dsq) return json({ status: 'dsq', reason: entry.dsq });
    if (entry && entry.status === 'running' && entry.done === 0 && entry.on_stage === 0) return again(0);
    if (entry) return json({ error: 'already started: the first start counts', entry: { status: entry.status, done: entry.done } }, 409);
    const car = carByName(b.car) || CARS.find((c) => c.id === b.car);
    if (!car || (ev.car ? car.name !== ev.car : car.cls !== ev.car_class)) return err('not a car of this event', 422);
    await env.DB.prepare(`INSERT OR IGNORE INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated, app_version)
      VALUES (?, ?, ?, 'running', 0, 0, 0, ?, ?, ?)`).bind(ev.id, me.steam_id, car.name, now, now, v).run();
    return json({ started: true, car: car.name, status: 'running' });
  }
  if (!entry) return err('not started', 409);
  if (entry.dsq && action !== 'dnf') return action === 'begin' ? json({ status: 'dsq', reason: entry.dsq })
    : err(`disqualified by the stewards: ${entry.dsq}`, 409);
  if (action === 'begin') {                               // a later stage started (or SS1 again)
    const no2 = Math.round(+b.no);
    if (entry.status !== 'running') return json({ status: entry.status, reason: entry.reason || '' });
    if (no2 !== entry.done) return err(`expected SS${entry.done + 1}`, 409);
    if (entry.on_stage === no2) return again(no2);
    await env.DB.prepare('UPDATE league_entries SET on_stage = ?, updated = ? WHERE event_id = ? AND steam_id = ?')
      .bind(no2, now, ev.id, me.steam_id).run();
    return json({ status: 'running' });
  }
  if (action === 'stage') {
    const no2 = Math.round(+b.no);
    const timeMs = Math.round(+b.timeMs), penMs = Math.round(+b.penaltyMs);
    if (entry.status !== 'running') return err(`this entry is ${entry.status}`, 409);
    if (now > ev.closes + LIMITS.graceMs) return err('the event is closed', 409);
    if (no2 !== entry.done) return err(`expected SS${entry.done + 1}`, 409);
    if (!(timeMs > 0 && timeMs < 4 * 3600000) || !(penMs >= 0 && penMs < 3600000)) return err('no official result from the game');
    const splits = Array.isArray(b.splitsMs) ? b.splitsMs.slice(0, 10).map((x) => Math.round(+x)).filter(Number.isFinite) : null;
    const done = entry.done + 1;
    const status = done >= nStages ? 'finished' : 'running';
    await env.DB.batch([
      env.DB.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, splits, started, created)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)`).bind(ev.id, me.steam_id, no2, timeMs, penMs, splits ? JSON.stringify(splits) : null,
        Number.isFinite(+b.startedAt) ? Math.round(+b.startedAt) : null, now),
      env.DB.prepare(`UPDATE league_entries SET done = ?, on_stage = NULL, total_ms = total_ms + ?, status = ?, updated = ?, app_version = ?
        WHERE event_id = ? AND steam_id = ?`).bind(done, timeMs + penMs, status, now, v, ev.id, me.steam_id),
    ]);
    return json({ done, status });
  }
  if (action === 'dnf') {
    if (entry.status !== 'running') return json({ status: entry.status });
    const reason = text(b.reason, 120) || 'retired';
    await env.DB.prepare('UPDATE league_entries SET status = \'dnf\', reason = ?, updated = ? WHERE event_id = ? AND steam_id = ?')
      .bind(reason, now, ev.id, me.steam_id).run();
    return json({ status: 'dnf', reason });
  }
  return err('not found', 404);
}

// ------------------------------------------------------------------ the leagues' Discord posts (cron, every minute)

/** Post what is due on the leagues' own Discord channels (leaguediscord.js duePosts): a few events a minute. A webhook
 *  Discord no longer knows (deleted in the channel) is forgotten; Discord busy or not reachable: the next minute again.
 *  -> [{event, post, status}] */
export async function leagueDiscordTick(env, now = Date.now(), fetchFn = fetch) {
  const { results: evs } = await env.DB.prepare(`SELECT e.*, l.name AS league_name, l.discord AS hook FROM league_events e
    JOIN leagues l ON l.id = e.league_id WHERE l.discord IS NOT NULL AND (
      (e.posted_open IS NULL AND e.opens <= ?1) OR (e.posted_24h IS NULL AND e.closes - 86400000 <= ?1) OR
      (e.posted_results IS NULL AND e.closes + ?2 <= ?1)) ORDER BY e.closes LIMIT 10`).bind(now, LIMITS.graceMs).all();
  const out = [];
  let routes = null;
  for (const ev of evs) {
    const due = duePosts(ev, now);
    let done = true;
    if (due.post) {
      const hook = hookOf(env, ev.hook, fetchFn);
      if (hook) {
        routes = routes || await routesRows(env);
        const lg = { id: ev.league_id, name: ev.league_name };
        const o = eventOut(ev, routes, now);
        const season = ev.season_id && await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(ev.season_id).first();
        o.season = season ? seasonOut(season) : null;
        let msg;
        if (due.post === 'open') msg = openMessage(o, lg, env.SITE_URL);
        else {
          const res = await resultsOf(env, due.post === 'results' && season ? { leagueId: ev.league_id } : { eventId: ev.id });
          const st = standingsOf(ev, res.get(ev.id) || EMPTY, now);
          if (due.post === '24h') msg = reminderMessage(o, lg, env.SITE_URL, st.rows);
          else {
            let table = null;
            if (season) {
              const { results: sevs } = await env.DB.prepare('SELECT * FROM league_events WHERE season_id = ? ORDER BY opens, id').bind(season.id).all();
              table = seasonStandings(o.season, sevs.map((x) => {
                const s2 = standingsOf(x, res.get(x.id) || EMPTY, now);
                return { id: x.id, status: eventStatus(x, now), rows: s2.rows, stages: s2.stages };
              }));
            }
            msg = resultsMessage(o, lg, env.SITE_URL, st.rows, st.stages, o.season, table);
          }
        }
        const r = await hook.post(msg);
        out.push({ event: ev.id, post: due.post, status: r.status });
        if (r.status === 401 || r.status === 404) {
          await env.DB.prepare('UPDATE leagues SET discord = NULL WHERE id = ?').bind(ev.league_id).run();
        } else if (!r.ok) done = false;
      }
    }
    if (done && due.mark.length) {
      const cols = due.mark.map((k) => ({ open: 'posted_open', '24h': 'posted_24h', results: 'posted_results' })[k]);
      await env.DB.prepare(`UPDATE league_events SET ${cols.map((c) => `${c} = ?1`).join(', ')} WHERE id = ?2`).bind(now, ev.id).run();
    }
  }
  return out;
}
