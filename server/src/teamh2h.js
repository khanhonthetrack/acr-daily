// Team 1V1s (/team1v1): a team's captain or one of its managers (src/drivers.js runsTeam) challenges another team to an
// event of their making, scored as they choose (src/teamscore.js checkScoring: open or named lineups, all or the best X,
// times added up, average, places or points). The other team's captain or a manager accepts within TH2H.answerMs, or
// declines. Accepted, it is one match both teams drive from the app's 1V1 tab (src/teammatch.js): an open lineup is
// every driver of both teams then; a named one the drivers each team names (on /team1v1, until they start). No
// credits, not rated. Settled by the cron once the window and its grace are over, or once every named driver of both
// full lineups has a final result. Every step is a notice in the teams' inboxes.
//
//   GET  /api/th2h                                  my team's: {team, incoming, outgoing, active, past}
//   POST /api/th2h {opponent: teamId, event, scoring}
//   POST /api/th2h/<id>/accept | decline | cancel   (the challenged team's runners; cancel: the challenger's)
//   POST /api/th2h/<id>/lineup {steamIds}           my team's named lineup
//   POST /api/th2h/<id>/rematch                     either team's runners, once it is over

import { stageParts } from './conditions.js';
import { clash } from './credits.js';
import { runsTeam, teamRoleOf } from './drivers.js';
import { LIMITS, text } from './leagues.js';
import { checkMatchSpec, makeHolder, makeMatchEvent, matchRows } from './leaguesapi.js';
import { maskStage, viewHide } from './hidden.js';
import { noticesStmt } from './social.js';
import { checkScoring, describeScoring, TEAMSCORE } from './teamscore.js';
import { decideMatch, lineupStmts, lineupsOf, matchOut, nameLineup, runnersNoticeStmt, teamNoticesStmt, teamOf } from './teammatch.js';

export const TH2H = { answerMs: 2 * 86400000, pending: 5, windowDays: 14 };
const REF = (id) => `th2h:${id}`;

const LIST_SQL = `SELECT h.*, a.id AS a_id, a.name AS a_name, a.tag AS a_tag, a.color AS a_color, a.tag_fmt AS a_tag_fmt,
    b.id AS b_id, b.name AS b_name, b.tag AS b_tag, b.color AS b_color, b.tag_fmt AS b_tag_fmt, p.name AS by_name
  FROM team_h2h h LEFT JOIN teams a ON a.id = h.challenger LEFT JOIN teams b ON b.id = h.opponent LEFT JOIN players p ON p.steam_id = h.by`;
const label = (t, fallback) => (t ? (t.tag ? `[${t.tag}] ${t.name}` : t.name) : fallback);

/** A team challenge as the website shows it. mine: my team's id; knows: the match events whose set-up I see; lineup: its
 *  match's (Map teamId -> [steamId]); rows: its match's standings (one under way); names: Map steamId -> name (its
 *  lineups' drivers); settled: over (its result as it was settled). */
function out(r, mine, me, knows, lineup, rows, names, settled) {
  const spec = JSON.parse(r.spec);
  const h = ['sent', 'accepted'].includes(r.status) && spec.hide && (spec.hide.weather || spec.hide.times || spec.hide.stages) ? spec.hide : null;
  const v = viewHide(h, { knows: r.by === me || knows.has(r.event_id) });
  const a = teamOf(r, 'a_') || { id: r.challenger, name: 'a team' }, b = teamOf(r, 'b_') || { id: r.opponent, name: 'a team' };
  return {
    id: r.id, status: r.status, mine: r.challenger === mine ? 'challenger' : 'opponent', challenger: a, opponent: b,
    by: { steamId: r.by, name: r.by_name || 'a driver' },
    name: spec.name, rally: spec.rally, car: spec.car, carClass: spec.car_class, opens: spec.opens, closes: spec.closes, rules: spec.rules,
    stages: spec.stages.map((s) => maskStage({ name: stageParts(s.track).stageName, weather: s.weather, time: s.time }, v)),
    hidden: h ? { weather: !!h.weather, times: !!h.times, stages: !!h.stages } : null, revealed: !v || !(v.weather || v.time || v.stages),
    scoring: spec.scoring, about: describeScoring(spec.scoring), answerBy: r.answer_by, eventId: r.event_id, winner: r.winner, note: r.note,
    created: r.created,
    // the match: each team's lineup and (the results not hidden) its result as it stands; once over, as it was settled
    teams: !r.event_id || !lineup ? null : settled ? settledOut(r, [a, b], lineup, names)
      : matchOut(rows || [], [a, b], lineup, spec.scoring, !!(v && v.results), names),
  };
}

