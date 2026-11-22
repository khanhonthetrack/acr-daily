// The leagues' API (the rules and standings: src/leagues.js). The website signs in with a session cookie, the app with
// its Bearer token. Who may do what: every championship is listed and can be opened, public or private; anyone signed
// in joins a public one, and asks to join a private one (an application, with a short word to its admins: 0043),
// which its owner or an admin accepts or declines (the driver is told in their inbox); they can also add a driver
// straight away. Members drive its events; admins (and the owner) run events and seasons, the applications, the
// members (add, remove, ban, divisions) and the stewarding (time penalties, disqualifications); only the owner changes
// the league's settings, banner and Discord posts, makes or unmakes admins, and deletes it. Invite codes let nobody into
// a championship any more: a code is a private rally's password (every rally is listed, a private one with a lock).
//
//   GET  /api/catalog                         what an event can be made of
//   GET  /api/me                              who is signed in on the website
//   GET  /api/me/events                       the app: events of my leagues, open or coming, with my entry and
//                                             their league's banner (leagueBanner); every public rally; an app that
//                                             says so (X-ACR-Locked: 1) the private ones too, `locked` until it has
//                                             their code
//   GET  /api/leagues                         every championship (public: the public ones, as apps before 0043 list
//                                             them to JOIN; private: the others) and rally, mine, my applications, the
//                                             applications to the ones I run; whether I am a Community organizer
//   POST /api/leagues                         a new championship (a league): Community organizers only
//   POST /api/rallies                         a new rally (anyone signed in): one event, public or private
//   POST /api/leagues/join {code}             a private rally's code (a championship's old code: its page says how)
//   GET  /api/leagues/code?code=              the invite page: which rally a code opens (a championship's: its id)
//   GET  /api/leagues/:id                     a league: members, events, seasons and their standings; my application;
//                                             for its staff, the applications
//   POST /api/leagues/:id/<action>            join (a public one), apply {message} (a private one), withdraw, leave,
//                                             accept / decline {steamId} (an application), add {steamId}, edit,
//                                             banner, discord, remove, unban, role, delete, events (a new event),
//                                             seasons (a new season), divisions {divisions: [names]},
//                                             division {steamId, division: a name | null}; teams, teamadd, teamedit,
//                                             teamdelete, teamset (its teams: src/leagueteams.js)
//   POST /api/seasons/:id/edit | delete       a season's settings (teamChamp: its team championship)
//   POST /api/seasons/:id/teampenalty         a team's points penalty (src/leagueteams.js)
//   GET  /api/events/:id                      an event: itinerary, standings, the stewards' decisions (a private
//                                             rally without its code: `locked`, what it races, no results)
//   GET  /api/events/:id/live                 who is on its stages right now, and its stages for its live map
//                                             (src/eventlive.js; none while it hides them)
//   POST /api/events/:id/<action>             join {code} (a private rally); edit, delete, penalty, dsq (staff);
//                                             reveal (a hidden event's set-up, on DRIVE: src/hidden.js), start, begin,
//                                             stage, missed, dnf (the app); nominate, entryteam (its teams:
//                                             src/leagueteams.js)
// GET /l/:id/banner (the picture) and the cron's leagueDiscordTick are called from src/index.js.

import { CARS, carByName } from './cars.js';
import { stageParts, SURFACE, WEATHER } from './conditions.js';
import { webhook } from './discord.js';
import { BANNER, bannerUrl, catalog, checkBanner, checkDivisions, checkEvent, checkLeague, checkPenalty, checkSeason,
  DEFAULT_SEASON, describeSeason, entryState, eventClasses, eventStandings, eventStatus, groupStandings, LIMITS, newCode,
  newLeagueId, normCode, OFFICIAL_OWNER, seasonStandings, showCode, text } from './leagues.js';
import { duePosts, openMessage, reminderMessage, resultsMessage, testMessage } from './leaguediscord.js';
import { menuName } from './stages.js';
import { impossiblyFast } from './validate.js';
import { LOOK_COLS, lookJoin, lookOfRow } from './shop.js';
import { balanceOf, creditsOn } from './credits.js';
import { withTeams } from './drivers.js';
import { activeHide, hideOf, maskEvent, maskRows, viewerOf, viewHide } from './hidden.js';
import { eventComments } from './comments.js';
import { liveTiming } from './glide.js';
import { liveRefused, liveRevived, liveSessionOf, liveStarted } from './liverallies.js';
import { lineupNames, lineupsOf, matchOut, TEAM_KINDS, teamMatchInfo } from './teammatch.js';
import { describeScoring } from './teamscore.js';
import { champOf, entryTeamStmts, eventTeamAction, eventTeams, leagueTeamAction, leagueTeamData, seasonChampField, seasonTeamPenalty,
  seasonTeams, tagRows, teamOfEntries } from './leagueteams.js';
import { noticesStmt, noticeStmt } from './social.js';

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
// An event over 3 days (the most the game's own menus put in one Rally Weekend; nobody has driven a 4th day in it) is
// driven in legs of whole days, each its own Rally Weekend: only by an app that says it can (X-ACR-Legs: 1,
// client/acr_daily/leagues.py legs). An older one would set the whole rally up. Stages are not limited: 9 drivers
// finished RALLY MONTECARLO 2026's 14 in one Rally Weekend.
export const LEG = { days: 3 };
export const needsLegs = (stages) => Math.max(...stages.map((s) => s.day || 1)) > LEG.days;
const canLegs = (req) => req.headers.get('X-ACR-Legs') === '1';
const hookOf = (env, url, fetchFn = fetch) => webhook(url, fetchFn, env.DEV_LOGIN === '1');   // (a local stand-in in tests)

// Rallies (0033): a rally is one event anyone signed in makes, held by a league row of kind 'event' (as a 1V1's or a
// cup's matches are held), so DRIVE, the timing and the standings are the leagues'. Public: every app lists it and a
// driver joins it by starting it; private: listed too, with a lock (0043): what it races shows, its results and DRIVE
// need its code (its password: the invite link /join/<code>, or typed in). Its maker stewards it. A championship (a
// league, kind 'league') is made by Community organizers only (players.organizer, given by the admin).
const RALLY = 'event';
const DAY = 86400000;
/** May someone see a league's events at all (a private rally without its code: only what it races, `locked`)? */
const canSee = (l, role) => !!(l.public || role || l.kind === 'league');
const lockedRally = (l, role) => l.kind === RALLY && !l.public && !role;
// apps that list private rallies with a lock and ask for their code (client api.py sends it from 0.1.6): older ones
// list only the public ones, as before
const knowsLocks = (req) => req.headers.get('X-ACR-Locked') === '1';
const LIVE_KIND = 'live';                         // a live rally's session (src/liverallies.js): its holder's kind
const STEWARDED = new Set(['league', RALLY]);      // with stewards: a championship's owner and admins, a rally's maker
const RALLIES_APP = '0.1.5.1';                     // the first app that lists rallies as such (older ones: as a league's event;
                                                   // 0.1.5.1: the test build of 0.1.6)
const RALLY_SQL = `SELECT e.id, e.name, e.rally, e.car, e.car_class, e.car_classes, e.stages, e.opens, e.closes, e.hide,
    l.id AS holder, l.about, l.public, l.owner, p.name AS owner_name,
    (SELECT COUNT(*) FROM league_entries x WHERE x.event_id = e.id) AS drivers
  FROM league_events e JOIN leagues l ON l.id = e.league_id LEFT JOIN players p ON p.steam_id = l.owner`;
/** A rally in a list (the Rallies page): what it races, who made it, how many have driven it. */
function rallyListItem(r, now) {
  const classes = eventClasses(r);                 // (a hidden rally keeps its stages' names, never their number)
  return { id: r.id, holder: r.holder, name: r.name, about: r.about, public: !!r.public, owner: r.owner_name || 'Driver',
    rally: r.rally, car: r.car, carClass: classes.length > 1 ? classes.join(' or ') : r.car_class,
    stages: JSON.parse(r.stages).length, opens: r.opens, closes: r.closes,
    status: eventStatus(r, now), drivers: r.drivers };
}

async function readBody(req) {
  try { return await req.json(); } catch { return null; }
}

export async function routesRows(env) {
  const { results } = await env.DB.prepare('SELECT track, stage_id, length FROM routes WHERE stage_id IS NOT NULL').all();
  return results;
}

/** An event row -> what the website and the app get: its stages with names, lengths, the game's ids and weathers. */
export function eventOut(ev, routes, now) {
  const stages = JSON.parse(ev.stages);
  const rt = new Map(routes.map((r) => [r.track, r]));
  const car = ev.car ? carByName(ev.car) : null, classes = eventClasses(ev);
  const cars = car ? [car] : CARS.filter((c) => classes.includes(c.cls));
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
    // several classes: carClass reads "Rally2/R5 or Rally4" (what an app before 0.0.17 shows), carClasses lists them
    car: ev.car, carClass: classes.length > 1 ? classes.join(' or ') : ev.car_class, carClasses: classes.length > 1 ? classes : undefined,
    cars: cars.map((c) => ({ name: c.name, id: c.id, cls: c.cls, telemetry: c.telemetry, aliases: [c.telemetry, ...(c.aliases || [])].filter(Boolean) })),
    rules: JSON.parse(ev.rules), stages: out, days: stages.length ? stages[stages.length - 1].day : 0,
    lengthM: out.reduce((a, s) => a + s.lengthM, 0), opens: ev.opens, closes: ev.closes, status: eventStatus(ev, now),
  };
}

