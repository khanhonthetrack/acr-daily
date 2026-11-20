// The weekly time trial (src/timetrial.js): its weeks, the prizes, the week's picks, and a whole week on a real SQLite
// (schema.sql, node:sqlite) through the D1 stand-in: entering, runs (the best counts), the board, settling.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBoard, feeOf, firstWeek, isoWeek, isPrivateWeek, isWeek, parseTtId, pickWeek, PRIVATE, setTtPrivate, shiftWeek, TT,
  ttApi, ttOn, ttPayouts, ttTick, rejectTtRun, weekOf, weekStart } from '../src/timetrial.js';
import worker, { appVersionOf, olderThan } from '../src/index.js';
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

test('on from the week TIME_TRIAL_FROM is in; the fee only with credits on, and never on TT1', () => {
  const env = { TIME_TRIAL_FROM: '2026-11-11', CREDITS_FROM: '2026-10-12' };
  assert.equal(firstWeek(env), '2026-11-09');
  assert.equal(ttOn(env, '2026-11-02'), false);
  assert.equal(ttOn(env, '2026-11-09'), true);
  assert.equal(ttOn({ TIME_TRIAL_FROM: '' }, '2026-11-09'), false);
  assert.equal(firstWeek({}), null);
  assert.equal(TT.freeSlot, 1);
  assert.equal(feeOf(env, '2026-11-09', 2), TT.fee);
  assert.equal(feeOf(env, '2026-11-09', 1), 0, 'TT1 is free');
  assert.equal(feeOf({ CREDITS_FROM: '' }, '2026-11-09', 2), 0);
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

test('a stage\'s rally and name: the game\'s, a community one, one with its maker in brackets (Lousã)', () => {
  assert.deepEqual(stageParts('Wales Afon Bidno'), { rally: 'Wales', stageName: 'Afon Bidno', surface: 'Gravel' });
  assert.deepEqual(stageParts('London Marylebone - Whitehall'), { rally: 'London', stageName: 'Marylebone - Whitehall', surface: null });
  assert.deepEqual(stageParts('Portugal (Hattori Rally) Lousã'), { rally: 'Portugal', stageName: 'Lousã', surface: null });
  assert.equal(stageParts('[MOD] Germany Full').stageName, 'Germany Full');                // (as before)
});

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
  const last = CARS.length - 1;
  const all = POOL_TRACKS.flatMap((t) => CARS.slice(0, last).map((c) => ({ track: t, car: c.name })));
  const p2 = pickWeek(pool(), week, all, [], hash);
  assert.equal(p2.length, 2);
  assert.deepEqual(p2.map((x) => x.car), [CARS[last].name, CARS[last].name], 'the one car no daily drives there, twice rather than a daily\'s');
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
    tooOld: () => null, appVersion: appVersionOf, olderThan,
    startedMs: (v, now) => (Number(v) > 0 ? Math.round(Number(v) * 1000) : now) };
  const me = (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i));
  // app: the app's version (its User-Agent), else a browser
  const call = (method, path, { who = null, body, now, query = '', app = null } = {}) => {
    const url = new URL('https://acrdaily.test' + path + query);
    const headers = { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(app ? { 'User-Agent': `ACR-Daily/${app} public` } : {}) };
    const req = new Request(url, { method, headers, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    return ttApi(req, f.env, path, url, who ? me(who) : null, true, now, deps);
  };
  return { ...f, deps, call };
}

const run = (stage, totalMs, { startedAt, car, status = 'finished', penaltyMs = 0 } = {}) => ({
  challengeId: stage.id, track: stage.track, car: car || stage.car, status, clockMs: totalMs - penaltyMs, resets: 0,
  official: { timeMs: totalMs - penaltyMs, penaltyMs }, startedAt: startedAt / 1000, trace: trace(totalMs - penaltyMs), appVersion: '0.0.23' });

test('a week of time trial on TT2: enter, drive as often as you like (the best counts), the board, and the prizes paid once', async () => {
  const w = world();
  const { db, call, count } = w;
  let now = T0 + 10 * H;
  const tt = await call('GET', '/api/tt', { who: 1, now });
  assert.equal(tt.status, 200);
  const t = tt.data;
  assert.equal(t.on, true);
  assert.equal(t.week, WEEK);
  assert.equal(t.endsAt - t.startsAt, 7 * D);
  assert.equal(t.fee, undefined, 'each stage has its own fee');
  assert.equal(t.stages.length, 2);
  // (s2: the stage with the fee, TT2; s1: the free one, TT1)
  const [s1, s2] = t.stages;
  assert.deepEqual([s1.id, s2.id], [`tt:${WEEK}/1`, `tt:${WEEK}/2`]);
  assert.deepEqual([s1.fee, s2.fee], [0, TT.fee]);
  assert.ok(s2.route && s2.route.length === ROUTE.length, 'the app gets the route to judge with');
  assert.equal(s2.mode, 'weekend');
  assert.deepEqual(s2.me, { entered: false, bestMs: null, runs: 0 });
  assert.deepEqual(s1.me, { entered: true, bestMs: null, runs: 0 }, 'TT1 is free: nothing to enter');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_schedule WHERE week = ?').get(WEEK).n, 2, 'the week\'s picks are kept');
  assert.equal((await call('GET', '/api/tt', { now, query: '?lite=1' })).data.stages[0].route, undefined);
  assert.equal((await call('GET', '/api/tt', { now, query: '?week=' + shiftWeek(WEEK, 1) })).status, 403, 'no peeking');
  assert.equal((await call('GET', '/api/tt', { now, query: '?week=' + shiftWeek(WEEK, -1) })).data.on, false, 'before the first week');

  // no entry: no run on the board
  let r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s2, 200000, { startedAt: now - 5 * 60000 }) });
  assert.equal(r.status, 402);
  assert.match(r.data.error, /^invalid run: TT2 takes runs from drivers who entered/);
  // the fee: not without the credits, once, from the ledger
  db.prepare('UPDATE credits SET balance = 10 WHERE steam_id = ?').run(sid(7));
  r = await call('POST', '/api/tt/enter', { who: 7, now, body: { slot: 2 } });
  assert.equal(r.status, 402);
  assert.match(r.data.error, /the entry fee is 200 credits: you have 10/);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_entries').get().n, 0);
  r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 2 } });
  assert.deepEqual([r.status, r.data.entered, r.data.balance, r.data.entrants, r.data.pot], [200, true, 800, 1, 200]);
  r = await call('POST', '/api/tt/enter', { who: 1, now: now + 1000, body: { slot: 2 } });
  assert.deepEqual([r.data.already, r.data.balance], [true, 800], 'entering twice takes the fee once');
  assert.deepEqual(db.prepare("SELECT delta, kind, ref FROM credit_ledger WHERE steam_id = ?").all(sid(1)).map((x) => ({ ...x })),
    [{ delta: -200, kind: 'tt-fee', ref: `tt:${WEEK}/2` }]);
  assert.ok(LABELS['tt-fee'] && LABELS['tt-prize'] && LABELS['tt-refund']);

  // a run that started before the entry doesn't count; the ones after it do, the best on the board
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s2, 200000, { startedAt: now - 10 * 60000 }) });
  assert.equal(r.status, 409);
  assert.match(r.data.error, /started before your entry/);
  now += H;
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s2, 200000, { startedAt: now - 5 * 60000 }) });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.deepEqual([r.data.best, r.data.rank, r.data.bestMs, r.data.runs], [true, 1, 200000, 1]);
  const first = r.data.id;
  r = await call('POST', '/api/tt/runs', { who: 1, now: now + 60000, body: run(s2, 210000, { startedAt: now - 60000 }) });
  assert.deepEqual([r.data.best, r.data.bestMs, r.data.runs], [false, 200000, 2], 'a slower run changes nothing on the board');
  r = await call('POST', '/api/tt/runs', { who: 1, now: now + 120000, body: run(s2, 196000, { startedAt: now, penaltyMs: 1000 }) });
  assert.deepEqual([r.data.best, r.data.improvedMs, r.data.bestMs], [true, 4000, 196000]);
  const best1 = r.data.id;
  assert.deepEqual(db.prepare('SELECT id FROM tt_runs WHERE trace IS NOT NULL').all().map((x) => x.id), [best1],
    'only the best run keeps its trace');
  const tr = await call('GET', `/api/tt/runs/${best1}/trace`, { now });
  assert.equal(tr.status, 200);
  assert.equal(tr.data.trace.length, 61);
  assert.equal((await call('GET', `/api/tt/runs/${first}/trace`, { now })).status, 404);

  // refused: another car, a DNF, no official time
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: run(s2, 199000, { startedAt: now, car: s1.car }) });
  assert.equal(r.status, 422);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: { ...run(s2, 199000, { startedAt: now }), status: 'dnf' } });
  assert.equal(r.status, 422);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: { ...run(s2, 199000, { startedAt: now }), official: null } });
  assert.equal(r.status, 422);
  assert.match(r.data.error, /no official result/);

  // five more drivers enter TT2: four set times, one never drives
  const times = { 2: 190000, 3: 230000, 4: 205000, 5: 220000 };
  for (const i of [2, 3, 4, 5, 6]) assert.equal((await call('POST', '/api/tt/enter', { who: i, now, body: { slot: 2 } })).status, 200);
  now += H;
  for (const [i, ms] of Object.entries(times)) {
    r = await call('POST', '/api/tt/runs', { who: +i, now, body: run(s2, ms, { startedAt: now - 5 * 60000 }) });
    assert.equal(r.status, 200);
  }
  // a tie: the time set first is ahead
  r = await call('POST', '/api/tt/runs', { who: 5, now: now + 5000, body: run(s2, 205000, { startedAt: now }) });
  assert.equal(r.data.rank, 4, 'a tie with 4: set later, so behind');
  const b = (await call('GET', '/api/tt/board', { now, query: `?week=${WEEK}&slot=2` })).data;
  assert.deepEqual(b.entries.map((e) => [e.steamId, e.rank, e.totalMs]),
    [[sid(2), 1, 190000], [sid(1), 2, 196000], [sid(4), 3, 205000], [sid(5), 4, 205000], [sid(3), 5, 230000]]);
  assert.deepEqual(b.entries.map((e) => e.runs), [1, 3, 1, 2, 1]);
  assert.equal(b.entries[1].clockMs, 195000);
  assert.equal(b.entries[1].gapMs, 6000);
  assert.ok(Array.isArray(b.entries[0].splits) && b.entries[0].splits.length === 3);
  // 5 with a time: 3 places paid; the pot of 6 fees: the 2 outside the top 3 pay the prizes, the 6th driver's fee goes back
  assert.deepEqual(b.entries.map((e) => e.prize), [401, 333, 266, 0, 0]);
  assert.equal(b.prizes, true);
  assert.deepEqual(b.stats, { drivers: 5, runs: 8, entrants: 6, pot: 1200, paidPlaces: 3 });
  assert.equal(b.settled, null);

  // a banned driver leaves the board (and the field)
  db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(sid(3));
  assert.deepEqual((await buildBoard(w.env, WEEK, 2)).entries.map((e) => e.steamId), [sid(2), sid(1), sid(4), sid(5)]);
  db.prepare('UPDATE players SET banned = 0 WHERE steam_id = ?').run(sid(3));

  // my side of it, in /api/tt
  const mine = (await call('GET', '/api/tt', { who: 1, now, query: '?lite=1' })).data.stages[1];
  assert.deepEqual([mine.me, mine.entrants, mine.pot], [{ entered: true, bestMs: 196000, runs: 3 }, 6, 1200]);

  // an admin takes a run off: the driver's next best counts
  const tie = r.data.id;
  assert.equal(await rejectTtRun(w.env, tie, 'checked'), true);
  assert.equal((await buildBoard(w.env, WEEK, 2)).entries.find((e) => e.steamId === sid(5)).totalMs, 220000);
  assert.equal(await rejectTtRun(w.env, 999999), false);
  db.prepare("UPDATE tt_runs SET status = 'finished' WHERE id = ?").run(tie);

  // the week closes: a run that started after it is refused, one finished before it may come a little late
  const end = T0 + 7 * D;
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 10 * 60000, body: run(s2, 180000, { startedAt: end + 60000 }) });
  assert.match(r.data.error, /started after the time trial closed/);
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 10 * 60000, body: run(s2, 189000, { startedAt: end - 5 * 60000 }) });
  assert.equal(r.status, 200, 'a run finished just before the close');
  r = await call('POST', '/api/tt/runs', { who: 2, now: end + 40 * 60000, body: run(s2, 188000, { startedAt: end - 5 * 60000 }) });
  assert.equal(r.status, 409);
  assert.match(r.data.error, /too late/);
  assert.equal((await call('POST', '/api/tt/enter', { who: 7, now: end + 60000, body: { slot: 2, week: WEEK } })).status, 409);

  // nothing settles until an hour after the close
  assert.deepEqual(await ttTick(w.env, end + 30 * 60000, w.deps), { settled: [] });
  count.queries = 0;
  const done = await ttTick(w.env, end + 2 * H, w.deps);
  assert.ok(count.queries <= 20, `settling the week took ${count.queries} queries`);
  assert.deepEqual(done.settled.map((x) => [x.week, x.slot, x.drivers]), [[WEEK, 1, 0], [WEEK, 2, 5]]);
  assert.deepEqual(done.settled[1].paid, { [sid(2)]: 401, [sid(1)]: 333, [sid(4)]: 266, [sid(6)]: 200 });
  const bal = (i) => db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(sid(i)).balance;
  assert.deepEqual([1, 2, 3, 4, 5, 6, 7].map(bal), [1133, 1201, 800, 1066, 800, 1000, 10]);
  assert.deepEqual(db.prepare("SELECT kind, COUNT(*) AS n, SUM(delta) AS s FROM credit_ledger GROUP BY kind ORDER BY kind").all().map((x) => ({ ...x })),
    [{ kind: 'tt-fee', n: 6, s: -1200 }, { kind: 'tt-prize', n: 3, s: 1000 }, { kind: 'tt-refund', n: 1, s: 200 }]);
  assert.deepEqual(db.prepare('SELECT steam_id, paid FROM tt_entries WHERE settled IS NOT NULL ORDER BY steam_id').all().map((x) => [x.steam_id, x.paid]),
    [[sid(1), 333], [sid(2), 401], [sid(3), 0], [sid(4), 266], [sid(5), 0], [sid(6), 200]]);
  const notes = db.prepare("SELECT to_id, body, ref FROM messages WHERE kind = 'tt' ORDER BY to_id").all();
  assert.equal(notes.length, 6);
  assert.ok(notes.every((n) => n.ref === `tt:${WEEK}`));
  assert.match(notes.find((n) => n.to_id === sid(1)).body, /^Time trial TT2 \(.+\), week 46 is over: you placed P2 of 5 \(3:16\.000, 3 runs\)\. Prize: 333 credits\.$/);
  assert.match(notes.find((n) => n.to_id === sid(6)).body, /You set no time: your entry fee of 200 credits is back\.$/);
  assert.match(notes.find((n) => n.to_id === sid(3)).body, /P5 of 5 .* Outside the top half: no prize this time\.$/);
  // the traces: the fastest few keep theirs
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_runs WHERE trace IS NOT NULL AND week = ?').get(WEEK).n, TT.keepTraces);
  // settled once; the board shows what was paid
  assert.deepEqual(await ttTick(w.env, end + 3 * H, w.deps), { settled: [] });
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM credit_ledger WHERE kind = 'tt-prize'").get().n, 3);
  const after = (await call('GET', '/api/tt/board', { now: end + 3 * H, query: `?week=${WEEK}&slot=2` })).data;
  assert.deepEqual(after.entries.map((e) => e.prize), [401, 333, 266, 0, 0]);
  assert.equal(after.settled, end + 2 * H);
  // the new week has its own stages, fixed by the cron
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_schedule WHERE week = ?').get(shiftWeek(WEEK, 1)).n, 2);
});

