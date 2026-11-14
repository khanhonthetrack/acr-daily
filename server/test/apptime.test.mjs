// The app's time standing in for a result the game lost (src/apptime.js, from app 0.1.4): the last line of support, only
// for a run without respawns (its stage clock); with any respawn a DNF. Flagged for the admin, shown like any other time.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import worker from '../src/index.js';
import { validateRun } from '../src/validate.js';
import { APP_FLAG, REINSTATED, reinstatedTime } from '../src/apptime.js';
import { fakeD1, sid } from './faked1.mjs';

const ROUTE = { length: 5000 };
const lost = (o = {}) => ({ status: 'finished', clockMs: 295475, resets: 0, appTime: true, trace: [], ...o });

test('the app\'s time: its stage clock without respawns, flagged; with any respawn a DNF; never unless sent so', () => {
  const v = validateRun(lost(), ROUTE, 0, true);
  assert.equal(v.ok, true);
  assert.equal(v.appTime, true);
  assert.equal(v.totalMs, 295475);
  assert.deepEqual(v.flags, [APP_FLAG]);
  const d = validateRun(lost({ resets: 2 }), ROUTE, 0, true);           // the game's penalty can't be known: a DNF
  assert.deepEqual([d.ok, d.status, d.totalMs, d.appTime, d.flags], [true, 'dnf', null, undefined, []]);
  assert.match(d.reason, /only counts without respawns \(2 seen\)/);
  assert.match(validateRun(lost({ appTime: false }), ROUTE, 0, true).reason, /no official result/);
  assert.match(validateRun(lost({ clockMs: 60000 }), ROUTE, 0, true).reason, /impossibly fast/);
  // the game's result, when there is one, is what counts
  const g = validateRun(lost({ official: { timeMs: 300000, penaltyMs: 5000 } }), ROUTE, 0, true);
  assert.equal(g.totalMs, 305000);
  assert.equal(g.appTime, undefined);
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
  assert.deepEqual([r.status, r.totalMs, r.counted, r.appTime], ['finished', 295475, true, { counted: true }]);
  const [e] = await board(1);
  // the board shows it like any other time (only the admin sees it's the app's: the review's flags)
  assert.deepEqual([e.status, e.totalMs, e.appTime, e.flags, e.rank], ['finished', 295475, undefined, undefined, 1]);

  [code, r] = await send(1, { startedAt: Date.now() / 1000 - 100, clockMs: 280000 });   // a practice run: practice
  assert.deepEqual([r.status, r.counted, r.appTime], ['finished', false, { counted: false }]);

  assert.deepEqual(JSON.parse(db.prepare('SELECT flags FROM runs WHERE id = ?').get(r.id - 1).flags), [APP_FLAG]);

  [code, r] = await send(2, { resets: 1 });                              // with a respawn: a DNF, as before 0.1.4
  assert.deepEqual([code, r.status, r.totalMs, r.counted, r.appTime], [200, 'dnf', null, true, undefined]);
  const [e2] = await board(2);
  assert.deepEqual([e2.status, e2.totalMs, e2.appTime], ['dnf', null, undefined]);
});

test('a lost result with respawns: a DNF; the admin may reinstate it case by case: the clock + 10 s a respawn', async () => {
  const ADMIN = 'k'.repeat(32);
  const { env, db } = fakeD1({ OFFICIAL_FROM: '2026-01-01', CREDITS_FROM: '2026-01-01', ADMIN_KEY: ADMIN });
  const today = new Date().toISOString().slice(0, 10);
  const token = 'cd'.repeat(32), me = sid(8), track = 'Monte Carlo Mézien - Sisteron';
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(me, 'brochloroflight');
  db.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, 0)')
    .run(createHash('sha256').update(token).digest('hex'), me);
  db.prepare('INSERT INTO routes (track, points, length, updated) VALUES (?, ?, 5000, 0)')
    .run(track, JSON.stringify(Array.from({ length: 51 }, (_, k) => [k * 100, 0])));
  db.prepare('INSERT INTO schedule (date, slot, track, car, weather, time) VALUES (?, 1, ?, ?, ?, ?)')
    .run(today, track, 'VW Polo GTI R5', 'Clear', 'midday');
  const call = async (path, o = {}) => {
    const r = await worker.fetch(new Request('https://acrdaily.com' + path, o), env, { waitUntil() {} });
    return [r.status, await r.json()];
  };
  const admin = (path, method = 'POST') => call(path, { method, headers: { Authorization: 'Bearer ' + ADMIN } });
  let [code, r] = await call('/api/runs', { method: 'POST', headers: { Authorization: 'Bearer ' + token,
    'Content-Type': 'application/json', 'User-Agent': 'ACR-Daily/0.1.5 public' },
  body: JSON.stringify(lost({ challengeId: `${today}/1`, track, car: 'VW Polo GTI R5', clockMs: 330941, resets: 1,
    startedAt: Date.now() / 1000 - 400, appVersion: '0.1.5' })) });
  assert.deepEqual([code, r.status, r.counted], [200, 'dnf', true]);
  assert.match(r.reason, /only counts without respawns \(1 seen\)/);       // (the app says so)
  const id = r.id;
  [code, r] = await admin(`/api/admin/runs/${id}/reinstate`);
  assert.equal(code, 200, JSON.stringify(r));
  assert.deepEqual([r.totalMs, r.rank, r.credits], [340941, 1, 50]);       // + 10 s for its respawn; the finish bonus
  const row = db.prepare('SELECT status, total_ms, flags FROM runs WHERE id = ?').get(id);
  assert.deepEqual([row.status, row.total_ms, JSON.parse(row.flags)], ['finished', 340941, [REINSTATED]]);
  [code] = await admin(`/api/admin/runs/${id}/reinstate`);                  // (once: it is finished now)
  assert.equal(code, 404);
});

test('reinstated with the game\'s own penalty when the admin knows it', async () => {
  assert.deepEqual(reinstatedTime(330941, 1).totalMs, 340941);                       // (the estimate: 10 s a respawn)
  const t = reinstatedTime(330941, 1, 7000);
  assert.equal(t.totalMs, 337941);
  assert.match(t.note, /the game's own penalty as the admin found it \(7 s\)$/);
  assert.match(reinstatedTime(330941, 1, 2500).note, /\(2\.5 s\)$/);
  assert.ok(reinstatedTime(330941, 1, -1).error);
});
