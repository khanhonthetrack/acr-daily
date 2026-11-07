// The weekly time trial (src/timetrial.js): its weeks, the prizes, the week's picks, and a whole week on a real SQLite
// (schema.sql, node:sqlite) through the D1 stand-in: entering, runs (the best counts), the board, settling.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBoard, feeOf, firstWeek, isoWeek, isWeek, parseTtId, pickWeek, shiftWeek, TT, ttApi, ttOn, ttPayouts, ttTick,
  rejectTtRun, weekOf, weekStart } from '../src/timetrial.js';
import { LABELS } from '../src/credits.js';
import { CARS } from '../src/cars.js';
import { stageParts } from '../src/conditions.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000, D = 24 * H;

test('a week is its Monday (UTC), whatever moment of it', () => {
  assert.equal(weekOf(Date.UTC(2026, 10, 9, 0, 0)), '2026-11-09');            // Monday 00:00
  assert.equal(weekOf(Date.UTC(2026, 10, 15, 23, 59, 59)), '2026-11-09');     // Sunday night
  assert.equal(weekOf(Date.UTC(2026, 10, 16)), '2026-11-16');
  assert.equal(weekOf(Date.UTC(2026, 10, 7, 12)), '2026-11-02');              // a Saturday
  assert.equal(weekOf(Date.UTC(2027, 0, 1)), '2026-12-28');                   // across the year
  assert.equal(weekOf(Date.UTC(1970, 0, 5)), '1970-01-05');
  assert.ok(isWeek('2026-11-09') && !isWeek('2026-11-10') && !isWeek('2026-13-02') && !isWeek('nope'));
  assert.equal(shiftWeek('2026-11-09', -1), '2026-11-02');
  assert.equal(shiftWeek('2026-12-28', 1), '2027-01-04');
  assert.deepEqual(isoWeek('2026-11-09'), { year: 2026, no: 46 });
  assert.deepEqual(isoWeek('2026-12-28'), { year: 2026, no: 53 });            // 2026 has 53 ISO weeks
  assert.deepEqual(isoWeek('2027-01-04'), { year: 2027, no: 1 });
});

test('on from the week TIME_TRIAL_FROM is in; the fee only with credits on', () => {
  const env = { TIME_TRIAL_FROM: '2026-11-11', CREDITS_FROM: '2026-10-12' };
  assert.equal(firstWeek(env), '2026-11-09');
  assert.equal(ttOn(env, '2026-11-02'), false);
  assert.equal(ttOn(env, '2026-11-09'), true);
  assert.equal(ttOn({ TIME_TRIAL_FROM: '' }, '2026-11-09'), false);
  assert.equal(firstWeek({}), null);
  assert.equal(feeOf(env, '2026-11-09'), TT.fee);
  assert.equal(feeOf({ CREDITS_FROM: '' }, '2026-11-09'), 0);
  assert.deepEqual(parseTtId('tt:2026-11-09/2'), { week: '2026-11-09', slot: 2 });
  assert.equal(parseTtId('tt:2026-11-10/1'), null, 'not a Monday');
  assert.equal(parseTtId('2026-11-09/1'), null, 'a daily');
  assert.equal(parseTtId('tt:2026-11-09/3'), null);
});

const fees = (ids, fee = 20) => new Map(ids.map((s) => [s, fee]));
const field = (n) => Array.from({ length: n }, (_, i) => 'p' + (i + 1));
const paid = (n, fee = 20) => { const f = field(n); return f.map((s) => ttPayouts(f, fees(f, fee)).get(s)); };

test('prizes: the top half (rounded up) get their fee back and a share of the others\', rising in equal steps', () => {
  assert.deepEqual(paid(1), [20], 'on your own: the fee back');
  assert.deepEqual(paid(2), [40, 0]);
  assert.deepEqual(paid(3), [34, 26, 0], '2 places paid: 2 and 1 shares of 20 (the rounding to P1)');
  assert.deepEqual(paid(4), [47, 33, 0, 0], '2 places: 2 and 1 shares of 40');
  assert.deepEqual(paid(10), [55, 46, 40, 33, 26, 0, 0, 0, 0, 0], '5 places: 5, 4, 3, 2, 1 shares of the 100 the others paid');
  for (const n of [1, 2, 3, 4, 5, 7, 10, 25, 64, 99, 100]) {
    const p = paid(n), k = Math.ceil(n / 2);
    assert.equal(p.reduce((a, x) => a + x, 0), 20 * n, `${n}: no credits made or lost`);
    assert.ok(p.slice(0, k).every((x) => x >= 20), `${n}: every place paid gets at least its fee back`);
    assert.ok(p.slice(k).every((x) => x === 0), `${n}: the rest lose their fee`);
    assert.ok(p.every((x, i) => i === 0 || x <= p[i - 1]), `${n}: never more for a lower place`);
  }
});

