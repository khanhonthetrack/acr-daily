// Team matches: a team 1V1's (src/teamh2h.js) or a team cup's (src/teamcups.js) match is one event of its holder league
// (kind th2h / tcup) that both teams drive. team_lineups says who drives for which team: an open lineup is the team's
// drivers when the match was made (a 1V1: its members then; a cup: its roster), a named one the drivers its captain or
// a manager names (up to the scoring's size; one who has started stays in it). league_events.only_ids lists them all:
// only they can start it. Its result: src/teamscore.js teamResult on the event's standings.

import { decideTeams, teamResult } from './teamscore.js';

export const TEAM_KINDS = ['th2h', 'tcup'];

/** The lineups of these events: -> Map eventId -> Map teamId -> [steamId] (in the order they were named). */
export async function lineupsOf(env, eventIds) {
  const out = new Map();
  if (!eventIds.length) return out;
  const { results } = await env.DB.prepare(`SELECT event_id, team_id, steam_id FROM team_lineups WHERE event_id IN (SELECT value FROM json_each(?))
    ORDER BY at, rowid`).bind(JSON.stringify(eventIds)).all();
  for (const r of results) {
    if (!out.has(r.event_id)) out.set(r.event_id, new Map());
    const m = out.get(r.event_id);
    if (!m.has(r.team_id)) m.set(r.team_id, []);
    m.get(r.team_id).push(r.steam_id);
  }
  return out;
}

/** The statement making a match's only_ids its lineups' drivers. */
export const onlyIdsStmt = (env, eventId) => env.DB.prepare(`UPDATE league_events SET only_ids =
  (SELECT COALESCE(json_group_array(steam_id), '[]') FROM team_lineups WHERE event_id = ?1) WHERE id = ?1`).bind(eventId);

/** The statements putting drivers in a match's lineups (rows: [{team, sid}]), members of its holder, and in its
 *  only_ids, for a batch. by: who named them (null: the roster). */
export const lineupStmts = (env, eventId, holder, rows, by, now) => (!rows.length ? [] : [
  env.DB.prepare(`INSERT OR IGNORE INTO team_lineups (event_id, team_id, steam_id, by, at)
    SELECT ?, json_extract(value, '$.team'), json_extract(value, '$.sid'), ?, ? FROM json_each(?)`).bind(eventId, by, now, JSON.stringify(rows)),
  env.DB.prepare(`INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role)
    SELECT ?, json_extract(value, '$.sid'), ?, 'member' FROM json_each(?)`).bind(holder, now, JSON.stringify(rows)),
  onlyIdsStmt(env, eventId),
]);

/** A team names its drivers for a match (a named lineup): ids, up to `size`, from `pool` (who may drive for it), none
 *  in the other team's lineup; a driver of it who has started stays. -> {value: ids} or {error, status}. */
export async function nameLineup(env, ev, holder, team, ids, me, now, { size, pool, other = [] }) {
  if (now >= ev.closes) return { error: 'the match is closed', status: 409 };
  ids = [...new Set((Array.isArray(ids) ? ids : []).map(String))];
  if (ids.length > size) return { error: `${size} drivers at most` };
  if (ids.some((x) => !pool.includes(x))) return { error: 'only the team\'s drivers can drive for it' };
  if (ids.some((x) => other.includes(x))) return { error: 'that driver drives for the other team' };
  const { results: started } = await env.DB.prepare(`SELECT l.steam_id FROM team_lineups l JOIN league_entries x ON x.event_id = l.event_id
    AND x.steam_id = l.steam_id WHERE l.event_id = ? AND l.team_id = ?`).bind(ev.id, team).all();
  const kept = started.map((r) => r.steam_id).filter((x) => !ids.includes(x));
  if (kept.length) return { error: 'a driver who has started the match stays in the lineup', status: 409 };
  await env.DB.batch([
    env.DB.prepare(`DELETE FROM team_lineups WHERE event_id = ? AND team_id = ? AND steam_id NOT IN (SELECT value FROM json_each(?))`)
      .bind(ev.id, team, JSON.stringify(ids)),
    ...lineupStmts(env, ev.id, holder, ids.map((sid) => ({ team, sid })), me, now),
    onlyIdsStmt(env, ev.id),
  ]);
  return { value: ids };
}

