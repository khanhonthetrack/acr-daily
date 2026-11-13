// Team results (src/teamscore.js): a match's scoring and a league season's team championship.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkScoring, checkTeamChamp, decideTeams, describeScoring, teamResult, teamRound, teamSeasonStandings,
  MATCH_PRESETS, matchDrivers } from '../src/teamscore.js';
import { eventStandings, seasonStandings } from '../src/leagues.js';

const S = 1000;
const fin = (steamId, s) => ({ steamId, name: steamId, status: 'finished', totalMs: s * S, done: 2 });
const dnf = (steamId) => ({ steamId, name: steamId, status: 'dnf', totalMs: 0, done: 1 });
const run = (steamId) => ({ steamId, name: steamId, status: 'running', totalMs: 0, done: 1 });
const RED = { id: 'red', drivers: ['r1', 'r2', 'r3', 'r4'] };
const BLUE = { id: 'blue', drivers: ['b1', 'b2', 'b3', 'b4'] };
const sc = (b) => { const c = checkScoring(b); assert.ok(c.value, c.error); return c.value; };

test('the presets: top X, average, named, cross-country', () => {
  assert.deepEqual(sc({ preset: 'top' }), { lineup: 'open', count: 'best', best: 3, by: 'time', min: 1, short: 'fewer' });
  assert.deepEqual(sc({ preset: 'top', best: 2 }).best, 2);
  assert.deepEqual(sc({ preset: 'average' }), { lineup: 'open', count: 'all', by: 'avg', min: 2, short: 'slowest', plusS: 60, plusPct: 0 });
  assert.deepEqual(sc({ preset: 'named', size: 4 }), { lineup: 'named', count: 'all', by: 'time', size: 4, min: 1, short: 'slowest', plusS: 60, plusPct: 0 });
  assert.equal(sc({ preset: 'places' }).by, 'places');
  assert.equal(Object.keys(MATCH_PRESETS).length, 4);
  assert.equal(matchDrivers(sc({ preset: 'named', size: 4 })), 4);
  assert.match(describeScoring(sc({ preset: 'top' })), /the best 3 count; times added up/);
});

test('scoring: what is refused', () => {
  assert.match(checkScoring({ lineup: 'mixed' }).error, /lineup/);
  assert.match(checkScoring({ by: 'speed' }).error, /add up by/);
  assert.match(checkScoring({ lineup: 'named', size: 9 }).error, /names 1 to 8/);
  assert.match(checkScoring({ lineup: 'named', size: 3, count: 'best', best: 4 }).error, /the best X/);
  assert.match(checkScoring({ short: 'slowest', plusPct: 300 }).error, /missing finisher/);
  assert.match(checkScoring({ by: 'points', points: 'a, b' }).error, /points/);
  assert.deepEqual(checkScoring({ by: 'points', points: '10, 8, 6' }).value.points, [10, 8, 6]);
  assert.equal(checkScoring({ lineup: 'named', size: 2, min: 5 }).value.min, 2, 'min at most the lineup');
});

test('top X: the best 3 times added up; a fourth driver does not count', () => {
  const s = sc({ preset: 'top' });
  const rows = [fin('r1', 300), fin('r2', 310), fin('r3', 320), fin('r4', 400), fin('b1', 290), fin('b2', 305), fin('b3', 330), dnf('b4')];
  const r = teamResult(rows, [RED, BLUE], s);
  assert.deepEqual(r.map((t) => [t.id, t.rank, t.score]), [['blue', 1, 925 * S], ['red', 2, 930 * S]]);
  assert.deepEqual(r[1].drivers.filter((d) => d.counted).map((d) => d.steamId), ['r1', 'r2', 'r3']);
  assert.deepEqual(decideTeams(r, 'red', 'blue', s), { winner: 'blue', note: 'by 5.000 s' });
});

