// A league's teams and its team championships (README: Leagues › Teams). Its staff turn teams on (leagues.teams) and
// choose where they come from:
//   league  the league's own teams (league_teams), made by its admins: a name, a tag, a colour, a manager (a driver
//           who runs it); who puts drivers in them: the admins / the drivers themselves / each team's manager; how
//           many drivers a team has at most; transfers open, or (admins) a driver who has driven an event for a team
//           is moved by the admins only
//   site    ACR Daily's teams (/teams): a driver is in their team's; one league_teams row stands for each (made as their
//           drivers turn up), its captain and managers run it here
// Each entry keeps the team its driver drove the event for (league_entries.team_id, set as they start it): a driver
// changing teams takes no points along. An entry from before teams were on counts for the driver's team now, and the
// staff can set any entry's team (entryteam).
// A season's team championship (league_seasons.team_champ, src/teamscore.js): who counts, how, a team points table,
// dropped rounds, nominations (each team names up to M drivers for an event before it opens: its manager, or the
// league's admins; the staff can change them until it closes) and the stewards' points penalties on a team.
//
//   POST /api/leagues/:id/teams {source, pick, max, transfers} | {off: true}      the settings (staff)
//   POST /api/leagues/:id/teamadd {name, tag, color, manager}                      a league team (staff)
//   POST /api/leagues/:id/teamedit {teamId, name, tag, color, manager}             (staff; its manager: name, tag, colour)
//   POST /api/leagues/:id/teamdelete {teamId}                                      (staff)
//   POST /api/leagues/:id/teamset {steamId, teamId | null}                         a driver's team (as the settings allow; a
//                                                                                  driver accepting an invite: that team)
//   POST /api/leagues/:id/teaminvite {steamId, teamId | null}                      a team's manager invites a driver in no team
//                                                                                  (pick managers; null: the invite taken back)
//   POST /api/leagues/:id/teamdecline                                              a driver declines the invite they have
//   POST /api/events/:id/nominate {teamId, steamIds}                               a team's nominations for an event
//   POST /api/events/:id/entryteam {steamId, teamId | null}                        the team an entry counts for (staff)
//   POST /api/seasons/:id/teampenalty {teamId, points, reason} | {remove: id}      (staff)

import { TEAM } from './drivers.js';
import { noticeStmt } from './social.js';
import { LIMITS, text } from './leagues.js';
import { checkTeamChamp, describeTeamChamp, eligible, teamRound, teamSeasonStandings } from './teamscore.js';

export const LEAGUE_TEAMS = { teams: 40, drivers: [1, 50], picks: ['admins', 'drivers', 'managers'], transfers: ['open', 'admins'],
  penaltyMax: 1000, nameMin: 3, nameMax: 30 };

/** A league's team settings from a form: -> {value: {source, pick, max, transfers} | null (off)} or {error}. */
export function checkLeagueTeams(b) {
  if (!b || b.off || !b.source) return { value: null };
  if (!['league', 'site'].includes(b.source)) return { error: 'the teams: the league\'s own, or ACR Daily\'s teams' };
  if (b.source === 'site') return { value: { source: 'site' } };
  const pick = b.pick || 'admins';
  if (!LEAGUE_TEAMS.picks.includes(pick)) return { error: 'who puts drivers in teams: the admins, the drivers or the teams\' managers' };
  const max = b.max == null || b.max === '' ? 10 : Number(b.max);
  if (!Number.isInteger(max) || max < LEAGUE_TEAMS.drivers[0] || max > LEAGUE_TEAMS.drivers[1]) return { error: `drivers in a team: 1 to ${LEAGUE_TEAMS.drivers[1]}` };
  const transfers = b.transfers || 'open';
  if (!LEAGUE_TEAMS.transfers.includes(transfers)) return { error: 'transfers: open, or by the admins only' };
  return { value: { source: 'league', pick, max, transfers } };
}

