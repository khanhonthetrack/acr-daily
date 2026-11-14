// Team cups (src/teamcups.js) on a real SQLite (schema.sql, node:sqlite): teams sign up with rosters, a short roster is
// out at the start, the rest seeded by team rating; rounds open with their matches' lineups, are decided by the scoring
// (the higher seed on a dead heat), the final places them; lineups named per match; who may do what; few queries.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkTeamCup, tcupsApi, tcupsTick, teamRating } from '../src/teamcups.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { LIMITS } from '../src/leagues.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const NOW = Date.UTC(2026, 10, 13, 12, 0);
const STARTS = NOW + 24 * H;
const CAR = 'Hyundai i20 N Rally2';
const EVENT = { rally: 'Alsace', car: CAR, rules: {}, stages: [{ track: 'Alsace Obersteigen', day: 1, service: true, weather: 'Clear', time: '14:00' }],
  hide: { weather: false, times: false, stages: false } };
// five teams of three (t1 the best rated ... t5); team i's drivers: sid(10 i + 1..3), the first its captain
const TEAMS = [1, 2, 3, 4, 5].map((i) => ({ id: `team000${i}`, name: `Team ${i}`, tag: `T${i}`, drivers: [1, 2, 3].map((k) => sid(10 * i + k)) }));
const MAKER = sid(99);

function setup() {
  const f = fakeD1();
  const { db } = f;
  db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Alsace Obersteigen', '[]', 2000, 0, 'AlsaceS1ObersteigenFullForward')").run();
  db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Maker', 0)").run(MAKER);
  for (const [i, t] of TEAMS.entries()) {
    db.prepare(`INSERT INTO teams (id, name, tag, tag_key, color, captain, code, created) VALUES (?, ?, ?, ?, '#E30613', ?, ?, 0)`)
      .run(t.id, t.name, t.tag, t.tag, t.drivers[0], `CODE000${i}`);
    for (const [k, s] of t.drivers.entries()) {
      db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, `${t.tag}-${k + 1}`);
      db.prepare('INSERT INTO team_members (steam_id, team_id, joined, role) VALUES (?, ?, 0, ?)').run(s, t.id, k === 1 ? 'manager' : 'member');
      db.prepare('INSERT INTO ratings (steam_id, rating, races, peak, updated) VALUES (?, ?, 1, 0, 0)').run(s, 2000 - 100 * i - k);
    }
  }
  return f;
}
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const err = (error, status = 400) => json({ error }, status);
async function call(env, who, path, body = null, now = NOW) {
  const req = new Request(`https://acrdaily.com${path}`, body ? { method: 'POST', body: JSON.stringify(body) } : {});
  const res = await tcupsApi(req, env, path, who ? { steam_id: who, name: 'x' } : null, true, now, { json, err });
  return { status: res.status, body: await res.json() };
}
const ok = async (p) => { const r = await p; assert.ok(r.status < 300, JSON.stringify(r.body)); return r.body; };
async function drive(env, who, eventId, s, now) {
  const go = async (action, body) => {
    const url = new URL(`https://acrdaily.com/api/events/${eventId}/${action}`);
    const res = await leaguesApi(new Request(url, { method: 'POST', body: JSON.stringify(body), headers: { 'User-Agent': 'ACR-Daily/0.1.2 public' } }),
      env, url.pathname, url, { steam_id: who, name: 'x' }, true, now);
    return { status: res.status, body: await res.json() };
  };
  await ok(go('start', { car: CAR, at: now }));
  await ok(go('stage', { no: 0, timeMs: s * 1000, penaltyMs: 0 }));
}
const newCup = (env, extra = {}) => ok(call(env, MAKER, '/api/tcups', { name: 'Team Cup', size: 8, event: EVENT, starts: STARTS, roundHours: 24,
  scoring: { preset: 'top', best: 2 }, rosterMin: 2, rosterMax: 3, ...extra }));

test('a team cup\'s form: sizes, rosters, scoring, the named lineup\'s rosters', async () => {
  const { env } = setup();
  const base = { name: 'Cup', size: 8, event: EVENT, starts: STARTS, roundHours: 24, scoring: { preset: 'top' } };
  assert.match((await checkTeamCup(env, { ...base, size: 128 }, NOW)).error, /size/);
  assert.match((await checkTeamCup(env, { ...base, rosterMin: 4, rosterMax: 2 }, NOW)).error, /roster/);
  const cupWide = await checkTeamCup(env, { ...base, scoring: { preset: 'named', size: 4 }, lineupFor: 'cup' }, NOW);
  assert.deepEqual([cupWide.value.rosterMin, cupWide.value.rosterMax, cupWide.value.spec.lineupFor], [4, 4, 'cup']);
  assert.match((await checkTeamCup(env, { ...base, scoring: { preset: 'named', size: 3 }, rosterMin: 2 }, NOW)).error, /at least 3/);
  assert.equal(teamRating([2000, null, 1800], 2), 1900);
});

