// Head-to-heads and cups: who wins a 1v1, the bracket, the places and the pot.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { LABELS, potPayouts } from '../src/credits.js';
import { bracketSize, checkSplit, CUP, decideMatch, drawStages, firstRound, pickRally, places, potOf, prizeGroups, roundCloses, roundLength,
  roundName, seedOrder, utcWhen } from '../src/cups.js';
import { h2hOutcome } from '../src/h2h.js';

const row = (steamId, status, totalMs = null) => ({ steamId, status, totalMs });

test('a head-to-head: the lower total wins; one finisher wins; nobody, or a dead heat: no contest', () => {
  assert.deepEqual(h2hOutcome([row('a', 'finished', 300000), row('b', 'finished', 301500)], 'a', 'b'), { winner: 'a', note: 'by 1.500 s' });
  assert.deepEqual(h2hOutcome([row('b', 'finished', 290000), row('a', 'dnf')], 'a', 'b'), { winner: 'b', note: 'the only finisher' });
  assert.deepEqual(h2hOutcome([row('a', 'dnf'), row('b', 'running')], 'a', 'b'), { winner: null, note: 'nobody finished' });
  assert.deepEqual(h2hOutcome([], 'a', 'b'), { winner: null, note: 'nobody finished' });
  assert.deepEqual(h2hOutcome([row('a', 'finished', 300000), row('b', 'finished', 300000)], 'a', 'b'), { winner: null, note: 'a dead heat' });
  // someone else in the rows (not one of the two) counts for nothing
  assert.equal(h2hOutcome([row('z', 'finished', 1), row('b', 'finished', 5)], 'a', 'b').winner, 'b');
});

test('the bracket: a power of two that holds everyone, the top seeds apart until late', () => {
  assert.deepEqual([2, 3, 4, 5, 8, 9, 17, 32, 33, 65, 128].map(bracketSize), [2, 4, 4, 8, 8, 16, 32, 32, 64, 128, 128]);
  assert.equal(CUP.sizes.at(-1), 128);
  assert.deepEqual(seedOrder(2), [1, 2]);
  assert.deepEqual(seedOrder(4), [1, 4, 2, 3]);
  assert.deepEqual(seedOrder(8), [1, 8, 4, 5, 2, 7, 3, 6]);
  const s16 = seedOrder(16);
  assert.equal(new Set(s16).size, 16);
  assert.ok(s16.indexOf(1) < 8 && s16.indexOf(2) >= 8, 'seeds 1 and 2 in different halves');
});

test('round 1: byes go to the top seeds; nobody meets an empty slot twice', () => {
  const r = firstRound(['s1', 's2', 's3', 's4', 's5']);          // 5 in a bracket of 8: three byes
  assert.deepEqual(r, [{ slot: 0, a: 's1', b: null }, { slot: 1, a: 's4', b: 's5' }, { slot: 2, a: 's2', b: null }, { slot: 3, a: 's3', b: null }]);
  assert.deepEqual(firstRound(['x', 'y']), [{ slot: 0, a: 'x', b: 'y' }]);
  for (let n = 2; n <= 128; n++) {
    const m = firstRound(Array.from({ length: n }, (_, i) => 'd' + i));
    assert.equal(m.length, bracketSize(n) / 2);
    assert.ok(m.every((x) => x.a), 'every match has its higher seed');
    assert.equal(m.filter((x) => x.b).length * 2 + m.filter((x) => !x.b).length, n, 'everyone placed once');
  }
});

test('the rounds are named from the final back', () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 7].map((r) => roundName(r, 7)),
    ['Round of 128', 'Round of 64', 'Round of 32', 'Round of 16', 'Quarter-final', 'Semi-final', 'Final']);
  assert.equal(roundName(1, 1), 'Final');
});

