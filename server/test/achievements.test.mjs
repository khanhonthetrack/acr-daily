// Achievements (src/achievements.js): streaks, the bulk check on a real SQLite (who unlocked what, kept once, one notice
// each), the cron picking the drivers who did something since their last check, and the icons.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { ACH_PAGE_JS, ACHIEVEMENTS, achievementIcon, achievementsTick, checkAchievements, longestStreak, unlockedBy } from '../src/achievements.js';
import { fakeD1, sid } from './faked1.mjs';

test('streaks: the longest run of days in a row', () => {
  assert.equal(longestStreak([]), 0);
  assert.equal(longestStreak(['2026-10-01', '2026-10-01', '2026-10-02', '2026-10-04', '2026-10-05', '2026-10-06']), 3);
  assert.equal(longestStreak(['2026-09-29', '2026-09-30', '2026-10-01']), 3);   // (across a month)
});

test('every achievement has a name, what it takes, a tier and an icon; ids are unique', () => {
  assert.equal(new Set(ACHIEVEMENTS.map((a) => a.id)).size, ACHIEVEMENTS.length);
  for (const a of ACHIEVEMENTS) {
    assert.ok(a.name && a.desc.endsWith('.') && ['bronze', 'silver', 'gold', 'platinum'].includes(a.tier), a.id);
    const on = achievementIcon(a, true), off = achievementIcon(a, false);
    assert.match(on, /^<svg class="ach-ic" viewBox="0 0 64 64".*<\/svg>$/);
    assert.notEqual(on, off);
    assert.ok(off.includes('#9A9AA2') && !on.includes('#9A9AA2'), 'locked: the lock');
  }
  // the page draws the same tiles with the same function
  const page = new Function(`${ACH_PAGE_JS}; return [ACH, achievementIcon];`)();
  assert.equal(page[0].length, ACHIEVEMENTS.length);
  assert.equal(page[1](page[0][2], true, 56), achievementIcon(ACHIEVEMENTS[2], true, 56));
});

const none = { dailies: 0, finishes: 0, wins: 0, podiums: 0, streak: 0, km: 0, rallies: new Set(), rain: 0, snow: 0, fog: 0, evening: 0,
  clean: 0, jump: 0, wagers: 0, balance: 0, looks: 0, duels: 0, finals: 0, cups: 0, official: 0, peak: 0, team: 0, leagues: 0 };

test('what the numbers unlock', () => {
  assert.deepEqual(unlockedBy(none), []);
  assert.deepEqual(unlockedBy({ ...none, finishes: 1, wins: 1, podiums: 1, dailies: 1 }), ['first-finish', 'podium', 'stage-winner']);
  assert.deepEqual(unlockedBy({ ...none, rallies: new Set(['Alsace', 'Greece', 'Monte Carlo']) }), []);
  assert.deepEqual(unlockedBy({ ...none, rallies: new Set(['Alsace', 'Greece', 'Monte Carlo', 'Wales']) }), ['grand-tour']);
  assert.deepEqual(unlockedBy({ ...none, jump: 30, km: 1200, peak: 1650 }), ['km-100', 'km-1000', 'big-air', 'flying-finn', 'rising-star']);
});