const leagueRow = (env, id) => env.DB.prepare('SELECT * FROM leagues WHERE id = ?').bind(id).first();
/** A rally's event (its holder holds that one): -> its id, or null. */
const rallyEventId = async (env, holder) => ((await env.DB.prepare('SELECT id FROM league_events WHERE league_id = ? ORDER BY id LIMIT 1')
  .bind(holder).first()) || {}).id || null;
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
async function resultsOf(env, { leagueId = null, eventId = null, eventIds = null }) {
  const one = eventId != null, some = Array.isArray(eventIds);
  const where = (col) => (one ? `${col} = ?` : some ? `${col} IN (SELECT value FROM json_each(?))`
    : `${col} IN (SELECT id FROM league_events WHERE league_id = ?)`);
  const key = one ? eventId : some ? JSON.stringify(eventIds) : leagueId;
  const [en, ti, pe] = await env.DB.batch([
    env.DB.prepare(`SELECT e.*, p.name, p.country, p.avatar, s.name AS dsq_by_name, m.division FROM league_entries e
      LEFT JOIN players p ON p.steam_id = e.steam_id LEFT JOIN players s ON s.steam_id = e.dsq_by
      LEFT JOIN league_events v ON v.id = e.event_id LEFT JOIN league_members m ON m.league_id = v.league_id AND m.steam_id = e.steam_id
      WHERE ${where('e.event_id')}`).bind(key),
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
const evSpec = (ev) => ({ stages: JSON.parse(ev.stages), opens: ev.opens, closes: ev.closes,
  retireMs: ((JSON.parse(ev.rules || '{}') || {}).retire || 0) * 60000 });
const standingsOf = (ev, res, now) => eventStandings(evSpec(ev), res.entries, res.times, now, res.penalties);
const divisionsOf = (l) => (l.kind === 'league' && l.divisions ? JSON.parse(l.divisions) : []);
/** An event's standings within each of its classes and the league's divisions (leagues.js groupStandings). */
const groupsOf = (ev, res, now, classes, divisions) => groupStandings(evSpec(ev), res.entries, res.times, now, res.penalties, classes, divisions);

/** The stewards' decisions on an event, as everyone sees them. */
function decisions(res, nStages) {
  const out = res.penalties.map((p) => ({ id: p.id, kind: 'time', steamId: p.steam_id, driver: p.driver_name || 'Driver',
    stage: p.stage_no != null && p.stage_no < nStages ? p.stage_no + 1 : null, ms: p.ms, reason: p.reason, by: p.by_name || 'a steward', at: p.created }));
  for (const e of res.entries) {
    if (e.dsq) out.push({ id: null, kind: 'dsq', steamId: e.steam_id, driver: e.name || 'Driver', stage: null, ms: 0, reason: e.dsq, by: e.dsq_by_name || 'a steward', at: e.dsq_at });
  }
  return out.sort((a, b) => (a.at || 0) - (b.at || 0));
}

const listSql = (more = '') => `SELECT l.id, l.name, l.about, l.public, l.owner, l.banner, l.official, p.name AS owner_name,
    (SELECT COUNT(*) FROM league_members m WHERE m.league_id = l.id) AS members,
    (SELECT COUNT(*) FROM league_events e WHERE e.league_id = l.id) AS events,
    (SELECT COUNT(*) FROM league_events e WHERE e.league_id = l.id AND e.opens <= ?1 AND e.closes > ?1) AS open_events,
    (SELECT MIN(e.opens) FROM league_events e WHERE e.league_id = l.id AND e.opens > ?1) AS next_opens${more}
  FROM leagues l LEFT JOIN players p ON p.steam_id = l.owner`;
const leagueListItem = (r) => ({ id: r.id, name: r.name, about: r.about, public: !!r.public, official: !!r.official,
  owner: r.official ? OFFICIAL_OWNER.name : r.owner_name,
  banner: bannerUrl(r.id, r.banner), members: r.members, events: r.events, openEvents: r.open_events, nextOpens: r.next_opens });

/** Why a driver can't be in a league now (banned from it, or it is full): an error Response, or null. */
async function joinRefused(env, leagueId, steamId) {
  const ban = await env.DB.prepare('SELECT reason FROM league_bans WHERE league_id = ? AND steam_id = ?').bind(leagueId, steamId).first();
  if (ban) return err('you can\'t join this league' + (ban.reason ? ` (${ban.reason})` : ''), 403);
  const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_members WHERE league_id = ?').bind(leagueId).first();
  if (n.n >= LIMITS.members) return err(`this league is full (${LIMITS.members} drivers)`, 409);
  return null;
}
const memberStmt = (env, leagueId, steamId, now) => env.DB.prepare(
  'INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, ?, \'member\')').bind(leagueId, steamId, now);
// (an application of theirs goes once they are in)
const unapplyStmt = (env, leagueId, steamId) => env.DB.prepare('DELETE FROM league_applications WHERE league_id = ? AND steam_id = ?')
  .bind(leagueId, steamId);

async function addMember(env, leagueId, steamId, now) {
  const no = await joinRefused(env, leagueId, steamId);
  if (no) return no;
  await env.DB.batch([memberStmt(env, leagueId, steamId, now), unapplyStmt(env, leagueId, steamId)]);
  return json({ id: leagueId, joined: true });
}

// ------------------------------------------------------------------ applications (a private championship, 0043)

/** Who answers a championship's applications: its owner (a driver: not an official one's) and its admins. */
async function staffOf(env, l) {
  const { results } = await env.DB.prepare("SELECT steam_id FROM league_members WHERE league_id = ? AND role = 'admin'").bind(l.id).all();
  return [...new Set([...(/^\d{17}$/.test(l.owner) ? [l.owner] : []), ...results.map((r) => r.steam_id)])];
}

/** A driver asks to join a private championship (b.message: a short word to its admins), who are told in their inbox.
 *  Asked already: the word changes, nobody is told again; declined: again only LIMITS.reapplyDays after. */
async function applyTo(env, l, me, b, now) {
  const no = await joinRefused(env, l.id, me.steam_id);
  if (no) return no;
  const message = text(b.message, LIMITS.applyMessage);
  const was = await env.DB.prepare('SELECT status, decided FROM league_applications WHERE league_id = ? AND steam_id = ?')
    .bind(l.id, me.steam_id).first();
  if (was && was.status === 'pending') {
    await env.DB.prepare('UPDATE league_applications SET message = ? WHERE league_id = ? AND steam_id = ?').bind(message, l.id, me.steam_id).run();
    return json({ applied: true });
  }
  const again = was ? (was.decided || 0) + LIMITS.reapplyDays * DAY : 0;
  if (was && now < again) return err(`declined: you can ask again from ${new Date(again).toISOString().slice(0, 10)}`, 409);
  const staff = (await staffOf(env, l)).filter((sid) => sid !== me.steam_id);
  const said = `${me.name || 'A driver'} asks to join ${l.name}` + (message ? `: "${message}"` : '.') +
    ' Accept or decline on its page, or in the app under RALLIES.';
  await env.DB.batch([
    env.DB.prepare(`INSERT OR REPLACE INTO league_applications (league_id, steam_id, message, status, created, decided, by)
      VALUES (?, ?, ?, 'pending', ?, NULL, NULL)`).bind(l.id, me.steam_id, message, now),
    ...(staff.length ? [noticesStmt(env, 'apply', staff.map((to) => ({ to, body: said })), `league:${l.id}`, now)] : []),
  ]);
  return json({ applied: true });
}

/** The owner or an admin answers an application: accepted, the driver is in; either way they are told. */
async function answerApplication(env, l, me, sid, accept, now) {
  const a = await env.DB.prepare("SELECT * FROM league_applications WHERE league_id = ? AND steam_id = ? AND status = 'pending'")
    .bind(l.id, sid).first();
  if (!a) return err('no such application', 404);
  if (!accept) {
    await env.DB.batch([
      env.DB.prepare("UPDATE league_applications SET status = 'declined', decided = ?, by = ? WHERE league_id = ? AND steam_id = ?")
        .bind(now, me.steam_id, l.id, sid),
      noticeStmt(env, sid, 'league', `Your request to join ${l.name} was declined.`, `league:${l.id}`, now)]);
    return json({ declined: true });
  }
  const no = await joinRefused(env, l.id, sid);
  if (no) return no;
  await env.DB.batch([memberStmt(env, l.id, sid, now), unapplyStmt(env, l.id, sid),
    noticeStmt(env, sid, 'league', `You are in ${l.name}: its rounds are in the app, under RALLIES.`, `league:${l.id}`, now)]);
  return json({ accepted: true });
}

/** The owner or an admin puts a driver in straight away (they are told). */
async function addDriver(env, l, me, sid, now) {
  const p = /^\d{17}$/.test(sid) && await env.DB.prepare('SELECT steam_id, banned FROM players WHERE steam_id = ?').bind(sid).first();
  if (!p || p.banned) return err('no such driver', 404);
  if (sid === l.owner || await env.DB.prepare('SELECT 1 AS x FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, sid).first()) {
    return err('already in this championship', 409);
  }
  if (await env.DB.prepare('SELECT 1 AS x FROM league_bans WHERE league_id = ? AND steam_id = ?').bind(l.id, sid).first()) {
    return err('banned from this championship: unban them first', 409);
  }
  const no = await joinRefused(env, l.id, sid);
  if (no) return no;
  await env.DB.batch([memberStmt(env, l.id, sid, now), unapplyStmt(env, l.id, sid),
    noticeStmt(env, sid, 'league', `${me.name || 'An admin'} added you to ${l.name}: its rounds are in the app, under RALLIES.`,
      `league:${l.id}`, now)]);
  return json({ added: true });
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
  await storeBanner(env, l.id, bytes, c.value.type, now);
  return json({ banner: bannerUrl(l.id, now) });
}

/** Keep a league's banner (checked already: checkBanner): its picture and the league's mark of it (also a cup's, whose
 *  holder league has the cup's id). */
export async function storeBanner(env, id, bytes, type, now) {
  await env.DB.batch([
    env.DB.prepare('INSERT OR REPLACE INTO league_banners (league_id, type, data, updated) VALUES (?, ?, ?, ?)')
      .bind(id, type, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), now),
    env.DB.prepare('UPDATE leagues SET banner = ? WHERE id = ?').bind(now, id)]);
}

/** (the site's admin: POST /api/admin/rally-delete) A rally taken down (an offensive name or words): its event, its
 *  entries and times, and its holder. -> {deleted} or {error}. */
export async function adminDeleteRally(env, eventId) {
  const ev = await env.DB.prepare(`SELECT e.id, e.league_id FROM league_events e JOIN leagues l ON l.id = e.league_id
    WHERE e.id = ? AND l.kind = '${RALLY}'`).bind(Math.round(+eventId) || 0).first();
  if (!ev) return { error: 'no rally with that event id' };
  await env.DB.batch([env.DB.prepare('DELETE FROM league_stage_times WHERE event_id = ?').bind(ev.id),
    env.DB.prepare('DELETE FROM league_entries WHERE event_id = ?').bind(ev.id),
    env.DB.prepare('DELETE FROM league_penalties WHERE event_id = ?').bind(ev.id),
    env.DB.prepare('DELETE FROM league_events WHERE id = ?').bind(ev.id),
    env.DB.prepare('DELETE FROM league_members WHERE league_id = ?').bind(ev.league_id),
    env.DB.prepare('DELETE FROM league_bans WHERE league_id = ?').bind(ev.league_id),
    env.DB.prepare('DELETE FROM leagues WHERE id = ?').bind(ev.league_id)]);
  return { deleted: ev.id };
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
  if (!path.startsWith('/api/leagues') && !path.startsWith('/api/events') && !path.startsWith('/api/seasons') && path !== '/api/rallies' &&
      path !== '/api/catalog' && path !== '/api/me' && path !== '/api/me/events') return null;
  const post = req.method === 'POST';
  const site = env.SITE_URL || url.origin;
  const need = () => (!me ? err('sign in with Steam first', 401) : me.banned ? err('this account is banned', 403)
    : post && !sameOrigin ? err('refused: not from this site', 403) : null);

  if (path === '/api/catalog') return json(catalog(await routesRows(env)));
  if (path === '/api/me') {
    if (!me) return json({ signedIn: false });
    // credits on: the balance for the header, and whether today's bonus is still to claim (the page claims it: src/bonus.js)
    const today = new Date(now).toISOString().slice(0, 10);
    const b = creditsOn(env, today) ? await balanceOf(env, me.steam_id) : null;
    return json({ signedIn: true, steamId: me.steam_id, name: me.name, avatar: me.avatar, organizer: !!me.organizer,
      ...(b ? { credits: { balance: b.balance, claimable: b.lastDay !== today } } : {}) });
  }

  if (path === '/api/leagues' && !post) {
    // every championship, the public ones (the list apps before 0043 offer to JOIN) apart from the private ones (asked
    // to join: 0043); every rally open or coming, public or private (a private one with a lock: its code lets a driver
    // in), soonest to close first (a banned maker's: listed to nobody)
    const [ch, ra] = await env.DB.batch([
      env.DB.prepare(`${listSql()} WHERE l.kind = 'league' ORDER BY l.official DESC, members DESC, l.created DESC LIMIT 400`).bind(now),
      env.DB.prepare(`${RALLY_SQL} WHERE l.kind = '${RALLY}' AND e.closes > ?1
        AND COALESCE(p.banned, 0) = 0 ORDER BY e.closes LIMIT 200`).bind(now)]);
    const champs = ch.results.map(leagueListItem);
    let mine = [], myRallies = [], myApps = [], toAnswer = [];
    if (me) {
      // mine: my championships (my role in each; the applications waiting in the ones I run) and the rallies I made or
      // am in (a week after they close); my applications; the ones waiting for my answer
      const [mi, mr, ma, ta] = await env.DB.batch([
        env.DB.prepare(`${listSql(', m.role AS my_role')} JOIN league_members m ON m.league_id = l.id AND m.steam_id = ?2
          WHERE l.kind = 'league' ORDER BY l.created DESC`).bind(now, me.steam_id),
        env.DB.prepare(`${RALLY_SQL} JOIN league_members m ON m.league_id = l.id AND m.steam_id = ?2
          WHERE l.kind = '${RALLY}' AND e.closes > ?1 - 7 * 86400000 ORDER BY e.closes`).bind(now, me.steam_id),
        env.DB.prepare('SELECT league_id, status, created, decided FROM league_applications WHERE steam_id = ?').bind(me.steam_id),
        env.DB.prepare(`SELECT a.league_id, l.name AS league_name, a.steam_id, p.name, p.country, p.avatar, a.message, a.created
          FROM league_applications a JOIN leagues l ON l.id = a.league_id LEFT JOIN players p ON p.steam_id = a.steam_id
          WHERE a.status = 'pending' AND l.kind = 'league' AND (l.owner = ?1 OR EXISTS (SELECT 1 FROM league_members m
            WHERE m.league_id = a.league_id AND m.steam_id = ?1 AND m.role = 'admin'))
          ORDER BY a.created LIMIT 200`).bind(me.steam_id)]);
      toAnswer = ta.results.map((a) => ({ leagueId: a.league_id, league: a.league_name, steamId: a.steam_id, name: a.name || 'Driver',
        country: a.country || null, avatar: a.avatar || null, message: a.message || '', at: a.created }));
      mine = mi.results.map((r) => {
        const role = r.owner === me.steam_id ? 'owner' : r.my_role === 'admin' ? 'admin' : 'member';
        return { ...leagueListItem(r), role, ...(isStaff(role) ? { applications: toAnswer.filter((a) => a.leagueId === r.id).length } : {}) };
      });
      myRallies = mr.results;
      myApps = ma.results.map((a) => ({ id: a.league_id, status: a.status, at: a.created,
        again: a.status === 'declined' ? (a.decided || 0) + LIMITS.reapplyDays * DAY : null }));
    }
    return json({ public: champs.filter((x) => x.public), private: champs.filter((x) => !x.public), mine,
      rallies: ra.results.map((r) => rallyListItem(r, now)), myRallies: myRallies.map((r) => rallyListItem(r, now)),
      applied: myApps, applications: me ? toAnswer : [], organizer: !!(me && me.organizer) });
  }
  if (path === '/api/leagues' && post) {                 // a championship: Community organizers only (the admin's rank)
    const no = need(); if (no) return no;
    if (!me.organizer) return err('championships are made by Community organizers: ask the admin on Discord. Anyone can make a rally', 403);
    const c = checkLeague(await readBody(req) || {});
    if (c.error) return err(c.error);
    const owned = await env.DB.prepare("SELECT COUNT(*) AS n FROM leagues WHERE owner = ? AND kind = 'league'").bind(me.steam_id).first();
    if (owned.n >= LIMITS.leaguesPerOwner) return err(`you run ${LIMITS.leaguesPerOwner} leagues already`, 409);
    for (let tries = 0; tries < 5; tries++) {
      const id = newLeagueId();          // (its code, the column's: it lets nobody in, 0043)
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO leagues (id, name, about, owner, public, code, created)
        VALUES (?, ?, ?, ?, ?, ?, ?)`).bind(id, c.value.name, c.value.about, me.steam_id, c.value.public, newCode(), now).run();
      if (r.meta.changes) {
        await env.DB.prepare('INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, ?, \'member\')')
          .bind(id, me.steam_id, now).run();
        return json({ id });
      }
    }
    return err('try again', 503);
  }
  if (path === '/api/rallies' && post) {                 // a new rally: anyone signed in (ralliesPerOwner open or coming at once)
    const no = need(); if (no) return no;
    const b = await readBody(req) || {};
    const c = checkEvent(b, catalog(await routesRows(env)), now);
    if (c.error) return err(c.error);
    const mineOpen = await env.DB.prepare(`SELECT COUNT(*) AS n FROM leagues l JOIN league_events e ON e.league_id = l.id
      WHERE l.owner = ? AND l.kind = '${RALLY}' AND e.closes > ?`).bind(me.steam_id, now).first();
    if (mineOpen.n >= LIMITS.ralliesPerOwner) return err(`you have ${LIMITS.ralliesPerOwner} rallies open or coming already`, 409);
    const v = c.value;
    const holder = await makeHolder(env, { kind: RALLY, name: v.name, owner: me.steam_id, members: [me.steam_id],
      pub: b.public !== false, about: text(b.about, LIMITS.about) }, now);
    const r = await env.DB.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, car_classes, rules,
      stages, opens, closes, created, hide) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(holder, v.name, v.rally, v.car, v.car_class,
      v.car_classes ? JSON.stringify(v.car_classes) : null, JSON.stringify(v.rules), JSON.stringify(v.stages), v.opens, v.closes, now,
      v.hide ? JSON.stringify(v.hide) : null).run();
    return json({ id: r.meta.last_row_id, holder });
  }
  if (path === '/api/leagues/join' && post) {          // a private rally's code (a public one: joined by driving it)
    const no = need(); if (no) return no;
    const b = await readBody(req) || {};
    const code = normCode(b.code);
    const l = code && await env.DB.prepare(`SELECT id, kind FROM leagues WHERE code = ? AND kind IN ('league', '${RALLY}')`).bind(code).first();
    if (!l) return err('no rally with that code', 404);
    // a championship's old code lets nobody in (0043): its page, where a driver joins a public one or asks to join
    if (l.kind !== RALLY) return json({ error: 'championships take no codes: join or ask to join on its page', id: l.id, kind: l.kind }, 410);
    const r = await addMember(env, l.id, me.steam_id, now);
    if (!r.ok) return r;
    return json({ id: l.id, joined: true, eventId: await rallyEventId(env, l.id) });   // (a rally's page is its event's)
  }
  if (path === '/api/leagues/code' && !post) {           // the invite page: which rally a code opens (a championship's:
    const code = normCode(url.searchParams.get('code')); // its page, src/index.js sends the link there)
    const l = code && await env.DB.prepare(`SELECT l.id, l.name, l.about, l.public, l.banner, l.official, l.kind,
      (SELECT COUNT(*) FROM league_members m WHERE m.league_id = l.id) AS members FROM leagues l WHERE l.code = ? AND l.kind IN ('league', '${RALLY}')`)
      .bind(code).first();
    if (!l) return err('this invite link no longer works: ask for a new one', 404);
    const member = !!me && !!await env.DB.prepare('SELECT 1 AS x FROM league_members WHERE league_id = ? AND steam_id = ?')
      .bind(l.id, me.steam_id).first();
    return json({ id: l.id, name: l.name, about: l.about, public: !!l.public, official: !!l.official, banner: bannerUrl(l.id, l.banner),
      members: l.members, member, kind: l.kind, eventId: l.kind === RALLY ? await rallyEventId(env, l.id) : undefined });
  }

  let m = path.match(/^\/api\/leagues\/([a-z0-9]{8})(?:\/([a-z]+))?$/);
  if (m) {
    const l = await leagueRow(env, m[1]);
    if (!l || l.kind !== 'league') return err('no such league', 404);   // (a head-to-head's or a cup's holder: theirs)
    const role = await roleIn(env, l, me);
    const action = m[2] || '';
    if (!action && !post) return leagueOut(env, l, role, me, url, now);
    if (!post) return err('not found', 404);
    const no = need(); if (no) return no;
    return leagueAction(env, l, role, me, action, req, now, site, fetchFn);
  }

  m = path.match(/^\/api\/seasons\/(\d+)\/(edit|delete|teampenalty)$/);
  if (m && post) {
    const no = need(); if (no) return no;
    const s = await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(+m[1]).first();
    if (!s) return err('no such season', 404);
    if (!isStaff(await roleIn(env, await leagueRow(env, s.league_id), me))) return err('only the league\'s owner and admins can do that', 403);
    if (m[2] === 'delete') {                              // its events become one-offs; their results stay
      await env.DB.batch([env.DB.prepare('UPDATE league_events SET season_id = NULL WHERE season_id = ?').bind(s.id),
        env.DB.prepare('DELETE FROM league_team_penalties WHERE season_id = ?').bind(s.id),
        env.DB.prepare('DELETE FROM league_seasons WHERE id = ?').bind(s.id)]);
      return json({ deleted: true });
    }
    const b = await readBody(req) || {};
    if (m[2] === 'teampenalty') return seasonTeamPenalty(env, s, me, b, now, { json, err });
    const c = checkSeason(b);
    if (c.error) return err(c.error);
    const tc = seasonChampField(b);
    if (tc.error) return err(tc.error);
    await env.DB.prepare('UPDATE league_seasons SET name = ?, points = ?, power = ?, drop_worst = ?, team_champ = ? WHERE id = ?')
      .bind(c.value.name, JSON.stringify(c.value.points), JSON.stringify(c.value.power), c.value.drop, tc.keep ? s.team_champ : tc.value, s.id).run();
    return json({ ok: true });
  }

  if (path === '/api/me/events') {                       // the app: events of my leagues, open or coming, with my entry
    const no = need(); if (no) return no;              // (and my head-to-heads' and cup matches: only the ones I drive)
    // ...and every public rally, for everyone (0033: a driver joins one by starting it), but whom its maker turned away;
    // to an app that says it can (X-ACR-Locked), the private rallies too: locked until it sends their code (0043)
    const { results: evs } = await env.DB.prepare(`SELECT e.*, l.name AS league_name, l.kind AS league_kind, l.banner AS league_banner,
        l.public AS league_public, p.name AS owner_name, (SELECT COUNT(*) FROM league_entries x WHERE x.event_id = e.id) AS drivers,
        EXISTS (SELECT 1 FROM league_members m WHERE m.league_id = e.league_id AND m.steam_id = ?1) AS member
      FROM league_events e JOIN leagues l ON l.id = e.league_id LEFT JOIN players p ON p.steam_id = l.owner
      WHERE e.closes > ?2 AND e.opens < ?3 AND (e.only_ids IS NULL OR EXISTS (SELECT 1 FROM json_each(e.only_ids) WHERE value = ?1))
        AND (EXISTS (SELECT 1 FROM league_members m WHERE m.league_id = e.league_id AND m.steam_id = ?1)
          OR (l.kind = '${RALLY}' AND (l.public = 1 OR ?4 = 1) AND COALESCE(p.banned, 0) = 0
            AND NOT EXISTS (SELECT 1 FROM league_bans b WHERE b.league_id = l.id AND b.steam_id = ?1)))
      ORDER BY e.closes`).bind(me.steam_id, now - 86400000, now + 14 * 86400000, knowsLocks(req) ? 1 : 0).all();
    const routes = await routesRows(env);
    const { results: mine } = await env.DB.prepare(`SELECT * FROM league_entries WHERE steam_id = ? AND event_id IN
      (SELECT value FROM json_each(?))`).bind(me.steam_id, JSON.stringify(evs.map((ev) => ev.id))).all();
    // a match's other driver, by their name now (the app says "VS <name>")
    // (a live rally's session names all its drivers: no "VS" for it)
    const other = (ev) => (ev.only_ids && ev.league_kind !== LIVE_KIND ? JSON.parse(ev.only_ids).find((sid) => sid !== me.steam_id) || null : null);
    const others = [...new Set(evs.map(other).filter(Boolean))];
    const names = new Map(others.length ? (await env.DB.prepare(`SELECT steam_id, name FROM players WHERE steam_id IN
      (${others.map(() => '?').join(',')})`).bind(...others).all()).results.map((p) => [p.steam_id, p.name]) : []);
    const out = [];
    // hidden events (src/hidden.js): their set-up comes once the driver presses DRIVE (reveal) or has started them; an app
    // too old to ask for it doesn't list them
    const who = await viewerOf(env, me.steam_id, evs.filter((ev) => activeHide(ev, ev.league_kind, now)).map((ev) => ev.id));
    const oldApp = !appVersion(req) || older(appVersion(req), hiddenMinApp(env));
    const oldRallies = !appVersion(req) || older(appVersion(req), RALLIES_APP);
    // team matches (src/teammatch.js): my team and the other in each
    const tms = evs.filter((ev) => TEAM_KINDS.includes(ev.league_kind)).map((ev) => ev.id);
    const sides = new Map();
    if (tms.length) {
      const { results: tr } = await env.DB.prepare(`SELECT DISTINCT l.event_id, l.team_id, t.name, t.tag, t.color,
          EXISTS (SELECT 1 FROM team_lineups x WHERE x.event_id = l.event_id AND x.team_id = l.team_id AND x.steam_id = ?2) AS mine
        FROM team_lineups l LEFT JOIN teams t ON t.id = l.team_id WHERE l.event_id IN (SELECT value FROM json_each(?1))`)
        .bind(JSON.stringify(tms), me.steam_id).all();
      for (const r of tr) {
        if (!sides.has(r.event_id)) sides.set(r.event_id, {});
        sides.get(r.event_id)[r.mine ? 'mine' : 'other'] = { id: r.team_id, name: r.name || 'a team', tag: r.tag || null, color: r.color || null };
      }
    }
    for (const ev of evs) {
      const entry = mine.find((x) => x.event_id === ev.id);
      const h = activeHide(ev, ev.league_kind, now);
      if (h && oldApp) continue;
      // (too long for an app without legs: not listed, unless its entry is over)
      if (!canLegs(req) && needsLegs(JSON.parse(ev.stages)) && !(entry && entry.status !== 'running')) continue;
      const o = maskEvent(eventOut(ev, routes, now), h, viewHide(h, { knows: who.knows.has(ev.id), staff: who.staff.has(ev.id) }));
      o.league = ev.league_name;
      o.kind = ev.league_kind;                           // league / event (a rally) / h2h / cup / live (a live rally's session)
      if (ev.league_kind === LIVE_KIND) Object.assign(o, liveSessionOf(ev));
      o.drivers = ev.drivers;                            // how many have started it (the app's list)
      if (ev.league_kind === RALLY) {                    // a rally: who made it; an app before 0.1.6 lists it as a league's
        o.organizer = ev.owner_name || 'Driver';
        o.public = !!ev.league_public;
        if (!ev.league_public && !ev.member) o.locked = true;   // (private, its code not given yet: 0043)
        if (oldRallies) { o.kind = 'league'; o.league = o.organizer; }
      }
      o.leagueBanner = bannerUrl(ev.league_id, ev.league_banner);   // its league's banner, or its cup's (the app's card)
      if (TEAM_KINDS.includes(ev.league_kind)) {         // a team match: in the app's 1V1 or CUPS tab, against the other team
        const sd = sides.get(ev.id) || {};
        o.kind = ev.league_kind === 'th2h' ? 'h2h' : 'cup';
        o.teamMatch = { kind: ev.league_kind, mine: sd.mine || null, other: sd.other || null };
        o.opponent = sd.other ? { steamId: null, name: sd.other.tag ? `[${sd.other.tag}] ${sd.other.name}` : sd.other.name } : null;
      } else if (other(ev)) o.opponent = { steamId: other(ev), name: names.get(other(ev)) || null };
      o.entry = entry ? { car: entry.car, ...entryState(entry, ev, now), done: entry.done, totalMs: entry.total_ms, started: entry.started } : null;
      out.push(o);
    }
    return json(await withTeams(env, { now, events: out }));
  }

  // WATCH (the app 0.2: everyone on a stage now): the drivers on the stages of rallies, championships, 1V1s and cups
  // right now, each with its stage's set-up (to take the game there) -- only where the asker may look: a private
  // rally only to its members, and a stage a hidden event keeps from them not at all (the user, 22 Nov 2026: "if stage
  // is hidden in a league for you, and someone is currently driving it, then you don't see. But if you can see the
  // stages (you already finished it, or you're an admin) then you can")
  if (path === '/api/events/live' && !post) {
    const { results: rows } = await env.DB.prepare(`SELECT DISTINCT event_id FROM event_live WHERE state = 'live' AND updated > ?`)
      .bind(now - EVENT_LIVE.staleMs).all();
    const ids = rows.map((r) => r.event_id);
    if (!ids.length) return json({ now, drivers: [] });
    const { results: evs } = await env.DB.prepare(`SELECT e.*, l.kind AS league_kind, l.public AS league_public, l.owner AS league_owner,
        l.name AS league_name, (SELECT role FROM league_members m WHERE m.league_id = l.id AND m.steam_id = ?2) AS my_role
      FROM league_events e JOIN leagues l ON l.id = e.league_id WHERE e.id IN (SELECT value FROM json_each(?1))`)
      .bind(JSON.stringify(ids), me ? me.steam_id : '').all();
    const hid = evs.filter((ev) => activeHide(ev, ev.league_kind, now)).map((ev) => ev.id);
    const who = me && hid.length ? await viewerOf(env, me.steam_id, hid) : { knows: new Set(), staff: new Set() };
    const routes = await routesRows(env);
    const seen = new Map();
    for (const ev of evs) {
      const role = me && me.steam_id === ev.league_owner ? 'owner' : ev.my_role || null;
      if (!canSee({ public: ev.league_public, kind: ev.league_kind }, role)) continue;          // (a private rally)
      if (ev.only_ids && !role && !(me && JSON.parse(ev.only_ids).includes(me.steam_id)) && ev.league_kind === RALLY) continue;
      const h = activeHide(ev, ev.league_kind, now);
      const v = viewHide(h, { knows: who.knows.has(ev.id), staff: who.staff.has(ev.id) });
      if (v && v.stages) continue;                       // (its stages kept from this driver: nobody on it shown)
      seen.set(ev.id, { ev, v, out: maskEvent(eventOut(ev, routes, now), h, v) });
    }
    const drivers = [];
    for (const d of await eventLive(env, [...seen.keys()], now)) {
      const s = seen.get(d.eventId);
      if (!s || d.state !== 'live') continue;
      const stage = s.out.stages[(d.stageNo || 1) - 1];
      if (!stage || !stage.track) continue;
      drivers.push({ kind: s.ev.league_kind, eventId: d.eventId, event: s.ev.name, league: s.ev.league_name,
        stageNo: d.stageNo, stage, car: s.out.car || null, cars: s.out.cars, rules: s.out.rules, rally: s.out.rally,
        steamId: d.steamId, name: d.name, country: d.country, look: d.look, progress: d.progress,
        totalMs: s.v && s.v.results ? null : d.totalMs });
    }
    return json({ now, drivers });
  }

  m = path.match(/^\/api\/events\/(\d+)(?:\/([a-z]+))?$/);
  if (m) {
    const ev = await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(+m[1]).first();
    if (!ev) return err('no such event', 404);
    const l = await leagueRow(env, ev.league_id);
    const role = await roleIn(env, l, me);
    const action = m[2] || '';
    // ?code=: a private rally's invite code shows its results to whoever has it, as it lets a driver in (the public API
    // and its embeds: src/publicapi.js; its maker puts its results on their own page)
    const codeOk = !post && l.kind === RALLY && !l.public && !!l.code && normCode(url.searchParams.get('code')) === l.code;
    if (!action && !post) return eventView(env, ev, l, role, me, now, codeOk);
    if (action === 'live' && !post) {                    // who is on its stages right now (a cup match followed live)
      if (!canSee(l, role) && !codeOk) return err('no such event', 404);   // (a private rally: with its code)
      const h = activeHide(ev, l.kind, now);
      const who = h && me ? await viewerOf(env, me.steam_id, [ev.id]) : null;
      const v = viewHide(h, { knows: !!who && who.knows.has(ev.id), staff: !!who && who.staff.has(ev.id) });
      // stages: what its live map draws (the event page's, a championship's page, the satellite map's), none while
      // it hides them from this viewer (who then sees who is on which stage, without the map: count, its number of
      // stages); privateMap: they see a map the others don't (the league's staff, a driver who pressed DRIVE);
      // timing: how often to ask again
      const all = JSON.parse(ev.stages), stages = liveStages(all, v);
      return json(await withTeams(env, { now, eventId: ev.id, hidden: h ? maskEvent({ stages: [] }, h, v).hidden : null,
        stages, count: all.length, privateMap: !!(h && h.stages && stages), timing: liveTiming(env),
        drivers: maskLive(await eventLive(env, [ev.id], now), v) }));
    }
    if (!post) return err('not found', 404);
    const no = need(); if (no) return no;
    return eventAction(env, ev, l, role, me, action, req, now);
  }
  return null;
}

// ------------------------------------------------------------------ a league

async function leagueOut(env, l, role, me, url, now) {
  // every championship can be opened, public or private (0043: a private one is asked to join, its page says how)
  const staff = isStaff(role);
  const [mem, evs, sea, bans, apps] = await env.DB.batch([
    env.DB.prepare(`SELECT m.steam_id, m.joined, m.role, m.division, m.team_invite, p.name, p.country, p.avatar FROM league_members m
      LEFT JOIN players p ON p.steam_id = m.steam_id WHERE m.league_id = ? ORDER BY m.joined`).bind(l.id),
    env.DB.prepare('SELECT * FROM league_events WHERE league_id = ? ORDER BY opens, id').bind(l.id),
    env.DB.prepare('SELECT * FROM league_seasons WHERE league_id = ? ORDER BY created, id').bind(l.id),
    env.DB.prepare(`SELECT b.steam_id, b.reason, b.created, p.name FROM league_bans b LEFT JOIN players p ON p.steam_id = b.steam_id
      WHERE b.league_id = ? ORDER BY b.created DESC`).bind(l.id),
    // its applications: the waiting ones for its staff, the viewer's own
    env.DB.prepare(`SELECT a.steam_id, a.message, a.status, a.created, a.decided, p.name, p.country, p.avatar FROM league_applications a
      LEFT JOIN players p ON p.steam_id = a.steam_id WHERE a.league_id = ? AND (a.status = 'pending' OR a.steam_id = ?) ORDER BY a.created`)
      .bind(l.id, me ? me.steam_id : ''),
  ]);
  const mineApp = me && apps.results.find((a) => a.steam_id === me.steam_id);
  const myBan = me && bans.results.find((x) => x.steam_id === me.steam_id);
  const routes = await routesRows(env);
  const res = await resultsOf(env, { leagueId: l.id });
  const divisions = divisionsOf(l);
  const td = await leagueTeamData(env, l, now);          // its teams (src/leagueteams.js), or null
  const events = evs.results.map((ev) => {
    const st = standingsOf(ev, res.get(ev.id) || EMPTY, now);
    const o = eventOut(ev, routes, now);
    const win = st.rows.find((r) => r.rank === 1);
    // a hidden event (src/hidden.js): its length and, its results hidden, its place in the championship wait for its end
    const h = activeHide(ev, l.kind, now), v = viewHide(h, { staff });
    maskEvent(o, h, v);
    return { id: ev.id, name: ev.name, seasonId: ev.season_id || null, rally: ev.rally, car: ev.car, carClass: o.carClass, carClasses: o.carClasses,
      stages: o.stages.length, days: o.days, lengthM: o.lengthM, opens: ev.opens, closes: ev.closes, status: o.status, hidden: o.hidden,
      // (its winner only once its results show: a hidden event's leader named while it ran was a spoiler, 21 Nov 2026)
      entries: st.rows.length, finished: st.rows.filter((r) => r.status === 'finished').length, winner: win && !(v && v.results) ? win.name : null,
      _st: st, _ev: ev, _blind: !!(v && v.results) };
  });
  const seasons = sea.results.map((s) => {
    const so = seasonOut(s);
    const mine = events.filter((e) => e.seasonId === s.id);
    so.about = describeSeason(so);
    so.events = mine.map((e) => e.id);
    const counted = (e) => (e._blind ? 'upcoming' : e.status);   // (a hidden event's results count once it is over)
    so.standings = seasonStandings(so, mine.map((e) => ({ id: e.id, status: counted(e), rows: e._st.rows, stages: e._st.stages })));
    // the championship within each class of its multi-class events and each division: [{kind, name, standings}]
    const classes = [...new Set(mine.flatMap((e) => (e.carClasses || [])))];
    const per = mine.map((e) => groupsOf(e._ev, res.get(e.id) || EMPTY, now, classes, divisions));
    so.groups = (per[0] || groupStandings({ stages: [] }, [], [], now, [], classes, divisions)).map((g, k) => ({ kind: g.kind, name: g.name,
      standings: seasonStandings(so, mine.map((e, i) => ({ id: e.id, status: counted(e), rows: per[i][k].rows, stages: per[i][k].stages }))) }));
    // its team championship (src/leagueteams.js, teamscore.js)
    Object.assign(so, seasonTeams(td, s, mine.map((e) => ({ id: e.id, status: counted(e), rows: e._st.rows, stages: e._st.stages,
      entries: (res.get(e.id) || EMPTY).entries })), so.standings));
    if (td) {
      tagRows(td, so.standings);
      for (const g of so.groups) tagRows(td, g.standings);
    }
    return so;
  });
  for (const e of events) { delete e._st; delete e._ev; delete e._blind; }
  const ownerName = (mem.results.find((x) => x.steam_id === l.owner) || {}).name || null;
  return json(await withTeams(env, {
    id: l.id, name: l.name, about: l.about, public: !!l.public, official: !!l.official, created: l.created, banner: bannerUrl(l.id, l.banner),
    // an official league (src/officialleagues.js): ACR Daily's own, run by no driver
    owner: l.official ? { steamId: null, name: OFFICIAL_OWNER.name } : { steamId: l.owner, name: ownerName },
    discord: role === 'owner' ? (l.discord ? { set: true, hint: l.discord.slice(-4) } : { set: false }) : undefined,
    // the drivers asking to join, for its owner and admins to accept or decline (0043)
    applications: staff ? apps.results.filter((a) => a.status === 'pending').map((a) => ({ steamId: a.steam_id, name: a.name || 'Driver',
      country: a.country || null, avatar: a.avatar || null, message: a.message || '', at: a.created })) : undefined,
    members: tagRows(td, mem.results.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver', country: x.country, avatar: x.avatar,
      joined: x.joined, role: x.steam_id === l.owner ? 'owner' : x.role === 'admin' ? 'admin' : 'member', division: x.division || null,
      teamId: td ? td.teamNow.get(x.steam_id) || null : null, teamInvite: td && td.settings.source === 'league' ? x.team_invite || null : null }))),
    divisions,
    // its teams: the settings, each team (its drivers now), and the ones I run (src/leagueteams.js)
    teams: td ? { ...td.settings, list: td.teams.map(({ runners, ...t }) => t),
      runs: me ? td.teams.filter((t) => t.runners.includes(me.steam_id)).map((t) => t.id) : [] } : null,
    bans: staff ? bans.results.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver', reason: x.reason, at: x.created })) : undefined,
    events, seasons,
    // application: mine (pending, or declined: `again` is when I can ask again); banned: kept out of it (its reason)
    me: { signedIn: !!me, member: !!role, owner: role === 'owner', role, staff,
      application: !role && mineApp ? { status: mineApp.status, message: mineApp.message || '', at: mineApp.created,
        again: mineApp.status === 'declined' ? (mineApp.decided || 0) + LIMITS.reapplyDays * DAY : null } : null,
      banned: !role && myBan ? { reason: myBan.reason || '' } : null },
  }));
}

async function leagueAction(env, l, role, me, action, req, now, site, fetchFn) {
  const owner = role === 'owner', staff = isStaff(role);
  if (action === 'banner') return owner ? setBanner(env, l, req, now) : err('only the league\'s owner can do that', 403);
  const b = await readBody(req) || {};
  if (action === 'join' || action === 'apply') {          // a public one: in now; a private one: asked (0043)
    if (role) return json({ id: l.id, joined: true });
    if (l.public) return addMember(env, l.id, me.steam_id, now);
    if (action === 'join') return err('this championship is private: ask to join it on its page', 403);
    return applyTo(env, l, me, b, now);
  }
  if (action === 'withdraw') {                            // my application taken back
    const r = await env.DB.prepare("DELETE FROM league_applications WHERE league_id = ? AND steam_id = ? AND status = 'pending'")
      .bind(l.id, me.steam_id).run();
    return r.meta.changes ? json({ withdrawn: true }) : err('no such application', 404);
  }
  if (action === 'leave') {
    if (owner) return err('the owner can\'t leave their league (delete it instead)', 409);
    await env.DB.prepare('DELETE FROM league_members WHERE league_id = ? AND steam_id = ?').bind(l.id, me.steam_id).run();
    return json({ left: true });
  }
  // its teams (src/leagueteams.js: each action says who may)
  const ta = await leagueTeamAction(env, l, role, me, action, b, now, { json, err, staff });
  if (ta) return ta;
  if (!staff) return err('only the league\'s owner and admins can do that', 403);

  // the applications (a private championship: 0043): accepted (in) or declined, the driver told; or a driver put in
  if (action === 'accept' || action === 'decline') return answerApplication(env, l, me, String(b.steamId || ''), action === 'accept', now);
  if (action === 'add') return addDriver(env, l, me, String(b.steamId || ''), now);
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
        .bind(l.id, sid, reason, me.steam_id, now), unapplyStmt(env, l.id, sid));
    }
    await env.DB.batch(stmts);
    return json({ removed: true, banned: !!b.ban });
  }
  if (action === 'unban') {
    await env.DB.prepare('DELETE FROM league_bans WHERE league_id = ? AND steam_id = ?').bind(l.id, String(b.steamId || '')).run();
    return json({ unbanned: true });
  }
  if (action === 'divisions') {                           // the league's divisions (e.g. PRO, AM); none: []
    const c = checkDivisions(b.divisions);
    if (c.error) return err(c.error);
    await env.DB.batch([
      env.DB.prepare('UPDATE leagues SET divisions = ? WHERE id = ?').bind(c.value.length ? JSON.stringify(c.value) : null, l.id),
      // a driver in a division no longer there: in none
      env.DB.prepare(`UPDATE league_members SET division = NULL WHERE league_id = ? AND division IS NOT NULL
        AND division NOT IN (SELECT value FROM json_each(?))`).bind(l.id, JSON.stringify(c.value)),
    ]);
    return json({ divisions: c.value });
  }
  if (action === 'division') {                            // a driver's division, or none (null)
    const d = b.division == null || b.division === '' ? null : String(b.division);
    if (d !== null && !divisionsOf(l).includes(d)) return err('not one of the league\'s divisions');
    const r = await env.DB.prepare('UPDATE league_members SET division = ? WHERE league_id = ? AND steam_id = ?')
      .bind(d, l.id, String(b.steamId || '')).run();
    return r.meta.changes ? json({ division: d }) : err('not a member of this league', 404);
  }
  if (action === 'seasons') {                             // a new season
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = ?').bind(l.id).first();
    if (n.n >= LIMITS.seasonsPerLeague) return err(`at most ${LIMITS.seasonsPerLeague} seasons in a league`, 409);
    const c = checkSeason(b);
    if (c.error) return err(c.error);
    const tc = seasonChampField(b);
    if (tc.error) return err(tc.error);
    const r = await env.DB.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created, team_champ)
      VALUES (?, ?, ?, ?, ?, ?, ?)`).bind(l.id, c.value.name, JSON.stringify(c.value.points), JSON.stringify(c.value.power),
      c.value.drop, now, tc.keep ? null : tc.value).run();
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
    const r = await env.DB.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, car_classes, rules,
      stages, opens, closes, created, hide) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(l.id, se.id, v.name, v.rally, v.car, v.car_class,
      v.car_classes ? JSON.stringify(v.car_classes) : null, JSON.stringify(v.rules), JSON.stringify(v.stages), v.opens, v.closes, now,
      v.hide ? JSON.stringify(v.hide) : null).run();
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
      env.DB.prepare(`DELETE FROM league_nominations WHERE ${inLeague}`).bind(l.id),
      env.DB.prepare('DELETE FROM league_team_penalties WHERE season_id IN (SELECT id FROM league_seasons WHERE league_id = ?)').bind(l.id),
      env.DB.prepare('DELETE FROM league_teams WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_events WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_seasons WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_members WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_bans WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_applications WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM league_banners WHERE league_id = ?').bind(l.id),
      env.DB.prepare('DELETE FROM leagues WHERE id = ?').bind(l.id),
    ]);
    return json({ deleted: true });
  }
  return err('not found', 404);
}

