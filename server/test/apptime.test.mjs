// The app's time standing in for a result the game lost (src/apptime.js, from app 0.1.4): the last line of support, taken
// every time: the app's stage clock + 10 s a respawn, marked on the board.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import worker from '../src/index.js';
import { validateRun } from '../src/validate.js';
import { APP_FLAG, APP_TIME, isAppTime } from '../src/apptime.js';
import { fakeD1, sid } from './faked1.mjs';

const ROUTE = { length: 5000 };
const lost = (o = {}) => ({ status: 'finished', clockMs: 295475, resets: 2, appTime: true, trace: [], ...o });

test('the app\'s time: its stage clock + 10 s a respawn, marked; never without the game\'s result unless sent so', () => {
  const v = validateRun(lost(), ROUTE, 0, true);
  assert.equal(v.ok, true);
  assert.equal(v.appTime, true);
  assert.equal(v.totalMs, 295475 + 2 * APP_TIME.resetMs);
  assert.deepEqual(v.flags, [APP_FLAG]);
  assert.match(validateRun(lost({ appTime: false }), ROUTE, 0, true).reason, /no official result/);
  assert.match(validateRun(lost({ clockMs: 60000 }), ROUTE, 0, true).reason, /impossibly fast/);
  // the game's result, when there is one, is what counts
  const g = validateRun(lost({ official: { timeMs: 300000, penaltyMs: 5000 } }), ROUTE, 0, true);
  assert.equal(g.totalMs, 305000);
  assert.equal(g.appTime, undefined);
  assert.ok(isAppTime(JSON.stringify([APP_FLAG])) && isAppTime('reinstated by the admin with the app stage clock'));
  assert.ok(!isAppTime('[]') && !isAppTime(null));
});

test('sent by the app: taken every time, marked on the board; a practice run stays practice', async () => {
  const { env, db } = fakeD1({ OFFICIAL_FROM: '2026-01-01' });
  const today = new Date().toISOString().slice(0, 10);
  const token = 'ab'.repeat(32), me = sid(7);
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(me, 'satosangokusi');
  db.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, 0)')
    .run(createHash('sha256').update(token).digest('hex'), me);
  const points = Array.from({ length: 51 }, (_, k) => [k * 100, 0]);      // 5 km
  for (const [slot, track] of [[1, 'Monte Carlo Pra d\'Alart'], [2, 'Greece Loutraki - Aghii Theodori']]) {
    db.prepare('INSERT INTO routes (track, points, length, updated) VALUES (?, ?, 5000, 0)').run(track, JSON.stringify(points));
    db.prepare('INSERT INTO schedule (date, slot, track, car, weather, time) VALUES (?, ?, ?, ?, ?, ?)')
      .run(today, slot, track, 'Lancia Rally 037 Evo2', 'Clear', 'morning');
  }
  const send = async (slot, o = {}) => {
    const track = slot === 1 ? 'Monte Carlo Pra d\'Alart' : 'Greece Loutraki - Aghii Theodori';
    const r = await worker.fetch(new Request('https://acrdaily.com/api/runs', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json',
        'User-Agent': 'ACR-Daily/0.1.4 public' },
      body: JSON.stringify(lost({ challengeId: `${today}/${slot}`, track, car: 'Lancia Rally 037 Evo2',
        startedAt: Date.now() / 1000 - 400, appVersion: '0.1.4', ...o })) }), env, { waitUntil() {} });
    return [r.status, await r.json()];
  };
  const board = async (slot) => (await (await worker.fetch(
    new Request(`https://acrdaily.com/api/leaderboard?date=${today}&slot=${slot}`), env, { waitUntil() {} })).json()).entries;

  let [code, r] = await send(1);
  assert.equal(code, 200, JSON.stringify(r));
  assert.deepEqual([r.status, r.totalMs, r.counted, r.appTime], ['finished', 315475, true, { counted: true }]);
  const [e] = await board(1);
  assert.deepEqual([e.status, e.totalMs, e.appTime, e.rank], ['finished', 315475, true, 1]);

  [code, r] = await send(1, { startedAt: Date.now() / 1000 - 100, clockMs: 280000 });   // a practice run: practice
  assert.deepEqual([r.status, r.counted, r.appTime], ['finished', false, { counted: false }]);

  [code, r] = await send(2);                                             // another one the same day: taken too
  assert.deepEqual([code, r.status, r.totalMs, r.appTime], [200, 'finished', 315475, { counted: true }]);
  const [e2] = await board(2);
  assert.deepEqual([e2.status, e2.appTime], ['finished', true]);
  assert.deepEqual(JSON.parse(db.prepare('SELECT flags FROM runs WHERE id = ?').get(r.id).flags), [APP_FLAG]);
});
