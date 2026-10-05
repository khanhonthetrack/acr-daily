import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isoWeek, pointsFor, weekDays, weekStandings, weekStart } from '../src/week.js';

test('weeks start on Monday (UTC)', () => {
  assert.equal(weekStart('2026-10-05'), '2026-10-05');   // a Monday
  assert.equal(weekStart('2026-10-11'), '2026-10-05');   // Sunday
  assert.equal(weekStart('2026-10-04'), '2026-09-28');   // the Sunday before
  assert.deepEqual(weekDays('2026-10-05'), ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']);
  assert.equal(isoWeek('2026-10-05'), 41);
});

test('points: WRC scale, then 1 per finisher, DNF 0', () => {
  assert.deepEqual([1, 2, 3, 10, 11, 40].map(pointsFor), [25, 18, 15, 1, 1, 1]);
  assert.equal(pointsFor(null), 0);
});

test('standings add up across stages, ties broken by wins then stages scored', () => {
  const e = (id, rank, status = 'finished') => ({ steamId: id, name: id, rank, status, runId: 1 });
  const stages = [
    { date: '2026-10-05', slot: 1, board: [e('a', 1), e('b', 2), e('c', null, 'dnf')] },
    { date: '2026-10-05', slot: 2, board: [e('b', 1), e('a', 2)] },
    { date: '2026-10-06', slot: 1, board: [e('c', 1)] },
    { date: '2026-10-06', slot: 2, future: true, board: null },
  ];
  const s = weekStandings(stages);
  assert.deepEqual(s.map((p) => [p.name, p.total, p.rank]), [['a', 43, 1], ['b', 43, 1], ['c', 25, 3]]);
  assert.equal(s.find((p) => p.name === 'c').cells['2026-10-05/1'].dnf, true);
  assert.equal(s.find((p) => p.name === 'a').scored, 2);
});
