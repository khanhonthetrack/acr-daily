// Team cups (/tcups, /tcup/<id>): a knockout of team matches (src/teammatch.js) anyone can make. Its maker sets the
// size (4 to 64 teams), what every match races (as a league event), how a match is scored (src/teamscore.js), how many
// drivers a team signs up (its roster: rosterMin..rosterMax), who drives each match, when it starts and how long each
// round is open. Who drives:
//   open            any driver on the team's roster (the scoring says who counts: the best X, everyone...)
//   named, cup      the roster is the lineup: each team signs up exactly the lineup's size, for the whole cup
//   named, match    the team's captain or a manager names the lineup's size from its roster for each match, on the
//                   website, until each driver starts
// A team's captain or a manager signs it up with its roster (its own drivers; a driver is on one roster a cup), changes
// the roster or takes the team out until the start; a driver can take themselves off a roster. At the start, teams short
// of the roster's minimum are out, the others seeded by their team rating (the average rating of the roster's best
// drivers, as many as a match counts; src/rating.js, 1500 unrated; equal ones at random), the bracket the smallest that
// holds them (byes for the top seeds; fewer than two teams: called off). Each round's matches open together; a match is
// decided once it closes (and its grace is over): the scoring's winner goes through; nobody with a finisher, or a dead
// heat: the higher seed. No entry fee, no prizes, not rated. Opening or deciding a round takes the same few bulk
// statements whatever its size (the free plan allows 50 database queries a cron run). Hidden set-ups and results stay
// hidden until the cup is over, as a cup's (src/hidden.js).
//
//   GET  /api/tcups                         {open, running, finished, mine, team, limits}
//   GET  /api/tcups/<id>                    a team cup: its settings, teams and rosters, bracket
//   POST /api/tcups {name, about, size, event, scoring, lineupFor, rosterMin, rosterMax, starts, roundHours}
//   POST /api/tcups/<id>/join {steamIds}    my team in, with its roster (its captain or a manager)
//   POST /api/tcups/<id>/roster {steamIds}  my team's roster changed (before the start)
//   POST /api/tcups/<id>/leave              my team out (before the start)
//   POST /api/tcups/<id>/withdraw           me off my team's roster (before the start)
//   POST /api/tcups/<id>/cancel             its maker, before the start
//   POST /api/tcups/<id>/lineup {eventId, steamIds}   my team's lineup for its match (named, per match)

import { stageParts } from './conditions.js';
import { clash } from './credits.js';
import { runsTeam, teamRoleOf } from './drivers.js';
import { bannerUrl, LIMITS, newLeagueId, text } from './leagues.js';
import { checkMatchSpec, holderRows, makeHolder, matchEventsStmt } from './leaguesapi.js';
import { firstRound, places, roundCloses, roundName, seedOrderOf, utcWhen } from './cups.js';
import { RATING } from './rating.js';
import { maskStage, viewHide } from './hidden.js';
import { checkScoring, describeScoring, matchDrivers, TEAMSCORE } from './teamscore.js';
import { decideMatch, lineupsOf, matchOut, matchReminders, nameLineup, runnersOf, teamOf } from './teammatch.js';
import { noticesStmt } from './social.js';

export const TCUP = { sizes: [4, 8, 16, 32, 64], roundHours: [24, 48, 72, 96, 168], perOwner: 3, startWithinDays: 30, roster: [1, 20] };
const REF = (id) => `tcup:${id}`;
const PER_RUN = { start: 2, running: 2 };
const label = (t) => (t ? (t.tag ? `[${t.tag}] ${t.name}` : t.name) : 'a team');

/** A team cup's hide flags while it is under way (src/hidden.js), or null. */
const tcupHide = (c) => {
  const h = c.status === 'finished' || c.status === 'cancelled' ? null : JSON.parse(c.spec).hide || null;
  return h && (h.weather || h.times || h.stages) ? h : null;
};

/** A team cup from its form: -> {value: {name, about, size, hours, starts, spec (with scoring and lineupFor), rosterMin,
 *  rosterMax}} or {error}. (The event's window is set by each round.) */
export async function checkTeamCup(env, b, now) {
  const name = text(b.name, LIMITS.name);
  if (name.length < 3) return { error: 'give the cup a name (3 to 60 characters)' };
  const size = Number(b.size), hours = Number(b.roundHours);
  if (!TCUP.sizes.includes(size)) return { error: `the size: ${TCUP.sizes.join(', ')} teams` };
  if (!TCUP.roundHours.includes(hours)) return { error: `each round is open ${TCUP.roundHours.join(', ')} hours` };
  const starts = Math.round(+b.starts);
  if (!(starts >= now + 3600000 && starts <= now + TCUP.startWithinDays * 86400000)) {
    return { error: `the cup starts from an hour to ${TCUP.startWithinDays} days from now` };
  }
  const sc = checkScoring(b.scoring);
  if (sc.error) return sc;
  const s = sc.value;
  const lineupFor = s.lineup === 'named' ? (b.lineupFor === 'cup' ? 'cup' : 'match') : null;
  const num = (v, d) => (v == null || v === '' ? d : Number(v));
  let rosterMin = num(b.rosterMin, Math.max(1, matchDrivers(s))), rosterMax = num(b.rosterMax, Math.max(rosterMin, 6));
  if (lineupFor === 'cup') rosterMin = rosterMax = s.size;           // (the roster is the lineup)
  if (![rosterMin, rosterMax].every((x) => Number.isInteger(x) && x >= TCUP.roster[0] && x <= TCUP.roster[1]) || rosterMin > rosterMax) {
    return { error: `a team's roster: ${TCUP.roster[0]} to ${TCUP.roster[1]} drivers, the least first` };
  }
  if (lineupFor === 'match' && rosterMin < s.size) return { error: `a roster of at least ${s.size}: each match names ${s.size} from it` };
  const c = await checkMatchSpec(env, { ...(b.event || {}), name, opens: now, closes: now + 2 * 3600000 }, now);
  if (c.error) return c;
  const { opens, closes, ...spec } = c.value;
  return { value: { name, about: text(b.about, LIMITS.about), size, hours, starts, rosterMin, rosterMax,
    spec: { ...spec, scoring: s, ...(lineupFor ? { lineupFor } : {}) } } };
}

