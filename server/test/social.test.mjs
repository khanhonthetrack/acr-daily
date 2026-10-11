// Head-to-heads and cups: who wins a 1v1, the bracket, the places and the pot.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { potPayouts } from '../src/credits.js';
import { bracketSize, CUP, decideMatch, firstRound, places, roundName, seedOrder } from '../src/cups.js';
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
  assert.deepEqual([2, 3, 4, 5, 8, 9, 17, 32].map(bracketSize), [2, 4, 4, 8, 8, 16, 32, 32]);
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
  for (let n = 2; n <= 32; n++) {
    const m = firstRound(Array.from({ length: n }, (_, i) => 'd' + i));
    assert.equal(m.length, bracketSize(n) / 2);
    assert.ok(m.every((x) => x.a), 'every match has its higher seed');
    assert.equal(m.filter((x) => x.b).length * 2 + m.filter((x) => !x.b).length, n, 'everyone placed once');
  }
});

test('the rounds are named from the final back', () => {
  assert.deepEqual([1, 2, 3, 4, 5].map((r) => roundName(r, 5)), ['Round 1', 'Round 2', 'Quarter-final', 'Semi-final', 'Final']);
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