test('top X, a team short of finishers: fewer finishers lose, however fast', () => {
  const s = sc({ preset: 'top' });
  const r = teamResult([fin('r1', 200), fin('r2', 200), dnf('r3'), fin('b1', 400), fin('b2', 400), fin('b3', 400)], [RED, BLUE], s);
  assert.deepEqual(r.map((t) => [t.id, t.missing]), [['blue', 0], ['red', 1]]);
  assert.deepEqual(decideTeams(r, 'red', 'blue', s), { winner: 'blue', note: 'more finishers' });
});

test('slowest: a missing finisher counts as the slowest time + its penalty', () => {
  const s = sc({ preset: 'top', short: 'slowest', plusS: 10, plusPct: 10 });
  const r = teamResult([fin('r1', 200), fin('r2', 200), dnf('r3'), fin('b1', 300), fin('b2', 300), fin('b3', 400)], [RED, BLUE], s);
  // red: 200 + 200 + (400 * 1.1 + 10) = 850; blue 1000
  assert.deepEqual(r.map((t) => [t.id, t.score]), [['red', 850 * S], ['blue', 1000 * S]]);
});

test('average: everyone who drove, at least min; missing ones the slowest + 60 s', () => {
  const s = sc({ preset: 'average' });
  // red: only one drove (min 2): 300 and a missing one at 400 + 60 -> 380; blue: three drove: (310 + 320 + 400) / 3
  const r = teamResult([fin('r1', 300), fin('b1', 310), fin('b2', 320), fin('b3', 400)], [RED, BLUE], s);
  assert.deepEqual(r.map((t) => [t.id, t.score, t.need]), [['blue', 343333, 3], ['red', 380000, 2]]);
});

test('named: only the named drivers count; one who never drove is missing', () => {
  const s = sc({ preset: 'named', size: 2 });
  const red = { id: 'red', drivers: ['r1', 'r2'] }, blue = { id: 'blue', drivers: ['b1', 'b2'] };
  // r3 drove but is not named: not counted (and not a position); b2 named but never drove
  const r = teamResult([fin('r1', 300), fin('r2', 300), fin('r3', 100), fin('b1', 250)], [red, blue], s);
  assert.deepEqual(r.map((t) => [t.id, t.score, t.missing]), [['red', 600 * S], ['blue', (250 + 300 + 60) * S]].map(([a, b]) => [a, b, a === 'red' ? 0 : 1]));
});

test('cross-country: places added up, lowest wins; a DNF one behind the last finisher', () => {
  const s = sc({ preset: 'places', best: 2 });
  const r = teamResult([fin('r1', 100), fin('b1', 110), fin('b2', 120), fin('r2', 130), dnf('r3')], [RED, BLUE], s);
  assert.deepEqual(r.map((t) => [t.id, t.score]), [['red', 5], ['blue', 5]].map((x) => x), 'a tie on places');
  assert.equal(r[0].id, 'red', 'the tie-break: the best driver');
  assert.deepEqual(decideTeams(r, 'red', 'blue', s), { winner: 'red', note: 'on the tie-break: the best driver' });
});

test('points: a table by position, added up, highest wins', () => {
  const s = sc({ by: 'points', points: [10, 6, 4, 2], count: 'best', best: 2 });
  const r = teamResult([fin('r1', 100), fin('b1', 110), fin('b2', 120), fin('r2', 130)], [RED, BLUE], s);
  assert.deepEqual(r.map((t) => [t.id, t.score]), [['red', 12], ['blue', 10]]);
  assert.deepEqual(decideTeams(r, 'red', 'blue', s), { winner: 'red', note: 'by 2 points' });
});