const LIST = `SELECT c.*, p.name AS owner_name, h.banner, (SELECT COUNT(*) FROM team_cup_entries e WHERE e.cup_id = c.id) AS teams
  FROM team_cups c LEFT JOIN players p ON p.steam_id = c.owner LEFT JOIN leagues h ON h.id = c.id`;

const cupOut = (c, v = viewHide(tcupHide(c), {})) => {
  const spec = JSON.parse(c.spec), h = tcupHide(c);
  return { id: c.id, name: c.name, about: c.about, official: !!c.official,
    owner: c.official ? { steamId: null, name: 'ACR Daily' } : { steamId: c.owner, name: c.owner_name || 'a driver' },
    size: c.size, starts: c.starts, roundHours: c.round_hours, status: c.status, round: c.round, teams: c.teams || 0,
    banner: bannerUrl(c.id, c.banner), rally: spec.rally, car: spec.car, carClass: spec.car_class, rules: spec.rules,
    scoring: spec.scoring, scoringAbout: describeScoring(spec.scoring), lineupFor: spec.lineupFor || null,
    rosterMin: c.roster_min, rosterMax: c.roster_max,
    stages: spec.stages.map((s) => maskStage({ name: stageParts(s.track).stageName, day: s.day, weather: s.weather, time: s.time }, v)),
    hidden: h ? { weather: !!h.weather, times: !!h.times, stages: !!h.stages } : null, revealed: !v || !(v.weather || v.time || v.stages) };
};

/** A team's rating in a cup: the average of its roster's best `n` drivers' ratings (unrated: RATING.start). */
export function teamRating(ratings, n) {
  const r = ratings.map((x) => (x == null ? RATING.start : x)).sort((a, b) => b - a).slice(0, Math.max(1, n));
  return r.length ? Math.round(r.reduce((a, x) => a + x, 0) / r.length) : RATING.start;
}

/** A roster from a form: ids of `pool` (my team's drivers), between the cup's limits. -> {value} or {error}. */
function checkRoster(c, ids, pool) {
  ids = [...new Set((Array.isArray(ids) ? ids : []).map(String))];
  if (ids.length < c.roster_min || ids.length > c.roster_max) {
    return { error: c.roster_min === c.roster_max ? `a roster of ${c.roster_min} drivers` : `a roster of ${c.roster_min} to ${c.roster_max} drivers` };
  }
  if (ids.some((x) => !pool.includes(x))) return { error: 'only your team\'s drivers can be on its roster' };
  return { value: ids };
}

