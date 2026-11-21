// A cup's cron work on a real SQLite (schema.sql, node:sqlite) through a stand-in for D1 that counts the queries: a
// 100-driver cup from its start to its final. The free plan allows 50 D1 queries a cron run, so a round has to open,
// be decided and be paid with a handful of bulk statements, however big the cup.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { cupsApi, cupsTick, drawStages, seedOrderOf, shuffle } from '../src/cups.js';
import { LIMITS } from '../src/leagues.js';
import { fakeD1, sid } from './faked1.mjs';

const SPEC = { rally: 'Wales', car: 'Ford Fiesta Rally2', car_class: null, rules: {},
  stages: [{ track: 'wal_1', day: 1, service: false, weather: 'clear', time: '12:00' }] };

test('a 100-driver cup: 7 rounds (28 byes), each cron run a few queries, the top seed wins, the pot shared', async () => {
  const { env, db, count } = fakeD1();
  const now0 = Date.UTC(2026, 9, 12, 12, 0);
  const n = 100;
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  db.prepare(`INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('bigcup01', 'Big Cup', ?, 'CODE2345', 0, 'cup')`).run(sid(0));
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('bigcup01', 'Big Cup', ?, 128, 10, '[60,30,5,5]', ?, ?, 24, 'open', 0)`).run(sid(0), JSON.stringify(SPEC), now0 - 1);
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES (?, ?, 10, 0)').run('bigcup01', sid(i));

  // the start: seeds, round 1 (64 slots: 36 matches, 28 byes) and a notice to everyone, in a few queries
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now0), [{ cup: 'bigcup01', did: 'started' }]);
  assert.ok(count.queries <= 6, `the start took ${count.queries} queries`);
  const seeds = db.prepare('SELECT seed FROM cup_entries WHERE cup_id = ? ORDER BY seed').all('bigcup01').map((r) => r.seed);
  assert.deepEqual(seeds, Array.from({ length: n }, (_, i) => i + 1));
  const r1 = db.prepare('SELECT * FROM cup_matches WHERE cup_id = ? AND round = 1').all('bigcup01');
  assert.equal(r1.length, 64);
  assert.equal(r1.filter((m) => !m.b && m.winner === m.a && m.note === 'a bye').length, 28);
  const games = r1.filter((m) => m.a && m.b);
  assert.equal(games.length, 36);
  assert.ok(games.every((m) => m.event_id && !m.winner), 'every match has its event');
  const ev = db.prepare('SELECT * FROM league_events WHERE id = ?').get(games[0].event_id);
  assert.deepEqual(JSON.parse(ev.only_ids), [games[0].a, games[0].b]);
  assert.match(ev.name, /^Round of 128: Driver \d+ vs Driver \d+$/);
  assert.equal(ev.closes, now0 - 1 + 24 * 3600000, 'a round closes at the start plus a round, not a round from when it opened');
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM league_events WHERE league_id = 'bigcup01'").get().n, 36);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE kind = 'cup'").get().n, 100);
  assert.match(db.prepare("SELECT body FROM messages WHERE kind = 'cup' AND body LIKE '%you against%' LIMIT 1").get().body,
    /under CUPS, by Tue 13 Oct, 11:59 UTC\.$/);

  // nothing to do until the round's matches close: no work at all
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now0 + 3600000), []);
  assert.ok(count.queries <= 3);

  // a quarter of the round before it closes (6 h of 24): a reminder to each driver who hasn't driven, once
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, ev.closes - 5 * 3600000), [{ cup: 'bigcup01', did: 'reminded 72' }]);
  assert.ok(count.queries <= 9, `the reminders took ${count.queries} queries`);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE '%haven''t driven your match against Driver%'").get().n, 72);
  assert.deepEqual(await cupsTick(env, ev.closes - 4 * 3600000), []);

  // each round closes with nobody having driven: the higher seed goes through, the next round opens in the same run
  let now = now0;
  for (let round = 1; round <= 7; round++) {
    now += 25 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'bigcup01'").run(now - LIMITS.graceMs - 1);
    count.queries = 0;
    const did = await cupsTick(env, now);
    assert.ok(count.queries <= 8, `round ${round} took ${count.queries} queries`);
    assert.deepEqual(did.map((d) => d.did), [round < 7 ? `round ${round + 1}` : 'finished']);
  }
  const cup = db.prepare("SELECT * FROM cups WHERE id = 'bigcup01'").get();
  assert.equal(cup.status, 'finished');
  assert.equal(cup.round, 7);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM cup_matches WHERE cup_id = 'bigcup01'").get().n, 127);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM cup_matches WHERE cup_id = 'bigcup01' AND winner IS NULL").get().n, 0);

  // places: the top seed won, then 2, the losing semi-finalists 3 ...; the pot of 1000 as 60 / 30 / 5 / 5
  const seedOf = new Map(db.prepare("SELECT steam_id, seed FROM cup_entries WHERE cup_id = 'bigcup01'").all().map((r) => [r.steam_id, r.seed]));
  const placed = db.prepare("SELECT steam_id, place FROM cup_entries WHERE cup_id = 'bigcup01' AND place IS NOT NULL ORDER BY place").all();
  assert.equal(placed.length, n);
  assert.equal(seedOf.get(placed[0].steam_id), 1);
  assert.deepEqual(placed.slice(0, 4).map((p) => p.place), [1, 2, 3, 3]);
  const paid = db.prepare("SELECT steam_id, delta FROM credit_ledger WHERE kind = 'cup-prize' ORDER BY delta DESC").all();
  assert.deepEqual(paid.map((p) => p.delta), [600, 300, 50, 50]);
  assert.equal(paid[0].steam_id, placed[0].steam_id);
  assert.equal(db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(placed[0].steam_id).balance, 600);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE 'Big Cup is over:%'").get().n, n);

  // and nothing more to do
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now + 3600000), []);
  assert.ok(count.queries <= 3);
});

test('a 128 cup with 63 drivers shrinks to a bracket of 64: a Round of 64, one bye (the top seed), 6 rounds', async () => {
  const { env, db } = fakeD1();
  const n = 63;
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('half0001', 'Half Cup', ?, 128, 0, '[100]', ?, 1, 24, 'open', 0)`).run(sid(0), JSON.stringify(SPEC));
  for (let i = 0; i < n; i++) db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('half0001', ?, 0, 0)").run(sid(i));
  await cupsTick(env, 1000);
  const r1 = db.prepare("SELECT * FROM cup_matches WHERE cup_id = 'half0001' AND round = 1 ORDER BY slot").all();
  assert.equal(r1.length, 32);
  const byes = r1.filter((m) => !m.b);
  assert.equal(byes.length, 1);
  assert.equal(db.prepare("SELECT seed FROM cup_entries WHERE cup_id = 'half0001' AND steam_id = ?").get(byes[0].a).seed, 1);
  assert.match(db.prepare("SELECT name FROM league_events WHERE league_id = 'half0001' LIMIT 1").get().name, /^Round of 64: /);
  let now = 1000;
  for (let round = 1; round <= 6; round++) {
    now += 25 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'half0001'").run(now - LIMITS.graceMs - 1);
    await cupsTick(env, now);
  }
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'half0001'").get().status, 'finished');
  assert.equal(db.prepare("SELECT MAX(round) AS r FROM cup_matches WHERE cup_id = 'half0001'").get().r, 6);
});