test('sign-ups: a team\'s captain or manager, with a roster of its own drivers, one roster a driver', async () => {
  const { env, db } = setup();
  const { id } = await newCup(env);
  const [t1, t2] = TEAMS;
  assert.equal((await call(env, t1.drivers[2], `/api/tcups/${id}/join`, { steamIds: t1.drivers })).status, 403, 'a plain driver');
  assert.match((await call(env, t1.drivers[0], `/api/tcups/${id}/join`, { steamIds: [t1.drivers[0]] })).body.error, /2 to 3/);
  assert.match((await call(env, t1.drivers[0], `/api/tcups/${id}/join`, { steamIds: [t1.drivers[0], t2.drivers[0]] })).body.error, /your team's drivers/);
  await ok(call(env, t1.drivers[1], `/api/tcups/${id}/join`, { steamIds: t1.drivers.slice(0, 2) }));
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE ref = ?").get(`tcup:${id}`).n, 1, 'the other driver told');
  await ok(call(env, t1.drivers[0], `/api/tcups/${id}/roster`, { steamIds: t1.drivers }));
  const v = await ok(call(env, t1.drivers[2], `/api/tcups/${id}`));
  assert.deepEqual(v.teams.map((t) => [t.name, t.roster.length]), [['Team 1', 3]]);
  assert.equal(v.me.onRoster, true);
  await ok(call(env, t1.drivers[2], `/api/tcups/${id}/withdraw`, {}));
  await ok(call(env, t1.drivers[0], `/api/tcups/${id}/leave`, {}));
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM team_cup_roster').get().n, 0);
});

test('a cup of five teams: a short roster out, four seeded by rating, semi-finals, the final, places', async () => {
  const { env, db, count } = setup();
  const { id } = await newCup(env);
  for (const t of TEAMS.slice(0, 4)) await ok(call(env, t.drivers[0], `/api/tcups/${id}/join`, { steamIds: t.drivers }));
  await ok(call(env, TEAMS[4].drivers[0], `/api/tcups/${id}/join`, { steamIds: TEAMS[4].drivers.slice(0, 2) }));
  db.prepare('DELETE FROM team_cup_roster WHERE steam_id = ?').run(TEAMS[4].drivers[1]);   // (Team 5 one short at the start)
  count.queries = 0;
  assert.deepEqual(await tcupsTick(env, STARTS), [{ cup: id, did: 'started' }]);
  assert.ok(count.queries <= 10, `${count.queries} queries`);
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ? ORDER BY rowid DESC').get(TEAMS[4].drivers[0]).body, /without your team/);
  // seeds by rating: 1 v 4, 2 v 3; each match's lineup: both rosters; only they drive it
  const ms = db.prepare('SELECT * FROM team_cup_matches ORDER BY slot').all();
  assert.deepEqual(ms.map((m) => [m.a, m.b]), [['team0001', 'team0004'], ['team0002', 'team0003']]);
  assert.equal(JSON.parse(db.prepare('SELECT only_ids FROM league_events WHERE id = ?').get(ms[0].event_id).only_ids).length, 6);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE 'Team Cup, semi-final: %'").get().n, 12);
  // semi 1: Team 4 faster (best two: 200 v 230); semi 2: nobody finishes: the higher seed (Team 2)
  const at = STARTS + H;
  for (const [s, t] of [[TEAMS[0].drivers[0], 110], [TEAMS[0].drivers[1], 120], [TEAMS[3].drivers[0], 100], [TEAMS[3].drivers[1], 100]]) {
    await drive(env, s, ms[0].event_id, t, at);
  }
  const page = await ok(call(env, MAKER, `/api/tcups/${id}`, null, at));
  assert.deepEqual(page.matches[0].teams.map((t) => [t.name, t.score]), [['Team 1', 230000], ['Team 4', 200000]]);
  const close = STARTS + 24 * H + LIMITS.graceMs;
  assert.deepEqual(await tcupsTick(env, close), [{ cup: id, did: 'round 2' }]);
  const done = db.prepare('SELECT winner, note FROM team_cup_matches WHERE round = 1 ORDER BY slot').all().map((x) => ({ ...x }));
  assert.deepEqual(done, [{ winner: 'team0004', note: 'by 30.000 s' }, { winner: 'team0002', note: 'nobody finished: the higher seed goes through' }]);
  const fin = db.prepare('SELECT * FROM team_cup_matches WHERE round = 2').get();
  assert.deepEqual([fin.a, fin.b], ['team0002', 'team0004']);
  await drive(env, TEAMS[1].drivers[0], fin.event_id, 100, close + H);
  assert.deepEqual(await tcupsTick(env, STARTS + 48 * H + LIMITS.graceMs), [{ cup: id, did: 'finished', winner: 'team0002' }]);
  assert.deepEqual(db.prepare('SELECT team_id, place FROM team_cup_entries ORDER BY place, team_id').all().map((x) => [x.team_id, x.place]),
    [['team0002', 1], ['team0004', 2], ['team0001', 3], ['team0003', 3]]);
  assert.equal(db.prepare('SELECT status FROM team_cups').get().status, 'finished');
});

test('lineups named per match: the captain picks from the roster; nobody else drives', async () => {
  const { env, db } = setup();
  const { id } = await newCup(env, { scoring: { preset: 'named', size: 2 }, lineupFor: 'match', rosterMin: 2, rosterMax: 3 });
  for (const t of TEAMS.slice(0, 2)) await ok(call(env, t.drivers[0], `/api/tcups/${id}/join`, { steamIds: t.drivers }));
  await tcupsTick(env, STARTS);
  const m = db.prepare('SELECT * FROM team_cup_matches').get();
  assert.equal(db.prepare('SELECT only_ids FROM league_events WHERE id = ?').get(m.event_id).only_ids, '[]');
  const [a, b] = TEAMS;
  assert.equal((await call(env, a.drivers[2], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: [a.drivers[2]] }, STARTS + H)).status, 403);
  assert.match((await call(env, a.drivers[0], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: a.drivers }, STARTS + H)).body.error, /2 drivers at most/);
  await ok(call(env, a.drivers[1], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: [a.drivers[1], a.drivers[2]] }, STARTS + H));
  await ok(call(env, b.drivers[0], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: [b.drivers[0], b.drivers[1]] }, STARTS + H));
  assert.deepEqual(JSON.parse(db.prepare('SELECT only_ids FROM league_events WHERE id = ?').get(m.event_id).only_ids).sort(),
    [a.drivers[1], a.drivers[2], b.drivers[0], b.drivers[1]].sort());
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ? ORDER BY rowid DESC').get(a.drivers[2]).body, /you drive Team 1's match/);
});