test('the live map: entrants on a stage show for 15 s after their last position (a finish for a minute)', async () => {
  const { call } = world();
  const now = T0 + 3 * D;
  const s2 = (await call('GET', '/api/tt', { now })).data.stages[1];
  const pos = (who, at, body = {}) => call('POST', '/api/tt/live', { who, now: at, body: { challengeId: s2.id, x: 100, z: 0, progress: 0.25,
    totalMs: 50000, state: 'live', ...body } });
  let r = await pos(1, now);
  assert.equal(r.status, 402, 'not entered: not on the map');
  assert.match(r.data.error, /^invalid run: enter TT2 first/);
  await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 2 } });
  await call('POST', '/api/tt/enter', { who: 2, now, body: { slot: 2 } });
  r = await pos(1, now);
  assert.deepEqual(r.data, { ok: true });
  r = await pos(2, now + 1000, { progress: 0.5, others: true });
  assert.deepEqual(r.data.drivers.map((d) => [d.steamId, d.progress, d.state]), [[sid(2), 0.5, 'live'], [sid(1), 0.25, 'live']],
    'others: who else is on the stage comes back with my position');
  const live = (at, q = '?slot=all') => call('GET', '/api/tt/live', { now: at, query: q });
  r = await live(now + 2000);
  assert.deepEqual(r.data.drivers.map((d) => [d.steamId, d.slot, d.name]), [[sid(2), 2, 'Driver 2'], [sid(1), 2, 'Driver 1']]);
  assert.deepEqual((await live(now + 2000, '?slot=1')).data.drivers, []);
  await pos(1, now + 5000, { progress: 1, state: 'finished' });
  r = await live(now + 20000);
  assert.deepEqual(r.data.drivers.map((d) => [d.steamId, d.state]), [[sid(1), 'finished']], 'a driver gone quiet leaves; a finish stays');
  assert.deepEqual((await live(now + 70000)).data.drivers, []);
  assert.equal((await call('POST', '/api/tt/live', { who: 1, now, body: { challengeId: `tt:${shiftWeek(WEEK, -1)}/1` } })).status, 400,
    'only this week\'s stages');
});