// ------------------------------------------------------------------ an event

async function eventView(env, ev, l, role, me, now, codeOk = false) {
  // a private rally without its code: what it races (it is listed, with a lock), not its results (0043); codeOk: its code
  // came with the request (?code=: what the public API takes), its results show (nothing else of a member's)
  const locked = lockedRally(l, role) && !codeOk;
  if (!canSee(l, role) && !locked && !codeOk) return err('no such event', 404);
  const o = eventOut(ev, await routesRows(env), now);
  const res = (await resultsOf(env, { eventId: ev.id })).get(ev.id) || EMPTY;
  const st = standingsOf(ev, res, now);
  const season = ev.season_id && await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(ev.season_id).first();
  // kind: league (a championship), event (a rally: its maker stewards it), or h2h / cup (a 1V1's or a cup's match: its
  // page is /1v1 or /cup/<id>, no stewards)
  o.league = { id: l.id, name: l.name, public: !!l.public, banner: bannerUrl(l.id, l.banner), kind: l.kind };
  if (l.kind === RALLY) {                                // a rally: who made it, its words, and for its maker its invite link
    const owner = await env.DB.prepare('SELECT name FROM players WHERE steam_id = ?').bind(l.owner).first();
    Object.assign(o.league, { owner: (owner || {}).name || 'Driver', ownerId: l.owner, about: l.about,
      code: role === 'owner' ? showCode(l.code) : undefined });
  }
  if (ev.only_ids) o.only = JSON.parse(ev.only_ids);
  o.season = season ? { id: season.id, name: season.name, ...seasonOut(season), about: describeSeason(seasonOut(season)) } : null;
  o.standings = st.rows;
  o.stageResults = st.stages;
  // the standings within each class (a multi-class event) and each of the league's divisions
  const divisions = divisionsOf(l);
  o.groups = groupsOf(ev, res, now, eventClasses(ev), divisions).map((g) => ({ kind: g.kind, name: g.name, standings: g.rows }));
  o.decisions = decisions(res, o.stages.length);
  const td = l.kind === 'league' ? await leagueTeamData(env, l, now) : null;
  const mine = me && st.rows.find((r) => r.steamId === me.steam_id);
  // a hidden event (src/hidden.js): its set-up and the results kept from whoever may not see them yet
  const h = activeHide(ev, l.kind, now);
  const who = h && me ? await viewerOf(env, me.steam_id, [ev.id]) : null;
  const v = viewHide(h, { knows: !!who && who.knows.has(ev.id), staff: !!who && who.staff.has(ev.id) });
  maskEvent(o, h, v);
  // when what it hides shows (the page says so: nothing told the drivers when, a UI review, Nov 2026): once it has
  // closed and its grace for late results is over; a cup's match when the cup is over (no time known: null)
  if (h) o.revealsAt = l.kind === 'cup' || l.kind === 'tcup' ? null : ev.closes + LIMITS.graceMs;   // (a team cup's too)
  // its teams: who drove for which, nominations and (a season with a team championship) the team points on it
  if (td) {
    const champ = champOf(season);
    let cells = new Map();
    if (champ && (champ.method === 'drivers' || champ.method === 'season')) {    // (the drivers' championship points on it)
      const so = seasonOut(season);
      const sd = seasonStandings(so, [{ id: ev.id, status: eventStatus(ev, now), rows: st.rows, stages: st.stages }]);
      cells = new Map(sd.map((d) => [d.steamId, d.cells[ev.id] || {}]));
    }
    o.teams = eventTeams(td, ev, season, st.rows, res.entries, cells, me ? me.steam_id : null, isStaff(role), !!(v && v.results), now);
    const teamOf = teamOfEntries(td, res.entries);
    o.teams.entryTeams = Object.fromEntries([...teamOf].filter(([, t]) => t != null));
    tagRows(td, o.standings, teamOf);
    for (const g of o.groups) tagRows(td, g.standings, teamOf);
  }
  // a team match (a team 1V1's, a team cup's: src/teammatch.js): its two teams, their lineups and result as it stands
  if (TEAM_KINDS.includes(l.kind)) {
    const info = await teamMatchInfo(env, ev, l.kind);
    if (info) {
      const lineup = (await lineupsOf(env, [ev.id])).get(ev.id) || new Map();
      o.match = { scoring: info.scoring, about: describeScoring(info.scoring), page: info.page,
        teams: matchOut(st.rows, [info.a, info.b], lineup, info.scoring, !!(v && v.results), await lineupNames(env, lineup)) };
    }
  }
  if (v && v.results) {
    const sid = me ? me.steam_id : null;
    o.standings = maskRows(o.standings, sid);
    o.stageResults = [];
    o.groups = o.groups.map((g) => ({ ...g, standings: maskRows(g.standings, sid) }));
  }
  const holder = !STEWARDED.has(l.kind);               // (a 1V1's or a cup's: no owner or stewards on its page)
  const division = divisions.length && role ? ((await env.DB.prepare('SELECT division FROM league_members WHERE league_id = ? AND steam_id = ?')
    .bind(l.id, me.steam_id).first()) || {}).division || null : null;
  // the drivers' comments on its stages (src/comments.js): all of them for whoever runs it (a championship's owner and
  // admins, a rally's or a cup's maker), else the viewer's own
  const readsAll = !!me && ((l.kind === 'league' && isStaff(role)) || ((l.kind === 'cup' || l.kind === RALLY) && me.steam_id === l.owner));
  o.comments = await eventComments(env, ev.id, readsAll, me ? me.steam_id : null);
  o.me = { signedIn: !!me, member: !!role && (!o.only || o.only.includes(me.steam_id)), owner: role === 'owner' && !holder, role,
    staff: isStaff(role) && !holder, entry: mine || null, division, readsComments: readsAll };
  // what it was set to hide, for those who can change it or copy it (its edit and copy forms start from it: a copy
  // came up with all three ticked whatever the event hid, and hid a rally whose maker wanted it all shown; Timo,
  // 21 Nov 2026). Its hidden note goes once it has closed; this stays.
  if (o.me.staff || (l.kind === RALLY && me && me.steam_id === l.owner)) {
    const hs = hideOf(ev) || {};
    o.hideSet = { weather: !!hs.weather, times: !!hs.times, stages: !!hs.stages };
  }
  if (locked) {                                          // (its code first: POST /api/events/<id>/join)
    Object.assign(o, { locked: true, drivers: st.rows.length, standings: [], stageResults: [], decisions: [], comments: [] });
    o.groups = o.groups.map((g) => ({ ...g, standings: [] }));
  }
  return json(await withTeams(env, o));
}

