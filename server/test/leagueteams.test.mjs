// A league's teams and its team championship (src/leagueteams.js through src/leaguesapi.js) on a real SQLite
// (schema.sql, node:sqlite): the settings, the league's own teams and who puts drivers in them, each entry keeping the
// team it was driven for, nominations, the stewards' team penalties, ACR Daily's teams as a league's.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const NOW = Date.UTC(2026, 10, 9, 12, 0);
const [OWN, ANN, BEN, CAT, DAN] = [sid(1), sid(2), sid(3), sid(4), sid(5)];
const NAMES = { [OWN]: 'Olga', [ANN]: 'Ann', [BEN]: 'Ben', [CAT]: 'Cat', [DAN]: 'Dan' };
const STAGES = [{ track: 'Alsace Obersteigen', day: 1, service: true, weather: 'Clear', time: '14:00' }];
const CAR = 'Hyundai i20 N Rally2';

function setup() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of Object.entries(NAMES)) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO leagues (id, name, owner, code, created) VALUES ('lg000001', 'Teams', ?, 'CODE2345', 0)").run(OWN);
  for (const s of Object.keys(NAMES)) db.prepare('INSERT INTO league_members (league_id, steam_id, joined) VALUES (\'lg000001\', ?, 0)').run(s);
  db.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created) VALUES ('lg000001', 'Season 1', ?, '[]', 0, 0)`)
    .run(JSON.stringify({ table: [10, 8, 6, 5], finisher: 1 }));
  for (const [i, opens] of [[1, NOW - H], [2, NOW + 2 * H]]) {
    db.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, rules, stages, opens, closes, created)
      VALUES ('lg000001', 1, ?, 'Alsace', ?, '{}', ?, ?, ?, 0)`).run(`Round ${i}`, CAR, JSON.stringify(STAGES), opens, opens + 24 * H);
  }
  return f;
}

async function call(env, who, path, body = null, now = NOW) {
  const url = new URL(`https://acrdaily.com${path}`);
  const req = new Request(url, body ? { method: 'POST', body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', 'User-Agent': 'ACR-Daily/0.1.2 public' } } : {});
  const res = await leaguesApi(req, env, url.pathname, url, who ? { steam_id: who, name: NAMES[who] } : null, true, now);
  return { status: res.status, body: await res.json() };
}
const ok = async (p) => { const r = await p; assert.ok(r.status < 300, JSON.stringify(r.body)); return r.body; };

/** A driver drives event 1 (one stage) in `s` seconds through the app's calls. */
async function drive(env, who, s, ev = 1, now = NOW) {
  await ok(call(env, who, `/api/events/${ev}/start`, { car: CAR, at: now }, now));
  await ok(call(env, who, `/api/events/${ev}/stage`, { no: 0, timeMs: s * 1000, penaltyMs: 0 }, now));
}

test('the league\'s own teams: staff make them, drivers pick one (as the settings say), full teams, locked transfers', async () => {
  const { env, db } = setup();
  assert.equal((await call(env, ANN, '/api/leagues/lg000001/teams', { source: 'league' })).status, 403, 'only the staff');
  assert.deepEqual(await ok(call(env, OWN, '/api/leagues/lg000001/teams', { source: 'league', pick: 'drivers', max: 2, transfers: 'admins' })),
    { teams: { source: 'league', pick: 'drivers', max: 2, transfers: 'admins' } });
  const red = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Red Team', tag: 'red', color: '#E30613', manager: ANN }))).id;
  const blue = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Blue Team', tag: 'BLU', color: '#5BA8FF' }))).id;
  assert.match((await call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'X' })).body.error, /name/);
  await ok(call(env, ANN, '/api/leagues/lg000001/teamset', { steamId: ANN, teamId: red }));
  await ok(call(env, BEN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: red }));
  assert.match((await call(env, CAT, '/api/leagues/lg000001/teamset', { steamId: CAT, teamId: red })).body.error, /full/);
  assert.equal((await call(env, CAT, '/api/leagues/lg000001/teamset', { steamId: DAN, teamId: blue })).status, 403, 'not someone else');
  await ok(call(env, CAT, '/api/leagues/lg000001/teamset', { steamId: CAT, teamId: blue }));
  await ok(call(env, DAN, '/api/leagues/lg000001/teamset', { steamId: DAN, teamId: blue }));
  // Ann drives round 1 for Red: her entry keeps it; then she can't move herself (transfers by the admins), the owner can
  await drive(env, ANN, 100);
  assert.equal(db.prepare('SELECT team_id FROM league_entries WHERE steam_id = ?').get(ANN).team_id, red);
  assert.match((await call(env, ANN, '/api/leagues/lg000001/teamset', { steamId: ANN, teamId: null })).body.error, /transfers/);
  const l = await ok(call(env, OWN, '/api/leagues/lg000001'));
  assert.deepEqual(l.teams.list.map((t) => [t.name, t.tag, t.drivers.length, t.manager && t.manager.name]),
    [['Red Team', 'RED', 2, 'Ann'], ['Blue Team', 'BLU', 2, null]]);
  assert.deepEqual(l.members.find((m) => m.steamId === ANN).team, { tag: 'RED', color: '#E30613' }, 'the league team\'s tag by her name');
  assert.equal(l.members.find((m) => m.steamId === OWN).team, null, 'no tag for a driver in no league team');
  // Ann's manager: may rename her team, not choose its manager
  await ok(call(env, ANN, '/api/leagues/lg000001/teamedit', { teamId: red, name: 'Red Racing' }));
  assert.equal((await call(env, ANN, '/api/leagues/lg000001/teamedit', { teamId: red, manager: BEN })).status, 403);
});