test('prizes: an entrant without a time gets the fee back and is not in the field; a time without an entry wins nothing', () => {
  const f = fees(['a', 'b', 'c', 'nodrive']);
  const p = ttPayouts(['a', 'b', 'c', 'free'], f);
  assert.deepEqual(Object.fromEntries(p), { a: 34, b: 26, c: 0, nodrive: 20 }, 'a field of 3 (the driver without an entry left out)');
  assert.deepEqual(Object.fromEntries(ttPayouts([], fees(['a', 'b']))), { a: 20, b: 20 }, 'nobody set a time: refunds');
  assert.equal(ttPayouts([], new Map()).size, 0);
  // a fee that differs (TT.fee changed): what each paid comes back, the others' fees are the pot
  assert.deepEqual(Object.fromEntries(ttPayouts(['a', 'b'], new Map([['a', 10], ['b', 30]]))), { a: 40, b: 0 });
});

// a stand-in for index.js's hashStr (any stable hash will do for the picks)
const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h; };
const POOL_TRACKS = ['Alsace A', 'Alsace B', 'Wales A', 'Wales B', 'Greece A', 'Monte Carlo A'];
const pool = (tracks = POOL_TRACKS, fixed = {}) => ({ tracks, byTrack: new Map(tracks.map((t) => [t, fixed[t] || []])) });

test('the week\'s picks: two stages, off the week\'s dailies and on two rallies when it can, never a daily\'s stage + car', () => {
  const week = '2026-11-09';
  const p = pickWeek(pool(), week, [], [], hash);
  assert.equal(p.length, 2);
  assert.notEqual(p[0].track, p[1].track);
  assert.notEqual(stageParts(p[0].track).rally, stageParts(p[1].track).rally);
  assert.notEqual(p[0].car, p[1].car);
  assert.ok(p.every((x) => CARS.some((c) => c.name === x.car) && x.weather && x.time));
  assert.deepEqual(pickWeek(pool(), week, [], [], hash), p, 'the same every time');
  assert.notDeepEqual(pickWeek(pool(), shiftWeek(week, 1), [], [], hash).map((x) => x.track), p.map((x) => x.track), 'the next week moves on');
  // the week's dailies on all but two stages: those two
  const dailies = POOL_TRACKS.filter((t) => t !== 'Wales B' && t !== 'Greece A').map((t) => ({ track: t, car: CARS[0].name }));
  assert.deepEqual(pickWeek(pool(), week, dailies, [], hash).map((x) => x.track).sort(), ['Greece A', 'Wales B']);
  // every stage a daily's: still two, each without the car any daily drives on it
  const all = POOL_TRACKS.flatMap((t) => CARS.slice(0, 17).map((c) => ({ track: t, car: c.name })));
  const p2 = pickWeek(pool(), week, all, [], hash);
  assert.equal(p2.length, 2);
  assert.equal(CARS.length, 18);
  assert.deepEqual(p2.map((x) => x.car), [CARS[17].name, CARS[17].name], 'the one car no daily drives there, twice rather than a daily\'s');
  // a stage with fixed cars drives one of them; a stored pick stays
  const fixedPool = pool(['Alsace A'], { 'Alsace A': ['Skoda Fabia RS Rally2'] });
  assert.equal(pickWeek(fixedPool, week, [], [], hash)[0].car, 'Skoda Fabia RS Rally2');
  assert.equal(pickWeek(fixedPool, week, [], [], hash).length, 1, 'one stage in the pool: one time trial stage');
  const kept = { slot: 1, track: 'Wales A', car: CARS[3].name, weather: 'Clear', time: 'midday' };
  const p3 = pickWeek(pool(), week, [], [kept], hash);
  assert.deepEqual(p3[0], kept);
  assert.notEqual(p3[1].track, 'Wales A');
});

