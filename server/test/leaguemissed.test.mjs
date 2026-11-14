// A league stage the game's rally shows driven while ACR Daily was not watching (from app 0.1.5, POST
// /api/events/:id/missed): with the event's retirement rule it counts as retired (its slowest time + the rule's
// minutes) and the entry goes on; without the rule, a DNF as before. On a real SQLite (schema.sql) through a stand-in for D1.
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 14, 18, 0);
const [ANN, BEN] = [sid(1), sid(2)];
const STAGES = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' },
  { track: 'Wales Sweet Lamb', day: 1, service: false, weather: 'Clear', time: '10:00' },
  { track: 'Wales Afon Biga', day: 2, service: true, weather: 'Clear', time: '09:00' }];

function world(rules) {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben']]) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('pub00001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('pub00001', ?, 0, 'member'), ('pub00001', ?, 0, 'member')").run(ANN, BEN);
  const id = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('pub00001', 'Round 1', 'Wales', 'Ford Fiesta Rally2', ?, ?, ?, ?, 0, NULL)`).run(JSON.stringify(rules), JSON.stringify(STAGES),
    NOW - 3600000, NOW + 86400000).lastInsertRowid;
  // Ann has driven all three; Ben SS1 (with the app), then SS2 without it
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated)
    VALUES (?, ?, 'Ford Fiesta Rally2', 'finished', 3, NULL, 600000, 0, 0)`).run(id, ANN);
  db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, splits, started, created)
    VALUES (?1, ?2, 0, 250000, 0, NULL, 0, 0), (?1, ?2, 1, 150000, 10000, NULL, 0, 0), (?1, ?2, 2, 190000, 0, NULL, 0, 0)`).run(id, ANN);
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated)
    VALUES (?, ?, 'Ford Fiesta Rally2', 'running', 1, NULL, 240000, 0, 0)`).run(id, BEN);
  db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, splits, started, created)
    VALUES (?, ?, 0, 240000, 0, NULL, 0, 0)`).run(id, BEN);
  return { ...f, id };
}

const call = async (env, path, me, body = null) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.5 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, { steam_id: me, name: 'x' }, true, NOW);
  return { status: res.status, body: await res.json() };
};

test('with the retirement rule: the stage counts as retired, at its slowest + N minutes, and the entry goes on', async () => {
  const { env, id } = world({ retire: 5 });
  const r = await call(env, `/api/events/${id}/missed`, BEN, { no: 1, reason: 'SS2 was driven without ACR Daily watching' });
  assert.deepEqual(r.body, { done: 2, status: 'running', retired: true });
  assert.equal((await call(env, `/api/events/${id}/missed`, BEN, { no: 1 })).status, 409);   // (SS3 next now)
  // SS3 driven with the app: Ben finishes
  assert.equal((await call(env, `/api/events/${id}/begin`, BEN, { no: 2, at: NOW - 60000 })).body.status, 'running');
  assert.equal((await call(env, `/api/events/${id}/stage`, BEN, { no: 2, timeMs: 180000, penaltyMs: 0 })).body.status, 'finished');
  const st = (await call(env, `/api/events/${id}`, BEN)).body.standings;
  // Ben: 240 + (SS2's slowest, Ann's 160, + 300) + 180 = 880 s; behind Ann (2 driven stages to her 3)
  assert.deepEqual(st.map((x) => [x.name, x.status, x.rank, x.totalMs]), [['Ann', 'finished', 1, 600000], ['Ben', 'finished', 2, 880000]]);
  assert.deepEqual(st[1].stages.map((x) => [x.totalMs, !!x.retired]), [[240000, false], [460000, true], [180000, false]]);
  assert.equal(st[1].stages[1].reason, 'SS2 was driven without ACR Daily watching');
});

test('without the rule: a DNF, as before', async () => {
  const { env, id } = world({});
  const r = await call(env, `/api/events/${id}/missed`, BEN, { no: 1, reason: 'SS2 was driven without ACR Daily watching' });
  assert.deepEqual(r.body, { status: 'dnf', reason: 'SS2 was driven without ACR Daily watching' });
  const st = (await call(env, `/api/events/${id}`, BEN)).body.standings;
  assert.deepEqual(st.map((x) => [x.name, x.status, x.rank ?? null]), [['Ann', 'finished', 1], ['Ben', 'dnf', null]]);
});
