// The dailies fixed ahead (index.js scheduleAhead): the coming 30 days in a few queries (the free plan allows 50 a
// cron run or request), two different stages a day, a day already fixed (a daily bought in the shop) kept.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { scheduleAhead } from '../src/index.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 9, 23, 9, 45);
const day = (n) => new Date(NOW + n * 86400000).toISOString().slice(0, 10);
const TRACKS = ['Wales Afon Bidno', 'Wales Severn', 'Alsace Forêt', 'Greece Elatia', 'Monte Carlo La Bollène'];

test('the coming 30 days fixed in one go, in three queries; then nothing to do', async () => {
  const { env, db, count } = fakeD1();
  for (const t of TRACKS) {
    db.prepare("INSERT INTO routes (track, points, length, updated) VALUES (?, '[]', 5000, 0)").run(t);
    db.prepare("INSERT INTO pool (track, car) VALUES (?, '*')").run(t);
  }
  // a day a driver set in the shop (SS1), and today's SS1 fixed already
  db.prepare(`INSERT INTO schedule (date, slot, track, car, weather, time, set_by) VALUES (?, 1, 'Wales Severn', 'Mini Cooper S 1275',
    'Clear', 'midday', ?)`).run(day(12), sid(1));
  db.prepare("INSERT INTO schedule (date, slot, track, car, weather, time) VALUES (?, 1, 'Greece Elatia', 'Lancia Stratos HF', 'Clear', 'evening')").run(day(0));
  count.queries = 0;
  const fixed = await scheduleAhead(env, NOW);
  assert.ok(count.queries <= 3, `${count.queries} queries`);
  assert.deepEqual(fixed.map((d) => d.date), Array.from({ length: 31 }, (_, i) => day(i)));
  const rows = db.prepare('SELECT * FROM schedule ORDER BY date, slot').all();
  assert.equal(rows.length, 62);
  for (let i = 0; i <= 30; i++) {
    const [a, b] = rows.filter((r) => r.date === day(i));
    assert.ok(a && b && a.track !== b.track, `${day(i)}: two different stages`);
    assert.ok(a.weather && a.time && b.weather && b.time);
  }
  const kept = rows.find((r) => r.date === day(12) && r.slot === 1);
  assert.deepEqual([kept.track, kept.set_by], ['Wales Severn', sid(1)]);
  assert.equal(rows.find((r) => r.date === day(0) && r.slot === 1).track, 'Greece Elatia');
  // the rotation (away from the days fixed by hand): no stage twice in two days
  for (let i = 13; i <= 29; i++) {
    const seen = rows.filter((r) => r.date >= day(i) && r.date <= day(i + 1)).map((r) => r.track);
    assert.equal(new Set(seen).size, 4, `${day(i)}: ${seen}`);
  }
  count.queries = 0;
  assert.deepEqual(await scheduleAhead(env, NOW + 3600000), []);
  assert.equal(count.queries, 1);
  // a day later: just the new 31st day
  assert.deepEqual((await scheduleAhead(env, NOW + 86400000)).map((d) => d.date), [day(31)]);
});