// ------------------------------------------------------------------ a whole week, on SQLite

const WEEK = '2026-11-09', T0 = weekStart(WEEK);
// a straight 3 km stage, a point every 10 m
const ROUTE = Array.from({ length: 301 }, (_, i) => [i * 10, 0]);
const trace = (ms) => Array.from({ length: 61 }, (_, i) => [Math.round((ms * i) / 60), i * 50, 0, 100, 0]);

function world({ credits = true } = {}) {
  const f = fakeD1({ TIME_TRIAL_FROM: WEEK, ...(credits ? { CREDITS_FROM: '2026-10-12' } : {}) });
  const { db } = f;
  for (const t of POOL_TRACKS) {
    db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, 3000, 0, NULL)').run(t, JSON.stringify(ROUTE));
    db.prepare("INSERT INTO pool (track, car, enabled) VALUES (?, '*', 1)").run(t);
  }
  for (let i = 1; i <= 8; i++) {
    db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
    db.prepare('INSERT INTO credits (steam_id, balance, streak, last_day) VALUES (?, 1000, 0, NULL)').run(sid(i));
  }
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const deps = { json, err, hash, splits: [0.25, 0.5, 0.75], timing: { liveSendS: 5 },
    pool: async () => {
      const rows = db.prepare('SELECT track, car FROM pool WHERE enabled = 1').all();
      const tracks = [...new Set(rows.map((r) => r.track))].sort((a, b) => hash(a) - hash(b));
      return { tracks, byTrack: new Map(tracks.map((t) => [t, []])) };
    },
    tooOld: () => null, startedMs: (v, now) => (Number(v) > 0 ? Math.round(Number(v) * 1000) : now) };
  const me = (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i));
  const call = (method, path, { who = null, body, now, query = '' } = {}) => {
    const url = new URL('https://acrdaily.test' + path + query);
    const req = new Request(url, { method, ...(body !== undefined ? { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } } : {}) });
    return ttApi(req, f.env, path, url, who ? me(who) : null, true, now, deps);
  };
  return { ...f, deps, call };
}

const run = (stage, totalMs, { startedAt, car, status = 'finished', penaltyMs = 0 } = {}) => ({
  challengeId: stage.id, track: stage.track, car: car || stage.car, status, clockMs: totalMs - penaltyMs, resets: 0,
  official: { timeMs: totalMs - penaltyMs, penaltyMs }, startedAt: startedAt / 1000, trace: trace(totalMs - penaltyMs), appVersion: '0.0.23' });