test('a cup match: the faster goes through; nobody finishing or a dead heat: the higher seed; a bye: the one there', () => {
  const seed = { a: 1, b: 4 };
  const seedOf = (s) => seed[s];
  assert.deepEqual(decideMatch([row('b', 'finished', 100), row('a', 'finished', 200)], 'a', 'b', seedOf), { winner: 'b', note: 'by 0.100 s' });
  assert.equal(decideMatch([row('a', 'dnf'), row('b', 'dnf')], 'a', 'b', seedOf).winner, 'a');
  assert.equal(decideMatch([row('a', 'finished', 100), row('b', 'finished', 100)], 'a', 'b', seedOf).winner, 'a');
  assert.equal(decideMatch([row('b', 'finished', 100)], 'a', 'b', seedOf).winner, 'b');
  assert.deepEqual(decideMatch([], 'a', null, seedOf), { winner: 'a', note: 'a bye' });
});

test('the places: winner 1, runner-up 2, the losing semi-finalists 3, quarter-final losers 5', () => {
  const seedOf = (s) => +s.slice(1);
  const ms = [
    { round: 1, a: 's1', b: 's8', winner: 's1' }, { round: 1, a: 's4', b: 's5', winner: 's5' },
    { round: 1, a: 's2', b: 's7', winner: 's7' }, { round: 1, a: 's3', b: 's6', winner: 's3' },
    { round: 2, a: 's1', b: 's5', winner: 's5' }, { round: 2, a: 's3', b: 's7', winner: 's3' },
    { round: 3, a: 's3', b: 's5', winner: 's5' },
  ];
  assert.deepEqual(places(ms, 3, seedOf), [['s5', 1], ['s3', 2], ['s1', 3], ['s7', 3], ['s2', 5], ['s4', 5], ['s6', 5], ['s8', 5]]);
  // byes lose nobody: three drivers, the top seed's bye
  const three = [{ round: 1, a: 's1', b: null, winner: 's1' }, { round: 1, a: 's2', b: 's3', winner: 's3' }, { round: 2, a: 's1', b: 's3', winner: 's1' }];
  assert.deepEqual(places(three, 2, seedOf), [['s1', 1], ['s3', 2], ['s2', 3]]);
});

test('a cup\'s pot by its split: by place, the rounding and missing places to the winner', () => {
  const fees = new Map([['a', 25], ['b', 25], ['c', 25], ['d', 25]]);
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['c', 'a', 'd', 'b'], CUP.splits.four.shares)), { c: 60, a: 30, d: 5, b: 5 });
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['c', 'a'], CUP.splits.all.shares)), { c: 100 });
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['c', 'a', 'd'], CUP.splits.two.shares)), { c: 70, a: 30 });
  // a free cup: nothing to share
  assert.equal(potPayouts(new Map(), ['a', 'b'], CUP.splits.four.shares).size, 0);
});

test('a split of the maker\'s own: a % per place down the bracket, 100 in all, no place worth more than a better one', () => {
  assert.deepEqual(checkSplit({ split: 'two' }, 8), { shares: [70, 30] });
  assert.ok(checkSplit({ split: 'nope' }, 8).error);
  // 1st, 2nd, each of 3rd-4th, each of 5th-8th; trailing zeros dropped
  assert.deepEqual(checkSplit({ prizes: [40, 20, 10, 5, 0] }, 16), { shares: [40, 20, 10, 10, 5, 5, 5, 5] });
  assert.deepEqual(checkSplit({ prizes: ['50', '30', '10', ''] }, 8), { shares: [50, 30, 10, 10] });
  assert.match(checkSplit({ prizes: [50, 30, 15] }, 8).error, /110%/);
  assert.match(checkSplit({ prizes: [30, 40, 15] }, 8).error, /better place/);
  assert.ok(checkSplit({ prizes: [40, 20, 10, 5] }, 4).error, 'a cup of 4 has no 5th-8th');
  assert.ok(checkSplit({ prizes: [99.5, 0.5] }, 4).error, 'whole percentages');
  assert.ok(checkSplit({ prizes: [] }, 4).error);
  // shown by place; paid as places() orders the drivers
  assert.deepEqual(prizeGroups([40, 20, 10, 10, 5, 5, 5, 5]), [{ places: '1st', pct: 40 }, { places: '2nd', pct: 20 },
    { places: '3rd–4th', pct: 10, each: true }, { places: '5th–8th', pct: 5, each: true }]);
  assert.deepEqual(prizeGroups(CUP.splits.all.shares), [{ places: '1st', pct: 100 }]);
  const fees = new Map(['a', 'b', 'c', 'd', 'e', 'f'].map((s) => [s, 100]));
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['a', 'b', 'c', 'd', 'e', 'f'], checkSplit({ prizes: [40, 20, 10, 5] }, 8).shares)),
    { a: 300, b: 120, c: 60, d: 60, e: 30, f: 30 }, '6 of 8: the two 5th-8th places nobody reached go to the winner');
});

