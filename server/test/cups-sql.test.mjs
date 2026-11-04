// A cup's cron work on a real SQLite (schema.sql, node:sqlite) through a stand-in for D1 that counts the queries: a
// 100-driver cup from its start to its final. The free plan allows 50 D1 queries a cron run, so a round has to open,
// be decided and be paid with a handful of bulk statements, however big the cup.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { adminCup, cupsTick, seedOrderOf } from '../src/cups.js';
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

// every stage of the game as the live routes have them (2026-11-04): track, the game's id, km
const POOL = [['Alsace Descente', 'AlsaceS2MunsterFullReverse', 10.2], ['Alsace Forêt', 'AlsaceS4SaverneFullForward', 9.0],
  ['Alsace Forêt de Munster', 'AlsaceS2MunsterShort1Reverse', 6.7], ['Alsace La Mossig', 'AlsaceS4SaverneShort1Reverse', 4.7],
  ['Alsace Luttenbach', 'AlsaceS2MunsterShort1Forward', 6.9], ['Alsace Montée', 'AlsaceS2MunsterFullForward', 10.2],
  ['Alsace Obersteigen', 'AlsaceS4SaverneShort1Forward', 4.5], ['Alsace Petit Ballon', 'AlsaceS2MunsterShort2Reverse', 5.6],
  ['Alsace Sommet', 'AlsaceS2MunsterShort2Forward', 5.3], ['Alsace Steigenbach', 'AlsaceS4SaverneFullReverse', 8.9],
  ['Greece Aghii Theodori', 'GreeceS4LoutrakiCut2Forward', 5.7], ['Greece Aghii Theodori - Loutraki', 'GreeceS4LoutrakiFullReverse', 10.0],
  ['Greece Aghii Theodori Reverse', 'GreeceS4LoutrakiCut2Reverse', 5.7], ['Greece Elatia', 'GreeceS3ElatiaCut1Forward', 6.3],
  ['Greece Elatia - Zeli', 'GreeceS3ElatiaFullForward', 11.5], ['Greece Elatia Reverse', 'GreeceS3ElatiaCut1Reverse', 6.2],
  ['Greece Loutraki - Aghii Theodori', 'GreeceS4LoutrakiFullForward', 10.0], ['Greece New Loutraki', 'GreeceS4LoutrakiCut1Forward', 4.8],
  ['Greece New Loutraki Reverse', 'GreeceS4LoutrakiCut1Reverse', 4.8], ['Greece Zeli', 'GreeceS3ElatiaCut2Forward', 5.5],
  ['Greece Zeli - Elatia', 'GreeceS3ElatiaFullReverse', 11.7], ['Greece Zeli Reverse', 'GreeceS3ElatiaCut2Reverse', 5.7],
  ['Monte Carlo La Bollène', 'MonteCarloS1BolleneFullForward', 17.8], ['Monte Carlo Mézien - Sisteron', 'MonteCarloS2SisteronCut1Reverse', 7.1],
  ['Monte Carlo Mézien - St. Geniez', 'MonteCarloS2SisteronCut2Forward', 5.2], ['Monte Carlo Peïra Cava', 'MonteCarloS1BolleneFullReverse', 17.9],
  ['Monte Carlo Peïra Cava - Turini', 'MonteCarloS1BolleneCut2Reverse', 6.2], ["Monte Carlo Pra d'Alart", 'MonteCarloS1BolleneCut3Forward', 5.1],
  ['Monte Carlo Sisteron - Mézien', 'MonteCarloS2SisteronCut1Forward', 7.2], ['Monte Carlo Sisteron - St. Geniez', 'MonteCarloS2SisteronFullForward', 12.9],
  ['Monte Carlo Sommet de Turini', 'MonteCarloS1BolleneCut3Reverse', 5.2], ['Monte Carlo St. Geniez - Mézien', 'MonteCarloS2SisteronCut2Reverse', 5.2],
  ['Monte Carlo St. Geniez - Sisteron', 'MonteCarloS2SisteronFullReverse', 13.0], ['Monte Carlo Turini - Peïra Cava', 'MonteCarloS1BolleneCut2Forward', 6.1],
  ['Monte Carlo Turini Descente', 'MonteCarloS1BolleneCut1Reverse', 11.6], ['Monte Carlo Turini Montée', 'MonteCarloS1BolleneCut1Forward', 11.7],
  ['Wales Afon Bidno', 'WelesS4HafrenSouthFullForward', 5.2], ['Wales Afon Biga', 'WelesS3HafrenNorthFullReverse', 11.5],
  ['Wales Banc Gwyn', 'WelesS3HafrenNorthCut2Forward', 5.3], ['Wales Cwmbiga', 'WelesS3HafrenNorthFullForward', 11.5],
  ['Wales Fedw Fain', 'WelesS3HafrenNorthCut1Reverse', 6.3], ['Wales Hafren Forest', 'WelesS3HafrenNorthCut1Forward', 6.3],
  ['Wales Ospreys', 'WelesS3HafrenNorthCut2Reverse', 5.4], ['Wales Severn', 'WelesS4HafrenSouthFullReverse', 5.0]];