test('the check on SQLite: unlocked from the driver\'s numbers, kept once, one notice for them', async () => {
  const { env, db, count } = fakeD1();
  for (let i = 0; i < 3; i++) db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)").run(sid(i), 'Driver ' + i);
  db.prepare("INSERT INTO routes (track, points, length, updated) VALUES ('Wales Afon Bidno', '[]', 110000, 0)").run();
  // driver 0: won a daily in the rain (no penalty), a 7-day streak, a long jump, a 1V1 won, a team
  for (let d = 1; d <= 7; d++) {
    const date = `2026-10-0${d}`;
    db.prepare("INSERT INTO schedule (date, slot, track, car, weather, time) VALUES (?, 1, 'Wales Afon Bidno', 'x', ?, ?)").run(date, d === 3 ? 'HeavyRain' : 'Clear', d === 4 ? 'evening' : 'midday');
    const run = db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, created, clock_ms, total_ms, jumps)
      VALUES (?, 1, ?, 'Wales Afon Bidno', 'x', 'finished', 0, 300000, ?, ?)`).run(date, sid(0), d === 5 ? 305000 : 300000,
      d === 2 ? JSON.stringify([[1000, 1200, 500, 72]]) : null).lastInsertRowid;   // 72 km/h for 1.2 s: 24 m
    db.prepare(`INSERT INTO daily_results (date, slot, steam_id, place, field, status, total_ms, run_id, track)
      VALUES (?, 1, ?, ?, 2, 'finished', 300000, ?, 'Wales Afon Bidno')`).run(date, sid(0), d === 3 ? 1 : 2, run);
  }
  db.prepare("INSERT INTO h2h (challenger, opponent, stake, spec, status, created, answer_by, winner) VALUES (?, ?, 0, '{}', 'settled', 0, 0, ?)").run(sid(0), sid(1), sid(0));
  db.prepare("INSERT INTO teams (id, name, tag, tag_key, color, captain, code, created) VALUES ('team0001', 'T', 'TT', 'TT', '#FFFFFF', ?, 'CODE', 0)").run(sid(0));
  db.prepare("INSERT INTO team_members (steam_id, team_id, joined) VALUES (?, 'team0001', 0)").run(sid(0));
  count.queries = 0;
  const got = await checkAchievements(env, [sid(0), sid(1), sid(2)], 5000);
  assert.ok(count.queries <= 2, count.queries);
  assert.deepEqual([...got.get(sid(0)).keys()].sort(), ['big-air', 'clean-10', 'duellist', 'dusk', 'first-finish', 'km-100', 'podium', 'rain',
    'stage-winner', 'streak-7', 'team-player'].filter((x) => x !== 'clean-10').sort());   // (6 clean finishes: not 10)
  assert.equal(got.get(sid(1)).size, 0);
  const notes = db.prepare("SELECT to_id, body, ref FROM messages WHERE kind = 'ach'").all();
  assert.equal(notes.length, 1);
  assert.match(notes[0].body, /^10 achievements unlocked: /);
  assert.equal(notes[0].ref, 'ach:' + sid(0));
  // again: nothing new, no notice; a new one later: its own notice, with what it takes
  await checkAchievements(env, [sid(0)], 6000);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE kind = 'ach'").get().n, 1);
  db.prepare("INSERT INTO credits (steam_id, balance) VALUES (?, 1200)").run(sid(0));
  await checkAchievements(env, [sid(0)], 7000);
  assert.equal(db.prepare("SELECT body FROM messages WHERE kind = 'ach' ORDER BY id DESC").get().body, 'Achievement unlocked: Saver. Have 1,000 credits.');
  assert.equal(db.prepare("SELECT at FROM achievements WHERE steam_id = ? AND id = 'first-finish'").get(sid(0)).at, 5000, 'kept as first unlocked');
});

test('the cron: the drivers who did something since their last check, once', async () => {
  const { env, db } = fakeD1();
  const now = Date.UTC(2026, 9, 12, 12);
  for (let i = 0; i < 3; i++) db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)").run(sid(i), 'Driver ' + i);
  db.prepare("INSERT INTO runs (date, slot, steam_id, track, car, status, created) VALUES ('2026-10-12', 1, ?, 'x', 'x', 'finished', ?)").run(sid(0), now - 60000);
  db.prepare("INSERT INTO runs (date, slot, steam_id, track, car, status, created) VALUES ('2026-09-01', 1, ?, 'x', 'x', 'finished', 0)").run(sid(1));
  assert.deepEqual((await achievementsTick(env, now)).checked, 1);
  assert.equal(db.prepare('SELECT ach_at FROM players WHERE steam_id = ?').get(sid(0)).ach_at, now);
  assert.deepEqual((await achievementsTick(env, now + 600000)).checked, 0, 'nothing new since');
  db.prepare("INSERT INTO runs (date, slot, steam_id, track, car, status, created) VALUES ('2026-10-12', 2, ?, 'x', 'x', 'finished', ?)").run(sid(0), now + 700000);
  assert.deepEqual((await achievementsTick(env, now + 1200000)).checked, 1);
});