/** A match's teams as the pages show them: teamResult's rows with each team's name, tag and colour and its lineup.
 *  teams: [{id, name, tag, color, tagFmt}] (a first, b second); lineup: Map teamId -> [steamId]; blind: the results
 *  kept from this viewer (hidden times): only who drives and who is done; names: Map steamId -> name (the drivers in
 *  a lineup who have not started: no row to name them). */
export function matchOut(rows, teams, lineup, scoring, blind = false, names = null) {
  const res = teamResult(rows, teams.map((t) => ({ id: t.id, drivers: (lineup && lineup.get(t.id)) || [] })), scoring);
  return teams.map((t) => {
    const r = res.find((x) => x.id === t.id) || {};
    const rowNames = new Map(rows.map((x) => [x.steamId, x.name]));
    const ds = ((lineup && lineup.get(t.id)) || []).map((sid) => {
      const d = (r.drivers || []).find((x) => x.steamId === sid);
      const row = rows.find((x) => x.steamId === sid);
      return { steamId: sid, name: rowNames.get(sid) || (names && names.get(sid)) || null, status: row ? row.status : 'not started', done: row ? row.done : 0,
        ...(blind ? {} : { totalMs: d ? d.totalMs : null, pos: d ? d.pos : null, pts: d ? d.pts : null, counted: !!(d && d.counted) }) };
    });
    return { id: t.id, name: t.name, tag: t.tag || null, color: t.color || null, ...(t.tagFmt ? { tagFmt: t.tagFmt } : {}), drivers: ds,
      ...(blind ? {} : { rank: r.rank || null, score: r.score == null ? null : r.score, missing: r.missing, out: !!r.out, pending: r.pending || 0 }) };
  });
}

/** A match of teams a and b decided: -> {winner, note, result: [{id, rank, score, missing, out, counted: [steamId]}]}. */
export function decideMatch(rows, a, b, lineup, scoring) {
  const res = teamResult(rows, [a, b].map((id) => ({ id, drivers: (lineup && lineup.get(id)) || [] })), scoring);
  const d = decideTeams(res, a, b, scoring);
  return { ...d, result: res.map((t) => ({ id: t.id, rank: t.rank, score: t.score, missing: t.missing, out: t.out,
    counted: t.drivers.filter((x) => x.counted).map((x) => x.steamId) })) };
}

/** The statement giving many teams' drivers a notice (each team's members now): teams [{id, body}]. */
export const teamNoticesStmt = (env, kind, teams, ref, now, cond = null, binds = []) => env.DB.prepare(
  `INSERT INTO messages (to_id, from_id, kind, body, ref, created)
   SELECT m.steam_id, NULL, ?, json_extract(j.value, '$.body'), ?, ? FROM json_each(?) j JOIN team_members m ON m.team_id = json_extract(j.value, '$.id')
   ${cond ? `WHERE ${cond}` : ''}`).bind(kind, ref, now, JSON.stringify(teams.map((t) => ({ id: t.id, body: String(t.body).slice(0, 300) }))), ...binds);

/** The statement giving a team's captain and managers a notice. */
export const runnersNoticeStmt = (env, kind, teamId, body, ref, now, cond = null, binds = []) => env.DB.prepare(
  `INSERT INTO messages (to_id, from_id, kind, body, ref, created)
   SELECT m.steam_id, NULL, ?, ?, ?, ? FROM team_members m JOIN teams t ON t.id = m.team_id
   WHERE m.team_id = ? AND (m.steam_id = t.captain OR m.role = 'manager')${cond ? ` AND ${cond}` : ''}`)
  .bind(kind, String(body).slice(0, 300), ref, now, teamId, ...binds);

/** A team match's own: its two teams (a: the challenger, the higher seed), its scoring, its page. kind: its holder's
 *  (th2h / tcup). -> {a, b: {id, name, tag, color, tagFmt}, scoring, page} or null. */