test('the credits history names every kind of line the code writes (never "h2h-stake")', () => {
  const dir = new URL('../src/', import.meta.url);
  const kinds = new Set();
  for (const f of readdirSync(dir).filter((x) => x.endsWith('.js'))) {
    const src = readFileSync(new URL(f, dir), 'utf8');
    // the kind: give/takeWhenStmts' 4th argument, giveManyWhenStmts' 3rd (after its list)
    for (const m of src.matchAll(/(?:give|take)WhenStmts\(env, [^,()]+, [^,()]+, '([a-z0-9-]+)'|giveManyWhenStmts\(env, [^;]*?\)\), '([a-z0-9-]+)'/g)) kinds.add(m[1] || m[2]);
  }
  for (const k of ['h2h-stake', 'h2h-refund', 'cup-fee', 'cup-refund', 'cup-prize', 'wager', 'shop']) assert.ok(kinds.has(k), k);
  // (and the kinds passed in a variable: a 1V1's and a wager's payouts, the daily bonuses)
  for (const k of ['h2h-win', 'wager-win', 'wager-refund', 'welcome', 'daily']) kinds.add(k);
  assert.deepEqual([...kinds].filter((k) => !LABELS[k]), []);
  assert.equal(LABELS['h2h-stake'], '1V1 stake');
});

test('an official cup\'s pot: ACR Daily\'s prize with the fees, shared alike; ACR Daily is paid nothing', () => {
  const free = potOf([{ steam_id: 'a', fee: 0 }, { steam_id: 'b', fee: 0 }], 1000);
  const pay = potPayouts(free, ['a', 'b'], CUP.splits.four.shares);
  pay.delete('');                                         // (ACR Daily's share of a refund: there is none to make)
  assert.deepEqual(Object.fromEntries(pay), { a: 700, b: 300 });   // 60 % + the missing places' 5 + 5, and 30 %
  assert.deepEqual(Object.fromEntries(potOf([{ steam_id: 'a', fee: 10 }, { steam_id: 'b', fee: 0 }], 0)), { a: 10 });
  assert.equal([...potOf([{ steam_id: 'a', fee: 10 }], 50).values()].reduce((x, y) => x + y, 0), 60);
});

test('how long a round is, said', () => {
  assert.deepEqual([12, 24, 36, 48, 72, 168, 336].map(roundLength), ['12 hours', '24 hours', '36 hours', '2 days', '3 days', '7 days', '14 days']);
});

test('rounds close at fixed times: the start plus a round each, whenever they opened', () => {
  const H = 3600000, starts = Date.UTC(2026, 9, 25, 18), c = { starts, round_hours: 168 };
  assert.equal(roundCloses(c, 1, starts + 3 * 60000), starts + 168 * H);                // round 1, opened by the cron a few minutes in
  assert.equal(roundCloses(c, 2, starts + 168 * H + 35 * 60000), starts + 336 * H);     // round 2, opened once round 1 was decided
  assert.equal(utcWhen(roundCloses(c, 2, starts + 168 * H + 35 * 60000)), 'Sun 8 Nov, 18:00 UTC');
  // opened with less than half a round left (the cron was down): a whole round from then
  assert.equal(roundCloses(c, 2, starts + 300 * H), starts + 468 * H);
});