export async function tcupsApi(req, env, path, me, sameOrigin, now, { json, err }) {
  if (!path.startsWith('/api/tcups')) return null;
  const post = req.method === 'POST';
  const my = me ? await teamRoleOf(env, me.steam_id) : null;
  if (path === '/api/tcups' && !post) {
    const [op, ru, fi] = await env.DB.batch([
      env.DB.prepare(`${LIST} WHERE c.status = 'open' ORDER BY c.official DESC, c.starts LIMIT 100`),
      env.DB.prepare(`${LIST} WHERE c.status = 'running' ORDER BY c.official DESC, c.starts LIMIT 100`),
      env.DB.prepare(`${LIST} WHERE c.status = 'finished' ORDER BY c.settled DESC LIMIT 20`),
    ]);
    const mine = my ? (await env.DB.prepare('SELECT cup_id FROM team_cup_entries WHERE team_id = ?').bind(my.teamId).all()).results.map((r) => r.cup_id) : [];
    return json({ open: op.results.map((c) => cupOut(c)), running: ru.results.map((c) => cupOut(c)), finished: fi.results.map((c) => cupOut(c)),
      mine, team: my ? { id: my.teamId, name: my.name, tag: my.tag, role: my.role, runs: runsTeam(my.role) } : null,
      limits: { sizes: TCUP.sizes, roundHours: TCUP.roundHours, roster: TCUP.roster, maxSize: TEAMSCORE.size[1] } });
  }
  let m = path.match(/^\/api\/tcups\/([a-z0-9]{8})$/);
  if (m && !post) return cupView(env, m[1], me, my, now, { json, err });
  if (!post) return err('not found', 404);
  if (!me) return err('sign in with Steam first', 401);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (me.banned) return err('this account is banned', 403);
  const b = await req.json().catch(() => ({})) || {};

  if (path === '/api/tcups') {                            // a new team cup
    const c = await checkTeamCup(env, b, now);
    if (c.error) return err(c.error);
    const v = c.value;
    const mine = await env.DB.prepare("SELECT COUNT(*) AS n FROM team_cups WHERE owner = ? AND status IN ('open', 'running')").bind(me.steam_id).first();
    if (mine.n >= TCUP.perOwner) return err(`you run ${TCUP.perOwner} team cups already`, 409);
    for (let tries = 0; tries < 5; tries++) {
      const id = newLeagueId();
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO team_cups (id, name, about, owner, size, spec, roster_min, roster_max, starts,
        round_hours, status, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)`).bind(id, v.name, v.about, me.steam_id, v.size,
        JSON.stringify(v.spec), v.rosterMin, v.rosterMax, v.starts, v.hours, now).run();
      if (r.meta.changes) {
        try {
          await makeHolder(env, { id, kind: 'tcup', name: v.name, owner: me.steam_id }, now);
        } catch (e) {                                   // (its id taken by a league: another id)
          await env.DB.prepare('DELETE FROM team_cups WHERE id = ?').bind(id).run();
          continue;
        }
        return json({ id });
      }
    }
    return err('try again', 503);
  }

  m = path.match(/^\/api\/tcups\/([a-z0-9]{8})\/(join|roster|leave|withdraw|cancel|lineup)$/);
  if (!m) return err('not found', 404);
  const c = await env.DB.prepare('SELECT * FROM team_cups WHERE id = ?').bind(m[1]).first();
  if (!c) return err('no such team cup', 404);
  const spec = JSON.parse(c.spec);
  if (m[2] === 'lineup') return cupLineup(env, c, spec, my, me, b, now, { json, err });
  if (c.status !== 'open' || now >= c.starts) return err('the cup has started: no more changes to who is in it', 409);
  const open = "(SELECT status FROM team_cups WHERE id = ?) = 'open'";
  if (m[2] === 'cancel') {
    if (c.owner !== me.steam_id) return err('only the cup\'s maker calls it off', 403);
    return json(await callOff(env, c, now, `${c.name} was called off by its maker.`));
  }
  if (m[2] === 'withdraw') {                              // me off my team's roster
    const r = await env.DB.prepare(`DELETE FROM team_cup_roster WHERE cup_id = ? AND steam_id = ? AND ${open}`).bind(c.id, me.steam_id, c.id).run();
    return r.meta.changes ? json({ withdrawn: true }) : err('you are on no roster in this cup', 409);
  }
  if (!my) return err('you are in no team: join or make one on /teams', 403);
  if (!runsTeam(my.role)) return err('only the team\'s captain and managers sign it up', 403);
  const entered = await env.DB.prepare('SELECT 1 AS x FROM team_cup_entries WHERE cup_id = ? AND team_id = ?').bind(c.id, my.teamId).first();
  if (m[2] === 'leave') {
    if (!entered) return err('your team is not in this cup', 409);
    await env.DB.batch([
      env.DB.prepare(`DELETE FROM team_cup_roster WHERE cup_id = ? AND team_id = ? AND ${open}`).bind(c.id, my.teamId, c.id),
      env.DB.prepare(`DELETE FROM team_cup_entries WHERE cup_id = ? AND team_id = ? AND ${open}`).bind(c.id, my.teamId, c.id),
    ]);
    return json({ entered: false });
  }
  const pool = (await env.DB.prepare('SELECT steam_id FROM team_members WHERE team_id = ?').bind(my.teamId).all()).results.map((x) => x.steam_id);
  const ro = checkRoster(c, b.steamIds, pool);
  if (ro.error) return err(ro.error);
  const taken = (await env.DB.prepare(`SELECT steam_id FROM team_cup_roster WHERE cup_id = ? AND team_id != ? AND steam_id IN
    (SELECT value FROM json_each(?))`).bind(c.id, my.teamId, JSON.stringify(ro.value)).all()).results;
  if (taken.length) return err('a driver can be on one team\'s roster a cup: one of them is on another\'s', 409);
  const ids = JSON.stringify(ro.value);
  if (m[2] === 'join') {
    if (entered) return err('your team is in already: change its roster instead', 409);
    const joined = 'EXISTS (SELECT 1 FROM team_cup_entries WHERE cup_id = ? AND team_id = ? AND joined = ?)';
    await env.DB.batch([
      env.DB.prepare(`INSERT OR IGNORE INTO team_cup_entries (cup_id, team_id, by, joined) SELECT ?1, ?2, ?3, ?4
        WHERE (SELECT COUNT(*) FROM team_cup_entries WHERE cup_id = ?1) < ?5 AND (SELECT status FROM team_cups WHERE id = ?1) = 'open'`)
        .bind(c.id, my.teamId, me.steam_id, now, c.size),
      env.DB.prepare(`INSERT OR IGNORE INTO team_cup_roster (cup_id, team_id, steam_id, joined) SELECT ?, ?, value, ? FROM json_each(?)
        WHERE ${joined}`).bind(c.id, my.teamId, now, ids, c.id, my.teamId, now),
      env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT value, NULL, 'cup', ?, ?, ? FROM json_each(?)
        WHERE value != ? AND ${joined}`).bind(`${my.name} signed you up for the team cup ${c.name} (it starts ${utcWhen(c.starts)}).`,
        REF(c.id), now, ids, me.steam_id, c.id, my.teamId, now),
    ]);
    if (!await env.DB.prepare('SELECT 1 AS x FROM team_cup_entries WHERE cup_id = ? AND team_id = ?').bind(c.id, my.teamId).first()) {
      return err('the cup is full', 409);
    }
    return json({ entered: true, roster: ro.value });
  }
  if (!entered) return err('your team is not in this cup', 409);
  await env.DB.batch([                                    // roster: changed
    env.DB.prepare(`DELETE FROM team_cup_roster WHERE cup_id = ? AND team_id = ? AND steam_id NOT IN (SELECT value FROM json_each(?)) AND ${open}`)
      .bind(c.id, my.teamId, ids, c.id),
    env.DB.prepare(`INSERT OR IGNORE INTO team_cup_roster (cup_id, team_id, steam_id, joined) SELECT ?, ?, value, ? FROM json_each(?) WHERE ${open}`)
      .bind(c.id, my.teamId, now, ids, c.id),
  ]);
  return json({ roster: ro.value });
}

