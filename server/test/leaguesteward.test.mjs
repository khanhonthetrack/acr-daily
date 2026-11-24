// The car's damage kept with a stage (0046: the app read it at the finish line; after a crash past the line the driver
// goes on from the next stage with it), and the stewards' decisions on entries: a DNF taken back, an entry retired, a
// stage's time set (24 Nov 2026). On a real SQLite (schema.sql) through a stand-in for D1.
import test from 'node:test';
import assert from 'node:assert/strict';
import { carDamage, leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 24, 18, 0);
const [ANN, BEN, CAT] = [sid(1), sid(2), sid(3)];
const STAGES = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' },
  { track: 'Wales Sweet Lamb', day: 1, service: false, weather: 'Clear', time: '10:00' },
  { track: 'Wales Afon Biga', day: 1, service: false, weather: 'Clear', time: '11:00' }];

function world() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CAT, 'Cat']]) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('club0001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('club0001', ?, 0, 'member'), ('club0001', ?, 0, 'member')").run(BEN, CAT);
  const id = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('club0001', 'Round 1', 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0, NULL)`).run(JSON.stringify(STAGES),
    NOW - 3600000, NOW + 86400000).lastInsertRowid;
  return { ...f, id };
}

const call = async (env, path, me, body = null) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.2.1 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, { steam_id: me, name: 'x' }, true, NOW);
  return { status: res.status, body: await res.json() };
};
const mine = async (env, id, who) => (await call(env, '/api/me/events', who)).body.events.find((e) => e.id === id).entry;

test('the car at the finish line is kept with the stage, for the next one after a crash', async () => {
  const { env, id } = world();
  await call(env, `/api/events/${id}/start`, BEN, { car: 'Skoda Fabia RS Rally2', at: NOW - 600000 });
  const r = await call(env, `/api/events/${id}/stage`, BEN, { no: 0, timeMs: 250000, penaltyMs: 0,
    damage: { Engine: 40, Radiator: 25.04, 'bad key!': 3, Gearbox: 120, Bodywork: -1 } });
  assert.deepEqual(r.body, { done: 1, status: 'running' });
  assert.deepEqual((await mine(env, id, BEN)).damage, { no: 0, parts: { Engine: 40, Radiator: 25 } });
  // the next stage sent by an app that read none (an older one): no car kept (it would be another stage's)
  await call(env, `/api/events/${id}/begin`, BEN, { no: 1, at: NOW - 300000 });
  await call(env, `/api/events/${id}/stage`, BEN, { no: 1, timeMs: 150000, penaltyMs: 0 });
  assert.equal((await mine(env, id, BEN)).damage, null);
  // a DNF that says where the car was: kept (the stewards may take the DNF back)
  await call(env, `/api/events/${id}/begin`, BEN, { no: 2, at: NOW - 100000 });
  await call(env, `/api/events/${id}/dnf`, BEN, { no: 2, reason: 'left from the results', damage: { Engine: 10 } });
  assert.deepEqual((await mine(env, id, BEN)).damage, { no: 2, parts: { Engine: 10 } });
  assert.equal(carDamage(null, 0), null);
  assert.equal(carDamage({ Engine: 50 }, -1), null);
});

test('the stewards take a DNF back, retire an entry, and set a stage\'s time; everyone sees each decision', async () => {
  const { env, id } = world();
  await call(env, `/api/events/${id}/start`, BEN, { car: 'Skoda Fabia RS Rally2', at: NOW - 600000 });
  await call(env, `/api/events/${id}/stage`, BEN, { no: 0, timeMs: 250000, penaltyMs: 0, damage: { Engine: 40 } });
  await call(env, `/api/events/${id}/begin`, BEN, { no: 1, at: NOW - 300000 });
  await call(env, `/api/events/${id}/dnf`, BEN, { no: 1, reason: 'the game closed before saving its official result' });
  // only staff
  assert.equal((await call(env, `/api/events/${id}/steward`, CAT, { steamId: BEN, op: 'reinstate', reason: 'game crash' })).status, 403);
  assert.equal((await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'reinstate', reason: '' })).status, 400);
  // the lost finish entered: the entry moves on, the DNF gone
  const t = await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'time', stage: 2, timeMs: 160000, penaltyMs: 5000,
    reason: 'finish-line time from the driver\'s video' });
  assert.deepEqual(t.body, { done: 2, status: 'running' });
  let e = await mine(env, id, BEN);
  assert.deepEqual([e.status, e.done, e.totalMs], ['running', 2, 415000]);
  // a counted time corrected: the total follows
  await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'time', stage: 1, timeMs: 248000, penaltyMs: 0, reason: 'timing fix' });
  assert.equal((await mine(env, id, BEN)).totalMs, 413000);
  // no time given: refused
  assert.equal((await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'time', stage: 3, timeMs: 0, reason: 'x x x' })).status, 400);
  // retired by the stewards, then taken back
  await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'retire', reason: 'drove off the route' });
  e = await mine(env, id, BEN);
  assert.equal(e.status, 'dnf');
  assert.equal((await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'retire', reason: 'again' })).status, 409);
  const back = await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'reinstate', reason: 'appeal upheld' });
  assert.deepEqual(back.body, { status: 'running', done: 2 });
  // every decision on the event's page, in order
  const d = (await call(env, `/api/events/${id}`, CAT)).body.decisions.filter((x) => x.kind !== 'time');
  assert.deepEqual(d.map((x) => [x.kind, x.stage, x.ms, x.reason]), [
    ['settime', 2, 165000, 'finish-line time from the driver\'s video'], ['settime', 1, 248000, 'timing fix'],
    ['retire', 3, 0, 'drove off the route'], ['reinstate', 3, 0, 'appeal upheld']]);
});

test('times go in order: a stage past the next one is refused', async () => {
  const { env, id } = world();
  await call(env, `/api/events/${id}/start`, BEN, { car: 'Skoda Fabia RS Rally2', at: NOW - 600000 });
  const r = await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'time', stage: 3, timeMs: 200000, reason: 'too early' });
  assert.equal(r.status, 409);
  assert.equal((await call(env, `/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'reinstate', reason: 'not a DNF' })).status, 409);
});