/** A league team from a form: -> {value: {name, tag, color}} or {error}. */
export function checkLeagueTeam(b) {
  const name = text(b && b.name, LEAGUE_TEAMS.nameMax + 1);
  if (name.length < LEAGUE_TEAMS.nameMin || name.length > LEAGUE_TEAMS.nameMax) return { error: `the team's name: ${LEAGUE_TEAMS.nameMin} to ${LEAGUE_TEAMS.nameMax} characters` };
  const tag = String((b && b.tag) || '').trim().toUpperCase();
  if (tag && !/^[A-Z0-9]{2,4}$/.test(tag)) return { error: 'the tag: 2 to 4 letters or digits' };
  const color = TEAM.colors.includes(b && b.color) ? b.color : TEAM.colors[1];
  return { value: { name, tag: tag || null, color } };
}

export const teamsOf = (l) => (l && l.kind === 'league' && l.teams ? JSON.parse(l.teams) : null);
export const champOf = (s) => (s && s.team_champ ? JSON.parse(s.team_champ) : null);

/** The statement adding the ACR Daily teams of a league's drivers to its teams (site: one row each, kept). sid: only that
 *  driver's. */
const siteRowsStmt = (env, leagueId, now, sid = null) => env.DB.prepare(`INSERT OR IGNORE INTO league_teams (league_id, name, tag, color, site_team, created)
  SELECT DISTINCT lm.league_id, t.name, t.tag, t.color, t.id, ? FROM league_members lm JOIN team_members m ON m.steam_id = lm.steam_id
  JOIN teams t ON t.id = m.team_id WHERE lm.league_id = ?${sid ? ' AND lm.steam_id = ?' : ''}`).bind(now, leagueId, ...(sid ? [sid] : []));

/** The statements giving a new entry its team (the one its driver drives the event for), for the batch with its INSERT. */
export function entryTeamStmts(env, l, eventId, sid, now) {
  const s = teamsOf(l);
  if (!s) return [];
  if (s.source === 'site') {
    return [siteRowsStmt(env, l.id, now, sid),
      env.DB.prepare(`UPDATE league_entries SET team_id = (SELECT lt.id FROM league_teams lt JOIN team_members m ON m.team_id = lt.site_team
        WHERE lt.league_id = ? AND m.steam_id = ?) WHERE event_id = ? AND steam_id = ? AND team_id IS NULL`).bind(l.id, sid, eventId, sid)];
  }
  return [env.DB.prepare(`UPDATE league_entries SET team_id = (SELECT team_id FROM league_members WHERE league_id = ? AND steam_id = ?)
    WHERE event_id = ? AND steam_id = ? AND team_id IS NULL`).bind(l.id, sid, eventId, sid)];
}

/** A league's teams, who is in which now, its nominations and its team penalties (one batch). -> null (no teams) or
 *  {settings, teams: [{id, name, tag, color, tagFmt, manager: {steamId, name} | null, siteTeam, drivers: [steamId],
 *  runners: [steamId] (site: its captain and managers)}], teamNow: Map steamId -> teamId, nominations: Map eventId ->
 *  Map teamId -> Set steamId, penalties: [{id, seasonId, teamId, points, reason, by, at}], names: {steamId: name} (the
 *  teams' drivers)} */
