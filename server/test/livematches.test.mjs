// Every match being driven right now (src/leaguesapi.js liveMatches, GET /api/events/live): the app's LIVE tab and the
// website's /live page. On a real SQLite (schema.sql, node:sqlite) through a stand-in for D1 that counts the queries.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi, liveMatches } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 8, 18, 0);
const [ANN, BEN, CID, DOT] = [sid(1), sid(2), sid(3), sid(4)];
const STAGES = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' },
  { track: 'Wales Sweet Lamb', day: 1, service: false, weather: 'Clear', time: '10:00' }];

/** A public league's event (Ann on SS2), a private league's (Cid on SS1), a 1V1 (Ben, finished a while ago, and Dot,
 *  gone quiet: off the map) and a cup match nobody drives. */
function world() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CID, 'Cid'], [DOT, 'Dot']]) {
    db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  }
  db.prepare(`INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES
    ('pub00001', 'Sunday Gravel Club', ?, 1, 'CODE0001', 0, 'league'), ('prv00001', 'Secret Club', ?, 0, 'CODE0002', 0, 'league'),
    ('hh000001', '1V1: Ben vs Dot', ?, 1, 'CODE0003', 0, 'h2h'), ('cup00001', 'Autumn Cup', ?, 1, 'CODE0004', 0, 'cup')`).run(ANN, CID, BEN, ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined) VALUES ('prv00001', ?, 0)").run(CID);
  db.prepare(`INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Wales Sweet Lamb', '[[0,0],[1,0]]', 4321.4, 0, NULL),
    ('Wales Afon Biga', '[[0,0],[1,0]]', 9876.2, 0, NULL)`).run();
  const ev = (league, name, car) => db.prepare(`INSERT INTO league_events (league_id, name, rally, car, car_class, rules, stages, opens, closes, created)
    VALUES (?, ?, 'Wales', ?, ?, '{}', ?, ?, ?, 0)`).run(league, name, car, car ? null : 'Rally2/R5', JSON.stringify(STAGES),
    NOW - 3600000, NOW + 86400000).lastInsertRowid;
  const ids = { pub: ev('pub00001', 'Round 3', 'Ford Fiesta Rally2'), prv: ev('prv00001', 'Night Run', null),
    duel: ev('hh000001', 'Ben vs Dot', 'Ford Fiesta Rally2'), cup: ev('cup00001', 'Quarter-final: Ann vs Cid', 'Ford Fiesta Rally2') };
  const live = (event, who, no, p, state, ago) => db.prepare(`INSERT INTO event_live (event_id, steam_id, stage_no, x, z, progress, total_ms, state, updated)
    VALUES (?, ?, ?, 1, 2, ?, 60000, ?, ?)`).run(event, who, no, p, state, NOW - ago);
  live(ids.pub, ANN, 1, 0.4, 'live', 2000);
  live(ids.prv, CID, 0, 0.7, 'live', 3000);
  live(ids.duel, BEN, 0, 1, 'finished', 30000);      // (a finish stays a minute)
  live(ids.duel, DOT, 0, 0.2, 'live', 20000);         // (quiet for 20 s: off the map)
  return { ...f, ids };
}

test('every match being driven: league events, 1V1s and cup matches; a private league\'s for its members only', async () => {
  const { env, ids, count } = world();
  count.queries = 0;
  const r = await liveMatches(env, null, NOW);
  assert.ok(count.queries <= 3, `${count.queries} queries`);
  assert.deepEqual(r.events.map((e) => e.id).sort(), [ids.pub, ids.duel].sort());     // (not the private one, nor the idle cup match)
  const pub = r.events.find((e) => e.id === ids.pub);
  assert.deepEqual({ ...pub, stages: undefined }, { id: ids.pub, name: 'Round 3', kind: 'league', league: 'Sunday Gravel Club',
    leagueId: 'pub00001', rally: 'Wales', car: 'Ford Fiesta Rally2', carClass: null, closes: NOW + 86400000, stages: undefined, hidden: null, revealed: true });
  assert.deepEqual(pub.stages.map((s) => [s.no, s.track, s.lengthM]), [[1, 'Wales Afon Biga', 9876], [2, 'Wales Sweet Lamb', 4321]]);
  assert.equal(r.events.find((e) => e.id === ids.duel).kind, 'h2h');
  assert.deepEqual(r.drivers.map((d) => [d.eventId, d.name, d.stageNo, d.state]).sort(),
    [[ids.duel, 'Ben', 0, 'finished'], [ids.pub, 'Ann', 1, 'live']].sort());
  const member = await liveMatches(env, { steam_id: CID }, NOW);                        // Cid: in the private league
  assert.ok(member.events.some((e) => e.id === ids.prv && e.carClass === 'Rally2/R5'));
});

test('nobody driving: one query, nothing listed', async () => {
  const { env, count } = world();
  count.queries = 0;
  assert.deepEqual(await liveMatches(env, null, NOW + 120000), { now: NOW + 120000, events: [], drivers: [] });
  assert.equal(count.queries, 1);
});

test('GET /api/events/live, signed in or not', async () => {
  const { env, ids } = world();
  const url = new URL('https://acrdaily.com/api/events/live');
  const res = await leaguesApi(new Request(url), env, url.pathname, url, null, true, NOW);
  const body = await res.json();
  assert.equal(res.status, 200);
  assert.deepEqual(body.events.map((e) => e.id).sort(), [ids.pub, ids.duel].sort());
  assert.equal(body.drivers.length, 2);
});