/** A team cup's page: its settings, teams (seed, place, rating, roster), bracket (each match's teams, lineups and result
 *  as it stands: hidden results stay so until the cup is over) and what I can do. */
async function cupView(env, id, me, my, now, { json, err }) {
  const c = await env.DB.prepare(`${LIST} WHERE c.id = ?`).bind(id).first();
  if (!c) return err('no such team cup', 404);
  const spec = JSON.parse(c.spec);
  const [en, ro, ma] = await env.DB.batch([
    env.DB.prepare(`SELECT e.*, t.name, t.tag, t.color, t.tag_fmt FROM team_cup_entries e LEFT JOIN teams t ON t.id = e.team_id
      WHERE e.cup_id = ? ORDER BY COALESCE(e.seed, 999), e.joined`).bind(c.id),
    env.DB.prepare(`SELECT r.team_id, r.steam_id, p.name, p.country, rt.rating FROM team_cup_roster r LEFT JOIN players p ON p.steam_id = r.steam_id
      LEFT JOIN ratings rt ON rt.steam_id = r.steam_id WHERE r.cup_id = ? ORDER BY rt.rating DESC, p.name`).bind(c.id),
    env.DB.prepare(`SELECT m.*, e.closes FROM team_cup_matches m LEFT JOIN league_events e ON e.id = m.event_id
      WHERE m.cup_id = ? ORDER BY m.round, m.slot`).bind(c.id),
  ]);
  const n = matchDrivers(spec.scoring);
  const teams = en.results.map((e) => {
    const roster = ro.results.filter((r) => r.team_id === e.team_id);
    return { ...(teamOf(e) || {}), id: e.team_id, seed: e.seed, place: e.place, joined: e.joined,
      rating: teamRating(roster.map((r) => r.rating), n),
      roster: roster.map((r) => ({ steamId: r.steam_id, name: r.name || 'Driver', country: r.country || null,
        rating: r.rating == null ? null : Math.round(r.rating) })) };
  });
  const byId = new Map(teams.map((t) => [t.id, t]));
  const rosterNames = new Map(ro.results.map((r) => [r.steam_id, r.name || 'Driver']));
  const rounds = ma.results.length ? Math.log2(2 * ma.results.filter((x) => x.round === 1).length) : 0;
  const h = tcupHide(c);
  const knows = !!h && !!me && (c.owner === me.steam_id || !!await env.DB.prepare(`SELECT 1 AS x FROM league_events e WHERE e.league_id = ?1
    AND (EXISTS (SELECT 1 FROM league_entries x WHERE x.event_id = e.id AND x.steam_id = ?2)
      OR EXISTS (SELECT 1 FROM event_reveals r WHERE r.event_id = e.id AND r.steam_id = ?2)) LIMIT 1`).bind(c.id, me.steam_id).first());
  const v = viewHide(h, { knows });
  const evIds = ma.results.filter((x) => x.event_id).map((x) => x.event_id);
  const [rows, lineups] = evIds.length ? await Promise.all([holderRows(env, c.id, now, evIds), lineupsOf(env, evIds)]) : [new Map(), new Map()];
  const side = (tid) => (tid ? (({ roster, ...t }) => t)(byId.get(tid) || { id: tid, name: 'a team' }) : null);
  const myTeam = my && byId.get(my.teamId);
  return json({ ...cupOut(c, v), rounds, teams,
    matches: ma.results.map((x) => ({ id: x.id, round: x.round, slot: x.slot, name: roundName(x.round, rounds || 1), eventId: x.event_id,
      closes: x.closes || null, a: side(x.a), b: side(x.b), winner: x.winner, note: x.note,
      teams: x.event_id && x.a && x.b ? matchOut(rows.get(x.event_id) || [], [side(x.a), side(x.b)], lineups.get(x.event_id) || new Map(),
        spec.scoring, !!(v && v.results), rosterNames) : null })),
    me: me ? { signedIn: true, owner: c.owner === me.steam_id,
      team: my ? { id: my.teamId, name: my.name, tag: my.tag, role: my.role, runs: runsTeam(my.role), entered: !!myTeam,
        drivers: my && runsTeam(my.role) ? (await env.DB.prepare(`SELECT m.steam_id, p.name FROM team_members m LEFT JOIN players p
          ON p.steam_id = m.steam_id WHERE m.team_id = ? ORDER BY p.name`).bind(my.teamId).all()).results.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver' })) : null } : null,
      onRoster: teams.some((t) => t.roster.some((r) => r.steamId === me.steam_id)) } : { signedIn: false } });
}

/** POST /api/tcups/<id>/lineup {eventId, steamIds}: my team's drivers for its match (named lineups, per match). */
async function cupLineup(env, c, spec, my, me, b, now, { json, err }) {
  if (c.status !== 'running') return err('lineups are named once the cup is under way', 409);
  if (!(spec.scoring.lineup === 'named' && spec.lineupFor === 'match')) return err('this cup\'s lineups are its rosters', 409);
  if (!my || !runsTeam(my.role)) return err('only the team\'s captain and managers name its lineup', 403);
  const mt = await env.DB.prepare(`SELECT m.*, e.closes, e.opens FROM team_cup_matches m JOIN league_events e ON e.id = m.event_id
    WHERE m.cup_id = ? AND m.event_id = ? AND (m.a = ? OR m.b = ?)`).bind(c.id, Math.round(+b.eventId) || 0, my.teamId, my.teamId).first();
  if (!mt) return err('no match of your team', 404);
  if (mt.winner) return err('the match is decided', 409);
  const [pool, lineup] = await Promise.all([
    env.DB.prepare('SELECT steam_id FROM team_cup_roster WHERE cup_id = ? AND team_id = ?').bind(c.id, my.teamId).all(),
    lineupsOf(env, [mt.event_id]),
  ]);
  const before = (lineup.get(mt.event_id) || new Map()).get(my.teamId) || [];
  const other = (lineup.get(mt.event_id) || new Map()).get(mt.a === my.teamId ? mt.b : mt.a) || [];
  const r = await nameLineup(env, { id: mt.event_id, closes: mt.closes }, c.id, my.teamId, b.steamIds, me.steam_id, now,
    { size: spec.scoring.size, pool: pool.results.map((x) => x.steam_id), other });
  if (r.error) return err(r.error, r.status || 400);
  const added = r.value.filter((x) => !before.includes(x));
  if (added.length) {
    await env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT value, NULL, 'cup', ?, ?, ? FROM json_each(?)`)
      .bind(`${c.name}: you drive ${my.name}'s match. Drive it in the ACR Daily app, under CUPS, by ${utcWhen(mt.closes)}.`, REF(c.id), now,
        JSON.stringify(added)).run();
  }
  return json({ lineup: r.value });
}