test('fewer than two teams with a full roster: called off, told', async () => {
  const { env, db } = setup();
  const { id } = await newCup(env);
  await ok(call(env, TEAMS[0].drivers[0], `/api/tcups/${id}/join`, { steamIds: TEAMS[0].drivers }));
  assert.deepEqual(await tcupsTick(env, STARTS), [{ cup: id, did: 'called off' }]);
  assert.equal(db.prepare('SELECT status FROM team_cups').get().status, 'cancelled');
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE '%did not start%'").get().n, 3);
});

test('before a round closes: drivers who haven\'t driven their team\'s match, and a team that hasn\'t named its lineup, are reminded once', async () => {
  const { env, db } = setup();
  const { id } = await newCup(env, { scoring: { preset: 'named', size: 2 }, lineupFor: 'match', rosterMin: 2, rosterMax: 3 });
  for (const t of TEAMS.slice(0, 2)) await ok(call(env, t.drivers[0], `/api/tcups/${id}/join`, { steamIds: t.drivers }));
  await tcupsTick(env, STARTS);
  const m = db.prepare('SELECT * FROM team_cup_matches').get();
  const [a, b] = TEAMS;
  await ok(call(env, a.drivers[0], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: [a.drivers[0], a.drivers[1]] }, STARTS + H));
  await ok(call(env, b.drivers[0], `/api/tcups/${id}/lineup`, { eventId: m.event_id, steamIds: [b.drivers[0]] }, STARTS + H));
  await drive(env, a.drivers[0], m.event_id, 100, STARTS + H);
  db.prepare('DELETE FROM messages').run();
  assert.deepEqual(await tcupsTick(env, STARTS + 6 * H), [], 'not yet: a day before at most (a 24-hour round: 6 hours)');
  assert.deepEqual(await tcupsTick(env, STARTS + 19 * H), [{ cup: id, did: 'reminded 4' }]);
  const told = db.prepare('SELECT to_id, body FROM messages ORDER BY to_id, body').all().map((x) => [x.to_id, x.body.replace(/ It closes .*| Name them .*/, '')]);
  assert.deepEqual(told, [
    [a.drivers[1], "Team Cup, final: you haven't driven your team's match against [T2] Team 2 yet."],
    [b.drivers[0], 'Team Cup, final: [T2] Team 2 has named 1 of its 2 drivers against [T1] Team 1.'],
    [b.drivers[0], "Team Cup, final: you haven't driven your team's match against [T1] Team 1 yet."],
    [b.drivers[1], 'Team Cup, final: [T2] Team 2 has named 1 of its 2 drivers against [T1] Team 1.'],
  ]);
  assert.deepEqual(await tcupsTick(env, STARTS + 20 * H), [], 'once a round');
});