test('a cup that does not fill: called off, every fee back, in a few queries', async () => {
  const { env, db, count } = fakeD1();
  db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Ann', 0)").run(sid(1));
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('lonely01', 'Lonely Cup', ?, 8, 25, '[100]', ?, 1, 24, 'open', 0)`).run(sid(1), JSON.stringify(SPEC));
  db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('lonely01', ?, 25, 0)").run(sid(1));
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, 1000), [{ cup: 'lonely01', did: 'called off' }]);
  assert.ok(count.queries <= 5);
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'lonely01'").get().status, 'cancelled');
  assert.equal(db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(sid(1)).balance, 25);
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ?').get(sid(1)).body, /did not start: .*your entry fee is back\.$/);
});

test('seeds go by the driver rating; not rated yet counts as the start value; equal ratings in a random order', () => {
  const en = [{ steam_id: 'low', rating: 1400 }, { steam_id: 'new', rating: null }, { steam_id: 'top', rating: 1720 },
    { steam_id: 'mid', rating: 1550 }, { steam_id: 'new2', rating: null }];
  for (let k = 0; k < 20; k++) {
    const s = seedOrderOf(en);
    assert.deepEqual([s[0], s[1], s[4]], ['top', 'mid', 'low']);
    assert.deepEqual(s.slice(2, 4).sort(), ['new', 'new2']);
  }
  const orders = new Set(Array.from({ length: 40 }, () => seedOrderOf([{ steam_id: 'a' }, { steam_id: 'b' }, { steam_id: 'c' }]).join()));
  assert.ok(orders.size > 1, 'equal drivers are not always in the same order');
});
test('a cup seeded at random (the MINI CHALLENGE): ratings left out, every order as likely', () => {
  const en = [{ steam_id: 'top', rating: 2400 }, { steam_id: 'mid', rating: 1500 }, { steam_id: 'low', rating: 900 }];
  const count = new Map();
  for (let k = 0; k < 6000; k++) {
    const s = seedOrderOf(en, 'random').join();
    count.set(s, (count.get(s) || 0) + 1);
  }
  assert.equal(count.size, 6, 'all 6 orders of 3 drivers come up');
  for (const n of count.values()) assert.ok(n > 800 && n < 1200, `each about 1000 of 6000, not ${n}`);
  // the top seed (the bye, in a bracket not full) is anyone's: the best rated first only 1 time in 3
  const first = [...count].filter(([s]) => s.startsWith('top')).reduce((a, [, n]) => a + n, 0);
  assert.ok(first > 1700 && first < 2300);
  assert.deepEqual(seedOrderOf(en, 'rating'), ['top', 'mid', 'low']);
  assert.deepEqual(seedOrderOf(en), ['top', 'mid', 'low']);       // (every other cup: as before)
});
test('a shuffle with no modulo bias: a draw at the uneven top of the 32-bit range is thrown away', () => {
  // 3 items: first a place out of 3 (2^32 % 3 = 1, so 4294967295, the last value, would favour 0: drawn again, 7 -> 1),
  // then out of 2 (0)
  const draws = [4294967295, 7, 0];
  const got = shuffle(['a', 'b', 'c'], () => draws.shift());
  assert.deepEqual(draws, []);
  assert.deepEqual(got, ['c', 'a', 'b']);
});
test('a cup in a new rally each round: four rounds, four rallies in random order, each round its stages drawn there', async () => {
  const { env, db } = fakeD1();
  const add = (rally, id, km) => db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, '[]', ?, 0, ?)")
    .run(`${rally} ${id}`, km * 1000, (rally === 'Wales' ? 'Weles' : rally.replace(' ', '')) + id);
  for (const id of ['S2MunsterFullForward', 'S2MunsterFullReverse', 'S2MunsterShort1Forward', 'S2MunsterShort1Reverse', 'S2MunsterShort2Forward',
    'S2MunsterShort2Reverse', 'S4SaverneFullForward', 'S4SaverneFullReverse', 'S4SaverneShort1Forward', 'S4SaverneShort1Reverse']) add('Alsace', id, 6);
  for (const id of ['S4HafrenSouthFullForward', 'S4HafrenSouthFullReverse', 'S3HafrenNorthFullForward', 'S3HafrenNorthCut1Forward',
    'S3HafrenNorthCut1Reverse', 'S3HafrenNorthCut2Forward']) add('Wales', id, 6);
  for (const id of ['S1AFullForward', 'S2BFullForward', 'S3CFullForward', 'S4DFullForward', 'S5EFullForward']) { add('Greece', id, 7); add('Monte Carlo', id, 7); }
  const slot = (day, time) => ({ track: 'Alsace S2MunsterFullForward', day, service: false, weather: 'Clear', time });
  const spec = { rally: 'Alsace', car: 'Mini Cooper S 1275', car_class: null, rules: {}, stages: [slot(1, '09:00'), slot(1, '13:00'), slot(2, '10:00'), slot(2, '15:00')],
    draw: { maxKm: 40, rallies: ['Alsace', 'Greece', 'Monte Carlo', 'Wales'] } };
  const now0 = Date.UTC(2026, 10, 15, 18, 0);
  for (let i = 0; i < 16; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  db.prepare(`INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('minich01', 'Mini', 'acr-daily', 'CODE3456', 0, 'cup')`).run();
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created, official)
    VALUES ('minich01', 'Mini', 'acr-daily', 128, 0, '[100]', ?, ?, 168, 'open', 0, 1)`).run(JSON.stringify(spec), now0);
  for (let i = 0; i < 16; i++) db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('minich01', ?, 0, 0)").run(sid(i));
  assert.deepEqual(await cupsTick(env, now0), [{ cup: 'minich01', did: 'started' }]);
  let now = now0;
  for (let round = 1; round < 4; round++) {                 // nobody drives: the higher seeds go through, the next round opens
    now += 169 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'minich01'").run(now - LIMITS.graceMs - 1);
    assert.deepEqual((await cupsTick(env, now)).map((d) => d.did), [`round ${round + 1}`]);
  }
  const rounds = db.prepare(`SELECT m.round, MIN(e.rally) AS rally, COUNT(DISTINCT e.rally) AS n, MIN(e.stages) AS stages,
      COUNT(DISTINCT e.stages) AS sets FROM cup_matches m JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = 'minich01'
      GROUP BY m.round ORDER BY m.round`).all();
  assert.equal(rounds.length, 4);
  assert.ok(rounds.every((r) => r.n === 1 && r.sets === 1), 'every match of a round: the same rally, the same stages');
  assert.deepEqual(rounds.map((r) => r.rally).sort(), spec.draw.rallies, 'all four rallies, one each round');
  for (const r of rounds) {
    const st = JSON.parse(r.stages);
    assert.equal(st.length, 4, `${r.rally}: four stages`);
    assert.ok(st.every((s) => s.track.startsWith(r.rally + ' ')), `${r.rally}: its own stages (${st.map((s) => s.track)})`);
    assert.equal(new Set(st.map((s) => s.track)).size, 4);
  }
  // each driver told where their round is
  assert.match(db.prepare("SELECT body FROM messages WHERE kind = 'cup' AND body LIKE '%quarter-final%' LIMIT 1").get().body,
    new RegExp(`The stages \\((${spec.draw.rallies.join('|')})\\): `));
});