export async function leagueTeamData(env, l, now = Date.now()) {
  const settings = teamsOf(l);
  if (!settings) return null;
  const site = settings.source === 'site';
  const stmts = [
    env.DB.prepare(`SELECT lt.*, t.name AS s_name, t.tag AS s_tag, t.color AS s_color, t.tag_fmt AS s_tag_fmt, t.captain AS s_captain,
        p.name AS manager_name FROM league_teams lt LEFT JOIN teams t ON t.id = lt.site_team LEFT JOIN players p ON p.steam_id = lt.manager
      WHERE lt.league_id = ? AND lt.site_team IS ${site ? 'NOT ' : ''}NULL ORDER BY lt.id`).bind(l.id),
    site ? env.DB.prepare(`SELECT m.steam_id, lt.id AS team_id, m.role, p.name FROM league_members lm JOIN team_members m ON m.steam_id = lm.steam_id
        JOIN league_teams lt ON lt.site_team = m.team_id AND lt.league_id = lm.league_id LEFT JOIN players p ON p.steam_id = m.steam_id
        WHERE lm.league_id = ?`).bind(l.id)
      : env.DB.prepare(`SELECT lm.steam_id, lm.team_id, NULL AS role, p.name FROM league_members lm LEFT JOIN players p ON p.steam_id = lm.steam_id
        WHERE lm.league_id = ? AND lm.team_id IS NOT NULL`).bind(l.id),
    env.DB.prepare(`SELECT n.event_id, n.team_id, n.steam_id FROM league_nominations n JOIN league_events e ON e.id = n.event_id
      WHERE e.league_id = ?`).bind(l.id),
    env.DB.prepare(`SELECT x.*, p.name AS by_name FROM league_team_penalties x JOIN league_seasons s ON s.id = x.season_id
      LEFT JOIN players p ON p.steam_id = x.by WHERE s.league_id = ? ORDER BY x.created`).bind(l.id),
  ];
  // (site: the teams of drivers who joined since are added first; nothing is written when there are none)
  const res = await env.DB.batch(site ? [siteRowsStmt(env, l.id, now), ...stmts] : stmts);
  const [tm, mem, nom, pen] = site ? res.slice(1) : res;
  const teamNow = new Map(mem.results.map((r) => [r.steam_id, r.team_id]));
  const teams = tm.results.map((r) => ({ id: r.id, name: r.s_name || r.name, tag: (site ? r.s_tag : r.tag) || r.tag || null,
    color: r.s_color || r.color, ...(r.s_tag_fmt ? { tagFmt: r.s_tag_fmt } : {}),
    manager: !site && r.manager ? { steamId: r.manager, name: r.manager_name || 'a driver' } : null, siteTeam: r.site_team || null,
    drivers: mem.results.filter((x) => x.team_id === r.id).map((x) => x.steam_id),
    runners: site ? [r.s_captain, ...mem.results.filter((x) => x.team_id === r.id && x.role === 'manager').map((x) => x.steam_id)].filter(Boolean)
      : r.manager ? [r.manager] : [] }));
  const nominations = new Map();
  for (const n of nom.results) {
    if (!nominations.has(n.event_id)) nominations.set(n.event_id, new Map());
    const m = nominations.get(n.event_id);
    if (!m.has(n.team_id)) m.set(n.team_id, new Set());
    m.get(n.team_id).add(n.steam_id);
  }
  const penalties = pen.results.map((x) => ({ id: x.id, seasonId: x.season_id, teamId: x.team_id, points: x.points, reason: x.reason,
    by: x.by_name || 'a steward', at: x.created }));
  const names = Object.fromEntries(mem.results.map((r) => [r.steam_id, r.name || 'Driver']));
  return { settings, teams, teamNow, nominations, penalties, names };
}

/** Who each driver of an event drove it for: their entry's team (one of the league's teams), else their team now. */
export function teamOfEntries(td, entries) {
  const ids = new Set(td.teams.map((t) => t.id));
  return new Map(entries.map((e) => [e.steam_id, e.team_id != null && ids.has(e.team_id) ? e.team_id : td.teamNow.get(e.steam_id) || null]));
}

/** The drivers' rows of a league with league teams wearing their league team's tag (and nobody else a tag: withTeams
 *  leaves a row with `team` as it is). */
export function tagRows(td, rows, teamOf = null) {
  if (!td || td.settings.source !== 'league') return rows;
  const byId = new Map(td.teams.map((t) => [t.id, t]));
  for (const r of rows) {
    const t = byId.get((teamOf || td.teamNow).get(r.steamId));
    r.team = t && t.tag ? { tag: t.tag, color: t.color } : null;
  }
  return rows;
}