test('credits off: free to drive, no entry, no prizes; the week still settles (and trims its traces)', async () => {
  const w = world({ credits: false });
  const { db, call } = w;
  const now = T0 + 2 * D;
  const t = (await call('GET', '/api/tt', { who: 1, now })).data;
  assert.deepEqual([t.credits, t.stages[1].fee, t.stages[1].me.entered], [false, 0, true]);
  const r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 2 } });
  assert.deepEqual([r.data.entered, r.data.free], [true, true]);
  for (let i = 1; i <= 5; i++) {
    const s = await call('POST', '/api/tt/runs', { who: i, now, body: run(t.stages[1], 200000 + i * 1000, { startedAt: now - 60000 }) });
    assert.equal(s.status, 200);
  }
  const b = (await call('GET', '/api/tt/board', { now, query: `?week=${WEEK}&slot=2` })).data;
  assert.deepEqual([b.entries.length, b.entries[0].prize, b.credits, b.prizes], [5, null, false, false]);
  const done = await ttTick(w.env, T0 + 7 * D + 2 * H, w.deps);
  assert.equal(done.settled.length, 2);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM credit_ledger').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_runs WHERE trace IS NOT NULL').get().n, TT.keepTraces);
  assert.match(db.prepare("SELECT body FROM messages WHERE to_id = ?").get(sid(1)).body, /you placed P1 of 5 \(3:21\.000, 1 run\)\.$/);
});