// Sweden (the game's 0.7): its stage ids as the game has them, the typo SwedenS3FredriksbergCu1Reverse included
const SWEDEN = ['S1VargasenFullForward', 'S1VargasenFullReverse', 'S1VargasenCut1Forward', 'S1VargasenCut1Reverse',
  'S1VargasenCut2Forward', 'S1VargasenCut2Reverse', 'S1VargasenCut3Forward', 'S1VargasenCut3Reverse', 'S3FredriksbergFullForward',
  'S3FredriksbergFullReverse', 'S3FredriksbergCut1Forward', 'S3FredriksbergCu1Reverse', 'S3FredriksbergCut2Forward', 'S3FredriksbergCut2Reverse'];

test('Sweden\'s draw: its Cu1 typo is Cut1 the other way (the same road), never both in a round', () => {
  const pool = SWEDEN.map((id) => ({ track: `Sweden ${id}`, stageId: `Sweden${id}`, lengthM: 6000 }));
  const slots = [1, 1, 2, 2].map((day) => ({ day, service: false, weather: 'Clear', time: '10:00' }));
  for (let k = 0; k < 300; k++) {
    const got = drawStages(pool, slots, new Set(), 40, Math.random, { twice: true }).map((s) => s.track);
    assert.equal(new Set(got).size, 4);
    assert.ok(!(got.includes('Sweden S3FredriksbergCut1Forward') && got.includes('Sweden S3FredriksbergCu1Reverse')), got.join());
    assert.ok(!(got.includes('Sweden S3FredriksbergFullForward') && got.includes('Sweden S3FredriksbergCu1Reverse')), got.join());
  }
});