const teamsOut = (td) => td.teams.map(({ runners, ...t }) => t);

/** A season's team championship for the league page: {teamChamp, teamAbout, teamStandings, teamPenalties} (nothing
 *  without teams or a championship). events: the season's [{id, status (counted), rows, stages, entries}]; drivers:
 *  its seasonStandings. */
export function seasonTeams(td, season, events, drivers) {
  const c = champOf(season);
  if (!td || !c) return { teamChamp: c, teamAbout: c ? describeTeamChamp(c) : '', teamStandings: [], teamPenalties: [] };
  const evs = events.map((e) => ({ ...e, teamOf: teamOfEntries(td, e.entries), named: td.nominations.get(e.id) || null }));
  const pens = td.penalties.filter((p) => p.seasonId === season.id);
  return { teamChamp: c, teamAbout: describeTeamChamp(c), teamPenalties: pens,
    teamStandings: teamSeasonStandings(c, teamsOut(td), evs, drivers, pens) };
}

/** An event's teams for its page: each team's drivers on it, nominations, and (a season with a team championship) its
 *  points there. rows: the event's standings rows; entries: its entry rows; cells: Map steamId -> the driver's
 *  championship cell for it (seasonStandings of its season, or empty); blind: its results hidden from this viewer. */
export function eventTeams(td, ev, season, rows, entries, cells, me, staff, blind, now) {
  if (!td) return null;
  const c = champOf(season);
  const teamOf = teamOfEntries(td, entries);
  const named = td.nominations.get(ev.id) || null;
  const ids = td.teams.map((t) => t.id);
  const round = c && !blind && now >= ev.opens ? teamRound(c, { id: ev.id, rows, stages: [] }, eligible(c, ids, rows.map((r) => r.steamId), teamOf, named), cells) : null;
  const may = (t) => staff || (!!me && t.runners.includes(me));
  return {
    champ: c, about: c ? describeTeamChamp(c) : '', nominate: c ? c.nominate : 0, names: td.names,
    // nominations: before the event opens (its teams' managers); the staff until it closes
    nominationsOpen: !!c && !!c.nominate && (now < ev.opens || (staff && now < ev.closes)),
    results: teamsOut(td).map((t) => {
      const x = round && round.get(t.id);
      return { ...t, drove: rows.filter((r) => teamOf.get(r.steamId) === t.id).map((r) => r.steamId),
        nominated: named && named.get(t.id) ? [...named.get(t.id)] : [], pts: x ? x.pts : null, rank: x ? x.rank || null : null,
        counted: x ? x.counted : [], canNominate: may(td.teams.find((y) => y.id === t.id)) };
    }).filter((t) => t.drove.length || t.nominated.length || t.canNominate)
      .sort((a, b) => (a.rank || 1e9) - (b.rank || 1e9) || (b.pts || 0) - (a.pts || 0) || a.name.localeCompare(b.name)),
  };
}

// ------------------------------------------------------------------ actions

/** A league's team actions (leagueAction hands them over): -> a Response, or null (not one of them). staff: the
 *  league's owner or an admin. */