/** A settled match's teams from what was kept (team_h2h.result): each team's lineup, who counted, its place and score. */
function settledOut(r, teams, lineup, names) {
  const res = r.result ? JSON.parse(r.result) : [];
  return teams.map((t) => {
    const x = res.find((y) => y.id === t.id) || {};
    return { ...t, rank: x.rank || null, score: x.score == null ? null : x.score, missing: x.missing, out: !!x.out,
      drivers: (lineup.get(t.id) || []).map((sid) => ({ steamId: sid, name: names.get(sid) || null, counted: (x.counted || []).includes(sid) })) };
  });
}

export async function th2hApi(req, env, path, me, sameOrigin, now, { json, err }) {
  if (!path.startsWith('/api/th2h')) return null;
  if (!me) return err('sign in with Steam first', 401);
  const post = req.method === 'POST';
  const my = await teamRoleOf(env, me.steam_id);
  if (path === '/api/th2h' && !post) {
    if (!my) return json({ team: null, incoming: [], outgoing: [], active: [], past: [], maxSize: TEAMSCORE.size[1], windowDays: TH2H.windowDays });
    const [{ results }, { results: roster }] = await env.DB.batch([
      env.DB.prepare(`${LIST_SQL} WHERE h.challenger = ?1 OR h.opponent = ?1 ORDER BY h.id DESC LIMIT 60`).bind(my.teamId),
      env.DB.prepare(`SELECT m.steam_id, m.role, p.name FROM team_members m LEFT JOIN players p ON p.steam_id = m.steam_id
        WHERE m.team_id = ? ORDER BY p.name`).bind(my.teamId),
    ]);
    const evIds = results.filter((r) => r.event_id).map((r) => r.event_id);
    const names = new Map();
    const live = results.filter((r) => r.event_id && r.status === 'accepted').map((r) => r.event_id);
    const lineups = await lineupsOf(env, evIds);
    const ids = [...new Set([...lineups.values()].flatMap((m) => [...m.values()].flat()))];
    if (ids.length) {
      for (const p of (await env.DB.prepare('SELECT steam_id, name FROM players WHERE steam_id IN (SELECT value FROM json_each(?))')
        .bind(JSON.stringify(ids)).all()).results) names.set(p.steam_id, p.name);
    }
    const knows = new Set(live.length ? (await env.DB.prepare(`SELECT e.id FROM league_events e WHERE e.id IN (SELECT value FROM json_each(?1))
      AND (EXISTS (SELECT 1 FROM league_entries x WHERE x.event_id = e.id AND x.steam_id = ?2)
        OR EXISTS (SELECT 1 FROM event_reveals r WHERE r.event_id = e.id AND r.steam_id = ?2))`).bind(JSON.stringify(live), me.steam_id).all())
      .results.map((r) => r.id) : []);
    // the matches under way as they stand (a few: a team has few at once); those over show their settled result
    const rows = new Map();
    for (const id of live.slice(0, 6)) rows.set(id, await matchRows(env, id, now));   // (2 queries each: the free plan allows 50 a request)
    const all = results.map((r) => out(r, my.teamId, me.steam_id, knows, r.event_id ? lineups.get(r.event_id) || new Map() : null,
      rows.get(r.event_id), names, r.status === 'settled'));
    return json({
      team: { id: my.teamId, name: my.name, tag: my.tag, role: my.role, runs: runsTeam(my.role),
        drivers: roster.map((x) => ({ steamId: x.steam_id, name: x.name || 'Driver' })) },
      incoming: all.filter((h) => h.status === 'sent' && h.mine === 'opponent'),
      outgoing: all.filter((h) => h.status === 'sent' && h.mine === 'challenger'),
      active: all.filter((h) => h.status === 'accepted'),
      past: all.filter((h) => !['sent', 'accepted'].includes(h.status)),
      maxSize: TEAMSCORE.size[1], windowDays: TH2H.windowDays, answerHours: TH2H.answerMs / 3600000,
    });
  }
  if (!post) return err('not found', 404);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (me.banned) return err('this account is banned', 403);
  const b = await req.json().catch(() => ({})) || {};
  if (!my) return err('you are in no team: join or make one on /teams', 403);
  const runs = runsTeam(my.role);

  if (path === '/api/th2h') {
    if (!runs) return err('only the team\'s captain and managers challenge other teams', 403);
    return challenge(env, me, my, String(b.opponent || ''), b.event || {}, b.scoring, now, { json, err });
  }
  const rm = path.match(/^\/api\/th2h\/(\d+)\/rematch$/);
  if (rm) {
    const h = await env.DB.prepare('SELECT * FROM team_h2h WHERE id = ?').bind(+rm[1]).first();
    if (!h || (h.challenger !== my.teamId && h.opponent !== my.teamId)) return err('no such team 1V1', 404);
    if (!runs) return err('only the team\'s captain and managers challenge other teams', 403);
    if (h.status !== 'settled') return err('a rematch comes once the 1V1 is over', 409);
    const spec = JSON.parse(h.spec), len = Math.min(spec.closes - spec.opens, TH2H.windowDays * 86400000);
    const name = /^Rematch: /.test(spec.name) ? spec.name : `Rematch: ${spec.name}`;
    return challenge(env, me, my, h.challenger === my.teamId ? h.opponent : h.challenger,
      { name, rally: spec.rally, car: spec.car, carClass: spec.car_class, rules: spec.rules, stages: spec.stages,
        hide: spec.hide || { weather: false, times: false, stages: false }, opens: now, closes: now + Math.max(len, 2 * 3600000) },
      spec.scoring, now, { json, err });
  }
  const m = path.match(/^\/api\/th2h\/(\d+)\/(accept|decline|cancel|lineup)$/);
  if (!m) return err('not found', 404);
  const h = await env.DB.prepare('SELECT * FROM team_h2h WHERE id = ?').bind(+m[1]).first();
  if (!h || (h.challenger !== my.teamId && h.opponent !== my.teamId)) return err('no such team 1V1', 404);
  const spec = JSON.parse(h.spec);
  if (!runs) return err('only the team\'s captain and managers can do that', 403);
  const otherTeam = h.challenger === my.teamId ? h.opponent : h.challenger;
  if (m[2] === 'lineup') {                                // my team's named lineup
    if (h.status !== 'accepted' || !h.event_id) return err('the lineup is named once the 1V1 is accepted', 409);
    if (spec.scoring.lineup !== 'named') return err('every driver of the team can drive this one', 409);
    const ev = await env.DB.prepare('SELECT * FROM league_events WHERE id = ?').bind(h.event_id).first();
    const [{ results: pool }, lineup] = await Promise.all([
      env.DB.prepare('SELECT steam_id FROM team_members WHERE team_id = ?').bind(my.teamId).all(),
      lineupsOf(env, [h.event_id]),
    ]);
    const mine = (lineup.get(h.event_id) || new Map()).get(my.teamId) || [];
    const r = await nameLineup(env, ev, h.holder, my.teamId, b.steamIds, me.steam_id, now, { size: spec.scoring.size,
      pool: pool.map((x) => x.steam_id), other: (lineup.get(h.event_id) || new Map()).get(otherTeam) || [] });
    if (r.error) return err(r.error, r.status || 400);
    const added = r.value.filter((x) => !mine.includes(x));    // (a notice to each driver newly named)
    if (added.length) {
      await noticesStmt(env, 'h2h', added.map((to) => ({ to, body: `${my.name}: you drive ${spec.name} for the team. Drive it in the ACR Daily app, under 1V1, by ${new Date(ev.closes).toISOString().slice(0, 16).replace('T', ' ')} UTC.` })),
        REF(h.id), now).run();
    }
    return json({ lineup: r.value });
  }
  if (h.status !== 'sent') return err(`this challenge is ${h.status}`, 409);
  if (m[2] === 'decline' || m[2] === 'cancel') {
    if ((m[2] === 'decline') !== (h.opponent === my.teamId)) return err(m[2] === 'decline' ? 'only the challenged team declines' : 'only the challenging team cancels', 403);
    const status = m[2] === 'decline' ? 'declined' : 'cancelled';
    const done = ['EXISTS (SELECT 1 FROM team_h2h WHERE id = ? AND status = ? AND answered = ?)', [h.id, status, now]];
    await env.DB.batch([
      env.DB.prepare("UPDATE team_h2h SET status = ?, answered = ?, answered_by = ? WHERE id = ? AND status = 'sent'").bind(status, now, me.steam_id, h.id),
      runnersNoticeStmt(env, 'h2h', otherTeam, `${my.name} ${status} the team 1V1 ${spec.name}.`, REF(h.id), now, ...done),
    ]);
    const after = await env.DB.prepare('SELECT status FROM team_h2h WHERE id = ?').bind(h.id).first();
    return after.status === status ? json({ status }) : err(`this challenge is ${after.status}`, 409);
  }
  if (h.opponent !== my.teamId) return err('only the challenged team accepts', 403);
  if (now >= h.answer_by) return err('too late: it has expired', 409);
  const r = await env.DB.prepare("UPDATE team_h2h SET status = 'accepted', answered = ?, answered_by = ? WHERE id = ? AND status = 'sent'")
    .bind(now, me.steam_id, h.id).run();
  if (!r.meta.changes) return err('this challenge was answered already', 409);
  const eventId = await openMatch(env, { ...h, status: 'accepted' }, spec, now);
  return json({ status: 'accepted', eventId });
}

