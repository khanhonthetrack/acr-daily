// Which run of a daily counts for each driver (countedRuns): the run of their first start, however late it arrives.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countedRuns } from '../src/index.js';
import { fakeD1, sid } from './faked1.mjs';

const DATE = '2026-11-12';
const T = Date.UTC(2026, 10, 12, 6, 7, 4);    // the first start
const MIN = 60000;

function setUp() {
  const { env, db } = fakeD1();
  let id = 0;
  const run = (who, startedAt, created, status = 'finished') => {
    db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, total_ms, created, started_at)
                VALUES (?, 1, ?, 'Turini', 'Peugeot 306 Maxi', ?, '', 500000, ?, ?, ?)`)
      .run(DATE, who, status, status === 'finished' ? 500000 : null, created, startedAt);
    return ++id;
  };
  const start = (who, started) => db.prepare('INSERT INTO attempts (steam_id, date, slot, started) VALUES (?, ?, 1, ?)')
    .run(who, DATE, started);
  return { env, run, start };
}

test('a finished run that waited for the game\'s official result counts, though practice runs arrived before it', async () => {
  const { env, run, start } = setUp();
  start(sid(1), T);
  run(sid(1), T + 12 * MIN, T + 13 * MIN, 'dnf');    // practice, sent at once
  run(sid(1), T + 14 * MIN, T + 15 * MIN, 'dnf');
  const own = run(sid(1), T, T + 19 * MIN);          // the first start's run, sent once the game had saved it
  const c = (await countedRuns(env, DATE, 1, T + 20 * MIN)).counted.get(sid(1));
  assert.equal(c.run.id, own);
  assert.equal(c.dnf, null);
});

test('while the first start\'s run is on its way, a practice run in makes no DNF (before the hour)', async () => {
  const { env, run, start } = setUp();
  start(sid(1), T);
  run(sid(1), T + 12 * MIN, T + 13 * MIN, 'dnf');
  assert.equal((await countedRuns(env, DATE, 1, T + 14 * MIN)).counted.get(sid(1)), undefined);
  assert.deepEqual((await countedRuns(env, DATE, 1, T + 61 * MIN)).counted.get(sid(1)), { run: null, dnf: 'abandoned' });
});

test('the first run in still counts as before; a later run claiming another start does not replace it', async () => {
  const { env, run, start } = setUp();
  start(sid(1), T);
  const first = run(sid(1), T, T + 9 * MIN, 'dnf');
  run(sid(1), T + 10 * MIN, T + 19 * MIN);           // a better practice run
  assert.equal((await countedRuns(env, DATE, 1, T + 20 * MIN)).counted.get(sid(1)).run.id, first);
  // two runs claiming the first start: the first one in
  run(sid(1), T, T + 20 * MIN);
  assert.equal((await countedRuns(env, DATE, 1, T + 21 * MIN)).counted.get(sid(1)).run.id, first);
});

test('without a recorded start, or a run started just after it (within 2 min), the first run in counts', async () => {
  const { env, run, start } = setUp();
  const a = run(sid(1), T, T + 9 * MIN);
  start(sid(2), T);
  const b = run(sid(2), T + 30000, T + 9 * MIN);
  const { counted } = await countedRuns(env, DATE, 1, T + 10 * MIN);
  assert.equal(counted.get(sid(1)).run.id, a);
  assert.equal(counted.get(sid(2)).run.id, b);
});