test('TT1 is free with credits on: no entry, no prizes, on the map; a fee paid on it before it went free comes back', async () => {
  const w = world();
  const { db, call } = w;
  let now = T0 + D;
  const s1 = (await call('GET', '/api/tt', { who: 1, now })).data.stages[0];
  assert.deepEqual([s1.slot, s1.fee, s1.me.entered], [1, 0, true]);
  // an entry from before TT1 went free (the fee TT.fee was then)
  db.prepare('INSERT INTO tt_entries (week, slot, steam_id, fee, created) VALUES (?, 1, ?, 200, ?)').run(WEEK, sid(3), now - H);
  db.prepare("INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, -200, 'tt-fee', ?, NULL, ?)").run(sid(3), `tt:${WEEK}/1`, now - H);
  db.prepare('UPDATE credits SET balance = 800 WHERE steam_id = ?').run(sid(3));
  // entering takes nothing
  let r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 1 } });
  assert.deepEqual([r.status, r.data.entered, r.data.free], [200, true, true]);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM credit_ledger WHERE kind = 'tt-fee'").get().n, 1);
  // anyone signed in drives it, and shows on its map
  r = await call('POST', '/api/tt/live', { who: 2, now, body: { challengeId: s1.id, x: 100, z: 0, progress: 0.5, totalMs: 60000, state: 'live' } });
  assert.deepEqual(r.data, { ok: true });
  now += H;
  for (const [i, ms] of [[1, 200000], [2, 190000], [3, 210000], [4, 205000]]) {
    r = await call('POST', '/api/tt/runs', { who: i, now, body: run(s1, ms, { startedAt: now - 5 * 60000 }) });
    assert.equal(r.status, 200, JSON.stringify(r.data));
    assert.equal(r.data.prize, null);
  }
  const b = (await call('GET', '/api/tt/board', { now, query: `?week=${WEEK}&slot=1` })).data;
  assert.deepEqual(b.entries.map((e) => [e.steamId, e.prize]), [[sid(2), null], [sid(1), null], [sid(4), null], [sid(3), null]]);
  assert.deepEqual([b.fee, b.credits, b.prizes], [0, true, false]);
  // the week settles: no prizes; the fee paid before comes back
  const done = await ttTick(w.env, T0 + 7 * D + 2 * H, w.deps);
  assert.deepEqual(done.settled.map((x) => [x.slot, x.drivers, x.paid]), [[1, 4, { [sid(3)]: 200 }], [2, 0, {}]]);
  assert.deepEqual(db.prepare("SELECT steam_id, delta, note FROM credit_ledger WHERE kind = 'tt-refund'").all().map((x) => ({ ...x })),
    [{ steam_id: sid(3), delta: 200, note: 'the stage went free' }]);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM credit_ledger WHERE kind = 'tt-prize'").get().n, 0);
  assert.deepEqual([1, 2, 3, 4].map((i) => db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(sid(i)).balance), [1000, 1000, 1000, 1000]);
  const notes = db.prepare("SELECT to_id, body FROM messages WHERE kind = 'tt' ORDER BY to_id").all();
  assert.equal(notes.length, 4, 'one notice each');
  assert.match(notes.find((n) => n.to_id === sid(2)).body, /you placed P1 of 4 \(3:10\.000, 1 run\)\.$/);
  assert.match(notes.find((n) => n.to_id === sid(3)).body, /you placed P4 of 4 .*\. TT1 is free now: your entry fee of 200 credits is back\.$/);
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