test('a season\'s team championship: the best 2 drivers\' points per team, points staying with the team driven for, penalties', async () => {
  const { env, db } = setup();
  await ok(call(env, OWN, '/api/leagues/lg000001/teams', { source: 'league', pick: 'admins' }));
  const red = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Red', tag: 'RED' }))).id;
  const blue = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Blue', tag: 'BLU' }))).id;
  for (const [s, t] of [[ANN, red], [BEN, red], [CAT, blue], [DAN, blue]]) await ok(call(env, OWN, '/api/leagues/lg000001/teamset', { steamId: s, teamId: t }));
  assert.equal((await call(env, ANN, '/api/leagues/lg000001/teamset', { steamId: ANN, teamId: blue })).status, 403, 'pick admins');
  await ok(call(env, OWN, '/api/seasons/1/edit', { name: 'Season 1', points: { table: [10, 8, 6, 5], finisher: 1 }, power: [], drop: 0,
    teamChamp: { method: 'drivers', best: 2 } }));
  await drive(env, ANN, 100);
  await drive(env, CAT, 101);
  await drive(env, BEN, 102);
  await drive(env, DAN, 103);
  // after the round, Ben moves to Blue: his 6 points stay with Red
  await ok(call(env, OWN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: blue }));
  let l = await ok(call(env, OWN, '/api/leagues/lg000001'));
  let s = l.seasons[0];
  assert.deepEqual(s.teamChamp, { method: 'drivers', best: 2, nominate: 0, power: true, drop: 0 });
  assert.deepEqual(s.teamStandings.map((t) => [t.name, t.points, t.rank]), [['Red', 16, 1], ['Blue', 13, 2]]);
  assert.deepEqual(s.teamStandings[0].cells[1].counted, [ANN, BEN]);
  // the event's page: each team's points on it, who drove for it
  const e = await ok(call(env, OWN, '/api/events/1'));
  assert.deepEqual(e.teams.results.map((t) => [t.name, t.pts, t.rank, t.drove.length]), [['Red', 16, 1, 2], ['Blue', 13, 2, 2]]);
  assert.equal(e.teams.entryTeams[BEN], red);
  // the stewards: Red loses 5 points (everyone sees why); an entry counted for another team
  await ok(call(env, OWN, '/api/seasons/1/teampenalty', { teamId: red, points: 5, reason: 'unsporting conduct' }));
  assert.match((await call(env, OWN, '/api/seasons/1/teampenalty', { teamId: red, points: 5, reason: '' })).body.error, /reason/);
  await ok(call(env, OWN, '/api/events/1/entryteam', { steamId: BEN, teamId: blue }));
  l = await ok(call(env, OWN, '/api/leagues/lg000001'));
  s = l.seasons[0];
  assert.deepEqual(s.teamStandings.map((t) => [t.name, t.points, t.penalty]), [['Blue', 14, 0], ['Red', 5, 5]]);
  assert.equal(s.teamPenalties[0].reason, 'unsporting conduct');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM league_team_penalties').get().n, 1);
});