/** A challenge from `my` team (me its captain or a manager) to team oppId. -> the response: {id, status: 'sent'}. */
async function challenge(env, me, my, oppId, ev, scoringIn, now, { json, err }) {
  const opp = await env.DB.prepare('SELECT id, name, tag FROM teams WHERE id = ?').bind(oppId).first();
  if (!opp) return err('no such team', 404);
  if (opp.id === my.teamId) return err('challenge another team', 409);
  const open = await env.DB.prepare("SELECT COUNT(*) AS n FROM team_h2h WHERE challenger = ? AND status = 'sent'").bind(my.teamId).first();
  if (open.n >= TH2H.pending) return err(`${TH2H.pending} challenges waiting for an answer at most`, 409);
  const sc = checkScoring(scoringIn);
  if (sc.error) return err(sc.error);
  const c = await checkMatchSpec(env, { ...ev, name: text(ev.name, LIMITS.name) || `${my.name} vs ${opp.name}`.slice(0, LIMITS.name) }, now);
  if (c.error) return err(c.error);
  const spec = { ...c.value, scoring: sc.value };
  if (spec.closes - spec.opens > TH2H.windowDays * 86400000 || spec.opens > now + TH2H.windowDays * 86400000) {
    return err(`a team 1V1 is open for ${TH2H.windowDays} days at most, from within the next ${TH2H.windowDays} days`);
  }
  const answerBy = Math.min(now + TH2H.answerMs, spec.closes - 3600000);
  const n = spec.stages.length;
  const said = `${label({ name: my.name, tag: my.tag })} challenges your team to ${spec.name}: ${spec.rally}, ${n} stage${n > 1 ? 's' : ''}; ` +
    `${describeScoring(sc.value)}. Answer on the website by ${new Date(answerBy).toISOString().slice(0, 16).replace('T', ' ')} UTC.`;
  const r = await env.DB.prepare(`INSERT INTO team_h2h (challenger, opponent, by, spec, status, created, answer_by)
    VALUES (?, ?, ?, ?, 'sent', ?, ?)`).bind(my.teamId, opp.id, me.steam_id, JSON.stringify(spec), now, answerBy).run();
  const id = r.meta.last_row_id;
  await runnersNoticeStmt(env, 'h2h', opp.id, said, REF(id), now).run();
  return json({ id, status: 'sent' });
}