// ------------------------------------------------------------------ private time trials

const LONDON = 'London Marylebone - Whitehall', GERMANY = '[MOD] Germany Full';

function privateWorld() {
  const w = world();
  w.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, 3000, 0, ?)')
    .run(LONDON, JSON.stringify(ROUTE), 'AcrXsLn02r0FullForward');
  w.db.prepare("INSERT INTO routes (track, points, length, updated, stage_id, contributed_by) VALUES (?, ?, 3000, 0, ?, 'game-files')")
    .run(GERMANY, JSON.stringify(ROUTE), 'WrcgDePanzerplatteFull');
  return w;
}

test('private ids: their own key and slots after the week\'s two; always free', () => {
  assert.ok(isPrivateWeek('p-abcdefghij') && !isPrivateWeek('p-abc') && !isPrivateWeek('2026-11-09') && !isPrivateWeek('p-ABCDEFGHIJ'));
  assert.equal(PRIVATE.firstSlot, 3);
  assert.deepEqual(parseTtId('tt:p-abcdefghij/3'), { week: 'p-abcdefghij', slot: 3, private: true });
  assert.deepEqual(parseTtId('tt:p-abcdefghij/17'), { week: 'p-abcdefghij', slot: 17, private: true });
  assert.equal(parseTtId('tt:p-abcdefghij/2'), null, 'a private stage never has a weekly slot');
  assert.equal(parseTtId('tt:p-abc/3'), null);
  assert.equal(feeOf({ CREDITS_FROM: '2026-10-12' }, 'p-abcdefghij', 3), 0, '"p-..." is after any date: never a fee');
});

