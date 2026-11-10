// A league stage's start sent twice (src/leaguesapi.js start / begin) on a real SQLite (schema.sql, node:sqlite): the
// same start again (its `at` as before: a retry, or two copies of the app open) is taken once; a start with another
// `at`, or with none (an app before 0.0.28), is a second start and ends the entry, as before.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1 } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 9, 13, 54);
const SID = '76561198000000001';
const STAGES = [{ track: 'Alsace Obersteigen', day: 1, service: true, weather: 'Clear', time: '14:00' },
  { track: 'Alsace Obersteigen', day: 1, service: true, weather: 'Clear', time: '16:00' }];

function setup() {
  const f = fakeD1();
  f.db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Driver', 0)").run(SID);
  f.db.prepare("INSERT INTO leagues (id, name, owner, code, created) VALUES ('lg000001', 'Test', ?, 'CODE2345', 0)").run(SID);
  f.db.prepare("INSERT INTO league_members (league_id, steam_id, joined) VALUES ('lg000001', ?, 0)").run(SID);
  f.db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created)
    VALUES ('lg000001', 'SprintTeszt', 'Alsace', 'Hyundai i20 N Rally2', '{}', ?, ?, ?, 0)`).run(JSON.stringify(STAGES), NOW - 3600000, NOW + 86400000);
  return f;
}
async function post(env, action, body, version = '0.0.28') {
  const url = new URL(`https://acrdaily.com/api/events/1/${action}`);
  const req = new Request(url, { method: 'POST', body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', 'User-Agent': `ACR-Daily/${version} public` } });
  const res = await leaguesApi(req, env, url.pathname, url, { steam_id: SID, name: 'Driver' }, true, NOW);
  return { status: res.status, body: await res.json() };
}
const entry = (db) => ({ ...db.prepare('SELECT status, reason, done, on_stage FROM league_entries WHERE event_id = 1').get() });

test('SS2\'s start sent twice (two copies of the app) is one start; SS1 and SS2 go on', async () => {
  const { env, db } = setup();
  assert.deepEqual((await post(env, 'start', { car: 'Hyundai i20 N Rally2', at: 1794232491000 })).body,
    { started: true, car: 'Hyundai i20 N Rally2', status: 'running' });
  assert.deepEqual((await post(env, 'start', { car: 'Hyundai i20 N Rally2', at: 1794232491000 })).body,
    { started: true, car: 'Hyundai i20 N Rally2', status: 'running' }, 'SS1\'s start again: the same one');
  assert.equal((await post(env, 'stage', { no: 0, timeMs: 141305, penaltyMs: 0 })).status, 200);
  assert.deepEqual((await post(env, 'begin', { no: 1, at: 1794232727000 })).body, { status: 'running' });
  assert.deepEqual((await post(env, 'begin', { no: 1, at: 1794232727000 })).body, { status: 'running' }, 'the same start');
  assert.deepEqual(entry(db), { status: 'running', reason: null, done: 1, on_stage: 1 });
  assert.deepEqual((await post(env, 'stage', { no: 1, timeMs: 141739, penaltyMs: 0 })).body, { done: 2, status: 'finished' });
});

test('a second start of a stage still ends the entry: another time, or an app that sends none', async () => {
  const { env, db } = setup();
  await post(env, 'start', { car: 'Hyundai i20 N Rally2', at: 1000 });
  await post(env, 'stage', { no: 0, timeMs: 141305, penaltyMs: 0 });
  await post(env, 'begin', { no: 1, at: 2000 });
  assert.deepEqual((await post(env, 'begin', { no: 1, at: 95000 })).body, { status: 'dnf', reason: 'SS2 started again' });
  assert.equal(entry(db).status, 'dnf');

  const b = setup();
  await post(b.env, 'start', { car: 'Hyundai i20 N Rally2' }, '0.0.27');
  assert.deepEqual((await post(b.env, 'start', { car: 'Hyundai i20 N Rally2' }, '0.0.27')).body, { status: 'dnf', reason: 'SS1 started again' });
  const c = setup();
  await post(c.env, 'start', { car: 'Hyundai i20 N Rally2', at: 1000 });
  await post(c.env, 'stage', { no: 0, timeMs: 141305, penaltyMs: 0 });
  await post(c.env, 'begin', { no: 1 }, '0.0.27');
  assert.deepEqual((await post(c.env, 'begin', { no: 1 }, '0.0.27')).body, { status: 'dnf', reason: 'SS2 started again' },
    'an app before 0.0.28: as before');
});