// Monte Carlo's stages as the game has them: two places, each a full stage and its cuts, each road both ways
const MC = [['La Bollène', 'S1BolleneFullForward', 18.1], ['Peïra Cava', 'S1BolleneFullReverse', 17.9], ['Turini Montée', 'S1BolleneCut1Forward', 11.9],
  ['Turini Descente', 'S1BolleneCut1Reverse', 11.7], ['Turini - Peïra Cava', 'S1BolleneCut2Forward', 6.2], ['Peïra Cava - Turini', 'S1BolleneCut2Reverse', 6.3],
  ["Pra d'Alart", 'S1BolleneCut3Forward', 5.3], ['Sommet de Turini', 'S1BolleneCut3Reverse', 5.3], ['Sisteron - St. Geniez', 'S2SisteronFullForward', 13.2],
  ['St. Geniez - Sisteron', 'S2SisteronFullReverse', 13.2], ['Sisteron - Mézien', 'S2SisteronCut1Forward', 7.3], ['Mézien - Sisteron', 'S2SisteronCut1Reverse', 7.3],
  ['Mézien - St. Geniez', 'S2SisteronCut2Forward', 5.4], ['St. Geniez - Mézien', 'S2SisteronCut2Reverse', 5.2]]
  .map(([n, id, km]) => ({ track: 'Monte Carlo ' + n, stageId: 'MonteCarlo' + id, lengthM: km * 1000 }));
const SLOTS = [{ day: 1, weather: 'Clear', time: '09:00' }, { day: 1, weather: 'LightCloud', time: '13:00' }, { day: 2, weather: 'Clear', time: '19:00' }];
const road = (track) => { const m = /^MonteCarlo(S\d\w+?)(Full|Cut\d)/.exec(MC.find((s) => s.track === track).stageId); return [m[1], m[2]]; };
const seeded = (seed) => () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);

test('a cup\'s draw: three stages on three roads, in the slots as set, a new draw each time', () => {
  const seen = new Set();
  for (let k = 1; k <= 300; k++) {
    const d = drawStages(MC, SLOTS, new Set(), 40, seeded(k));
    assert.equal(d.length, 3);
    assert.deepEqual(d.map((s) => [s.day, s.time, s.weather]), SLOTS.map((s) => [s.day, s.time, s.weather]));
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) {
      const [a, b] = [road(d[i].track), road(d[j].track)];
      assert.ok(a[0] !== b[0] || (a[1] !== b[1] && a[1] !== 'Full' && b[1] !== 'Full'), `same road: ${d[i].track} / ${d[j].track}`);
    }
    assert.ok(d.reduce((x, s) => x + MC.find((m) => m.track === s.track).lengthM, 0) <= 40000, 'within 40 km');
    seen.add(d.map((s) => s.track).sort().join('|'));
  }
  assert.ok(seen.size > 20, 'many different draws');
});

test('a cup\'s draw: stages not driven in the cup yet first; too few roads: none', () => {
  const used = new Set(MC.filter((s) => s.stageId.endsWith('Reverse')).map((s) => s.track));   // every road driven one way
  for (let k = 1; k <= 50; k++) {
    const d = drawStages(MC, SLOTS, used, null, seeded(k));
    assert.ok(d.every((s) => !used.has(s.track)), d.map((s) => s.track).join(', '));
  }
  // left undriven: only Sisteron's stages, two roads: two of them, and one driven before
  const most = new Set(MC.slice(0, 9).map((s) => s.track));
  for (let k = 1; k <= 50; k++) assert.equal(drawStages(MC, SLOTS, most, null, seeded(k)).filter((s) => most.has(s.track)).length, 1);
  const all = new Set(MC.map((s) => s.track));                       // all driven: a draw all the same
  assert.equal(drawStages(MC, SLOTS, all, null, seeded(7)).length, 3);
  assert.equal(drawStages(MC.slice(0, 2), SLOTS, new Set(), null, seeded(1)), null);   // two stages: not 3
  assert.equal(drawStages(MC, SLOTS, new Set(), 1, seeded(3)).length, 3);  // no draw that short: one longer all the same
});