const RALLIES = ['Alsace', 'Greece', 'Monte Carlo', 'Wales'];

test('an official cup visiting four rallies: each round a new one, four stages of it; not full: the prizes spread', async () => {
  const { env, db } = fakeD1({ CREDITS_FROM: '2026-10-12' });
  for (const [t, id, km] of POOL) db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, 0, ?)').run(t, '[]', km * 1000, id);
  const now0 = Date.UTC(2026, 10, 4, 22, 0), starts = Date.UTC(2026, 10, 8, 18, 0);
  const four = [{ day: 1, weather: 'Clear', time: '09:00' }, { day: 1, weather: 'LightCloud', time: '13:00' },
    { day: 2, weather: 'HeavyCloud', time: '10:00' }, { day: 2, weather: 'Clear', time: '15:00' }];
  const body = { name: 'MINI CHALLENGE', about: 'x', size: 16, fee: 300, prize: 1000, prizes: [40, 20, 10, 5], spread: true, roundHours: 168,
    starts, draw: { maxKm: 40, rallies: RALLIES }, event: { car: 'Mini Cooper S 1275', rules: { penalty: 'light' }, stages: four } };
  const made = await adminCup(env, body, now0);
  assert.ok(made.id, JSON.stringify(made));
  const row = db.prepare('SELECT * FROM cups WHERE id = ?').get(made.id);
  const spec = JSON.parse(row.spec);
  assert.deepEqual([spec.car, spec.car_class, spec.spread, spec.draw], ['Mini Cooper S 1275', null, true, { maxKm: 40, rallies: RALLIES }]);
  assert.equal(spec.stages.length, 4);
  assert.deepEqual(JSON.parse(row.split), [40, 20, 10, 10, 5, 5, 5, 5]);
  assert.match((await adminCup(env, { ...body, draw: { rallies: ['Alsace', 'Nowhere'] } }, now0)).error, /^Nowhere hasn't 4 stages/);
  // spread stays as it was when a change leaves it out
  assert.equal(JSON.parse(db.prepare('SELECT spec FROM cups WHERE id = ?').get((await adminCup(env, { id: made.id, about: 'y' }, now0)).id).spec).spread, true);

  // six drivers: a bracket of 8, three rounds (two quarter-final byes)
  for (let i = 0; i < 6; i++) {
    db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
    db.prepare('INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES (?, ?, 300, 0)').run(made.id, sid(i));
  }
  let now = starts;
  assert.deepEqual(await cupsTick(env, now), [{ cup: made.id, did: 'started' }]);
  const raced = [];
  for (let round = 1; round <= 3; round++) {
    const evs = db.prepare(`SELECT e.* FROM league_events e JOIN cup_matches m ON m.event_id = e.id WHERE m.cup_id = ? AND m.round = ?`).all(made.id, round);
    assert.ok(evs.length >= 1);
    assert.equal(new Set(evs.map((e) => e.rally + e.stages)).size, 1, 'every match of a round the same rally and stages');
    const st = JSON.parse(evs[0].stages);
    assert.equal(st.length, 4);
    assert.ok(st.every((s) => s.track.startsWith(evs[0].rally + ' ')), `${evs[0].rally}: ${st.map((s) => s.track)}`);
    assert.equal(new Set(st.map((s) => s.track)).size, 4, 'never a stage twice');
    assert.equal(evs[0].car, 'Mini Cooper S 1275');
    assert.ok(db.prepare("SELECT 1 FROM messages WHERE body LIKE ? LIMIT 1").get(`%The stages, in ${evs[0].rally}: %`), 'the notice names the rally');
    raced.push(evs[0].rally);
    now += 169 * 3600000;
    db.prepare('UPDATE league_events SET closes = ? WHERE league_id = ?').run(now - LIMITS.graceMs - 1, made.id);
    await cupsTick(env, now);
  }
  assert.equal(new Set(raced).size, 3, `a new rally each round: ${raced}`);
  assert.equal(db.prepare('SELECT status FROM cups WHERE id = ?').get(made.id).status, 'finished');
  // the pot, 6 x 300 + 1000 = 2800, by 40 / 20 / 10 / 10 / 5 / 5 of the 90 % the six places take
  const paid = db.prepare("SELECT delta FROM credit_ledger WHERE kind = 'cup-prize' ORDER BY delta DESC").all().map((p) => p.delta);
  assert.deepEqual(paid, [1246, 622, 311, 311, 155, 155]);
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