export async function leagueTeamAction(env, l, role, me, action, b, now, { json, err, staff }) {
  if (!['teams', 'teamadd', 'teamedit', 'teamdelete', 'teamset', 'teaminvite', 'teamdecline'].includes(action)) return null;
  const s = teamsOf(l);
  if (action === 'teams') {                                // the settings, or off ({off: true})
    if (!staff) return err('only the league\'s owner and admins can do that', 403);
    const c = checkLeagueTeams(b);
    if (c.error) return err(c.error);
    await env.DB.batch([env.DB.prepare('UPDATE leagues SET teams = ? WHERE id = ?').bind(c.value ? JSON.stringify(c.value) : null, l.id),
      ...(c.value && c.value.source === 'site' ? [siteRowsStmt(env, l.id, now)] : [])]);
    return json({ teams: c.value });
  }
  if (!s) return err('this league has no teams: turn them on first', 409);
  if (s.source !== 'league') return err('this league\'s teams are ACR Daily\'s: their drivers are in them on /teams', 409);
  const teamRow = async (id) => env.DB.prepare('SELECT * FROM league_teams WHERE id = ? AND league_id = ? AND site_team IS NULL')
    .bind(Math.round(+id) || 0, l.id).first();
  const memberOf = async (sid) => env.DB.prepare('SELECT steam_id, team_id, team_invite FROM league_members WHERE league_id = ? AND steam_id = ?')
    .bind(l.id, sid).first();
  const managerOk = async (v) => {
    if (v == null || v === '') return { id: null };
    const m = await memberOf(String(v));
    return m ? { id: m.steam_id } : { error: 'the manager: a driver of the league' };
  };
  if (action === 'teamadd') {
    if (!staff) return err('only the league\'s owner and admins can do that', 403);
    const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM league_teams WHERE league_id = ? AND site_team IS NULL').bind(l.id).first();
    if (n.n >= LEAGUE_TEAMS.teams) return err(`${LEAGUE_TEAMS.teams} teams at most`, 409);
    const c = checkLeagueTeam(b);
    if (c.error) return err(c.error);
    const mg = await managerOk(b.manager);
    if (mg.error) return err(mg.error);
    const r = await env.DB.prepare('INSERT INTO league_teams (league_id, name, tag, color, manager, created) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(l.id, c.value.name, c.value.tag, c.value.color, mg.id, now).run();
    return json({ id: r.meta.last_row_id });
  }
  if (action === 'teamedit' || action === 'teamdelete') {
    const t = await teamRow(b.teamId);
    if (!t) return err('no such team in this league', 404);
    const mine = !!me && t.manager === me.steam_id;
    if (action === 'teamdelete') {
      if (!staff) return err('only the league\'s owner and admins can do that', 403);
      await env.DB.batch([env.DB.prepare('UPDATE league_members SET team_id = NULL WHERE league_id = ? AND team_id = ?').bind(l.id, t.id),
        env.DB.prepare('UPDATE league_members SET team_invite = NULL WHERE league_id = ? AND team_invite = ?').bind(l.id, t.id),
        env.DB.prepare('DELETE FROM league_nominations WHERE team_id = ?').bind(t.id),
        env.DB.prepare('DELETE FROM league_team_penalties WHERE team_id = ?').bind(t.id),
        env.DB.prepare('DELETE FROM league_teams WHERE id = ?').bind(t.id)]);
      return json({ deleted: true });
    }
    if (!staff && !mine) return err('only the league\'s admins and the team\'s manager can do that', 403);
    const c = checkLeagueTeam({ name: b.name == null ? t.name : b.name, tag: b.tag == null ? t.tag : b.tag, color: b.color == null ? t.color : b.color });
    if (c.error) return err(c.error);
    let manager = t.manager;
    if ('manager' in b) {
      if (!staff) return err('only the league\'s owner and admins choose a team\'s manager', 403);
      const mg = await managerOk(b.manager);
      if (mg.error) return err(mg.error);
      manager = mg.id;
    }
    await env.DB.prepare('UPDATE league_teams SET name = ?, tag = ?, color = ?, manager = ? WHERE id = ?')
      .bind(c.value.name, c.value.tag, c.value.color, manager, t.id).run();
    return json({ ok: true });
  }
  if (action === 'teamdecline') {                        // the driver: no to the invite they have
    const r = await env.DB.prepare('UPDATE league_members SET team_invite = NULL WHERE league_id = ? AND steam_id = ? AND team_invite IS NOT NULL')
      .bind(l.id, me.steam_id).run();
    return r.meta.changes ? json({ declined: true }) : err('you have no invite to decline', 409);
  }
  const sid = String(b.steamId || '');
  const m = await memberOf(sid);
  if (!m) return err('not a member of this league', 404);
  if (action === 'teaminvite') {                          // a team's manager (or the staff) invites a driver in no team
    const to = b.teamId == null || b.teamId === '' ? null : await teamRow(b.teamId);
    if (b.teamId != null && b.teamId !== '' && !to) return err('no such team in this league', 404);
    if (!to) {                                            // the invite taken back (by the team that sent it)
      const was = m.team_invite != null ? await teamRow(m.team_invite) : null;
      if (!staff && !(was && me && was.manager === me.steam_id)) return err('only the team that invited them takes it back', 403);
      await env.DB.prepare('UPDATE league_members SET team_invite = NULL WHERE league_id = ? AND steam_id = ?').bind(l.id, sid).run();
      return json({ invite: null });
    }
    if (!staff && !(s.pick === 'managers' && me && to.manager === me.steam_id)) return err('only the team\'s manager invites drivers to it', 403);
    if (m.team_id != null) return err('that driver is in a team already', 409);
    await env.DB.batch([
      env.DB.prepare('UPDATE league_members SET team_invite = ? WHERE league_id = ? AND steam_id = ? AND team_id IS NULL').bind(to.id, l.id, sid),
      noticeStmt(env, sid, 'league', `${to.name} invites you to drive for it in ${l.name}: accept or decline on the league's page.`,
        `league:${l.id}`, now),
    ]);
    return json({ invite: to.id });
  }
  // teamset: a driver into a team (teamId), or out of theirs (null)
  const to = b.teamId == null || b.teamId === '' ? null : await teamRow(b.teamId);
  if (b.teamId != null && b.teamId !== '' && !to) return err('no such team in this league', 404);
  if ((to ? to.id : null) === m.team_id) return json({ teamId: m.team_id });
  if (!staff) {
    const cur = m.team_id != null ? await teamRow(m.team_id) : null;
    const self = !!me && sid === me.steam_id;
    // who may: the driver (pick drivers: into any team; a team that invited them; any pick: out of theirs), a manager
    // (pick managers: one of theirs out of it; a driver comes in by accepting their invite: teaminvite)
    const ok = (self && (s.pick === 'drivers' || !to || (to && m.team_invite === to.id)))
      || (s.pick === 'managers' && !!me && !to && cur && cur.manager === me.steam_id);
    if (!ok) return err(s.pick === 'admins' ? 'the league\'s admins put drivers in teams' : 'you can\'t move this driver', 403);
    // transfers by the admins only: a driver who has driven an event for a team stays where they are
    if (s.transfers === 'admins' && m.team_id != null) {
      const drove = await env.DB.prepare(`SELECT 1 AS x FROM league_entries e JOIN league_events v ON v.id = e.event_id
        WHERE v.league_id = ? AND e.steam_id = ? AND e.team_id IS NOT NULL LIMIT 1`).bind(l.id, sid).first();
      if (drove) return err('transfers are by the league\'s admins only once a driver has driven for a team', 403);
    }
  }
  if (to) {
    const r = await env.DB.prepare(`UPDATE league_members SET team_id = ?1, team_invite = NULL WHERE league_id = ?2 AND steam_id = ?3
      AND (SELECT COUNT(*) FROM league_members WHERE league_id = ?2 AND team_id = ?1) < ?4`).bind(to.id, l.id, sid, s.max).run();
    if (!r.meta.changes) return err(`the team is full (${s.max} drivers)`, 409);
  } else {
    await env.DB.prepare('UPDATE league_members SET team_id = NULL WHERE league_id = ? AND steam_id = ?').bind(l.id, sid).run();
  }
  return json({ teamId: to ? to.id : null });
}

/** An event's team actions (eventAction hands them over): nominate, entryteam. -> a Response, or null. */
export async function eventTeamAction(env, ev, l, me, action, b, now, { json, err, staff }) {
  if (!['nominate', 'entryteam'].includes(action)) return null;
  if (l.kind !== 'league') return err('not found', 404);
  const td = await leagueTeamData(env, l, now);
  if (!td) return err('this league has no teams', 409);
  const team = td.teams.find((t) => t.id === Math.round(+b.teamId));
  if (action === 'entryteam') {
    if (!staff) return err('only the league\'s owner and admins can do that', 403);
    if (b.teamId != null && b.teamId !== '' && !team) return err('no such team in this league', 404);
    const r = await env.DB.prepare('UPDATE league_entries SET team_id = ? WHERE event_id = ? AND steam_id = ?')
      .bind(team ? team.id : null, ev.id, String(b.steamId || '')).run();
    return r.meta.changes ? json({ teamId: team ? team.id : null }) : err('that driver has not started this event', 404);
  }
  const season = ev.season_id && await env.DB.prepare('SELECT * FROM league_seasons WHERE id = ?').bind(ev.season_id).first();
  const c = champOf(season);
  if (!c || !c.nominate) return err('this event\'s season has no nominations', 409);
  if (!team) return err('no such team in this league', 404);
  if (!staff && !(me && team.runners.includes(me.steam_id))) return err('only the team\'s manager and the league\'s admins nominate', 403);
  if (now >= ev.closes || (!staff && now >= ev.opens)) return err('nominations close when the event opens', 409);
  const ids = [...new Set((Array.isArray(b.steamIds) ? b.steamIds : []).map(String))];
  if (ids.length > c.nominate) return err(`${c.nominate} drivers at most`);
  const notIn = ids.filter((x) => !team.drivers.includes(x));
  if (notIn.length) return err('only the team\'s drivers can be nominated');
  await env.DB.batch([
    env.DB.prepare('DELETE FROM league_nominations WHERE event_id = ? AND team_id = ?').bind(ev.id, team.id),
    ...(ids.length ? [env.DB.prepare(`INSERT OR REPLACE INTO league_nominations (event_id, team_id, steam_id, by, at)
      SELECT ?, ?, value, ?, ? FROM json_each(?)`).bind(ev.id, team.id, me.steam_id, now, JSON.stringify(ids))] : []),
  ]);
  return json({ nominated: ids });
}

/** A season's team championship from its form (create or edit): -> {value: JSON | null, keep: true (not in the form)}
 *  or {error}. */
export function seasonChampField(b) {
  if (!b || !('teamChamp' in b)) return { keep: true };
  const c = checkTeamChamp(b.teamChamp);
  return c.error ? c : { value: c.value ? JSON.stringify(c.value) : null };
}

/** POST /api/seasons/:id/teampenalty (the staff): {teamId, points, reason} (points taken off; negative: given back), or
 *  {remove: id}. */
export async function seasonTeamPenalty(env, s, me, b, now, { json, err }) {
  if (b.remove != null) {
    const r = await env.DB.prepare('DELETE FROM league_team_penalties WHERE id = ? AND season_id = ?').bind(Math.round(+b.remove), s.id).run();
    return r.meta.changes ? json({ removed: true }) : err('no such penalty', 404);
  }
  const t = await env.DB.prepare('SELECT id FROM league_teams WHERE id = ? AND league_id = ?').bind(Math.round(+b.teamId) || 0, s.league_id).first();
  if (!t) return err('no such team in this league', 404);
  const points = Number(b.points);
  if (!Number.isInteger(points) || !points || Math.abs(points) > LEAGUE_TEAMS.penaltyMax) return err(`the points: 1 to ${LEAGUE_TEAMS.penaltyMax} (negative: given back)`);
  const reason = text(b.reason, LIMITS.reason);
  if (reason.length < 3) return err('give a reason: everyone sees it');
  const r = await env.DB.prepare(`INSERT INTO league_team_penalties (season_id, team_id, points, reason, by, created)
    VALUES (?, ?, ?, ?, ?, ?)`).bind(s.id, t.id, points, reason, me.steam_id, now).run();
  return json({ id: r.meta.last_row_id });
}