async function eventAction(env, ev, l, role, me, action, req, now) {
  const staff = isStaff(role);
  const b = await readBody(req) || {};
  const nStages = JSON.parse(ev.stages).length;
  // a head-to-head's or a cup's match: no stewards (its maker is one of its drivers); only its two drivers drive it
  if (!STEWARDED.has(l.kind) && ['edit', 'delete', 'penalty', 'dsq'].includes(action)) return err('a match has no stewards', 403);
  if (ev.only_ids && !JSON.parse(ev.only_ids).includes(me.steam_id)) {
    if (TEAM_KINDS.includes(l.kind)) return err('only the drivers in its teams\' lineups drive this match', 403);
    return err('this match is for its two drivers', 403);
  }
  const ta = await eventTeamAction(env, ev, l, me, action, b, now, { json, err, staff });   // its teams (src/leagueteams.js)
  if (ta) return ta;
  if (['edit', 'delete', 'penalty', 'dsq'].includes(action) && !staff) return err('only the league\'s owner and admins can do that', 403);
  if (action === 'delete') {
    await env.DB.batch([env.DB.prepare('DELETE FROM league_stage_times WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_entries WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_penalties WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_nominations WHERE event_id = ?').bind(ev.id),
      env.DB.prepare('DELETE FROM league_events WHERE id = ?').bind(ev.id),
      ...(l.kind === RALLY ? [env.DB.prepare('DELETE FROM league_members WHERE league_id = ?').bind(l.id),   // (a rally: its holder too)
        env.DB.prepare('DELETE FROM league_bans WHERE league_id = ?').bind(l.id),
        env.DB.prepare('DELETE FROM leagues WHERE id = ?').bind(l.id)] : [])]);
    return json({ deleted: true });
  }
  if (action === 'edit') {
    // a rally: no season; its words and who can join on its holder, whose name follows the event's (its invite page)
    // (written once the edit has passed its checks: a refused one changes nothing)
    const rallySync = async () => {
      if (l.kind !== RALLY) return;
      await env.DB.prepare('UPDATE leagues SET name = (SELECT name FROM league_events WHERE id = ?), about = ?, public = ? WHERE id = ?')
        .bind(ev.id, b.about == null ? l.about : text(b.about, LIMITS.about), b.public == null ? l.public : (b.public ? 1 : 0), l.id).run();
    };
    if (l.kind === RALLY) delete b.seasonId;
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
      // ... and what it hides may be shown now (never more hidden: some have driven it knowing less was), so a
      // maker who hid it by mistake can show it (Timo, 21 Nov 2026)
      let hide = hideOf(ev);
      if ('hide' in b && b.hide && typeof b.hide === 'object' && hide) {
        const keep = {};
        for (const k of ['weather', 'times', 'stages']) keep[k] = !!hide[k] && b.hide[k] !== false;
        hide = keep.weather || keep.times || keep.stages ? keep : null;
      }
      await env.DB.prepare('UPDATE league_events SET name = ?, closes = ?, season_id = ?, hide = ? WHERE id = ?')
        .bind(name, closes, seasonId, hide ? JSON.stringify(hide) : null, ev.id).run();
      await rallySync();
      return json({ ok: true, limited: true });
    }
    const c = checkEvent(b, catalog(await routesRows(env)), now);
    if (c.error) return err(c.error);
    const v = c.value;
    const hide = 'hide' in b ? v.hide : hideOf(ev);     // (left out of the form: as it was)
    await env.DB.prepare(`UPDATE league_events SET name = ?, rally = ?, car = ?, car_class = ?, car_classes = ?, rules = ?, stages = ?,
      opens = ?, closes = ?, season_id = ?, hide = ? WHERE id = ?`).bind(v.name, v.rally, v.car, v.car_class, v.car_classes ? JSON.stringify(v.car_classes) : null,
      JSON.stringify(v.rules), JSON.stringify(v.stages), v.opens, v.closes, seasonId, hide ? JSON.stringify(hide) : null, ev.id).run();
    await rallySync();
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

  if (action === 'join') {                                // a private rally's code (its password, 0043): its driver is in
    if (l.kind !== RALLY) return err('not found', 404);
    if (role || l.public) return json({ joined: true, eventId: ev.id });   // (a public one: joined by driving it)
    if (normCode(b.code) !== l.code) return err('wrong code', 403);
    const r = await addMember(env, l.id, me.steam_id, now);
    return r.ok ? json({ joined: true, eventId: ev.id }) : r;
  }
  const publicRally = !role && l.kind === RALLY && !!l.public;   // (every app lists it: joined by driving it)
  if (lockedRally(l, role)) return err('enter the rally\'s code first', 403);
  if (!role && !publicRally) return err('join the league first', 403);

  // the app: a driver's run through the event
  const v = appVersion(req);
  const min = env.LEAGUES_MIN_APP || '0.0.5';
  if (!v || older(v, min)) return err(`leagues need ACR Daily ${min} or newer`, 426);
  if (publicRally) {
    // a public rally is joined by starting it, from an app that may: nothing else makes anyone a member (a hidden one's
    // set-up, DRIVE's 'reveal', is given before it); a call that fails after this joins nobody
    // (joined at the entry's INSERT below, once the start has passed every check: a refused one joins nobody)
    if (action !== 'start' && action !== 'reveal') return err('join the league first', 403);
  }
  const entry = await env.DB.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, me.steam_id).first();
  if ((action === 'start' || action === 'begin' || action === 'reveal') && !canLegs(req) && needsLegs(JSON.parse(ev.stages))) {
    return err(`this rally has more days than the game takes at once (${LEG.days}): it is driven in legs, which needs a newer ACR Daily`, 426);
  }
  const hide = activeHide(ev, l.kind, now);
  if (hide && older(v, hiddenMinApp(env))) return err(`this event's details are hidden: it needs ACR Daily ${hiddenMinApp(env)} or newer`, 426);
  if (action === 'reveal') {                              // DRIVE on a hidden event: its set-up, to set the rally up (src/hidden.js)
    if (now < ev.opens) return err('the event is not open yet', 409);
    if (now >= ev.closes && !entry) return err('the event is closed', 409);
    await env.DB.prepare('INSERT OR IGNORE INTO event_reveals (event_id, steam_id, at) VALUES (?, ?, ?)').bind(ev.id, me.steam_id, now).run();
    const o = maskEvent(eventOut(ev, await routesRows(env), now), hide, null);
    o.kind = l.kind;
    return json(o);
  }
  // Each stage's first start counts, as a daily's: a stage started a second time without finishing it (the app
  // closed during it, then the stage driven again) ends the entry. The app (from 0.0.28) sends when the start was
  // (b.at, ms): that same start sent again (a retry after the server had it; two copies of the app open) is no second
  // start. Without it (an older app) every repeat is one.
  const at = Number.isFinite(+b.at) && +b.at > 0 ? Math.round(+b.at) : null;
  const same = (e) => at !== null && e.stage_at === at;
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
    if (entry && entry.status === 'running' && entry.done === 0 && entry.on_stage === 0) {
      return same(entry) ? json({ started: true, car: entry.car, status: 'running' }) : again(0);
    }
    if (entry) return json({ error: 'already started: the first start counts', entry: { status: entry.status, done: entry.done } }, 409);
    const car = carByName(b.car) || CARS.find((c) => c.id === b.car);
    if (!car || (ev.car ? car.name !== ev.car : !eventClasses(ev).includes(car.cls))) return err('not a car of this event', 422);
    if (l.kind === LIVE_KIND) {                          // a live rally: out of it for missing SS1's start too often
      const why = await liveRefused(env, ev, me.steam_id, b, now);
      if (why) return json({ status: 'dnf', reason: why });
    }
    if (publicRally) {                                   // a public rally: its driver joins it now, the start in order
      const r = await addMember(env, l.id, me.steam_id, now);
      if (!r.ok) return r;
    }
    // the entry, and the team its driver drives it for (a league with teams: src/leagueteams.js)
    await env.DB.batch([env.DB.prepare(`INSERT OR IGNORE INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated,
      app_version, stage_at) VALUES (?, ?, ?, 'running', 0, 0, 0, ?, ?, ?, ?)`).bind(ev.id, me.steam_id, car.name, now, now, v, at),
      ...entryTeamStmts(env, l, ev.id, me.steam_id, now)]);
    // a ranked rally (src/liverallies.js): the start kept on the driver's queue row (its turn judges it)
    const live = l.kind === LIVE_KIND ? { slot: await liveStarted(env, ev, me.steam_id, 0, b, now) } : {};
    return json({ started: true, car: car.name, status: 'running', ...live });
  }
  if (!entry) return err('not started', 409);
  if (action === 'live') {                                // where the driver is on the stage, every few seconds (followed live)
    const no2 = Math.round(+b.no), state = ['live', 'finished', 'dnf'].includes(b.state) ? b.state : 'live';
    if (!(no2 >= 0 && no2 < nStages)) return err('which stage?');
    if (entry.dsq || now > ev.closes + LIMITS.graceMs) return json({ shown: false });
    const n1 = (x) => (Number.isFinite(+x) && x !== null && x !== '' ? Math.round(+x * 10) / 10 : null);
    await env.DB.prepare(`INSERT INTO event_live (event_id, steam_id, stage_no, x, z, progress, total_ms, state, updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(event_id, steam_id) DO UPDATE SET stage_no = excluded.stage_no, x = excluded.x, z = excluded.z,
        progress = excluded.progress, total_ms = excluded.total_ms, state = excluded.state, updated = excluded.updated`)
      .bind(ev.id, me.steam_id, no2, n1(b.x), n1(b.z), Math.max(0, Math.min(1, +b.progress || 0)),
        Number.isFinite(+b.totalMs) && b.totalMs !== null ? Math.round(+b.totalMs) : null, state, now).run();
    return json({ shown: true });
  }
  if (entry.dsq && action !== 'dnf') return action === 'begin' ? json({ status: 'dsq', reason: entry.dsq })
    : err(`disqualified by the stewards: ${entry.dsq}`, 409);
  if (action === 'begin') {                               // a later stage started (or SS1 again)
    const no2 = Math.round(+b.no);
    // a live rally: a stage started in time whose start reached the server only after it had taken the driver out of
    // its queue (the DNF undone, src/liverallies.js)
    if (l.kind === LIVE_KIND && entry.status === 'dnf' && await liveRevived(env, ev, entry, no2, b, now)) entry.status = 'running';
    if (entry.status !== 'running') return json({ status: entry.status, reason: entry.reason || '' });
    if (no2 !== entry.done) return err(`expected SS${entry.done + 1}`, 409);
    if (entry.on_stage === no2) return same(entry) ? json({ status: 'running' }) : again(no2);
    await env.DB.prepare('UPDATE league_entries SET on_stage = ?, stage_at = ?, updated = ? WHERE event_id = ? AND steam_id = ?')
      .bind(no2, at, now, ev.id, me.steam_id).run();
    return json({ status: 'running', ...(l.kind === LIVE_KIND ? { slot: await liveStarted(env, ev, me.steam_id, no2, b, now) } : {}) });
  }
  if (action === 'stage') {
    const no2 = Math.round(+b.no);
    const timeMs = Math.round(+b.timeMs), penMs = Math.round(+b.penaltyMs);
    if (entry.status !== 'running') return err(`this entry is ${entry.status}`, 409);
    if (now > ev.closes + LIMITS.graceMs) return err('the event is closed', 409);
    if (no2 !== entry.done) return err(`expected SS${entry.done + 1}`, 409);
    // its start first (SS1: the entry's start; later ones: begin), as the app sends them: each stage's first start counts
    if (entry.on_stage !== no2) return err(`SS${no2 + 1} not started: its start comes first`, 409);
    if (!(timeMs > 0 && timeMs < 4 * 3600000) || !(penMs >= 0 && penMs < 3600000)) return err('no official result from the game');
    const st = JSON.parse(ev.stages)[no2];
    const route = st && await env.DB.prepare('SELECT length FROM routes WHERE track = ?').bind(st.track).first();
    if (route && impossiblyFast(timeMs, route.length)) return err('invalid: impossibly fast for the stage\'s length', 422);
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
  // a stage the game's rally shows driven while the app was not watching (from app 0.1.5): with the event's retirement
  // rule it counts as retired (its slowest time + the rule's minutes) and the entry goes on; without it, a DNF
  if (action === 'missed') {
    const no2 = Math.round(+b.no);
    if (entry.status !== 'running') return json({ status: entry.status, reason: entry.reason || '' });
    if (no2 !== entry.done) return err(`expected SS${entry.done + 1}`, 409);
    const reason = text(b.reason, 120) || `SS${no2 + 1} driven without ACR Daily watching`;
    if (!evSpec(ev).retireMs) {
      await env.DB.prepare('UPDATE league_entries SET status = \'dnf\', reason = ?, updated = ? WHERE event_id = ? AND steam_id = ?')
        .bind(reason, now, ev.id, me.steam_id).run();
      return json({ status: 'dnf', reason });
    }
    const done = entry.done + 1;
    const status = done >= nStages ? 'finished' : 'running';
    await env.DB.batch([
      env.DB.prepare(`INSERT OR IGNORE INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, created, retired)
        VALUES (?, ?, ?, 0, 0, ?, ?)`).bind(ev.id, me.steam_id, no2, now, reason),
      env.DB.prepare(`UPDATE league_entries SET done = ?, on_stage = NULL, status = ?, updated = ?, app_version = ?
        WHERE event_id = ? AND steam_id = ?`).bind(done, status, now, v, ev.id, me.steam_id),
    ]);
    return json({ done, status, retired: true });
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

// ------------------------------------------------------------------ holders: head-to-heads and cups (src/h2h.js, cups.js)
// A head-to-head's or a cup's matches are events of a hidden league of its own (kind h2h / cup): never listed, no
// stewards, its drivers its members, each match open to its two drivers only. So DRIVE, the stages, the timing and
// the standings are the leagues', in the website and the app.

/** A new holder: -> its id (`id` when given: a cup's own). A rally's (kind 'event'): public or private (its invite
 *  code), with its about. */
export async function makeHolder(env, { id = null, kind, name, owner, members = [], pub = true, about = '' }, now) {
  for (let tries = 0; tries < 5; tries++) {
    const hid = id || newLeagueId();
    const r = await env.DB.prepare(`INSERT OR IGNORE INTO leagues (id, name, about, owner, public, code, created, kind)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`).bind(hid, text(name, LIMITS.name), about, owner, pub ? 1 : 0, newCode(), now, kind).run();
    if (r.meta.changes) {
      if (members.length) await env.DB.batch(members.map((sid) => holderMemberStmt(env, hid, sid, now)));
      return hid;
    }
    if (id) break;
  }
  throw new Error('could not make a holder');
}

/** The statement making a driver a member of a holder (they can drive its matches that name them). */
export const holderMemberStmt = (env, holder, steamId, now) => env.DB.prepare(
  "INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, ?, 'member')").bind(holder, steamId, now);

/** A match: an event of a holder only `only` (the two drivers' steam ids) drive. spec: checkEvent's value (its
 *  stages, car, rules). -> the event's id. */
export async function makeMatchEvent(env, holder, spec, name, only, opens, closes, now) {
  const r = await env.DB.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, rules, stages,
    opens, closes, created, only_ids, hide) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).bind(holder, text(name, LIMITS.name),
    spec.rally, spec.car, spec.car_class, JSON.stringify(spec.rules), JSON.stringify(spec.stages), opens, closes, now,
    JSON.stringify(only), spec.hide ? JSON.stringify(spec.hide) : null).run();
  return r.meta.last_row_id;
}

