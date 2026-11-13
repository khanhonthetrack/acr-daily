// The app's time standing in for a result the game lost (src/apptime.js, from app 0.1.3): the app's stage clock + 10 s a
// respawn, marked on the board, at most once in 7 days a driver (dailies and time trial together); over it, a DNF.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import worker from '../src/index.js';
import { validateRun } from '../src/validate.js';
import { APP_FLAG, APP_TIME, appTimeUsed, isAppTime, usedUpReason } from '../src/apptime.js';
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

test('the allowance: results that counted in the last 7 days, dailies and time trial together', async () => {
  const { env, db } = fakeD1();
  const now = Date.UTC(2026, 10, 14, 12);
  const day = (k) => now - k * 86400000;
  const run = (who, created, flags, status = 'finished') => db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car,
      status, created, flags) VALUES ('2026-11-14', 1, ?, 't', 'c', ?, ?, ?)`).run(who, status, created, flags);
  run(sid(1), day(8), JSON.stringify([APP_FLAG]));                       // over a week ago
  run(sid(1), day(1), JSON.stringify(['app time (not counted, none of the allowance used): x']));   // practice
  run(sid(1), day(1), JSON.stringify(['official result lost: reinstated by the admin with the app stage clock']));
  run(sid(2), day(1), JSON.stringify([APP_FLAG]));                       // another driver
  assert.deepEqual(await appTimeUsed(env, sid(1), now), { used: 0, next: null });
  db.prepare(`INSERT INTO tt_runs (week, slot, steam_id, track, car, status, reason, created)
      VALUES ('2026-11-09', 2, ?, 't', 'c', 'finished', ?, ?)`).run(sid(1), APP_FLAG, day(2));
  assert.deepEqual(await appTimeUsed(env, sid(1), now), { used: 1, next: day(2) + 7 * 86400000 });
  assert.match(usedUpReason(day(2) + 7 * 86400000), /already stood in .*again from 2026-11-19 12:00 UTC/);
});

test('sent by the app: counted once, marked on the board; a practice run uses nothing; over it, a DNF', async () => {
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
        'User-Agent': 'ACR-Daily/0.1.3 public' },
      body: JSON.stringify(lost({ challengeId: `${today}/${slot}`, track, car: 'Lancia Rally 037 Evo2',
        startedAt: Date.now() / 1000 - 400, appVersion: '0.1.3', ...o })) }), env, { waitUntil() {} });
    return [r.status, await r.json()];
  };
  const board = async (slot) => (await (await worker.fetch(
    new Request(`https://acrdaily.com/api/leaderboard?date=${today}&slot=${slot}`), env, { waitUntil() {} })).json()).entries;

  let [code, r] = await send(1);
  assert.equal(code, 200, JSON.stringify(r));
  assert.deepEqual([r.status, r.totalMs, r.counted, r.appTime], ['finished', 315475, true, { counted: true, left: 0 }]);
  const [e] = await board(1);
  assert.deepEqual([e.status, e.totalMs, e.appTime, e.rank], ['finished', 315475, true, 1]);

  [code, r] = await send(1, { startedAt: Date.now() / 1000 - 100, clockMs: 280000 });   // practice: uses nothing
  assert.deepEqual([r.counted, r.appTime], [false, { counted: false }]);
  assert.equal(JSON.parse(db.prepare('SELECT flags FROM runs WHERE id = ?').get(r.id).flags)[0].startsWith('app time ('), true);

  [code, r] = await send(2);                                             // another counted one this week: a DNF
  assert.equal(code, 200);
  assert.equal(r.status, 'dnf');
  assert.equal(r.totalMs, null);
  assert.equal(r.appTime.usedUp, true);
  const [e2] = await board(2);
  assert.equal(e2.status, 'dnf');
  assert.match(e2.reason, /already stood in for one this week/);
});