export async function teamMatchInfo(env, ev, kind) {
  const T = (p) => `${p}.id AS ${p}_id, ${p}.name AS ${p}_name, ${p}.tag AS ${p}_tag, ${p}.color AS ${p}_color, ${p}.tag_fmt AS ${p}_tag_fmt`;
  const r = kind === 'th2h'
    ? await env.DB.prepare(`SELECT h.spec, h.id AS ref, h.challenger AS ta, h.opponent AS tb, ${T('a')}, ${T('b')} FROM team_h2h h
        LEFT JOIN teams a ON a.id = h.challenger LEFT JOIN teams b ON b.id = h.opponent WHERE h.event_id = ?`).bind(ev.id).first()
    : await env.DB.prepare(`SELECT c.spec, c.id AS ref, m.a AS ta, m.b AS tb, ${T('a')}, ${T('b')} FROM team_cup_matches m
        JOIN team_cups c ON c.id = m.cup_id LEFT JOIN teams a ON a.id = m.a LEFT JOIN teams b ON b.id = m.b WHERE m.event_id = ?`).bind(ev.id).first();
  if (!r) return null;
  return { a: teamOf(r, 'a_') || { id: r.ta, name: 'a team' }, b: teamOf(r, 'b_') || { id: r.tb, name: 'a team' },
    scoring: JSON.parse(r.spec).scoring, page: kind === 'th2h' ? '/team1v1' : `/tcup/${r.ref}` };
}

/** The reminders of a team match closing soon: each lineup driver who hasn't finished it, and (a named lineup not full
 *  yet) its team's captain and managers. rows: its standings; lineup: Map teamId -> [steamId]; teams: its two [{id,
 *  name}]; named: lineups are named (size each); runners: Map teamId -> [steamId]; what: 'Autumn Cup, semi-final';
 *  where: the app's tab; closes: when, in words; stages: how many. -> [{to, body}] */
export function matchReminders(rows, lineup, teams, { named, size, runners, what, where, closes, stages }) {
  const out = [];
  for (const [t, o] of [[teams[0], teams[1]], [teams[1], teams[0]]]) {
    const ds = (lineup && lineup.get(t.id)) || [];
    if (named && ds.length < size) {
      for (const to of (runners && runners.get(t.id)) || []) {
        out.push({ to, body: `${what}: ${t.name} has named ${ds.length} of its ${size} driver${size > 1 ? 's' : ''} against ${o.name}. ` +
          `Name them on the website before the match closes, ${closes}.` });
      }
    }
    for (const to of ds) {
      const r = rows.find((x) => x.steamId === to);
      if (r && r.status !== 'running') continue;       // finished (or out): nothing to remind of
      const left = r ? stages - r.done : stages;
      out.push({ to, body: `${what}: ${r ? `${left} ${left === 1 ? 'stage' : 'stages'} of your team's match against ${o.name} still to drive`
        : `you haven't driven your team's match against ${o.name} yet`}. It closes ${closes}: drive it in the ACR Daily app, under ${where}.` });
    }
  }
  return out;
}

/** The captains and managers of these teams: -> Map teamId -> [steamId] (one query). */
export async function runnersOf(env, teamIds) {
  const out = new Map(teamIds.map((id) => [id, []]));
  if (!teamIds.length) return out;
  const { results } = await env.DB.prepare(`SELECT m.team_id, m.steam_id FROM team_members m JOIN teams t ON t.id = m.team_id
    WHERE m.team_id IN (SELECT value FROM json_each(?)) AND (m.steam_id = t.captain OR m.role = 'manager')`).bind(JSON.stringify(teamIds)).all();
  for (const r of results) out.get(r.team_id).push(r.steam_id);
  return out;
}

/** The names of a match's lineups' drivers: -> Map steamId -> name (one query). */
export async function lineupNames(env, lineup) {
  const ids = [...new Set([...(lineup || new Map()).values()].flat())];
  if (!ids.length) return new Map();
  const { results } = await env.DB.prepare('SELECT steam_id, name FROM players WHERE steam_id IN (SELECT value FROM json_each(?))').bind(JSON.stringify(ids)).all();
  return new Map(results.map((r) => [r.steam_id, r.name]));
}

/** A team as the pages show it (a row of teams, or prefixed columns: p = 'a_' reads a_name, a_tag...). */
export const teamOf = (r, p = '') => (r[`${p}id`] || r[`${p}name`] ? { id: r[`${p}id`], name: r[`${p}name`] || 'a team', tag: r[`${p}tag`] || null,
  color: r[`${p}color`] || null, ...(r[`${p}tag_fmt`] ? { tagFmt: r[`${p}tag_fmt`] } : {}) } : null);