/** Many matches of a holder at once (a cup's round), one statement for all, when `cond` (SQL with plain ? binds) holds:
 *  matches [{name, only}] (only: the two drivers' steam ids). A match is made once: its drivers have no event of this
 *  holder yet (two drivers meet once at most in a cup). */
export const matchEventsStmt = (env, holder, spec, matches, opens, closes, now, cond, binds) => env.DB.prepare(
  `INSERT INTO league_events (league_id, season_id, name, rally, car, car_class, rules, stages, opens, closes, created, hide, only_ids)
   SELECT ?, NULL, json_extract(j.value, '$.name'), ?, ?, ?, ?, ?, ?, ?, ?, ?, json_extract(j.value, '$.only') FROM json_each(?) j
   WHERE ${cond} AND NOT EXISTS (SELECT 1 FROM league_events e WHERE e.league_id = ? AND e.only_ids = json_extract(j.value, '$.only'))`)
  .bind(holder, spec.rally, spec.car, spec.car_class, JSON.stringify(spec.rules), JSON.stringify(spec.stages), opens, closes, now,
    spec.hide ? JSON.stringify(spec.hide) : null,
    JSON.stringify(matches.map((m) => ({ name: text(m.name, LIMITS.name), only: JSON.stringify(m.only) }))), ...binds, holder);