test('a week of time trial: enter, drive as often as you like (the best counts), the board, and the prizes paid once', async () => {
  const w = world();
  const { db, call, count } = w;
  let now = T0 + 10 * H;
  const tt = await call('GET', '/api/tt', { who: 1, now });
  assert.equal(tt.status, 200);
  const t = tt.data;
  assert.equal(t.on, true);
  assert.equal(t.week, WEEK);
  assert.equal(t.endsAt - t.startsAt, 7 * D);
  assert.equal(t.fee, TT.fee);
  assert.equal(t.stages.length, 2);
  const [s1, s2] = t.stages;
  assert.deepEqual([s1.id, s2.id], [`tt:${WEEK}/1`, `tt:${WEEK}/2`]);
  assert.ok(s1.route && s1.route.length === ROUTE.length, 'the app gets the route to judge with');
  assert.equal(s1.mode, 'weekend');
  assert.deepEqual(s1.me, { entered: false, bestMs: null, runs: 0 });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_schedule WHERE week = ?').get(WEEK).n, 2, 'the week\'s picks are kept');
  assert.equal((await call('GET', '/api/tt', { now, query: '?lite=1' })).data.stages[0].route, undefined);
  assert.equal((await call('GET', '/api/tt', { now, query: '?week=' + shiftWeek(WEEK, 1) })).status, 403, 'no peeking');
  assert.equal((await call('GET', '/api/tt', { now, query: '?week=' + shiftWeek(WEEK, -1) })).data.on, false, 'before the first week');

  // no entry: no run on the board
  let r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s1, 200000, { startedAt: now - 5 * 60000 }) });
  assert.equal(r.status, 402);
  assert.match(r.data.error, /^invalid run: TT1 takes runs from drivers who entered/);
  // the fee: not without the credits, once, from the ledger
  db.prepare('UPDATE credits SET balance = 10 WHERE steam_id = ?').run(sid(7));
  r = await call('POST', '/api/tt/enter', { who: 7, now, body: { slot: 1 } });
  assert.equal(r.status, 402);
  assert.match(r.data.error, /the entry fee is 200 credits: you have 10/);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_entries').get().n, 0);
  r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 1 } });
  assert.deepEqual([r.status, r.data.entered, r.data.balance, r.data.entrants, r.data.pot], [200, true, 800, 1, 200]);
  r = await call('POST', '/api/tt/enter', { who: 1, now: now + 1000, body: { slot: 1 } });
  assert.deepEqual([r.data.already, r.data.balance], [true, 800], 'entering twice takes the fee once');
  assert.deepEqual(db.prepare("SELECT delta, kind, ref FROM credit_ledger WHERE steam_id = ?").all(sid(1)).map((x) => ({ ...x })),
    [{ delta: -200, kind: 'tt-fee', ref: `tt:${WEEK}/1` }]);
  assert.ok(LABELS['tt-fee'] && LABELS['tt-prize'] && LABELS['tt-refund']);

  // a run that started before the entry doesn't count; the ones after it do, the best on the board
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s1, 200000, { startedAt: now - 10 * 60000 }) });
  assert.equal(r.status, 409);
  assert.match(r.data.error, /started before your entry/);
  now += H;
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s1, 200000, { startedAt: now - 5 * 60000 }) });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.deepEqual([r.data.best, r.data.rank, r.data.bestMs, r.data.runs], [true, 1, 200000, 1]);
  const first = r.data.id;
  r = await call('POST', '/api/tt/runs', { who: 1, now: now + 60000, body: run(s1, 210000, { startedAt: now - 60000 }) });
  assert.deepEqual([r.data.best, r.data.bestMs, r.data.runs], [false, 200000, 2], 'a slower run changes nothing on the board');
  r = await call('POST', '/api/tt/runs', { who: 1, now: now + 120000, body: run(s1, 196000, { startedAt: now, penaltyMs: 1000 }) });
  assert.deepEqual([r.data.best, r.data.improvedMs, r.data.bestMs], [true, 4000, 196000]);
  const best1 = r.data.id;
  assert.deepEqual(db.prepare('SELECT id FROM tt_runs WHERE trace IS NOT NULL').all().map((x) => x.id), [best1],
    'only the best run keeps its trace');
  const tr = await call('GET', `/api/tt/runs/${best1}/trace`, { now });
  assert.equal(tr.status, 200);
  assert.equal(tr.data.trace.length, 61);
  assert.equal((await call('GET', `/api/tt/runs/${first}/trace`, { now })).status, 404);

  // refused: another car, a DNF, no official time, the other stage without its own entry
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s1, 199000, { startedAt: now, car: s2.car }) });
  assert.equal(r.status, 422);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: { ...run(s1, 199000, { startedAt: now }), status: 'dnf' } });
  assert.equal(r.status, 422);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: { ...run(s1, 199000, { startedAt: now }), official: null } });
  assert.equal(r.status, 422);
  assert.match(r.data.error, /no official result/);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s2, 150000, { startedAt: now }) });
  assert.equal(r.status, 402, 'each stage is entered on its own');

  // five more drivers enter TT1: four set times, one never drives
  const times = { 2: 190000, 3: 230000, 4: 205000, 5: 220000 };
  for (const i of [2, 3, 4, 5, 6]) assert.equal((await call('POST', '/api/tt/enter', { who: i, now, body: { slot: 1 } })).status, 200);
  now += H;
  for (const [i, ms] of Object.entries(times)) {
    r = await call('POST', '/api/tt/runs', { who: +i, now, body: run(s1, ms, { startedAt: now - 5 * 60000 }) });
    assert.equal(r.status, 200);
  }
  // a tie: the time set first is ahead
  r = await call('POST', '/api/tt/runs', { who: 5, now: now + 5000, body: run(s1, 205000, { startedAt: now }) });
  assert.equal(r.data.rank, 4, 'a tie with 4: set later, so behind');
  const b = (await call('GET', '/api/tt/board', { now, query: `?week=${WEEK}&slot=1` })).data;
  assert.deepEqual(b.entries.map((e) => [e.steamId, e.rank, e.totalMs]),
    [[sid(2), 1, 190000], [sid(1), 2, 196000], [sid(4), 3, 205000], [sid(5), 4, 205000], [sid(3), 5, 230000]]);
  assert.deepEqual(b.entries.map((e) => e.runs), [1, 3, 1, 2, 1]);
  assert.equal(b.entries[1].clockMs, 195000);
  assert.equal(b.entries[1].gapMs, 6000);
  assert.ok(Array.isArray(b.entries[0].splits) && b.entries[0].splits.length === 3);
  // 5 with a time: 3 places paid; the pot of 6 fees: the 2 outside the top 3 pay the prizes, the 6th driver's fee goes back
  assert.deepEqual(b.entries.map((e) => e.prize), [401, 333, 266, 0, 0]);
  assert.deepEqual(b.stats, { drivers: 5, runs: 8, entrants: 6, pot: 1200, paidPlaces: 3 });
  assert.equal(b.settled, null);

  // a banned driver leaves the board (and the field)
  db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(sid(3));
  assert.deepEqual((await buildBoard(w.env, WEEK, 1)).entries.map((e) => e.steamId), [sid(2), sid(1), sid(4), sid(5)]);
  db.prepare('UPDATE players SET banned = 0 WHERE steam_id = ?').run(sid(3));

  // my side of it, in /api/tt
  const mine = (await call('GET', '/api/tt', { who: 1, now, query: '?lite=1' })).data.stages[0];
  assert.deepEqual([mine.me, mine.entrants, mine.pot], [{ entered: true, bestMs: 196000, runs: 3 }, 6, 1200]);

  // an admin takes a run off: the driver's next best counts
  const tie = r.data.id;
  assert.equal(await rejectTtRun(w.env, tie, 'checked'), true);
  assert.equal((await buildBoard(w.env, WEEK, 1)).entries.find((e) => e.steamId === sid(5)).totalMs, 220000);
  assert.equal(await rejectTtRun(w.env, 999999), false);
  db.prepare("UPDATE tt_runs SET status = 'finished' WHERE id = ?").run(tie);

  // the week closes: a run that started after it is refused, one finished before it may come a little late
  const end = T0 + 7 * D;
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 10 * 60000, body: run(s1, 180000, { startedAt: end + 60000 }) });
  assert.match(r.data.error, /started after the time trial closed/);
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 10 * 60000, body: run(s1, 189000, { startedAt: end - 5 * 60000 }) });
  assert.equal(r.status, 200, 'a run finished just before the close');
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 40 * 60000, body: run(s1, 188000, { startedAt: end - 5 * 60000 }) });
  assert.equal(r.status, 409);
  assert.match(r.data.error, /too late/);
  assert.equal((await call('POST', '/api/tt/enter', { who: 7, now: end + 60000, body: { slot: 1, week: WEEK } })).status, 409);

  // nothing settles until an hour after the close
  assert.deepEqual(await ttTick(w.env, end + 30 * 60000, w.deps), { settled: [] });
  count.queries = 0;
  const done = await ttTick(w.env, end + 2 * H, w.deps);
  assert.ok(count.queries <= 20, `settling the week took ${count.queries} queries`);
  assert.deepEqual(done.settled.map((x) => [x.week, x.slot, x.drivers]), [[WEEK, 1, 5], [WEEK, 2, 0]]);
  assert.deepEqual(done.settled[0].paid, { [sid(2)]: 401, [sid(1)]: 333, [sid(4)]: 266, [sid(6)]: 200 });
  const bal = (i) => db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(sid(i)).balance;
  assert.deepEqual([1, 2, 3, 4, 5, 6, 7].map(bal), [1133, 1201, 800, 1066, 800, 1000, 10]);
  assert.deepEqual(db.prepare("SELECT kind, COUNT(*) AS n, SUM(delta) AS s FROM credit_ledger GROUP BY kind ORDER BY kind").all().map((x) => ({ ...x })),
    [{ kind: 'tt-fee', n: 6, s: -1200 }, { kind: 'tt-prize', n: 3, s: 1000 }, { kind: 'tt-refund', n: 1, s: 200 }]);
  assert.deepEqual(db.prepare('SELECT steam_id, paid FROM tt_entries WHERE settled IS NOT NULL ORDER BY steam_id').all().map((x) => [x.steam_id, x.paid]),
    [[sid(1), 333], [sid(2), 401], [sid(3), 0], [sid(4), 266], [sid(5), 0], [sid(6), 200]]);
  const notes = db.prepare("SELECT to_id, body, ref FROM messages WHERE kind = 'tt' ORDER BY to_id").all();
  assert.equal(notes.length, 6);
  assert.ok(notes.every((n) => n.ref === `tt:${WEEK}`));
  assert.match(notes.find((n) => n.to_id === sid(1)).body, /^Time trial TT1 \(.+\), week 46 is over: you placed P2 of 5 \(3:16\.000, 3 runs\)\. Prize: 333 credits\.$/);
  assert.match(notes.find((n) => n.to_id === sid(6)).body, /You set no time: your entry fee of 200 credits is back\.$/);
  assert.match(notes.find((n) => n.to_id === sid(3)).body, /P5 of 5 .* Outside the top half: no prize this time\.$/);
  // the traces: the fastest few keep theirs
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_runs WHERE trace IS NOT NULL AND week = ?').get(WEEK).n, TT.keepTraces);
  // settled once; the board shows what was paid
  assert.deepEqual(await ttTick(w.env, end + 3 * H, w.deps), { settled: [] });
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM credit_ledger WHERE kind = 'tt-prize'").get().n, 3);
  const after = (await call('GET', '/api/tt/board', { now: end + 3 * H, query: `?week=${WEEK}&slot=1` })).data;
  assert.deepEqual(after.entries.map((e) => e.prize), [401, 333, 266, 0, 0]);
  assert.equal(after.settled, end + 2 * H);
  // the new week has its own stages, fixed by the cron
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_schedule WHERE week = ?').get(shiftWeek(WEEK, 1)).n, 2);
});