test('a private time trial: made by the admin, a week long, seen by the newest apps and its page only, free, its own board and map', async () => {
  const w = privateWorld();
  const { db, call, env } = w;
  const now = T0 + 2 * D + 5 * H;                       // a Wednesday: it runs to the next Wednesday, not to Monday
  for (const bad of [{ stages: [] }, { stages: [{ track: LONDON, car: 'No Such Car' }] }, { stages: [{ track: LONDON, car: CARS[0].name }], minApp: 'new' },
    { stages: [{ track: LONDON, car: CARS[0].name, weather: 'Sunny' }] }]) {
    assert.ok((await setTtPrivate(env, bad, hash, now)).error, JSON.stringify(bad));
  }
  const made = await setTtPrivate(env, { title: 'Test drive', minApp: '0.1.5.42', stages: [
    { track: LONDON, car: CARS[0].name, weather: 'Clear', time: 'midday' }, { track: GERMANY, car: CARS[1].name }] }, hash, now);
  assert.equal(made.ok, true, JSON.stringify(made));
  const week = made.week;
  assert.ok(isPrivateWeek(week));
  assert.equal(made.page, '/tt/p/' + week.slice(2));
  assert.deepEqual([made.startsAt, made.endsAt - made.startsAt, made.minApp, made.title], [now, 7 * D, '0.1.5.42', 'Test drive']);
  assert.deepEqual(made.stages.map((s) => [s.slot, s.track, s.stageId, s.warning]),
    [[3, LONDON, 'AcrXsLn02r0FullForward', undefined], [4, GERMANY, 'WrcgDePanzerplatteFull', undefined]]);
  assert.ok(made.stages[1].weather && made.stages[1].time, 'conditions drawn when left out');
  const later = await setTtPrivate(env, { stages: [{ track: 'Nowhere', car: CARS[2].name }], startsAt: now + D }, hash, now);
  assert.deepEqual(later.stages.map((s) => [s.slot, s.warning]), [[5, 'no route for that track yet']], 'the next free slot');
  assert.notEqual(later.week, week);

  // the app: the newest sees them beside the week's two (not one that opens tomorrow); older apps and the website don't
  const tt = (app, who = 1, at = now) => call('GET', '/api/tt', { who, now: at, app });
  let t = (await tt('0.1.5.42')).data;
  assert.equal(t.stages.length, 2);
  assert.deepEqual(t.private.map((s) => [s.id, s.slot, s.private, s.page, s.fee]),
    [[`tt:${week}/3`, 3, true, made.page, 0], [`tt:${week}/4`, 4, true, made.page, 0]]);
  const [lon, ger] = t.private;
  assert.deepEqual([lon.requires, lon.rally, lon.surface, lon.menuName, lon.title], ['acrdaily-london', 'London', 'Tarmac', 'Westminster', 'Test drive']);
  assert.deepEqual([ger.requires, ger.rally, ger.surface, ger.menuName], ['wrcg-panzerplatte', 'Germany', 'Tarmac', 'Arena Panzerplatte']);
  assert.deepEqual([lon.startsAt, lon.endsAt, lon.mode, lon.route.length], [now, now + 7 * D, 'weekend', ROUTE.length]);
  assert.deepEqual(lon.me, { entered: true, bestMs: null, runs: 0 });
  assert.equal((await call('GET', '/api/tt', { who: 1, now, app: '0.1.5.42', query: '?lite=1' })).data.private[0].route, undefined);
  assert.equal((await tt('0.1.5.50')).data.private.length, 2, 'a later test build too');
  assert.equal((await tt('0.1.6')).data.private, undefined, 'never a release (a test build\'s min_app: the testers\' stages)');
  assert.equal((await tt('0.1.5.41')).data.private, undefined, 'an older app never sees them');
  assert.equal((await tt(null)).data.private, undefined, 'nor the website\'s /tt');

  // its page: whoever has the link (no sign-in), every stage with its route; a code that isn't one: nothing
  const page = (await call('GET', '/api/tt', { now, query: '?week=' + week })).data;
  assert.deepEqual([page.on, page.private, page.title, page.credits, page.startsAt, page.endsAt, page.stages.length], [true, true, 'Test drive', false, now, now + 7 * D, 2]);
  assert.equal(page.stages[0].route.length, ROUTE.length);
  assert.equal((await call('GET', '/api/tt', { now, query: '?week=p-zzzzzzzzzz' })).status, 404);

  // runs: from the newest app, inside its own dates; free (nothing to enter)
  const runOn = (s, ms, o = {}) => ({ ...run(s, ms, o), appVersion: o.app || '0.1.5.42' });
  let r = await call('POST', '/api/tt/enter', { who: 1, now, body: { slot: 3, week } });
  assert.deepEqual([r.data.entered, r.data.free], [true, true]);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: runOn(lon, 300000, { startedAt: now - 5 * 60000, app: '0.1.5.41' }) });
  assert.equal(r.status, 426, 'an older app: refused');
  assert.match(r.data.error, /0\.1\.5\.42 or newer/);
  r = await call('POST', '/api/tt/runs', { who: 1, now, body: runOn(lon, 300000, { startedAt: now - 10 * 60000 }) });
  assert.match(r.data.error, /started before the time trial opened/);
  r = await call('POST', '/api/tt/runs', { who: 1, now: now + H, body: runOn(lon, 300000, { startedAt: now + 10 * 60000 }) });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.deepEqual([r.data.best, r.data.rank, r.data.prize], [true, 1, null]);
  r = await call('POST', '/api/tt/runs', { who: 2, now: now + H, body: runOn(lon, 290000, { startedAt: now + 20 * 60000 }) });
  assert.equal(r.data.rank, 1);
  r = await call('POST', '/api/tt/runs', { who: 2, now: now + H, body: runOn(ger, 290000, { startedAt: now + 20 * 60000, car: lon.car }) });
  assert.equal(r.status, 422, 'its own car');
  const b = (await call('GET', '/api/tt/board', { now: now + H, query: `?week=${week}&slot=3` })).data;
  assert.deepEqual([b.entries.map((e) => [e.steamId, e.rank]), b.fee, b.prizes, b.credits], [[[sid(2), 1], [sid(1), 2]], 0, false, false]);
  assert.equal((await call('GET', '/api/tt/board', { now, query: `?week=${week}&slot=4` })).data.entries.length, 0);
  assert.equal((await call('GET', '/api/tt/board', { now, query: `?week=${week}&slot=5` })).status, 404, 'another page\'s slot');
  t = (await tt('0.1.5.42', 1, now + H)).data;
  assert.deepEqual(t.private[0].me, { entered: true, bestMs: 300000, runs: 1 });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM tt_runs WHERE week = ?').get(week).n, 2);

  // its live map
  r = await call('POST', '/api/tt/live', { who: 3, now: now + H, body: { challengeId: ger.id, x: 5, z: 0, progress: 0.1, totalMs: 9000, state: 'live', others: true } });
  assert.deepEqual(r.data.drivers.map((d) => [d.steamId, d.slot]), [[sid(3), 4]]);
  assert.deepEqual((await call('GET', '/api/tt/live', { now: now + H + 1000, query: `?week=${week}&slot=all` })).data.drivers.map((d) => d.slot), [4]);
  assert.equal((await call('GET', '/api/tt/live', { now: now + H, query: `?week=${week}&slot=x` })).status, 400);

  // past the Monday it goes on (its own week); then it closes: a run finished just before may come a little late
  const end = now + 7 * D;
  r = await call('POST', '/api/tt/runs', { who: 3, now: T0 + 7 * D + H, body: runOn(lon, 280000, { startedAt: T0 + 7 * D }) });
  assert.equal(r.status, 200, 'a new week of the weekly one: still open');
  r = await call('POST', '/api/tt/runs', { who: 3, now: end + 10 * 60000, body: runOn(lon, 279000, { startedAt: end - 5 * 60000 }) });
  assert.equal(r.status, 200);
  r = await call('POST', '/api/tt/runs', { who: 3, now: end + 10 * 60000, body: runOn(lon, 270000, { startedAt: end + 60000 }) });
  assert.match(r.data.error, /started after the time trial closed/);
  r = await call('POST', '/api/tt/runs', { who: 3, now: end + 40 * 60000, body: runOn(lon, 270000, { startedAt: end - 60000 }) });
  assert.match(r.data.error, /too late/);
  assert.deepEqual(((await tt('0.1.5.42', 1, end + 40 * 60000)).data.private || []).map((s) => s.week), [later.week],
    'closed: gone from the app (the page opened a day later is still on)');
  assert.equal((await call('GET', '/api/tt', { now: end + 40 * 60000, query: '?week=' + week })).data.stages.length, 2, 'its page stays');

  // nothing to settle: no messages, no credits; the weekly weeks settle as ever
  const done = await ttTick(env, T0 + 14 * D + 2 * H, w.deps);
  assert.ok(done.settled.every((x) => !isPrivateWeek(x.week)));
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE ref LIKE 'tt:p-%'").get().n, 0);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM credit_ledger WHERE ref LIKE 'tt:p-%'").get().n, 0);
});