/** A match's standings rows (eventStandings: finished by total, then running, DNF, DSQ), as they stand now. */
export async function matchRows(env, eventId, now) {
  const ev = await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(eventId).first();
  if (!ev) return [];
  return standingsOf(ev, (await resultsOf(env, { eventId })).get(eventId) || EMPTY, now).rows;
}

/** matchRows for these events in one look (RANKED's results list: who won each, where I came): -> Map eventId -> rows. */
export async function eventsRows(env, ids, now) {
  if (!ids.length) return new Map();
  const [{ results: evs }, res] = await Promise.all([
    env.DB.prepare('SELECT * FROM league_events WHERE id IN (SELECT value FROM json_each(?))').bind(JSON.stringify(ids)).all(),
    resultsOf(env, { eventIds: ids }),
  ]);
  return new Map(evs.map((ev) => [ev.id, standingsOf(ev, res.get(ev.id) || EMPTY, now).rows]));
}

/** matchRows for a holder's matches in one look (a cup's whole bracket): -> Map eventId -> rows; ids: only these. */
export async function holderRows(env, holder, now, ids = null) {
  const want = ids && new Set(ids);
  const [{ results: evs }, res] = await Promise.all([
    env.DB.prepare('SELECT * FROM league_events WHERE league_id = ?').bind(holder).all(),
    resultsOf(env, { leagueId: holder }),
  ]);
  return new Map(evs.filter((ev) => !want || want.has(ev.id)).map((ev) => [ev.id, standingsOf(ev, res.get(ev.id) || EMPTY, now).rows]));
}