/** An accepted team 1V1's match: its holder, its event and (open) its lineups: every driver of both teams now. Also the
 *  cron's, if accepting stopped half-way. */
async function openMatch(env, h, spec, now) {
  const teams = await env.DB.prepare('SELECT id, name, tag FROM teams WHERE id IN (?, ?)').bind(h.challenger, h.opponent).all();
  const nameOf = (id) => label(teams.results.find((t) => t.id === id), 'a team');
  let holder = h.holder;
  if (!holder) {
    holder = await makeHolder(env, { kind: 'th2h', name: `Team 1V1: ${nameOf(h.challenger)} vs ${nameOf(h.opponent)}`, owner: h.by }, now);
    await env.DB.prepare('UPDATE team_h2h SET holder = ? WHERE id = ?').bind(holder, h.id).run();
  }
  let eventId = h.event_id;
  if (!eventId) {
    eventId = await makeMatchEvent(env, holder, spec, spec.name, [], spec.opens, Math.max(spec.closes, now + 3600000), now);
    await env.DB.prepare('UPDATE team_h2h SET event_id = ? WHERE id = ?').bind(eventId, h.id).run();
  }
  const named = spec.scoring.lineup === 'named';
  const rows = named ? [] : (await env.DB.prepare('SELECT steam_id, team_id FROM team_members WHERE team_id IN (?, ?)').bind(h.challenger, h.opponent).all())
    .results.map((x) => ({ team: x.team_id, sid: x.steam_id }));
  const drive = named ? `Each team's captain or a manager names its ${spec.scoring.size} driver${spec.scoring.size > 1 ? 's' : ''} on the website; they drive it`
    : 'Drive it';
  await env.DB.batch([
    ...lineupStmts(env, eventId, holder, rows, null, now),
    teamNoticesStmt(env, 'h2h', [h.challenger, h.opponent].map((id) => ({ id,
      body: `${nameOf(h.opponent)} accepted ${spec.name} against ${nameOf(h.challenger)}. ${drive} in the ACR Daily app, under 1V1, by ${new Date(spec.closes).toISOString().slice(0, 16).replace('T', ' ')} UTC.` })),
    REF(h.id), now),
  ]);
  return eventId;
}