test('a private time trial changed: its apps, its close, its title', async () => {
  const w = privateWorld();
  const now = T0 + D;
  const made = await setTtPrivate(w.env, { minApp: '0.1.5.42', stages: [{ track: LONDON, car: CARS[0].name }] }, hash, now);
  const code = made.week.slice(2);
  assert.equal((await setTtPrivate(w.env, { page: 'nothere12' }, hash, now)).error, 'no such private time trial');
  assert.ok((await setTtPrivate(w.env, { page: code, endsAt: now - 1 }, hash, now)).error);
  let ch = await setTtPrivate(w.env, { page: code, minApp: '0.1.5.50', title: 'London only', endsAt: now + 3 * D }, hash, now);
  assert.deepEqual([ch.minApp, ch.title, ch.endsAt], ['0.1.5.50', 'London only', now + 3 * D]);
  assert.equal((await w.call('GET', '/api/tt', { now, app: '0.1.5.42' })).data.private, undefined);
  assert.equal((await w.call('GET', '/api/tt', { now, app: '0.1.5.50' })).data.private.length, 1);
  ch = await setTtPrivate(w.env, { page: made.week, minApp: '' }, hash, now);
  assert.equal(ch.minApp, null, 'every app');
  assert.equal((await w.call('GET', '/api/tt', { now, app: '0.1.4' })).data.private.length, 1);
});