// a driver on an event's stage drops off 15 s after their last position; a finish or a DNF stays a minute
export const EVENT_LIVE = { staleMs: 15000, keepDoneMs: 60000 };

/** Who is on these events' stages right now: [{eventId, steamId, name, country, avatar, look, stageNo, x, z, progress,
 *  totalMs, state, updated}] (one query). */
export async function eventLive(env, ids, now) {
  if (!ids.length) return [];
  const { results } = await env.DB.prepare(`SELECT el.*, p.name, p.country, p.avatar, ${LOOK_COLS} FROM event_live el
      JOIN players p ON p.steam_id = el.steam_id ${lookJoin('el.steam_id')}
    WHERE el.event_id IN (SELECT value FROM json_each(?)) AND (el.updated > ? OR (el.state != 'live' AND el.updated > ?))
    ORDER BY el.event_id, el.stage_no DESC, el.progress DESC`)
    .bind(JSON.stringify(ids), now - EVENT_LIVE.staleMs, now - EVENT_LIVE.keepDoneMs).all();
  return results.map((r) => ({ eventId: r.event_id, steamId: r.steam_id, name: r.name, country: r.country || null, avatar: r.avatar || null,
    look: lookOfRow(r), stageNo: r.stage_no, x: r.x, z: r.z, progress: r.progress, totalMs: r.total_ms, state: r.state, updated: r.updated }));
}

