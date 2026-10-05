// The daily report: the facts it is written from, and the plain report when Claude isn't available.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recapFacts, templateRecap, writeReport } from '../src/recap.js';

const entry = (rank, name, steamId, totalMs, extra = {}) => ({ runId: rank, steamId, name, country: 'fi', status: 'finished',
  rank, totalMs, gapMs: 0, resets: 0, splits: null, ...extra });

function day() {
  const b1 = [entry(1, 'osiek', 'a', 289637, { splits: [70000, 140000, 210000] }),
    entry(2, 'MaybeIWill', 'b', 347348, { gapMs: 57711, resets: 1, splits: [68035, 139754, 268444] }),
    entry(3, 'Kalle', 'c', 347900, { gapMs: 58263, splits: [71000, 142000, 269000] }),
    { runId: 9, steamId: 'd', name: 'Gone', status: 'dnf', reason: 'restarted', rank: null, totalMs: null, resets: 0 }];
  const b2 = [entry(1, 'MaybeIWill', 'b', 146085), entry(2, 'osiek', 'a', 149494, { gapMs: 3409 })];
  const stat = (ch, board, extra = {}) => ({
    challenge: ch, board, lengthM: 9017,
    field: { cleanRuns: board.filter((e) => e.status === 'finished' && !e.resets).length },
    records: { topSpeed: { name: 'osiek', kmh: 171.4, km: 6.31 }, avgSpeed: 112.1,
      longestFlatOut: { name: 'Kalle', ms: 18250, km: 2.4 }, ideal: { ms: 280000, gainMs: 9637 } },
    sections: { best: Array.from({ length: 10 }, (_, i) => ({ name: i < 7 ? 'osiek' : 'MaybeIWill', ms: 1000 })) },
    air: { longestJump: { name: 'MaybeIWill', ms: 1240, kmh: 118.2, km: 3.05 }, mostAirtime: { name: 'osiek', ms: 3100, count: 4 } },
    ...extra,
  });
  const ch1 = { track: 'Alsace Forêt', menuName: 'Forêt de Saverne', rally: 'Alsace', surface: 'Tarmac', car: 'Hyundai i20 N Rally2',
    weatherLabel: 'Light fog', timeLabel: 'Midday (12:00)' };
  const ch2 = { track: 'Alsace Obersteigen', menuName: 'Obersteigen', rally: 'Alsace', surface: 'Tarmac', car: 'Skoda Fabia RS Rally2' };
  return {
    date: '2026-10-05',
    stages: [{ slot: 1, st: stat(ch1, b1), prev: { date: '2026-09-29', car: 'Peugeot 208 Rally4', winner: 'Kalle', time: '5:01.002', drivers: 3 } },
      { slot: 2, st: stat(ch2, b2, { air: {} }), prev: null }],
    week: { week: 41, start: '2026-10-05', standings: [
      { steamId: 'a', name: 'osiek', rank: 1, total: 43, wins: 1, cells: { '2026-10-05/1': { pts: 25 }, '2026-10-05/2': { pts: 18 } } },
      { steamId: 'b', name: 'MaybeIWill', rank: 2, total: 43, wins: 1, cells: { '2026-10-05/1': { pts: 18 }, '2026-10-05/2': { pts: 25 } } },
      { steamId: 'c', name: 'Kalle', rank: 3, total: 15, wins: 0, cells: { '2026-10-05/1': { pts: 15 } } }] },
    history: [{ steam_id: 'a', dailies: 6, since: '2026-09-28' }, { steam_id: 'c', dailies: 2, since: '2026-10-01' }],
  };
}

test('facts: results, splits, the closest fight and the fun records, ready to quote', () => {
  const f = recapFacts(day());
  assert.equal(f.weekday, 'Monday');
  const s1 = f.stages[0];
  assert.equal(s1.stage, 'Forêt de Saverne');
  assert.deepEqual(s1.results[0], { pos: 1, driver: 'osiek', time: '4:49.637', gapToWinner: null, resets: 0 });
  assert.equal(s1.results[1].gapToWinner, '+57.711 s');
  assert.deepEqual(s1.dnf, [{ driver: 'Gone', reason: 'restarted' }]);
  assert.deepEqual(s1.splitLeaders.map((x) => x.driver), ['MaybeIWill', 'MaybeIWill', 'osiek']);   // led, then the reset
  assert.deepEqual(s1.closestFight, { positions: [2, 3], drivers: ['MaybeIWill', 'Kalle'], gap: '+0.552 s' });
  assert.deepEqual(s1.records.topSpeed, { driver: 'osiek', kmh: 171.4, atKm: 6.31 });
  assert.deepEqual(s1.records.longestJump, { driver: 'MaybeIWill', airtime: '1.2 s', takeOffKmh: 118.2, atKm: 3.05 });
  assert.equal(s1.records.longestFlatOut.flatOutFor, '18.3 s');
  assert.deepEqual(s1.records.fastestInMostTenths, { driver: 'osiek', tenths: 7, of: 10 });
  assert.equal(s1.records.perfectRun.quickerThanTheWinnersClockBy, '9.6 s');
  assert.deepEqual(s1.records.mostResets, { driver: 'MaybeIWill', resets: 1 });
  assert.equal(s1.lastTimeThisStageCameUp.winner, 'Kalle');
  assert.equal(f.stages[1].records.longestJump, null);
  assert.equal(f.stages[1].closestFight, null);             // two finishers: that is just the result
});

test('facts: history and the hall of fame as it stood before and after the day', () => {
  const f = recapFacts(day());
  const d = Object.fromEntries(f.drivers.map((x) => [x.driver, x]));
  assert.equal(d.osiek.dailiesBefore, 6);
  assert.equal(d.MaybeIWill.firstDaily, true);
  assert.equal(d.Kalle.drivingSince, '2026-10-01');
  assert.equal(f.hallOfFame.dayOfWeek, 1);
  assert.deepEqual(f.hallOfFame.standingsAfterTheDay[0], { pos: 1, driver: 'osiek', points: 43, wins: 1 });
  assert.equal(f.hallOfFame.leaderBeforeTheDay, null);      // a Monday: nobody had points before
  const later = day();
  later.date = '2026-10-06';
  later.week.standings[2].cells['2026-10-06/1'] = { pts: 25 };
  assert.deepEqual(recapFacts(later).hallOfFame.leaderBeforeTheDay, { driver: 'osiek', points: 43 });
});

test('nobody drove: no report', () => {
  const d = day();
  d.stages.forEach((s) => { s.st.board = []; });
  assert.equal(recapFacts(d), null);
});

test('the plain report names the winners, the gaps and a record, from the facts only', async () => {
  const f = recapFacts(day());
  const t = templateRecap(f);
  assert.match(t.title, /osiek and MaybeIWill share Monday/);
  assert.match(t.paragraphs[0], /SS1 Forêt de Saverne .*osiek won in 4:49\.637, \+57\.711 s ahead of MaybeIWill\. 1 DNF\. Top speed: osiek, 171\.4 km\/h\. Longest jump: MaybeIWill, 1\.2 s in the air\./);
  assert.match(t.paragraphs[2], /Hall of fame, week 41: 1\. osiek 43 pts/);
  const r = await writeReport({}, f);                         // no ANTHROPIC_API_KEY: the plain one
  assert.equal(r.model, 'template');
  assert.equal(r.text, t.paragraphs.join('\n\n'));
});
