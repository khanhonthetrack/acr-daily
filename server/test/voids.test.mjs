// A test build's committed daily run without the game's official time (src/voids.js): it doesn't count, it is no DNF,
// and its start is forgotten so the next run can count. Public builds keep the rules they had.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countedRuns } from '../src/index.js';
import { MAX_VOIDS, testBuild, voidStart } from '../src/voids.js';
import { fakeD1, sid } from './faked1.mjs';

const DATE = '2026-11-15';
const T = Date.UTC(2026, 10, 15, 20, 0, 0);    // the committed run's start (in Practice, say)
const MIN = 60000;

function setUp() {
  const { env, db } = fakeD1();
  const run = (who, startedAt, created, status = 'finished') => db.prepare(
    `INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, total_ms, created, started_at)
     VALUES (?, 1, ?, 'Turini', 'Peugeot 306 Maxi', ?, '', 500000, ?, ?, ?)`)
    .run(DATE, who, status, status === 'finished' ? 500000 : null, created, startedAt);
  const start = (who, started) => db.prepare('INSERT OR IGNORE INTO attempts (steam_id, date, slot, started) VALUES (?, ?, 1, ?)')
    .run(who, DATE, started);
  const v = (over = {}) => voidStart(env, { steamId: sid(1), date: DATE, slot: 1, startedAt: T, clockMs: 300000,
    reason: 'the game saved no time', version: '0.1.5.9', now: T + 6 * MIN, ...over });
  return { env, db, run, start, v };
}

test('only a four-part version is a test build', () => {
  assert.ok(testBuild('0.1.5.9'));
  for (const x of ['0.1.5', '0.1.6', '', null, undefined, '0.1.5.9.1', 'x.1.5.9']) assert.equal(testBuild(x), false, x);
});

test('a run that does not count: its start is forgotten, and the next run counts (no abandoned DNF)', async () => {
  const { env, db, run, start, v } = setUp();
  start(sid(1), T);                                         // the committed run's start, on the live map
  assert.deepEqual(await v(), { status: 'void', forgot: true });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM attempts').get().n, 0);
  const row = db.prepare('SELECT * FROM voided_runs').get();
  assert.equal(row.forgot, 1);
  assert.equal(row.app_version, '0.1.5.9');
  assert.equal(row.clock_ms, 300000);
  // without the void the start would be an abandoned DNF an hour on; now nothing, until the next run
  assert.equal((await countedRuns(env, DATE, 1, T + 90 * MIN)).counted.get(sid(1)), undefined);
  start(sid(1), T + 10 * MIN);                              // the next one, in the Rally Weekend
  run(sid(1), T + 10 * MIN, T + 20 * MIN);
  const c = (await countedRuns(env, DATE, 1, T + 90 * MIN)).counted.get(sid(1));
  assert.equal(c.dnf, null);
  assert.equal(c.run.started_at, T + 10 * MIN);
});

test('a public build is refused, and its start stays (the old rules: abandoned DNF after an hour)', async () => {
  const { env, db, start, v } = setUp();
  start(sid(1), T);
  for (const version of ['0.1.5', null]) {
    const r = await v({ version });
    assert.equal(r.code, 403);
    assert.match(r.error, /^invalid run/);
  }
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM attempts').get().n, 1);
  assert.deepEqual((await countedRuns(env, DATE, 1, T + 61 * MIN)).counted.get(sid(1)), { run: null, dnf: 'abandoned' });
});

test('a later run voided leaves an earlier first start as it was; a run already in cannot be voided', async () => {
  const { db, run, start, v } = setUp();
  start(sid(1), T - 30 * MIN);                              // an earlier first start: the counted one
  assert.deepEqual(await v(), { status: 'void', forgot: false });
  assert.equal(db.prepare('SELECT started FROM attempts').get().started, T - 30 * MIN);
  run(sid(1), T + 20 * MIN, T + 25 * MIN, 'dnf');
  const r = await v({ startedAt: T + 20 * MIN });
  assert.equal(r.code, 409);
});

test(`past ${MAX_VOIDS} on a daily in a day, the run goes on as a DNF`, async () => {
  const { v } = setUp();
  for (let i = 0; i < MAX_VOIDS; i++) assert.equal((await v({ startedAt: T + i * 10 * MIN })).status, 'void');
  const r = await v({ startedAt: T + 99 * MIN });
  assert.equal(r.status, 'dnf');
  assert.match(r.reason, /the game saved no time \(over the limit of 5 runs/);
});
