// Community content (src/community.js): the catalog the app's COMMUNITY page lists, its stages known as the game's,
// and a week's time trial fixed ahead on one (src/timetrial.js setTtSlot).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { catalog, COMMUNITY_STAGE_IDS, itemOfStage } from '../src/community.js';
import { menuName } from '../src/stages.js';
import { pickWeek, setTtSlot, ttPicks } from '../src/timetrial.js';
import { CARS } from '../src/cars.js';
import { fakeD1 } from './faked1.mjs';

const hash = (s) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

test('the catalog: tracks and cars; ACR DAILY London among the tracks, with its release', () => {
  const c = catalog('https://acrdaily.com');
  assert.deepEqual(c.categories.map((x) => x.id), ['tracks', 'cars']);
  const london = c.categories[0].items.find((it) => it.id === 'acrdaily-london');
  assert.ok(london);
  assert.match(london.manifest, /^https:\/\/github\.com\/khanhonthetrack\/acr-daily\/releases\/download\/acrdaily-london\/manifest\.json$/);
  assert.match(london.image, /^https:\/\//);
  assert.deepEqual(c.categories[1].items, []);
});

test('a community stage: its item (any case), its menu name', () => {
  assert.ok(COMMUNITY_STAGE_IDS.includes('AcrXsLn02r0FullForward'));
  assert.equal(itemOfStage('acrxsln02r0fullforward').id, 'acrdaily-london');
  assert.equal(itemOfStage('WelesS4HafrenSouthFullForward'), null);
  assert.equal(menuName('AcrXsLn02r0FullForward'), 'Westminster');
  assert.equal(menuName('WelesS4HafrenSouthFullForward'), 'Afon Bidno - Severn');
});

test('a week\'s time trial stage fixed ahead: kept when the week is picked, the other slot drawn as usual', async () => {
  const { env } = fakeD1({ TIME_TRIAL_FROM: '2026-11-09' });
  const now = Date.parse('2026-11-11T12:00:00Z');
  const bad = await setTtSlot(env, { week: '2026-11-17', slot: 1, track: 'London Westminster' }, hash, now);
  assert.match(bad.error, /Monday/);
  assert.match((await setTtSlot(env, { week: '2026-11-09', slot: 1, track: 'X' }, hash, now)).error, /started/);
  assert.match((await setTtSlot(env, { week: '2026-11-16', slot: 3, track: 'X' }, hash, now)).error, /slot/);
  const r = await setTtSlot(env, { week: '2026-11-16', slot: 1, track: 'London Westminster', car: '*', weather: 'Clear',
    time: 'midday' }, hash, now);
  assert.equal(r.ok, true);
  assert.ok(CARS.some((c) => c.name === r.car));                       // a car drawn for the week
  assert.equal(r.weather, 'Clear');
  assert.equal(r.time, 'midday');
  assert.equal(r.warning, 'no route for that track yet');
  // as the week starts: TT1 stays London, TT2 is picked from the pool (never the same stage)
  const pool = { byTrack: new Map([['Wales Afon Bidno', []], ['Alsace Obersteigen', []]]), tracks: ['Wales Afon Bidno', 'Alsace Obersteigen'] };
  const fixed = [{ slot: 1, track: 'London Westminster', car: r.car, weather: 'Clear', time: 'midday' }];
  const picks = pickWeek(pool, '2026-11-16', [], fixed, hash);
  assert.equal(picks[0].track, 'London Westminster');
  assert.notEqual(picks[1].track, 'London Westminster');
  const rows = await ttPicks(env, '2026-11-16', { pool: async () => pool, hash }, Date.parse('2026-11-16T00:05:00Z'));
  assert.equal(rows.length, 2);
  assert.equal(rows.find((x) => x.slot === 1).track, 'London Westminster');
  // taken off again
  const env2 = fakeD1({}).env;
  await setTtSlot(env2, { week: '2026-11-23', slot: 1, track: 'London Westminster' }, hash, now);
  assert.equal((await setTtSlot(env2, { week: '2026-11-23', slot: 1, remove: true }, hash, now)).removed, true);
});

test('a community stage is never drawn for the dailies (not everyone has it installed)', async () => {
  const { env, db } = fakeD1({});
  const { dailyPool } = await import('../src/index.js');
  for (const [track, id] of [['London Westminster', 'AcrXsLn02r0FullForward'], ['Wales Afon Bidno', 'WelesS4HafrenSouthFullForward']]) {
    db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, ?, ?)').run(track, '[]', 6000, 0, id);
    db.prepare("INSERT INTO pool (track, car, enabled) VALUES (?, '*', 1)").run(track);
  }
  assert.deepEqual((await dailyPool(env)).tracks, ['Wales Afon Bidno']);
});
