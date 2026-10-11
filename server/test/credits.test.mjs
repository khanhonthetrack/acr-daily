// Credits (a prototype): the daily bonus and its streak, the wager daily's payouts, a league event's pot.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { creditsOn, dailyBonus, nextStreak, potPayouts, wagerPayouts, wagerRefunds } from '../src/credits.js';

test('credits are on from CREDITS_FROM, and off without it', () => {
  assert.equal(creditsOn({ CREDITS_FROM: '2026-10-10' }, '2026-10-09'), false);
  assert.equal(creditsOn({ CREDITS_FROM: '2026-10-10' }, '2026-10-10'), true);
  assert.equal(creditsOn({ CREDITS_FROM: '' }, '2026-10-10'), false);
});

test('the daily bonus grows with the streak, up to 20; a missed day starts it again', () => {
  assert.deepEqual([1, 2, 3, 6, 7, 30].map(dailyBonus), [10, 12, 14, 20, 20, 20]);
  assert.equal(nextStreak('2026-10-08', '2026-10-09', 4), 5);
  assert.equal(nextStreak('2026-10-07', '2026-10-09', 4), 1);
  assert.equal(nextStreak(null, '2026-10-09', 0), 1);
  assert.equal(nextStreak('2026-09-30', '2026-10-01', 2), 3);           // across a month
});

const e = (steamId, totalMs) => ({ steamId, finished: totalMs != null, totalMs });
const sum = (m) => [...m.values()].reduce((a, x) => a + x, 0);

test('the wager: the top half doubles its stake, the rest lose it; nothing made or lost', () => {
  const four = wagerPayouts([e('a', 300), e('b', 200), e('c', 400), e('d', null)], 10);
  assert.deepEqual(Object.fromEntries(four), { a: 20, b: 20, c: 0, d: 0 });
  // five in: two winners, the odd stake to the fastest
  const five = wagerPayouts([e('a', 300), e('b', 200), e('c', 400), e('d', 500), e('e', 600)], 10);
  assert.deepEqual(Object.fromEntries(five), { a: 20, b: 30, c: 0, d: 0, e: 0 });
  // only one of four finished: the whole pot is theirs
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', null), e('b', 250), e('c', null), e('d', null)], 10)), { a: 0, b: 40, c: 0, d: 0 });
  for (const m of [four, five]) assert.equal(sum(m), m.size * 10);
});

test('the wager: no contest gives the stakes back', () => {
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', 300)], 10)), { a: 10 });                 // alone
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('a', null), e('b', null)], 10)), { a: 10, b: 10 });   // nobody finished
  assert.equal(wagerPayouts([], 10).size, 0);
  assert.deepEqual([[e('a', 300)], [e('a', null), e('b', null)], [e('a', 1), e('b', null)]].map(wagerRefunds), [true, true, false]);
});

test('the wager pays with what each driver staked, not with today\'s stake', () => {
  const s = (x, stake) => ({ ...x, stake });
  // staked 10 before WAGER.stake went up: settled at 10 (the default would pay 200)
  const m = wagerPayouts([s(e('a', 300), 10), s(e('b', 200), 10), s(e('c', null), 10)], 100);
  assert.deepEqual(Object.fromEntries(m), { a: 0, b: 30, c: 0 });
  assert.deepEqual(Object.fromEntries(wagerPayouts([s(e('a', 300), 10)], 100)), { a: 10 });    // a refund: their own 10
});

test('the wager: a tie goes to who staked first (the entrants come in staking order)', () => {
  assert.deepEqual(Object.fromEntries(wagerPayouts([e('x', 300), e('y', 300), e('z', null)], 10)), { x: 30, y: 0, z: 0 });
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
