// Credits (a prototype): the amounts, the wager daily's payouts (the house stakes too), a league event's pot.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { CREDITS, creditsOn, nextStreak, potPayouts, WAGER, wagerPayouts, wagerRefunds } from '../src/credits.js';

test('credits are on from CREDITS_FROM, and off without it', () => {
  assert.equal(creditsOn({ CREDITS_FROM: '2026-10-10' }, '2026-10-09'), false);
  assert.equal(creditsOn({ CREDITS_FROM: '2026-10-10' }, '2026-10-10'), true);
  assert.equal(creditsOn({ CREDITS_FROM: '' }, '2026-10-10'), false);
});

test('the amounts: a day brings exactly one stake (daily bonus + SS1), and day 1 one even with a DNF on SS1', () => {
  assert.deepEqual([CREDITS.welcome, CREDITS.daily, CREDITS.finish, WAGER.stake, WAGER.slot], [50, 50, 50, 100, 2]);
  assert.equal(CREDITS.daily + CREDITS.finish, WAGER.stake);
  assert.equal(CREDITS.welcome + CREDITS.daily, WAGER.stake);
});

test('days in a row: one more after yesterday, else 1 (shown only: the bonus is the same every day)', () => {
  assert.equal(nextStreak('2026-10-08', '2026-10-09', 4), 5);
  assert.equal(nextStreak('2026-10-07', '2026-10-09', 4), 1);
  assert.equal(nextStreak(null, '2026-10-09', 0), 1);
  assert.equal(nextStreak('2026-09-30', '2026-10-01', 2), 3);           // across a month
});

const e = (steamId, totalMs) => ({ steamId, finished: totalMs != null, totalMs });
const sum = (m) => [...m.values()].reduce((a, x) => a + x, 0);
// n drivers who all finished, P1 the fastest: their payouts in finishing order
const field = (n) => [...wagerPayouts(Array.from({ length: n }, (_, i) => e('p' + (i + 1), 100 + i)), 100).values()];

test('the wager: the house stakes too, so the top half of the drivers rounded up get 200, the fastest the rest', () => {
  assert.deepEqual(field(1), [200]);
  assert.deepEqual(field(2), [300, 0]);
  assert.deepEqual(field(3), [200, 200, 0]);
  assert.deepEqual(field(4), [300, 200, 0, 0]);
  assert.deepEqual(field(5), [200, 200, 200, 0, 0]);
  assert.deepEqual(field(6), [300, 200, 200, 0, 0, 0]);
  // the house's stake is the only credits made: one stake, whenever someone finished
  for (const n of [1, 2, 3, 4, 5, 6]) assert.equal(field(n).reduce((a, x) => a + x, 0), (n + 1) * 100);
});

test('the wager: DNFs lose their stake; fewer finishers than winners leave the rest to the fastest', () => {
  const four = wagerPayouts([e('a', 300), e('b', 200), e('c', 400), e('d', null)], 100);
  assert.deepEqual(Object.fromEntries(four), { a: 200, b: 300, c: 0, d: 0 });
  // only one of four finished: the whole pot, the house's stake too
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', null), e('b', 250), e('c', null), e('d', null)], 100)), { a: 0, b: 500, c: 0, d: 0 });
  assert.equal(sum(four), 500);
});

test('the wager: nobody finishing gives the stakes back (and the house pays nothing)', () => {
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', null)], 100)), { a: 100 });
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', null), e('b', null)], 100)), { a: 100, b: 100 });
  assert.equal(wagerPayouts([], 100).size, 0);
  assert.deepEqual([[e('a', 300)], [e('a', null), e('b', null)], [e('a', 1), e('b', null)], []].map(wagerRefunds), [false, true, false, true]);
});

test('the wager pays with what each driver staked, not with today\'s stake', () => {
  const s = (x, stake) => ({ ...x, stake });
  // staked 10 before WAGER.stake went up: settled at 10, the house's stake too (the default would pay 200)
  const m = wagerPayouts([s(e('a', 300), 10), s(e('b', 200), 10), s(e('c', null), 10)], 100);
  assert.deepEqual(Object.fromEntries(m), { a: 20, b: 20, c: 0 });
  assert.deepEqual(Object.fromEntries(wagerPayouts([s(e('a', null), 10)], 100)), { a: 10 });    // a refund: their own 10
});

test('the wager: a tie goes to who staked first (the entrants come in staking order)', () => {
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('x', 300), e('y', 300), e('z', null), e('q', null)], 100)),
    { x: 300, y: 200, z: 0, q: 0 });
});

test('a league pot: 50 / 30 / 20 to the top three, the rest to the winner, refunds when nobody finished', () => {
  const fees = new Map([['a', 25], ['b', 25], ['c', 25], ['d', 25]]);
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['c', 'a', 'd'])), { c: 50, a: 30, d: 20 });
  assert.deepEqual(Object.fromEntries(potPayouts(fees, ['b'])), { b: 100 });
  const odd = potPayouts(new Map([['a', 7], ['b', 7], ['c', 7]]), ['a', 'b', 'c']);
  assert.deepEqual(Object.fromEntries(odd), { a: 11, b: 6, c: 4 });          // 21: 10 + 1 left over, 6, 4
  assert.deepEqual(Object.fromEntries(potPayouts(fees, [])), { a: 25, b: 25, c: 25, d: 25 });
  assert.equal(potPayouts(new Map(), ['a']).size, 0);
  // a finisher who paid nothing still wins (the pot is the payers'; the league chooses who may enter free)
  assert.deepEqual(Object.fromEntries(potPayouts(new Map([['a', 10]]), ['z', 'a'])), { z: 7, a: 3 });
});