test('nobody finishing, a dead heat, one team out, still driving', () => {
  const s = sc({ preset: 'top', best: 1 });
  assert.deepEqual(decideTeams(teamResult([dnf('r1'), dnf('b1')], [RED, BLUE], s), 'red', 'blue', s), { winner: null, note: 'nobody finished' });
  assert.deepEqual(decideTeams(teamResult([fin('r1', 100), fin('b1', 100)], [RED, BLUE], s), 'red', 'blue', s), { winner: null, note: 'a dead heat' });
  assert.deepEqual(decideTeams(teamResult([dnf('r1'), fin('b1', 100)], [RED, BLUE], s), 'red', 'blue', s),
    { winner: 'blue', note: 'the only team with a finisher' });
  const r = teamResult([run('r1'), fin('b1', 100)], [RED, BLUE], s);
  assert.equal(r.find((t) => t.id === 'red').pending, 1);
});

// ------------------------------------------------------------------ league team championships

test('the team championship: what a form makes, what is refused', () => {
  assert.deepEqual(checkTeamChamp({ off: true }), { value: null });
  assert.deepEqual(checkTeamChamp({ method: 'drivers', best: 2 }).value, { method: 'drivers', best: 2, nominate: 0, power: true, drop: 0 });
  assert.deepEqual(checkTeamChamp({ method: 'reranked', best: 2, nominate: 3, table: '18 12 8' }).value,
    { method: 'reranked', best: 2, nominate: 3, fallback: 'all', table: [18, 12, 8], drop: 0 });
  assert.equal(checkTeamChamp({ method: 'result', by: 'avg', best: 0 }).value.by, 'avg');
  assert.deepEqual(checkTeamChamp({ method: 'season', best: 3 }).value, { method: 'season', best: 3, nominate: 0 });
  assert.match(checkTeamChamp({ method: 'x' }).error, /team championship/);
  assert.match(checkTeamChamp({ method: 'drivers', best: 4, nominate: 3 }).error, /more drivers count/);
  assert.match(checkTeamChamp({ method: 'result', by: 'points' }).error, /team result/);
});

// Two events, two teams of three: Ann, Ben, Cat (red); Dan, Eve, Fay (blue). Fay drives event 2 for red (a transfer).
const T = [{ id: 1, name: 'Red', tag: 'RED', color: '#E30613' }, { id: 2, name: 'Blue', tag: 'BLU', color: '#5BA8FF' }];
const ev = (id, times) => {
  const entries = Object.keys(times).map((sid) => ({ steam_id: sid, name: sid, car: 'x', status: times[sid] ? 'finished' : 'dnf' }));
  const st = eventStandings({ stages: [{}], opens: 0, closes: 1 }, entries,
    Object.entries(times).filter(([, s]) => s).map(([sid, s]) => ({ steam_id: sid, stage_no: 0, time_ms: s * S, penalty_ms: 0 })), 2);
  return { id, status: 'closed', rows: st.rows, stages: st.stages };
};
const E1 = ev(1, { ann: 100, dan: 101, ben: 102, eve: 103, cat: 104, fay: 105 });
const E2 = ev(2, { dan: 100, eve: 101, fay: 102, ann: 103, ben: null, cat: 104 });
const SEASON = { points: { table: [10, 8, 6, 5, 4, 3], finisher: 1 }, power: [3, 2, 1], drop: 0 };
const teamOf1 = new Map([['ann', 1], ['ben', 1], ['cat', 1], ['dan', 2], ['eve', 2], ['fay', 2]]);
const teamOf2 = new Map([...teamOf1, ['fay', 1]]);
const evs = () => [{ ...E1, teamOf: teamOf1, named: null }, { ...E2, teamOf: teamOf2, named: null }];
const drivers = seasonStandings(SEASON, [E1, E2]);
const champ = (b) => { const c = checkTeamChamp(b); assert.ok(c.value, c.error); return c.value; };
const table = (rows) => rows.map((t) => [t.name, t.points, t.rank]);