test('a draw in Alsace: its cuts are Short1 / Short2, never a stage and its reverse or a full stage with its cut', () => {
  const AL = [['Montée', 'S2MunsterFullForward'], ['Descente', 'S2MunsterFullReverse'], ['Luttenbach', 'S2MunsterShort1Forward'],
    ['Forêt de Munster', 'S2MunsterShort1Reverse'], ['Sommet', 'S2MunsterShort2Forward'], ['Petit Ballon', 'S2MunsterShort2Reverse'],
    ['Forêt', 'S4SaverneFullForward'], ['Steigenbach', 'S4SaverneFullReverse'], ['Obersteigen', 'S4SaverneShort1Forward'],
    ['La Mossig', 'S4SaverneShort1Reverse']].map(([n, id]) => ({ track: 'Alsace ' + n, stageId: 'Alsace' + id, lengthM: 6000 }));
  const roadAl = (t) => /^Alsace(S\d\w+?)(Full|Short\d)/.exec(AL.find((s) => s.track === t).stageId).slice(1);
  for (let k = 1; k <= 200; k++) {
    const d = drawStages(AL, SLOTS, new Set(), null, seeded(k));
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) {
      const [a, b] = [roadAl(d[i].track), roadAl(d[j].track)];
      assert.ok(a[0] !== b[0] || (a[1] !== b[1] && a[1] !== 'Full' && b[1] !== 'Full'), `same road: ${d[i].track} / ${d[j].track}`);
    }
  }
  // Saverne's full stage both ways and Munster's: two roads, so one of them twice (both ways), never a stage twice
  for (let k = 1; k <= 50; k++) {
    const d = drawStages(AL.filter((s) => /Full/.test(s.stageId)), SLOTS, new Set(), null, seeded(k));
    assert.equal(new Set(d.map((s) => s.track)).size, 3);
    assert.equal(new Set(d.map((s) => roadAl(s.track)[0])).size, 2, 'both roads');
  }
  assert.equal(drawStages(AL.filter((s) => /S4SaverneFull/.test(s.stageId)), SLOTS, new Set(), null, seeded(1)), null, 'two stages: not three');
  // all driven but Munster's full stage (both ways), which leaves one more road at most: three driven ones all the same
  const most = new Set(AL.filter((s) => !/MunsterFull/.test(s.stageId)).map((s) => s.track));
  for (let k = 1; k <= 50; k++) {
    const d = drawStages(AL, SLOTS, most, null, seeded(k));
    assert.ok(d && d.length === 3 && d.every((s) => most.has(s.track)), JSON.stringify(d));
  }
});

test('four stages in Wales (three roads): every road, one of them again, never a stage twice nor a full stage over two cuts', () => {
  // Wales as the game has it (the live routes, 2026-11-04): Hafren North, a full stage and two cuts, both ways; Hafren South
  const WA = [['Cwmbiga', 'S3HafrenNorthFullForward', 11.5], ['Afon Biga', 'S3HafrenNorthFullReverse', 11.5],
    ['Hafren Forest', 'S3HafrenNorthCut1Forward', 6.3], ['Fedw Fain', 'S3HafrenNorthCut1Reverse', 6.3], ['Banc Gwyn', 'S3HafrenNorthCut2Forward', 5.3],
    ['Ospreys', 'S3HafrenNorthCut2Reverse', 5.4], ['Afon Bidno', 'S4HafrenSouthFullForward', 5.2], ['Severn', 'S4HafrenSouthFullReverse', 5.0]]
    .map(([n, id, km]) => ({ track: 'Wales ' + n, stageId: 'Weles' + id, lengthM: km * 1000 }));
  const FOUR = [...SLOTS.slice(0, 2), { day: 2, weather: 'HeavyCloud', time: '10:00' }, { day: 2, weather: 'Clear', time: '17:30' }];
  const roadWa = (t) => /^Weles(S\d\w+?)(Full|Cut\d)/.exec(WA.find((s) => s.track === t).stageId).slice(1);
  const clash = (a, b) => a[0] === b[0] && (a[1] === b[1] || a[1] === 'Full' || b[1] === 'Full');
  for (let k = 1; k <= 200; k++) {
    const d = drawStages(WA, FOUR, new Set(), 40, seeded(k));
    assert.deepEqual(d.map((s) => [s.day, s.time, s.weather]), FOUR.map((s) => [s.day, s.time, s.weather]));
    assert.equal(new Set(d.map((s) => s.track)).size, 4, 'never a stage twice');
    const r = d.map((s) => roadWa(s.track));
    let clashes = 0;
    for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) if (clash(r[i], r[j])) clashes++;
    assert.equal(clashes, 1, `one road twice, no more: ${d.map((s) => s.track).join(', ')}`);
    assert.ok(d.reduce((x, s) => x + WA.find((m) => m.track === s.track).lengthM, 0) <= 40000);
  }
  // three slots: three roads, as before
  for (let k = 1; k <= 50; k++) {
    const r = drawStages(WA, SLOTS, new Set(), null, seeded(k)).map((s) => roadWa(s.track));
    assert.ok(!clash(r[0], r[1]) && !clash(r[0], r[2]) && !clash(r[1], r[2]));
  }
});