test('credits off: free to drive, no entry, no prizes; the week still settles (and trims its traces)', async () => {
  const w = world({ credits: false });
  const { db, call } = w;
  const now = T0 + 2 * D;
  const t = (await call('GET', '/api/tt', { who: 1, now })).data;
  assert.deepEqual([t.fee, t.credits, t.stages[0].fee, t.stages[0].me.entered], [0, false, 0, true]);
  const r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 1 } });
  assert.deepEqual([r.data.entered, r.data.free], [true, true]);
  for (let i = 1; i <= 5; i++) {
    const s = await call('POST', '/api/tt/runs', { who: i, now, body: run(t.stages[0], 200000 + i * 1000, { startedAt: now - 60000 }) });
    assert.equal(s.status, 200);
  }
  const b = (await call('GET', '/api/tt/board', { now, query: `?week=${WEEK}&slot=1` })).data;
  assert.deepEqual([b.entries.length, b.entries[0].prize, b.credits], [5, null, false]);
  const done = await ttTick(w.env, T0 + 7 * D + 2 * H, w.deps);
  assert.equal(done.settled.length, 2);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM credit_ledger').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_runs WHERE trace IS NOT NULL').get().n, TT.keepTraces);
  assert.match(db.prepare("SELECT body FROM messages WHERE to_id = ?").get(sid(1)).body, /you placed P1 of 5 \(3:21\.000, 1 run\)\.$/);
});

test('off without TIME_TRIAL_FROM: the app is told, nothing else answers', async () => {
  const { env } = fakeD1({});
  const json = (data, status = 200) => ({ status, data }), err = (msg, status = 400) => ({ status, data: { error: msg } });
  const url = new URL('https://x/api/tt');
  assert.deepEqual((await ttApi(new Request(url), env, '/api/tt', url, null, true, Date.now(), { json, err })).data, { on: false });
  const u2 = new URL('https://x/api/tt/enter');
  assert.equal((await ttApi(new Request(u2, { method: 'POST', body: '{}' }), env, '/api/tt/enter', u2, null, true, Date.now(), { json, err })).status, 404);
  assert.equal(await ttApi(new Request(url), env, '/api/ttx', url, null, true, Date.now(), { json, err }), null);
  assert.deepEqual(await ttTick(env, Date.now(), {}), { settled: [] });
});