test('nominations: each team names its drivers before the event opens (its manager or the staff); only they count', async () => {
  const { env } = setup();
  await ok(call(env, OWN, '/api/leagues/lg000001/teams', { source: 'league', pick: 'admins' }));
  const red = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Red', manager: ANN }))).id;
  const blue = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Blue', manager: CAT }))).id;
  for (const [s, t] of [[ANN, red], [BEN, red], [CAT, blue], [DAN, blue]]) await ok(call(env, OWN, '/api/leagues/lg000001/teamset', { steamId: s, teamId: t }));
  await ok(call(env, OWN, '/api/seasons/1/edit', { name: 'Season 1', points: { table: [10, 8, 6, 5], finisher: 1 }, power: [], drop: 0,
    teamChamp: { method: 'drivers', best: 1, nominate: 1, fallback: 'none' } }));
  // round 2 opens in 2 hours: Ann nominates Ben for Red; Cat can't nominate for Red, nor Ann two drivers
  await ok(call(env, ANN, '/api/events/2/nominate', { teamId: red, steamIds: [BEN] }));
  assert.equal((await call(env, CAT, '/api/events/2/nominate', { teamId: red, steamIds: [ANN] })).status, 403);
  assert.match((await call(env, ANN, '/api/events/2/nominate', { teamId: red, steamIds: [ANN, BEN] })).body.error, /at most/);
  assert.match((await call(env, ANN, '/api/events/2/nominate', { teamId: red, steamIds: [CAT] })).body.error, /team's drivers/);
  // once open: closed to the managers
  const later = NOW + 3 * H;
  assert.match((await call(env, CAT, '/api/events/2/nominate', { teamId: blue, steamIds: [DAN] }, later)).body.error, /close/);
  for (const [s, t] of [[ANN, 100], [CAT, 101], [BEN, 102], [DAN, 103]]) await drive(env, s, t, 2, later);
  const l = await ok(call(env, OWN, '/api/leagues/lg000001', null, later));
  // Red: Ben (6) only; Blue nominated nobody: no points
  assert.deepEqual(l.seasons[0].teamStandings.map((t) => [t.name, t.points]), [['Red', 6], ['Blue', 0]]);
  const e = await ok(call(env, ANN, '/api/events/2', null, later));
  assert.deepEqual(e.teams.results.find((t) => t.id === red).nominated, [BEN]);
});

test('ACR Daily\'s teams as the league\'s: one row each, the entry keeps it, their captain nominates', async () => {
  const { env, db } = setup();
  db.prepare(`INSERT INTO teams (id, name, tag, tag_key, color, captain, code, created) VALUES
    ('tmred001', 'Red Site', 'RS', 'RS', '#E30613', ?, 'AAAA2222', 0), ('tmblu001', 'Blue Site', 'BS', 'BS', '#5BA8FF', ?, 'BBBB2222', 0)`).run(ANN, CAT);
  db.prepare(`INSERT INTO team_members (steam_id, team_id, joined, role) VALUES (?, 'tmred001', 0, 'member'), (?, 'tmred001', 0, 'manager'),
    (?, 'tmblu001', 0, 'member'), (?, 'tmblu001', 0, 'member')`).run(ANN, BEN, CAT, DAN);
  await ok(call(env, OWN, '/api/leagues/lg000001/teams', { source: 'site' }));
  assert.match((await call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Mine' })).body.error, /ACR Daily's/);
  await ok(call(env, OWN, '/api/seasons/1/edit', { name: 'Season 1', points: { table: [10, 8, 6, 5], finisher: 1 }, power: [], drop: 0,
    teamChamp: { method: 'reranked', best: 1, nominate: 2, table: [5, 3] } }));
  let l = await ok(call(env, BEN, '/api/leagues/lg000001'));
  assert.deepEqual(l.teams.list.map((t) => [t.name, t.tag, t.drivers.length]), [['Red Site', 'RS', 2], ['Blue Site', 'BS', 2]]);
  const red = l.teams.list[0].id;
  assert.deepEqual(l.teams.runs, [red], 'Ben manages Red Site');
  await ok(call(env, BEN, '/api/events/2/nominate', { teamId: red, steamIds: [ANN] }));
  await drive(env, CAT, 100);
  assert.equal(db.prepare('SELECT team_id FROM league_entries WHERE steam_id = ?').get(CAT).team_id, l.teams.list[1].id);
  await drive(env, ANN, 101);
  l = await ok(call(env, OWN, '/api/leagues/lg000001'));
  assert.deepEqual(l.seasons[0].teamStandings.map((t) => [t.name, t.points]), [['Blue Site', 5], ['Red Site', 3]]);
  await ok(call(env, OWN, '/api/leagues/lg000001/teams', { off: true }));
  l = await ok(call(env, OWN, '/api/leagues/lg000001'));
  assert.equal(l.teams, null);
  assert.deepEqual(l.seasons[0].teamStandings, []);
});

test('a team\'s manager invites a driver in no team; the driver accepts or declines; the invite can be taken back', async () => {
  const { env, db } = setup();
  await ok(call(env, OWN, '/api/leagues/lg000001/teams', { source: 'league', pick: 'managers', max: 3 }));
  const red = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Red', manager: ANN }))).id;
  const blue = (await ok(call(env, OWN, '/api/leagues/lg000001/teamadd', { name: 'Blue', manager: DAN }))).id;
  await ok(call(env, OWN, '/api/leagues/lg000001/teamset', { steamId: ANN, teamId: red }));
  // a manager no longer puts a driver in directly: they invite them
  assert.equal((await call(env, ANN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: red })).status, 403);
  assert.equal((await call(env, DAN, '/api/leagues/lg000001/teaminvite', { steamId: BEN, teamId: red })).status, 403, 'not Red\'s manager');
  await ok(call(env, ANN, '/api/leagues/lg000001/teaminvite', { steamId: BEN, teamId: red }));
  assert.match(db.prepare("SELECT body, ref FROM messages WHERE to_id = ? AND kind = 'league'").get(BEN).body, /Red invites you to drive for it in Teams/);
  assert.equal((await call(env, BEN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: blue })).status, 403, 'not invited by Blue');
  let l = await ok(call(env, BEN, '/api/leagues/lg000001'));
  assert.equal(l.members.find((m) => m.steamId === BEN).teamInvite, red);
  await ok(call(env, BEN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: red }));
  l = await ok(call(env, BEN, '/api/leagues/lg000001'));
  assert.deepEqual([l.members.find((m) => m.steamId === BEN).teamId, l.members.find((m) => m.steamId === BEN).teamInvite], [red, null]);
  // declined; taken back; a driver in a team can't be invited
  await ok(call(env, ANN, '/api/leagues/lg000001/teaminvite', { steamId: CAT, teamId: red }));
  await ok(call(env, CAT, '/api/leagues/lg000001/teamdecline', {}));
  assert.equal(db.prepare('SELECT team_invite FROM league_members WHERE steam_id = ?').get(CAT).team_invite, null);
  await ok(call(env, DAN, '/api/leagues/lg000001/teaminvite', { steamId: CAT, teamId: blue }));
  assert.equal((await call(env, ANN, '/api/leagues/lg000001/teaminvite', { steamId: CAT, teamId: null })).status, 403, 'not Ann\'s invite');
  await ok(call(env, DAN, '/api/leagues/lg000001/teaminvite', { steamId: CAT, teamId: null }));
  assert.match((await call(env, DAN, '/api/leagues/lg000001/teaminvite', { steamId: BEN, teamId: blue })).body.error, /in a team already/);
  // the manager lets a driver of theirs go; the driver leaves on their own too
  await ok(call(env, ANN, '/api/leagues/lg000001/teamset', { steamId: BEN, teamId: null }));
  assert.equal(db.prepare('SELECT team_id FROM league_members WHERE steam_id = ?').get(BEN).team_id, null);
});