/** A team cup called off: its teams told (their rosters' drivers). */
async function callOff(env, c, now, why) {
  const off = ["EXISTS (SELECT 1 FROM team_cups WHERE id = ? AND status = 'cancelled' AND settled = ?)", [c.id, now]];
  await env.DB.batch([
    env.DB.prepare("UPDATE team_cups SET status = 'cancelled', settled = ? WHERE id = ? AND status = 'open'").bind(now, c.id),
    env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT DISTINCT steam_id, NULL, 'cup', ?, ?, ?
      FROM team_cup_roster WHERE cup_id = ? AND ${off[0]}`).bind(why, REF(c.id), now, c.id, ...off[1]),
  ]);
  return { cancelled: true };
}

// ------------------------------------------------------------------ the cron

/** The notices of a round to its teams' rosters (and, a lineup named per match, to their captains and managers):
 *  notes [{team, body}], when cond holds. */
function rosterNotices(env, c, notes, runners, now, cond, binds) {
  const j = JSON.stringify(notes.map((n) => ({ team: n.team, body: String(n.body).slice(0, 300) })));
  return [
    env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT r.steam_id, NULL, 'cup', json_extract(j.value, '$.body'), ?, ?
      FROM json_each(?) j JOIN team_cup_roster r ON r.cup_id = ? AND r.team_id = json_extract(j.value, '$.team') WHERE ${cond}`)
      .bind(REF(c.id), now, j, c.id, ...binds),
    ...(runners ? [env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT m.steam_id, NULL, 'cup', json_extract(j.value, '$.body'), ?, ?
      FROM json_each(?) j JOIN team_members m ON m.team_id = json_extract(j.value, '$.team') JOIN teams t ON t.id = m.team_id
      WHERE (m.steam_id = t.captain OR m.role = 'manager') AND NOT EXISTS (SELECT 1 FROM team_cup_roster r WHERE r.cup_id = ? AND r.steam_id = m.steam_id)
        AND ${cond}`).bind(REF(c.id), now, j, c.id, ...binds)] : []),
  ];
}

/** The statements opening a round (the same for 2 teams or 64), for the batch with the cup's change to that round
 *  (cond with binds: it went in): its matches (byes decided at once), each other match an event (only_ids its two teams'
 *  ids, to find it), its lineups (open, or the cup's rosters: the rosters; per match: none yet) and only_ids their
 *  drivers, the notices. */
function roundStmts(env, c, spec, round, rounds, pairs, names, now, opensAt, cond, binds) {
  const rn = roundName(round, rounds), name = (id) => names.get(id) || 'a team';
  const games = pairs.filter((p) => p.a && p.b), byes = pairs.filter((p) => !(p.a && p.b) && (p.a || p.b));
  const closes = roundCloses(c, round, now), perMatch = spec.scoring.lineup === 'named' && spec.lineupFor === 'match';
  const bye = (p) => !(p.a && p.b);
  const drive = perMatch ? `Your captain or a manager names its ${spec.scoring.size} driver${spec.scoring.size > 1 ? 's' : ''} on the website; they drive it`
    : 'Drive it';
  return [
    env.DB.prepare(`INSERT OR IGNORE INTO team_cup_matches (cup_id, round, slot, a, b, winner, note)
      SELECT ?, ?, json_extract(j.value, '$.slot'), json_extract(j.value, '$.a'), json_extract(j.value, '$.b'),
        json_extract(j.value, '$.w'), json_extract(j.value, '$.note') FROM json_each(?) j WHERE ${cond}`)
      .bind(c.id, round, JSON.stringify(pairs.map((p) => ({ slot: p.slot, a: p.a, b: p.b, w: bye(p) ? p.a || p.b : null,
        note: bye(p) ? 'a bye' : null }))), ...binds),
    matchEventsStmt(env, c.id, spec, games.map((p) => ({ name: `${rn}: ${name(p.a)} vs ${name(p.b)}`, only: [p.a, p.b] })), opensAt, closes, now, cond, binds),
    env.DB.prepare(`UPDATE team_cup_matches SET event_id = (SELECT e.id FROM league_events e WHERE e.league_id = team_cup_matches.cup_id
        AND e.only_ids = json_array(team_cup_matches.a, team_cup_matches.b))
      WHERE cup_id = ? AND round = ? AND event_id IS NULL AND a IS NOT NULL AND b IS NOT NULL`).bind(c.id, round),
    ...(perMatch ? [] : [env.DB.prepare(`INSERT OR IGNORE INTO team_lineups (event_id, team_id, steam_id, by, at)
      SELECT m.event_id, r.team_id, r.steam_id, NULL, ? FROM team_cup_matches m JOIN team_cup_roster r ON r.cup_id = m.cup_id AND r.team_id IN (m.a, m.b)
      WHERE m.cup_id = ? AND m.round = ? AND m.event_id IS NOT NULL`).bind(now, c.id, round)]),
    env.DB.prepare(`UPDATE league_events SET only_ids = (SELECT COALESCE(json_group_array(l.steam_id), '[]') FROM team_lineups l
      WHERE l.event_id = league_events.id) WHERE id IN (SELECT event_id FROM team_cup_matches WHERE cup_id = ? AND round = ? AND event_id IS NOT NULL)`)
      .bind(c.id, round),
    ...rosterNotices(env, c, [
      ...byes.map((p) => ({ team: p.a || p.b, body: `${c.name}: a bye in ${rn.toLowerCase()}, your team goes through.` })),
      ...games.flatMap((p) => [[p.a, p.b], [p.b, p.a]].map(([x, y]) => ({ team: x,
        body: `${c.name}, ${rn.toLowerCase()}: ${name(x)} against ${name(y)}. ${drive} in the ACR Daily app, under CUPS, by ${utcWhen(closes)}.` }))),
    ], perMatch, now, cond, binds),
  ];
}

/** The cron's part: team cups due to start start (or are called off), finished rounds are decided and the next opened, a
 *  decided final places the teams. opensAt: when the matches it opens open (the cron: now). -> [{cup, did}] */
export async function tcupsTick(env, now, opensAt = now) {
  const out = [];
  const { results: starting } = await env.DB.prepare("SELECT * FROM team_cups WHERE status = 'open' AND starts <= ? ORDER BY starts LIMIT ?")
    .bind(now, PER_RUN.start).all();
  for (const c of starting) {
    const spec = JSON.parse(c.spec);
    const [{ results: en }, { results: ro }] = await env.DB.batch([
      env.DB.prepare(`SELECT e.team_id, t.name, t.tag FROM team_cup_entries e LEFT JOIN teams t ON t.id = e.team_id WHERE e.cup_id = ?`).bind(c.id),
      env.DB.prepare(`SELECT r.team_id, r.steam_id, rt.rating FROM team_cup_roster r LEFT JOIN ratings rt ON rt.steam_id = r.steam_id
        WHERE r.cup_id = ?`).bind(c.id),
    ]);
    // a team short of the roster's minimum is out
    const size = (id) => ro.filter((r) => r.team_id === id).length;
    const ok = en.filter((e) => size(e.team_id) >= c.roster_min), short = en.filter((e) => size(e.team_id) < c.roster_min);
    if (ok.length < 2) {
      await callOff(env, c, now, `${c.name} did not start: fewer than two teams with a full roster.`);
      out.push({ cup: c.id, did: 'called off' });
      continue;
    }
    const n = matchDrivers(spec.scoring);
    const seeded = seedOrderOf(ok.map((e) => ({ steam_id: e.team_id, rating: teamRating(ro.filter((r) => r.team_id === e.team_id).map((r) => r.rating), n) })));
    const names = new Map(en.map((e) => [e.team_id, label(e)]));
    const went = ['EXISTS (SELECT 1 FROM team_cups WHERE id = ? AND round = 1 AND round_at = ?)', [c.id, now]];
    const shortIds = JSON.stringify(short.map((e) => e.team_id));
    await env.DB.batch([
      env.DB.prepare("UPDATE team_cups SET status = 'running', round = 1, round_at = ? WHERE id = ? AND status = 'open'").bind(now, c.id),
      // the teams short of a roster: told, then out
      env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT r.steam_id, NULL, 'cup', ?, ?, ? FROM team_cup_roster r
        WHERE r.cup_id = ? AND r.team_id IN (SELECT value FROM json_each(?)) AND ${went[0]}`)
        .bind(`${c.name} started without your team: its roster was short of ${c.roster_min} drivers.`, REF(c.id), now, c.id, shortIds, ...went[1]),
      env.DB.prepare(`DELETE FROM team_cup_roster WHERE cup_id = ? AND team_id IN (SELECT value FROM json_each(?)) AND ${went[0]}`).bind(c.id, shortIds, ...went[1]),
      env.DB.prepare(`DELETE FROM team_cup_entries WHERE cup_id = ? AND team_id IN (SELECT value FROM json_each(?)) AND ${went[0]}`).bind(c.id, shortIds, ...went[1]),
      env.DB.prepare(`UPDATE team_cup_entries SET seed = (SELECT j.key + 1 FROM json_each(?) j WHERE j.value = team_cup_entries.team_id)
        WHERE cup_id = ? AND ${went[0]}`).bind(JSON.stringify(seeded), c.id, ...went[1]),
      // the rosters' drivers: members of its holder (they drive its matches that name them)
      env.DB.prepare(`INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role) SELECT ?, steam_id, ?, 'member'
        FROM team_cup_roster WHERE cup_id = ? AND ${went[0]}`).bind(c.id, now, c.id, ...went[1]),
      ...roundStmts(env, c, spec, 1, Math.log2(bracketOf(seeded.length)), firstRound(seeded), names, now, opensAt, ...went),
    ]);
    out.push({ cup: c.id, did: 'started' });
  }
  // the cups with something to do: a match of their round closed (and its grace over) undecided, or the round all decided
  const { results: running } = await env.DB.prepare(`SELECT c.* FROM team_cups c WHERE c.status = 'running'
      AND EXISTS (SELECT 1 FROM team_cup_matches m WHERE m.cup_id = c.id AND m.round = c.round)
      AND (EXISTS (SELECT 1 FROM team_cup_matches m JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = c.id AND m.round = c.round
             AND m.winner IS NULL AND e.closes + ? <= ?)
        OR NOT EXISTS (SELECT 1 FROM team_cup_matches m WHERE m.cup_id = c.id AND m.round = c.round AND m.winner IS NULL))
    ORDER BY c.starts LIMIT ?`).bind(LIMITS.graceMs, now, PER_RUN.running).all();
  for (const c of running) {
    const spec = JSON.parse(c.spec);
    const [{ results: ms }, { results: en }] = await env.DB.batch([
      env.DB.prepare(`SELECT m.*, e.closes FROM team_cup_matches m LEFT JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = ?
        ORDER BY m.round, m.slot`).bind(c.id),
      env.DB.prepare(`SELECT e.team_id, e.seed, t.name, t.tag FROM team_cup_entries e LEFT JOIN teams t ON t.id = e.team_id WHERE e.cup_id = ?`).bind(c.id),
    ]);
    const rounds = Math.log2(2 * ms.filter((x) => x.round === 1).length);
    const seeds = new Map(en.map((e) => [e.team_id, e.seed])), names = new Map(en.map((e) => [e.team_id, label(e)]));
    const seedOf = (id) => seeds.get(id) || 999;
    const cur = ms.filter((x) => x.round === c.round);
    const due = cur.filter((y) => !y.winner && y.closes != null && now >= y.closes + LIMITS.graceMs);
    if (due.length) {                                     // the round's closed matches, all decided in one go
      const ids = due.map((x) => x.event_id);
      const [rows, lineups] = await Promise.all([holderRows(env, c.id, now, ids), lineupsOf(env, ids)]);
      const ds = due.map((x) => {
        const d = decideMatch(rows.get(x.event_id) || [], x.a, x.b, lineups.get(x.event_id) || new Map(), spec.scoring);
        const higher = seedOf(x.a) <= seedOf(x.b) ? x.a : x.b;
        return { id: x.id, winner: d.winner || higher, note: d.winner ? d.note : `${d.note}: the higher seed goes through` };
      });
      try {
        await env.DB.prepare(`UPDATE team_cup_matches SET
            winner = (SELECT json_extract(j.value, '$.winner') FROM json_each(?1) j WHERE json_extract(j.value, '$.id') = team_cup_matches.id),
            note = (SELECT json_extract(j.value, '$.note') FROM json_each(?1) j WHERE json_extract(j.value, '$.id') = team_cup_matches.id)
          WHERE id IN (SELECT json_extract(value, '$.id') FROM json_each(?1)) AND winner IS NULL`).bind(JSON.stringify(ds)).run();
      } catch (e) {
        if (!clash(e)) throw e;
        continue;
      }
      for (const d of ds) Object.assign(due.find((x) => x.id === d.id), { winner: d.winner, note: d.note });
    }
    if (!cur.length || cur.some((x) => !x.winner)) continue;
    if (c.round < rounds) {                               // the next round: the winners of slots 2k and 2k+1 meet
      const next = [];
      for (let k = 0; k < cur.length / 2; k++) {
        const [w1, w2] = [cur[2 * k].winner, cur[2 * k + 1].winner];
        next.push({ slot: k, a: seedOf(w1) <= seedOf(w2) ? w1 : w2, b: seedOf(w1) <= seedOf(w2) ? w2 : w1 });
      }
      const went = ['EXISTS (SELECT 1 FROM team_cups WHERE id = ? AND round = ? AND round_at = ?)', [c.id, c.round + 1, now]];
      await env.DB.batch([
        env.DB.prepare('UPDATE team_cups SET round = ?, round_at = ? WHERE id = ? AND round = ?').bind(c.round + 1, now, c.id, c.round),
        ...roundStmts(env, c, spec, c.round + 1, rounds, next, names, now, opensAt, ...went),
      ]);
      out.push({ cup: c.id, did: `round ${c.round + 1}` });
      continue;
    }
    // the final is decided: the places, every team told, the matches' details for everyone
    const pl = places(ms, rounds, seedOf);
    const over = ["EXISTS (SELECT 1 FROM team_cups WHERE id = ? AND status = 'finished' AND settled = ?)", [c.id, now]];
    try {
      await env.DB.batch([
        env.DB.prepare("UPDATE team_cups SET status = 'finished', settled = ? WHERE id = ? AND status = 'running'").bind(now, c.id),
        env.DB.prepare('UPDATE league_events SET hide = NULL WHERE league_id = ? AND hide IS NOT NULL').bind(c.id),
        env.DB.prepare(`UPDATE team_cup_entries SET place = (SELECT json_extract(j.value, '$[1]') FROM json_each(?1) j
            WHERE json_extract(j.value, '$[0]') = team_cup_entries.team_id)
          WHERE cup_id = ?2 AND team_id IN (SELECT json_extract(value, '$[0]') FROM json_each(?1))`).bind(JSON.stringify(pl), c.id),
        ...rosterNotices(env, c, pl.map(([id, place]) => ({ team: id, body: `${c.name} is over: ${names.get(pl[0][0])} won it. ${names.get(id)} placed ${place}.` })),
          false, now, ...over),
      ]);
    } catch (e) {
      if (!clash(e)) throw e;
    }
    out.push({ cup: c.id, did: 'finished', winner: pl[0] && pl[0][0] });
  }
  for (const r of await remindTick(env, now)) out.push(r);
  return out;
}

