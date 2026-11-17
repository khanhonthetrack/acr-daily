// Community content (src/community.js): the catalog the app's COMMUNITY page lists, its stages known as the game's,
// and a week's time trial fixed ahead on one (src/timetrial.js setTtSlot).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { catalog, COMMUNITY_STAGE_IDS, itemOfStage, STAGE_EXPORTER } from '../src/community.js';
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

test('GET /api/community: the catalog, no sign-in needed', async () => {
  const { default: worker } = await import('../src/index.js');
  const { env } = fakeD1({ SITE_URL: 'https://acrdaily.com' });
  const r = await worker.fetch(new Request('https://acrdaily.com/api/community'), env, { waitUntil() {} });
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.deepEqual(j.categories.map((c) => c.id), ['tracks', 'cars']);
  assert.equal(j.categories[0].items[0].photo, 'london');           // (the app's own copy of its picture)
});

test('a time trial car drawn ("*") is never the car a daily of that week has on the same stage', async () => {
  const { env, db } = fakeD1({ TIME_TRIAL_FROM: '2026-11-09' });
  const now = Date.parse('2026-11-11T12:00:00Z');
  const track = 'Wales Afon Bidno';
  // whatever the draw would give: a daily of the week on that stage with that car
  const first = await setTtSlot(env, { week: '2026-11-16', slot: 1, track, car: '*' }, hash, now);
  db.prepare("INSERT INTO schedule (date, slot, track, car, weather, time) VALUES ('2026-11-18', 1, ?, ?, 'Clear', 'morning')").run(track, first.car);
  const again = await setTtSlot(env, { week: '2026-11-16', slot: 1, track, car: '*' }, hash, now);
  assert.equal(again.ok, true);
  assert.notEqual(again.car, first.car);
  assert.ok(CARS.some((c) => c.name === again.car));
});

test('other tools\' stages go only to a test build: Sando Rally\'s Chile BioBio and WRC Generations\'', async () => {
  const ids = (c) => c.categories[0].items.map((it) => it.id);
  assert.deepEqual(ids(catalog('')), ['acrdaily-london']);
  const testIds = ids(catalog('', { test: true }));
  assert.deepEqual(testIds.slice(0, 4), ['acrdaily-london', 'sando-chile-biobio', 'wrcg-es-ss1', 'wrcg-es-ss1r']);
  assert.equal(testIds.length, 15);
  assert.equal(catalog('').tools, undefined);                                   // (the stage maker: test builds only)
  const { default: worker } = await import('../src/index.js');
  const { env } = fakeD1({ SITE_URL: 'https://acrdaily.com' });
  const ask = async (ua) => (await (await worker.fetch(new Request('https://acrdaily.com/api/community',
    { headers: { 'User-Agent': ua } }), env, { waitUntil() {} })).json());
  assert.deepEqual(ids(await ask('ACR-Daily/0.1.5 public')), ['acrdaily-london']);
  assert.deepEqual(ids(await ask('ACR-Daily/0.1.5.12 public')), testIds);
});

test('WRC Generations\' stages: one row each, made on the player\'s PC by Stage Exporter (pinned, checked file by file)', () => {
  const c = catalog('', { test: true });
  const wrcg = c.categories[0].items.filter((it) => it.group === 'wrcg');
  // (only the 13 playable ones: the set's allowed_stages.json)
  assert.deepEqual(wrcg.map((it) => it.slug), ['es_ss1', 'es_ss1r', 'es_ss4', 'es_ss4r', 'fr_ss1', 'fr_ss1r', 'gr_ss3',
    'it_ss1', 'it_ss1r', 'panzerplatte', 'pt_ss4', 'se_ss3', 'se_ss4']);
  const ex = c.tools[STAGE_EXPORTER.id];
  assert.equal(ex.name, 'Stage Exporter');
  assert.match(ex.commit, /^[0-9a-f]{40}$/);
  assert.equal(ex.url, `https://codeload.github.com/Faviogames/Stage-Exporter/zip/${ex.commit}`);   // (that commit, no other)
  assert.match(ex.payloadSha256, /^[0-9a-f]{64}$/);
  assert.equal(ex.base.version, '0.3.7');
  assert.match(ex.base.page, /^https:\/\/sandorally\.com\//);                    // (Sando's own word on it: never downloaded)
  for (const it of wrcg) {
    assert.equal(it.install, 'export');
    assert.equal(it.exporter, ex.id);
    assert.match(it.slug, /^[a-z0-9_]+$/);
    assert.equal(it.id, `wrcg-${it.slug.replace(/_/g, '-')}`);
    assert.equal(it.stages.length, 1);
    assert.match(it.stages[0].stageId, /^Wrcg\w+Full$/);
    assert.equal(it.download, undefined);                                       // (nothing of it downloaded from here)
    assert.match(it.subtitle, /^WRC Generations · \w+ · (tarmac|gravel|snow)$/);
  }
  const ri = wrcg.find((it) => it.slug === 'es_ss1');
  assert.deepEqual([ri.name, ri.subtitle, ri.stages[0].stageId], ['Riudecanyes', 'WRC Generations · Spain · tarmac', 'WrcgEsSS1Full']);
  assert.equal(itemOfStage('wrcgsess3full').slug, 'se_ss3');
  assert.equal(menuName('WrcgEsSS1RFull'), 'Riudecanyes reverse');
});

test('Sando Rally\'s Chile BioBio: the official download, installed by its own manager; never in the dailies\' pool', async () => {
  const sando = catalog('', { test: true }).categories[0].items.find((it) => it.id === 'sando-chile-biobio');
  assert.equal(sando.install, 'manager');
  assert.match(sando.download.url, /^https:\/\/dl\.sandorally\.com\//);       // (only from sandorally.com: its terms)
  assert.match(sando.download.sha256, /^[0-9a-f]{64}$/);
  assert.ok(sando.download.url.includes(sando.download.sha256.slice(0, 12)));  // (its address names its checksum)
  assert.deepEqual(sando.stages.map((s) => s.stageId), ['SandoChlBioFull', 'SandoChlBioRevFull']);
  assert.equal(itemOfStage('sandochlbiofull').id, 'sando-chile-biobio');
  assert.equal(menuName('SandoChlBioRevFull'), 'Chile BioBio Reverse');
  const { env, db } = fakeD1({});
  const { dailyPool } = await import('../src/index.js');
  for (const [track, id] of [['Chile BioBio', 'SandoChlBioFull'], ['Spain Riudecanyes', 'WrcgEsSS1Full'],
    ['Wales Afon Bidno', 'WelesS4HafrenSouthFullForward']]) {
    db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, ?, ?)').run(track, '[]', 6000, 0, id);
    db.prepare("INSERT INTO pool (track, car, enabled) VALUES (?, '*', 1)").run(track);
  }
  assert.deepEqual((await dailyPool(env)).tracks, ['Wales Afon Bidno']);
});