/** eventLive's rows without what v (hidden.js viewHide) keeps: where they are on the stage (it would show the stage),
 *  their times. */
export function maskLive(rows, v) {
  if (!v) return rows;
  return rows.map((d) => ({ ...d, ...(v.stages ? { x: null, z: null } : {}), ...(v.results ? { totalMs: null, timesHidden: true } : {}) }));
}

/** An event's stages as its live map draws them (the route of each, the drivers on it; never the weather or the time
 *  of day, so a map is drawn whatever else it hides): [{no, track, name, rally}], or null while it hides its stages from
 *  this viewer (v: viewHide's for them, null when they see everything: the map would show them the stages). */
export function liveStages(stages, v) {
  if (v && v.stages) return null;
  return stages.map((s, k) => { const p = stageParts(s.track); return { no: k + 1, track: s.track, name: p.stageName, rally: p.rally }; });
}

/** The first app that asks for a hidden event's set-up on DRIVE (HIDDEN_MIN_APP in wrangler.toml). */
const hiddenMinApp = (env) => env.HIDDEN_MIN_APP || '0.0.25';

/** A rally's stages an event can use (the routes with the game's stage id): [{track, stageId, lengthM}] (a cup's draw). */
export async function rallyPool(env, rally) {
  return (await routesRows(env)).filter((r) => stageParts(r.track).rally === rally)
    .map((r) => ({ track: r.track, stageId: r.stage_id, lengthM: Math.round(r.length || 0) }));
}

/** An event as checkEvent makes it from a form, for a head-to-head or a cup (its window set later for a cup). */
export async function checkMatchSpec(env, b, now) {
  return checkEvent({ ...b, carClasses: undefined }, catalog(await routesRows(env)), now);   // (a match: one car or one class)
}

// ------------------------------------------------------------------ the leagues' Discord posts (cron, every 5 minutes)

/** Post what is due on the leagues' own Discord channels (leaguediscord.js duePosts): a few events a minute. A webhook
 *  Discord no longer knows (deleted in the channel) is forgotten; Discord busy or not reachable: the next minute again.
 *  -> [{event, post, status}] */
export async function leagueDiscordTick(env, now = Date.now(), fetchFn = fetch) {
  const { results: evs } = await env.DB.prepare(`SELECT e.*, l.name AS league_name, l.discord AS hook, l.teams AS league_teams FROM league_events e
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
        // a hidden event (src/hidden.js): the channel is everyone's, so it is told only what everyone may see
        const h = activeHide(ev, 'league', now), v = viewHide(h, {});
        const o = maskEvent(eventOut(ev, routes, now), h, v);
        const season = ev.season_id && await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(ev.season_id).first();
        o.season = season ? seasonOut(season) : null;
        let msg;
        if (due.post === 'open') msg = openMessage(o, lg, env.SITE_URL);
        else {
          const res = await resultsOf(env, due.post === 'results' && season ? { leagueId: ev.league_id } : { eventId: ev.id });
          const st = standingsOf(ev, res.get(ev.id) || EMPTY, now);
          if (due.post === '24h') msg = reminderMessage(o, lg, env.SITE_URL, v && v.results ? maskRows(st.rows, null) : st.rows);
          else {
            let table = null, teamTable = null;
            if (season) {
              const { results: sevs } = await env.DB.prepare('SELECT * FROM league_events WHERE season_id = ? ORDER BY opens, id').bind(season.id).all();
              const per = sevs.map((x) => {
                const s2 = standingsOf(x, res.get(x.id) || EMPTY, now);
                return { id: x.id, status: eventStatus(x, now), rows: s2.rows, stages: s2.stages, entries: (res.get(x.id) || EMPTY).entries };
              });
              table = seasonStandings(o.season, per);
              // its team championship (src/leagueteams.js)
              if (season.team_champ && ev.league_teams) {
                const td = await leagueTeamData(env, { id: ev.league_id, kind: 'league', teams: ev.league_teams }, now);
                teamTable = seasonTeams(td, season, per, table).teamStandings;
                tagRows(td, st.rows);
                tagRows(td, table);
              }
            }
            await withTeams(env, { rows: st.rows, stages: st.stages, table });   // (their tags, in place)
            msg = resultsMessage(o, lg, env.SITE_URL, st.rows, st.stages, o.season, table, teamTable);
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