/** Before a round closes (a day before, or a quarter of a short round), a notice to each lineup driver who hasn't
 *  finished their team's match and, lineups named per match, to the captain and managers of a team that hasn't named
 *  all its drivers: once a round (marks). -> [{cup, did}] */
async function remindTick(env, now) {
  const out = [];
  const { results: soon } = await env.DB.prepare(`SELECT c.id, c.name, c.round, c.spec, MAX(e.closes) AS closes,
      (SELECT COUNT(*) FROM team_cup_matches x WHERE x.cup_id = c.id AND x.round = 1) AS r1
    FROM team_cups c JOIN team_cup_matches m ON m.cup_id = c.id AND m.round = c.round JOIN league_events e ON e.id = m.event_id
    WHERE c.status = 'running' AND NOT EXISTS (SELECT 1 FROM marks k WHERE k.key = 'remind:tcup:' || c.id || ':' || c.round)
    GROUP BY c.id HAVING MAX(e.closes) > ?1 AND MAX(e.closes) - ?1 <= MIN(MAX(c.round_hours) * 900000, 86400000)
    LIMIT 2`).bind(now).all();
  for (const c of soon) {
    const spec = JSON.parse(c.spec);
    const { results: ms } = await env.DB.prepare(`SELECT m.a, m.b, m.event_id, ta.name AS a_name, ta.tag AS a_tag, tb.name AS b_name, tb.tag AS b_tag
      FROM team_cup_matches m LEFT JOIN teams ta ON ta.id = m.a LEFT JOIN teams tb ON tb.id = m.b
      WHERE m.cup_id = ? AND m.round = ? AND m.winner IS NULL AND m.event_id IS NOT NULL`).bind(c.id, c.round).all();
    const ids = ms.map((m) => m.event_id);
    const named = spec.scoring.lineup === 'named' && spec.lineupFor === 'match';
    const [rows, lineups, runners] = await Promise.all([holderRows(env, c.id, now, ids), lineupsOf(env, ids),
      named ? runnersOf(env, ms.flatMap((m) => [m.a, m.b])) : new Map()]);
    const what = `${c.name}, ${roundName(c.round, Math.log2(2 * c.r1)).toLowerCase()}`;
    const list = ms.flatMap((m) => matchReminders(rows.get(m.event_id) || [], lineups.get(m.event_id),
      [{ id: m.a, name: label({ name: m.a_name, tag: m.a_tag }) }, { id: m.b, name: label({ name: m.b_name, tag: m.b_tag }) }],
      { named, size: spec.scoring.size, runners, what, where: 'CUPS', closes: utcWhen(c.closes), stages: spec.stages.length }));
    const key = `remind:tcup:${c.id}:${c.round}`, went = ['EXISTS (SELECT 1 FROM marks WHERE key = ? AND at = ?)', [key, now]];
    await env.DB.batch([
      env.DB.prepare('INSERT OR IGNORE INTO marks (key, at) VALUES (?, ?)').bind(key, now),
      noticesStmt(env, 'cup', list, REF(c.id), now, ...went),
    ]);
    out.push({ cup: c.id, did: `reminded ${list.length}` });
  }
  return out;
}

const bracketOf = (n) => { let b = 2; while (b < n) b *= 2; return b; };