test('a private time trial made public (listed): the main page points to it while open, its page is an ordinary one', async () => {
  const w = privateWorld();
  const now = T0 + D;
  const made = await setTtPrivate(w.env, { title: 'Community stages', minApp: '0.1.6', startsAt: now + D, days: 7,
    stages: [{ track: LONDON, car: CARS[0].name }] }, hash, now);
  assert.equal(made.listed, false);
  const ch = await setTtPrivate(w.env, { page: made.week, listed: true }, hash, now);
  assert.equal(ch.listed, true);
  assert.equal(ch.minApp, '0.1.6', 'its apps as they were');
  // before it opens and after it closes: not on the main page; while open: there, with its stages and its link
  assert.equal((await w.call('GET', '/api/tt', { now })).data.also, undefined);
  const open = (await w.call('GET', '/api/tt', { now: now + 2 * D })).data;
  assert.equal(open.also.length, 1);
  assert.deepEqual([open.also[0].page, open.also[0].title, open.also[0].minApp], [made.page, 'Community stages', '0.1.6']);
  assert.deepEqual(open.also[0].stages.map((s) => [s.slot, s.rally]), [[made.stages[0].slot, 'London']]);
  assert.equal(open.private, undefined, 'its stages still only to an app from its version');
  assert.equal((await w.call('GET', '/api/tt', { now: now + 9 * D })).data.also, undefined);
  // its own page: says so, and is an ordinary page (indexed, the referrer as usual)
  const pg = (await w.call('GET', '/api/tt', { now: now + 2 * D, query: '?week=' + made.week })).data;
  assert.deepEqual([pg.listed, pg.minApp], [true, '0.1.6']);
  const res = await worker.fetch(new Request('https://acrdaily.com' + made.page), w.env, { waitUntil() {} });
  assert.equal(res.status, 200);
  assert.doesNotMatch(res.headers.get('X-Robots-Tag') || '', /noindex/);
  assert.notEqual(res.headers.get('Referrer-Policy'), 'no-referrer');
  // link-only again
  assert.equal((await setTtPrivate(w.env, { page: made.week, listed: false }, hash, now)).listed, false);
  assert.equal((await w.call('GET', '/api/tt', { now: now + 2 * D })).data.also, undefined);
});

test('a private time trial\'s page: its own address, not indexed, its link never sent on', async () => {
  const { env } = privateWorld();
  const made = await setTtPrivate(env, { title: 'Test', stages: [{ track: LONDON, car: CARS[0].name }] }, hash, Date.now());
  const res = await worker.fetch(new Request('https://acrdaily.com' + made.page), env, { waitUntil() {} });
  assert.equal(res.status, 200);
  assert.match(res.headers.get('X-Robots-Tag'), /noindex/);
  assert.equal(res.headers.get('Referrer-Policy'), 'no-referrer');
  const html = await res.text();
  assert.match(html, /Private time trial/);
  assert.ok(html.includes(JSON.stringify(made.week)), 'the page asks for its own stages');
  const other = await worker.fetch(new Request('https://acrdaily.com/tt/p/abc'), env, { waitUntil() {} });
  assert.notEqual(other.headers.get('X-Robots-Tag'), 'noindex, nofollow', 'not a code: not that page');
});