test('a cup visiting several rallies: each round one it hasn\'t been to, at random; all been to: not the last one again', () => {
  const R = ['Alsace', 'Greece', 'Monte Carlo', 'Wales'];
  const seen = new Set();
  for (let k = 1; k <= 100; k++) {
    seen.add(pickRally(R, [], seeded(k)));
    assert.ok(['Greece', 'Wales'].includes(pickRally(R, ['Alsace', 'Alsace', 'Monte Carlo'], seeded(k))));
    assert.ok(['Alsace', 'Greece', 'Monte Carlo'].includes(pickRally(R, ['Monte Carlo', 'Alsace', 'Greece', 'Wales', 'Wales'], seeded(k))));
  }
  assert.equal(seen.size, 4, 'any of them first');
  assert.equal(pickRally(['Wales'], ['Wales'], seeded(1)), 'Wales');
});

test('a cup that spreads: the shares of places nobody reaches go to the places reached, in proportion', () => {
  const shares = checkSplit({ prizes: [40, 20, 10, 5] }, 16).shares;     // 1st 40, 2nd 20, 3rd-4th 10, 5th-8th 5
  const pot = (n) => potOf(Array.from({ length: n }, (_, i) => ({ steam_id: 's' + i, fee: 300 })), 1000);
  const order = (n) => Array.from({ length: n }, (_, i) => 's' + i);
  const paid = (n, spread) => { const p = potPayouts(pot(n), order(n), shares, spread); p.delete(''); return Object.fromEntries(p); };
  // full (16): 5800, as set; the quarter-final losers 5 % each
  assert.deepEqual(paid(16, true), { s0: 2320, s1: 1160, s2: 580, s3: 580, s4: 290, s5: 290, s6: 290, s7: 290 });
  assert.deepEqual(paid(16, true), paid(16, false));
  // 8 drivers: 3400, all 8 places reached
  assert.deepEqual(paid(8, true), { s0: 1360, s1: 680, s2: 340, s3: 340, s4: 170, s5: 170, s6: 170, s7: 170 });
  // 6 drivers (two quarter-final byes): 2800 by 40 / 20 / 10 / 10 / 5 / 5 of 90
  assert.deepEqual(paid(6, true), { s0: 1246, s1: 622, s2: 311, s3: 311, s4: 155, s5: 155 });
  assert.deepEqual(paid(6, false), { s0: 1400, s1: 560, s2: 280, s3: 280, s4: 140, s5: 140 }, 'not spread: the missing 10 % to the winner');
  // 4 drivers (semi-finals first): 2200 by 40 / 20 / 10 / 10 of 80; 2 drivers: 1600 by 40 / 20 of 60
  assert.deepEqual(paid(4, true), { s0: 1100, s1: 550, s2: 275, s3: 275 });
  assert.deepEqual(paid(2, true), { s0: 1067, s1: 533 });
  for (const n of [2, 3, 5, 6, 7, 9, 16]) assert.equal(Object.values(paid(n, true)).reduce((a, x) => a + x, 0), 300 * n + 1000, `${n}: all of the pot`);
});