/** The cron's part: challenges not answered in time expire, an accepted one without its match gets it, and those over
 *  are settled. -> [{id, status, winner}] */
export async function th2hTick(env, now) {
  const out = [];
  const { results: due } = await env.DB.prepare(`SELECT h.* FROM team_h2h h LEFT JOIN league_events e ON e.id = h.event_id
    WHERE (h.status = 'sent' AND h.answer_by <= ?1)
       OR (h.status = 'accepted' AND (h.event_id IS NULL OR e.id IS NULL OR e.closes + ?2 <= ?1
         OR (json_extract(h.spec, '$.scoring.lineup') = 'named'
           AND (SELECT COUNT(*) FROM team_lineups l WHERE l.event_id = h.event_id) >= 2 * json_extract(h.spec, '$.scoring.size')
           AND NOT EXISTS (SELECT 1 FROM team_lineups l LEFT JOIN league_entries x ON x.event_id = l.event_id AND x.steam_id = l.steam_id
             WHERE l.event_id = h.event_id AND (x.steam_id IS NULL OR (x.status = 'running' AND x.dsq IS NULL))))))
    ORDER BY h.id LIMIT 3`).bind(now, LIMITS.graceMs).all();
  for (const h of due) {
    const spec = JSON.parse(h.spec);
    if (h.status === 'sent') {
      const done = ["EXISTS (SELECT 1 FROM team_h2h WHERE id = ? AND status = 'expired' AND answered = ?)", [h.id, now]];
      await env.DB.batch([
        env.DB.prepare("UPDATE team_h2h SET status = 'expired', answered = ? WHERE id = ? AND status = 'sent'").bind(now, h.id),
        runnersNoticeStmt(env, 'h2h', h.challenger, `${spec.name} was not answered in time.`, REF(h.id), now, ...done),
      ]);
      out.push({ id: h.id, status: 'expired' });
      continue;
    }
    if (!h.event_id || !h.holder) { await openMatch(env, h, spec, now); continue; }
    const [rows, lineups, teams] = await Promise.all([matchRows(env, h.event_id, now), lineupsOf(env, [h.event_id]),
      env.DB.prepare('SELECT id, name, tag FROM teams WHERE id IN (?, ?)').bind(h.challenger, h.opponent).all()]);
    const d = decideMatch(rows, h.challenger, h.opponent, lineups.get(h.event_id) || new Map(), spec.scoring);
    const wn = d.winner ? label(teams.results.find((t) => t.id === d.winner), 'a team') : null;
    const said = d.winner ? `${wn} won ${spec.name} (${d.note}).` : `${spec.name}: no contest (${d.note}).`;
    const cond = "EXISTS (SELECT 1 FROM team_h2h WHERE id = ? AND status = 'settled' AND settled = ?)";
    try {
      await env.DB.batch([
        env.DB.prepare("UPDATE team_h2h SET status = 'settled', winner = ?, note = ?, result = ?, settled = ? WHERE id = ? AND status = 'accepted'")
          .bind(d.winner, d.note, JSON.stringify(d.result), now, h.id),
        env.DB.prepare(`UPDATE league_events SET closes = ? WHERE id = ? AND closes > ? AND ${cond}`).bind(now, h.event_id, now, h.id, now),
        env.DB.prepare(`UPDATE league_events SET hide = NULL WHERE id = ? AND ${cond}`).bind(h.event_id, h.id, now),
        teamNoticesStmt(env, 'h2h', [h.challenger, h.opponent].map((id) => ({ id, body: said })), REF(h.id), now, cond, [h.id, now]),
      ]);
    } catch (e) {
      if (!clash(e)) throw e;
    }
    out.push({ id: h.id, status: 'settled', winner: d.winner });
  }
  return out;
}