test('the MINI CHALLENGE: five rallies with Sweden, one each round, seeded at random', async () => {
  const { env, db } = fakeD1();
  const add = (rally, id, km) => db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, '[]', ?, 0, ?)")
    .run(`${rally} ${id}`, km * 1000, (rally === 'Wales' ? 'Weles' : rally.replace(' ', '')) + id);
  for (const id of ['S2MunsterFullForward', 'S2MunsterFullReverse', 'S2MunsterShort1Forward', 'S2MunsterShort1Reverse', 'S2MunsterShort2Forward',
    'S2MunsterShort2Reverse', 'S4SaverneFullForward', 'S4SaverneFullReverse', 'S4SaverneShort1Forward', 'S4SaverneShort1Reverse']) add('Alsace', id, 6);
  for (const id of ['S4HafrenSouthFullForward', 'S4HafrenSouthFullReverse', 'S3HafrenNorthFullForward', 'S3HafrenNorthCut1Forward',
    'S3HafrenNorthCut1Reverse', 'S3HafrenNorthCut2Forward']) add('Wales', id, 6);
  for (const id of ['S1AFullForward', 'S2BFullForward', 'S3CFullForward', 'S4DFullForward', 'S5EFullForward']) { add('Greece', id, 7); add('Monte Carlo', id, 7); }
  for (const id of SWEDEN) add('Sweden', id, 6);
  const slot = (day, time) => ({ track: 'Alsace S2MunsterFullForward', day, service: false, weather: 'Clear', time });
  const spec = { rally: 'Alsace', car: 'Mini Cooper S 1275', car_class: null, rules: {}, seeding: 'random',
    stages: [slot(1, '09:00'), slot(1, '13:00'), slot(2, '10:00'), slot(2, '15:00')],
    draw: { maxKm: 40, rallies: ['Alsace', 'Greece', 'Monte Carlo', 'Wales', 'Sweden'] } };
  const now0 = Date.UTC(2026, 10, 22, 18, 0);
  for (let i = 0; i < 32; i++) {
    db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
    db.prepare('INSERT INTO ratings (steam_id, rating, races, peak, updated) VALUES (?, ?, 10, ?, 0)')   // (sid(0) the best rated)
      .run(sid(i), 3000 - 50 * i, 3000 - 50 * i);
  }
  db.prepare(`INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('minich02', 'Mini', 'acr-daily', 'CODE3457', 0, 'cup')`).run();
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created, official)
    VALUES ('minich02', 'Mini', 'acr-daily', 128, 0, '[100]', ?, ?, 168, 'open', 0, 1)`).run(JSON.stringify(spec), now0);
  for (let i = 0; i < 32; i++) db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('minich02', ?, 0, 0)").run(sid(i));
  assert.deepEqual(await cupsTick(env, now0), [{ cup: 'minich02', did: 'started' }]);
  const seeds = db.prepare("SELECT steam_id FROM cup_entries WHERE cup_id = 'minich02' ORDER BY seed").all().map((r) => r.steam_id);
  assert.equal(new Set(seeds).size, 32);
  assert.notDeepEqual(seeds, Array.from({ length: 32 }, (_x, i) => sid(i)), 'not by rating (32! orders: never this one by chance)');
  let now = now0;
  for (let round = 1; round < 5; round++) {
    now += 169 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'minich02'").run(now - LIMITS.graceMs - 1);
    assert.deepEqual((await cupsTick(env, now)).map((d) => d.did), [`round ${round + 1}`]);
  }
  const rounds = db.prepare(`SELECT m.round, MIN(e.rally) AS rally, MIN(e.stages) AS stages FROM cup_matches m
      JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = 'minich02' GROUP BY m.round ORDER BY m.round`).all();
  assert.deepEqual(rounds.map((r) => r.rally).sort(), [...spec.draw.rallies].sort(), 'all five, Sweden too, one each round');
  const sweden = JSON.parse(rounds.find((r) => r.rally === 'Sweden').stages);
  assert.ok(sweden.every((s) => s.track.startsWith('Sweden ')) && new Set(sweden.map((s) => s.track)).size === 4);
});

test('the home page\'s strip: the official cup taking entries first, then the newest under way; never a driver\'s cup', async () => {
  const { env, db } = fakeD1();
  const add = (id, name, status, starts, official = 1) => db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts,
    round_hours, status, created, official) VALUES (?, ?, 'acr-daily', 16, 0, '[100]', ?, ?, 72, ?, 0, ?)`).run(id, name, JSON.stringify(SPEC), starts, status, official);
  const strip = async () => {
    const r = await cupsApi(new Request('https://acrdaily.test/api/cups/official'), env, '/api/cups/official', null, true, Date.now(),
      { json: (data) => data, err: (e) => ({ error: e }) });
    return r.cups.map((c) => c.name);
  };
  add('aaaaaaaa', 'Inaugural Cup', 'running', 1000);
  add('bbbbbbbb', 'Mini Challenge', 'open', 9000);
  add('cccccccc', 'A driver\'s cup', 'open', 5000, 0);
  add('dddddddd', 'An old one', 'finished', 500);
  assert.deepEqual(await strip(), ['Mini Challenge', 'Inaugural Cup'], 'the one taking entries first');
  db.prepare("UPDATE cups SET status = 'running' WHERE id = 'bbbbbbbb'").run();
  assert.deepEqual(await strip(), ['Mini Challenge', 'Inaugural Cup'], 'both under way: the newest');
});