test("drivers' points: the best 2 of each team's championship points (Power Stage in), points stay with the team driven for", () => {
  // E1 points (+power): ann 10+3, dan 8+2, ben 6+1, eve 5, cat 4, fay 3 -> red 13+7, blue 10+5
  // E2: dan 10+3, eve 8+2, fay 6+1 (for red), ann 5, cat 4, ben DNF -> red 7+5, blue 13+10
  const r = teamSeasonStandings(champ({ method: 'drivers', best: 2 }), T, evs(), drivers);
  assert.deepEqual(table(r), [['Blue', 38, 1], ['Red', 32, 2]]);
  assert.deepEqual(r[1].cells[2].counted, ['fay', 'ann']);
  const noPower = teamSeasonStandings(champ({ method: 'drivers', best: 2, power: false }), T, evs(), drivers);
  assert.deepEqual(table(noPower), [['Blue', 31, 1], ['Red', 27, 2]]);
});

test('re-ranked: the counted drivers ranked among themselves, the team table by position', () => {
  // E1, every finisher: ann 1, dan 2, ben 3, eve 4, cat 5, fay 6; best 2: red 18+8 (1, 3), blue 12+6 (2, 4)
  // E2: dan 1, eve 2, fay 3 (red), ann 4, cat 5: red 8+6 (3, 4), blue 18+12
  const r = teamSeasonStandings(champ({ method: 'reranked', best: 2, table: [18, 12, 8, 6, 4, 2] }), T, evs(), drivers);
  assert.deepEqual(table(r), [['Blue', 48, 1], ['Red', 40, 2]]);
  assert.equal(r[0].wins, 1);
});

test('team result: teams ranked on each event by their best 2 times, the team table by place; dropped rounds', () => {
  const c = champ({ method: 'result', best: 2, by: 'time', table: [10, 5] });
  // E1: red 100+102=202, blue 101+103=204 -> red 10; E2: blue 100+101, red 102+103 -> blue 10
  assert.deepEqual(table(teamSeasonStandings(c, T, evs(), drivers)), [['Blue', 15, 1], ['Red', 15, 1]]);
  const d = teamSeasonStandings({ ...c, drop: 1 }, T, evs(), drivers);
  assert.deepEqual(table(d), [['Blue', 10, 1], ['Red', 10, 1]]);
  assert.ok(d[0].cells[1].dropped || d[0].cells[2].dropped);
});

test('nominations: only the nominated count; a team that named nobody: all of it, or none', () => {
  const c = champ({ method: 'drivers', best: 1, nominate: 2, fallback: 'none' });
  const e = evs();
  e[0].named = new Map([[1, new Set(['cat', 'ben'])]]);      // red nominates its slower two on E1; blue nobody
  const r = teamSeasonStandings(c, T, [e[0]], drivers);
  assert.deepEqual(table(r), [['Red', 7, 1], ['Blue', 0, 2]]);
  const all = teamSeasonStandings({ ...c, fallback: 'all' }, T, [e[0]], drivers);
  assert.deepEqual(table(all), [['Blue', 10, 1], ['Red', 7, 2]]);
});

test("season: each team's best drivers' season points; team penalties", () => {
  const c = champ({ method: 'season', best: 2 });
  // red: ann 13+5=18, ben 7, cat 4+4=8, fay 7 (for red) -> 18 + 8; blue: dan 10+13=23, eve 5+10=15, fay 3 -> 38
  const r = teamSeasonStandings(c, T, evs(), drivers, [{ teamId: 2, points: 5 }]);
  assert.deepEqual(table(r), [['Blue', 33, 1], ['Red', 26, 2]]);
  assert.deepEqual(r[0].best.map((x) => x.steamId), ['dan', 'eve']);
  assert.equal(r[0].penalty, 5);
});

test('an event not run yet counts for nothing', () => {
  const e = evs();
  e[1].status = 'upcoming';
  const r = teamSeasonStandings(champ({ method: 'drivers', best: 2 }), T, e, seasonStandings(SEASON, [E1, { ...E2, status: 'upcoming' }]));
  assert.deepEqual(table(r), [['Red', 20, 1], ['Blue', 15, 2]]);
  assert.equal(teamRound(champ({ method: 'drivers', best: 2 }), E1, [{ id: 1, drivers: [] }], new Map()).get(1).out, true);
});
