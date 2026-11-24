// Ranked rallies (src/liverallies.js) on a real SQLite (schema.sql, node:sqlite): the two series in turn every 2 hours,
// registration in the 30 minutes before the hour, the rally drawn and the start list published once at the hour, the
// turns (20 s each, from the hour + 5 minutes, the best rated first), the later stages' queues after a 3-minute break,
// a turn missed sent to the end, a start on red given the seconds it jumped, and the session driven through the
// leagues' own start / begin / stage.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { driverRanked, driverRankedStmt, LIVE, liveApi, phaseOf, publish, rallyOfWeek, SERIES, seriesAt, sessionsBetween } from '../src/liverallies.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { MENU_NAMES } from '../src/stages.js';
import { fakeD1, sid } from './faked1.mjs';

const H = Date.UTC(2026, 10, 18, 8, 0);              // Wed 18 Nov 2026, 08:00 UTC: a Rally2 session
const MIN = 60000;
const [ANN, BEN, CAT, DAN] = [sid(1), sid(2), sid(3), sid(4)];
const RALLY_OF = { Alsace: 'Alsace', Greece: 'Greece', MonteCarlo: 'Monte Carlo', Weles: 'Wales' };
const ROUTES = Object.entries(MENU_NAMES).map(([id, name]) => ({ track: `${RALLY_OF[id.match(/^[A-Z][a-z]+(?:Carlo)?/)[0]]} ${name}`,
  stage_id: id, length: 8000 }));

function seeded(seed = 1) {
  let s = seed;
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
}
function world() {
  const f = fakeD1({ LIVE_FROM: '2026-11-18', LEAGUES_MIN_APP: '0.0.5' });
  for (const r of ROUTES) f.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, \'[]\', ?, 0, ?)').run(r.track, r.length, r.stage_id);
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CAT, 'Cat'], [DAN, 'Dan']]) {
    f.db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  }
  // the dailies' rating: Cat best, then Ben; Ann and Dan have none
  f.db.prepare('INSERT INTO ratings (steam_id, rating, races, peak, updated) VALUES (?, 1700, 5, 1700, 0), (?, 1600, 5, 1600, 0)').run(CAT, BEN);
  return f;
}
const player = (db, s) => (s ? { ...db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s) } : null);
const live = async (f, path, me, now, body = null, rand = seeded()) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.5.30 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await liveApi(req, f.env, url.pathname, player(f.db, me), now, rand);
  return { status: res.status, body: await res.json() };
};
const league = async (f, path, me, now, body = null) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.5.30 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, f.env, url.pathname, url, player(f.db, me), true, now);
  return { status: res.status, body: await res.json() };
};
const S = (k = 'rally2', h = H) => `/api/liverallies/${k}/${h}`;
const signUp = (f, who, car = 'Skoda Fabia RS Rally2', at = H - 10 * MIN) => live(f, `${S()}/signup`, who, at, { car });

test('the schedule: a session every hour, the four series in turn; each in its own country every week', () => {
  assert.deepEqual([0, 1, 2, 3, 4].map((h) => seriesAt(H + h * 3600000).key), ['rally2', 'junior', 'classic', 'sixties', 'rally2']);
  assert.equal(seriesAt(H + 30 * MIN), null);                    // (half past: none)
  const day = sessionsBetween(Date.UTC(2026, 10, 18), Date.UTC(2026, 10, 18, 23, 59));
  assert.equal(day.length, 24);
  assert.deepEqual(day.filter((x) => x.series.key === 'rally2').map((x) => new Date(x.starts).getUTCHours()), [0, 4, 8, 12, 16, 20]);
  assert.deepEqual(day.filter((x) => x.series.key === 'classic').map((x) => new Date(x.starts).getUTCHours()), [2, 6, 10, 14, 18, 22]);
  assert.deepEqual(day.filter((x) => x.series.key === 'sixties').map((x) => new Date(x.starts).getUTCHours()), [3, 7, 11, 15, 19, 23]);
  for (let w = 0; w < 4; w++) {
    const t = H + w * 7 * 86400000;
    assert.equal(new Set(SERIES.map((s) => rallyOfWeek(s, t))).size, 4);
  }
  assert.deepEqual(SERIES.map((s) => s.carClass), ['Rally2/R5', 'Rally4', 'H1', 'H3']);
  assert.equal(rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 16)), rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 22, 23)));   // Monday to Sunday
  assert.notEqual(rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 16)), rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 23)));
  assert.deepEqual([phaseOf(H, H - 31 * MIN), phaseOf(H, H - 30 * MIN), phaseOf(H, H), phaseOf(H, H + 105 * MIN)],
    ['upcoming', 'signup', 'running', 'over']);
});

test('sign-up: in the 30 minutes before the hour, with a car of the class; withdrawn before it', async () => {
  const f = world();
  assert.equal((await signUp(f, ANN, 'Skoda Fabia RS Rally2', H - 31 * MIN)).status, 409);
  assert.equal((await signUp(f, ANN, 'Lancia Stratos HF')).status, 422);
  const r = await signUp(f, ANN);
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.deepEqual([r.body.phase, r.body.me.signedUp, r.body.me.car, r.body.entrants.map((e) => e.name)],
    ['signup', true, 'Skoda Fabia RS Rally2', ['Ann']]);
  assert.equal((await signUp(f, ANN, 'VW Polo GTI R5')).body.me.car, 'VW Polo GTI R5');   // (the car changed)
  // the registered as the start list will have them: the rating, best first (with the world ranking's place), then
  // the drivers without one, by registration
  await signUp(f, BEN, 'VW Polo GTI R5', H - 9 * MIN);
  await signUp(f, CAT, 'VW Polo GTI R5', H - 8 * MIN);
  const all = (await live(f, S(), ANN, H - 7 * MIN)).body.entrants;
  assert.deepEqual(all.map((e) => [e.name, e.rating, e.rank]), [['Cat', 1700, 1], ['Ben', 1600, 2], ['Ann', null, null]]);
  for (const who of [BEN, CAT]) await live(f, `${S()}/withdraw`, who, H - 6 * MIN, {});
  assert.equal((await live(f, `${S()}/signup`, null, H - 5 * MIN, { car: 'VW Polo GTI R5' })).status, 401);
  const w = await live(f, `${S()}/withdraw`, ANN, H - 5 * MIN, {});
  assert.deepEqual([w.body.me.signedUp, w.body.entrants.length], [false, 0]);
  assert.equal((await signUp(f, ANN, 'VW Polo GTI R5', H)).status, 409);                   // (closed at the hour)
  assert.equal((await live(f, `/api/liverallies/classic/${H}`, ANN, H - 5 * MIN)).status, 404);   // (08:00 is Rally2's)
  const holder = f.db.prepare("SELECT * FROM leagues WHERE id = 'liverly2'").get();
  assert.deepEqual([holder.kind, holder.public, holder.owner], ['live', 0, 'acr-daily']);
});

test('at the hour: the rally drawn once, the start list by rating, the first turn 5 minutes on', async () => {
  const f = world();
  for (const [who, at] of [[DAN, 20], [ANN, 15], [BEN, 10], [CAT, 5]]) await signUp(f, who, 'Skoda Fabia RS Rally2', H - at * MIN);
  const before = await live(f, S(), ANN, H - MIN);
  assert.equal(before.body.event, undefined);                   // nothing of the rally before the hour
  const [a, b] = await Promise.all([live(f, S(), ANN, H + 1000), live(f, S(), BEN, H + 1000, null, seeded(7))]);
  assert.equal(a.status, 200, JSON.stringify(a.body));
  // published once: whoever asks meanwhile sees it being published (the app asks again in 2 s), then the same event
  assert.ok(b.body.eventId === a.body.eventId || (b.body.publishing && b.body.pollS === 2), JSON.stringify(b.body));
  assert.equal((await live(f, S(), BEN, H + 3000, null, seeded(7))).body.eventId, a.body.eventId);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_events').get().n, 1);
  const ev = a.body.event;
  assert.equal(ev.kind, 'live');
  assert.equal(ev.rally, rallyOfWeek(SERIES[0], H));
  assert.equal(ev.stages.length, 3);
  assert.deepEqual(ev.stages.map((s) => s.service), [true, false, false]);   // damage carries from SS1 to SS3
  assert.equal(new Set(ev.stages.map((s) => s.weather)).size, 1);
  assert.equal(new Set(ev.stages.map((s) => s.track)).size, 3);
  assert.equal(ev.carClass, 'Rally2/R5');
  // the start list: the best rated first, each turn 20 s at the latest; before 08:05 all getting ready
  const t0 = H + LIVE.firstStartMs;
  assert.deepEqual(a.body.queues[0].map((q) => [q.name, q.state, q.ahead, q.estAt - t0]),
    [['Cat', 'break', 0, 0], ['Ben', 'break', 1, 20000], ['Dan', 'break', 2, 40000], ['Ann', 'break', 3, 60000]]);
  assert.deepEqual(a.body.me.next, { no: 0, state: 'break', at: t0 + 60000, readyAt: t0, turnAt: null, deadline: null,
    estAt: t0 + 60000, ahead: 3, moved: 0, started: null, penaltyMs: 0, out: null });
  assert.deepEqual([a.body.resultsOut, a.body.live.turnS, a.body.live.breakS], [false, 20, 180]);
  // the app's leagues list has it for its drivers, and for nobody else
  const mine = (await league(f, '/api/me/events', ANN, H + 2000)).body.events;
  assert.deepEqual(mine.map((e) => [e.id, e.kind, e.series, e.sessionStarts]), [[a.body.eventId, 'live', 'rally2', H]]);
  f.db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Eve', 0)").run(sid(5));
  assert.equal((await league(f, '/api/me/events', sid(5), H + 2000)).body.events.length, 0);
  assert.equal((await signUp(f, sid(5), 'Skoda Fabia RS Rally2', H + 2000)).status, 409);
});

test('nobody signed up: the session is empty, nothing is made', async () => {
  const f = world();
  const r = await live(f, S(), ANN, H + MIN);
  assert.deepEqual([r.body.phase, r.body.eventId], ['empty', undefined]);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_events').get().n, 0);
});

async function published(f, who = [CAT, BEN]) {
  for (const [k, w] of who.entries()) await signUp(f, w, 'Skoda Fabia RS Rally2', H - (20 - k) * MIN);
  return (await live(f, S(), who[0], H + 1000)).body.eventId;   // the turns: Cat, Ben (, Ann)
}
const start = (f, id, who, now, at) => league(f, `/api/events/${id}/start`, who, now, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: at });
const rowOf = (f, id, who, no = 0) => f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = ? AND steam_id = ?').get(id, no, who);

test('turns: the top-ranked first, 20 s each; a start passes the turn on at once; on red, the seconds jumped added', async () => {
  const f = world();
  const id = await published(f, [CAT, BEN, ANN]);
  const t0 = H + LIVE.firstStartMs;
  let v = (await live(f, S(), BEN, t0 + 1000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.ahead, q.turnAt && q.turnAt - t0, q.estAt - t0]),
    [['Cat', 'turn', 0, 0, 0], ['Ben', 'waiting', 1, null, 20000], ['Ann', 'waiting', 2, null, 40000]]);
  assert.equal(v.queues[0][0].deadline, t0 + LIVE.turnMs);
  assert.equal(v.pollS, LIVE.pollS.turn);                       // (next: the app asks every 2 s)
  const cat = await start(f, id, CAT, t0 + 1500, t0 + 1200);
  assert.equal(cat.status, 200, JSON.stringify(cat.body));
  assert.deepEqual(cat.body.slot, { startedAt: t0 + 1200 });
  v = (await live(f, S(), BEN, t0 + 2000)).body;                // Cat away: Ben's turn from her start
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.turnAt && q.turnAt - t0]),
    [['Cat', 'driving', 0], ['Ben', 'turn', 1200], ['Ann', 'waiting', null]]);
  assert.deepEqual([v.me.next.state, v.me.next.turnAt, v.me.next.deadline], ['turn', t0 + 1200, t0 + 21200]);
  // Ann starts on red (08:05:04.8, Ben's turn): nothing yet; Ben starts at 08:05:09, her turn then: 4.2 s jumped, 5 s
  await start(f, id, ANN, t0 + 5000, t0 + 4800);
  v = (await live(f, S(), ANN, t0 + 6000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.penaltyMs]), [['Cat', 'driving', 0], ['Ben', 'turn', 0], ['Ann', 'driving', 0]]);
  await start(f, id, BEN, t0 + 9500, t0 + 9000);
  v = (await live(f, S(), ANN, t0 + 10000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.penaltyMs]), [['Cat', 'driving', 0], ['Ben', 'driving', 0], ['Ann', 'driving', 5000]]);
  assert.equal(v.me.next, null);
  const pen = f.db.prepare('SELECT * FROM league_penalties WHERE event_id = ?').all(id);
  assert.deepEqual(pen.map((p) => [p.steam_id, p.stage_no, p.ms, p.by]), [[ANN, 0, 5000, 'acr-daily']]);
  assert.match(pen[0].reason, /jump start: SS1 started 5 s before the turn/);
  // in the standings: on the stage, as a steward's penalty
  await league(f, `/api/events/${id}/stage`, ANN, t0 + 7 * MIN, { no: 0, timeMs: 360000, penaltyMs: 0 });
  const row = (await live(f, S(), ANN, t0 + 7 * MIN)).body.standings.find((r) => r.steamId === ANN);
  assert.deepEqual([row.stages[0].stewardMs, row.stages[0].totalMs], [5000, 365000]);
  // the same start sent again (the app's queue retried), and more looks: no second penalty
  await start(f, id, ANN, t0 + 25000, t0 + 4800);
  await live(f, S(), CAT, t0 + 26000);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_penalties').get().n, 1);
});

test('a turn missed: to the end of the queue, the next turn at once; missed too often, out', async () => {
  const f = world();
  const id = await published(f, [CAT, BEN, ANN]);
  const t0 = H + LIVE.firstStartMs;
  // Cat never starts: at 08:05:20 Ben's turn, Cat after Ann
  let v = (await live(f, S(), ANN, t0 + 21000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.moved, q.ahead, q.estAt - t0]),
    [['Ben', 'turn', 0, 0, 20000], ['Ann', 'waiting', 0, 1, 40000], ['Cat', 'waiting', 1, 2, 60000]]);
  await start(f, id, BEN, t0 + 25000, t0 + 25000);
  await start(f, id, ANN, t0 + 30000, t0 + 30000);
  // Cat's turns: 08:05:30, :50, 08:06:10, missed each, the last ending 08:06:30: out (did not start), in one look
  v = (await live(f, S(), CAT, t0 + 91000)).body;
  const cat = v.queues[0].find((q) => q.name === 'Cat');
  assert.deepEqual([cat.state, cat.moved], ['dns', LIVE.maxMoves]);
  assert.equal(rowOf(f, id, CAT).moved_at, t0 + 90000);
  assert.deepEqual([v.me.next, v.me.out.out], [null, 'dns']);
  // out is out: a start made after that is refused (the app stops following the session), and no entry is made
  const late = await start(f, id, CAT, t0 + 95000, t0 + 94000);
  assert.deepEqual([late.status, late.body.status], [200, 'dnf']);
  assert.match(late.body.reason, /did not start: missed the turn 4 times/);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_entries WHERE steam_id = ?').get(CAT).n, 0);
});

test('a start on its way while the queue moves on: in the turn it was made in', async () => {
  const f = world();
  const id = await published(f);                                // Cat, Ben
  const t0 = H + LIVE.firstStartMs;
  await live(f, S(), BEN, t0 + 21000);                          // Cat's turn over (her start not in yet): Ben's
  assert.deepEqual([rowOf(f, id, CAT).moved, rowOf(f, id, CAT).moved_at, rowOf(f, id, BEN).turn_at], [1, t0 + 20000, t0 + 20000]);
  // ...it was made at 08:05:10, in her turn, and comes in now: on time, Ben's turn as it was
  const r = await start(f, id, CAT, t0 + 22000, t0 + 10000);
  assert.equal(r.body.status, 'running');
  const v = (await live(f, S(), BEN, t0 + 23000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.turnAt - t0, q.penaltyMs]), [['Cat', 'driving', 0, 0], ['Ben', 'turn', 20000, 0]]);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_penalties').get().n, 0);
  // out of the queue the same way: a start made in the last turn still counts
  const g = world();
  const id2 = await published(g);
  await live(g, S(), BEN, t0 + 21000);
  await start(g, id2, BEN, t0 + 21000, t0 + 21000);            // Cat's turns then: :21, :41, 08:06:01, out at :21
  await live(g, S(), BEN, t0 + 82000);
  const out = rowOf(g, id2, CAT);
  assert.deepEqual([out.out, out.moved_at], ['dns', t0 + 81000]);
  const inTime = await start(g, id2, CAT, t0 + 85000, t0 + 75000);
  assert.equal(inTime.body.status, 'running');
  const v2 = (await live(g, S(), BEN, t0 + 86000)).body;
  assert.deepEqual(v2.queues[0].map((q) => [q.name, q.state, q.turnAt - t0, q.penaltyMs]),
    [['Ben', 'driving', 20000, 0], ['Cat', 'driving', 61000, 0]]);   // (in the order the turns came)
});

test('a later stage: a begin on its way when the queue made the entry a DNF undoes it', async () => {
  const f = world();
  const id = await published(f, [CAT]);
  const t0 = H + LIVE.firstStartMs;
  await start(f, id, CAT, t0, t0);
  const fin = t0 + 6 * MIN;
  const slot = (await live(f, `${S()}/queue`, CAT, fin + 300, { no: 1, finishedAt: fin })).body.slot;
  assert.equal(slot.readyAt, fin + LIVE.breakMs);
  await league(f, `/api/events/${id}/stage`, CAT, fin + 40000, { no: 0, timeMs: 360000, penaltyMs: 0 });
  // SS2 never seen starting: her 4 turns go by, then out, a DNF
  const t = slot.readyAt + 4 * LIVE.turnMs;
  await live(f, S(), CAT, t + 1000);
  assert.deepEqual([rowOf(f, id, CAT, 1).out, rowOf(f, id, CAT, 1).moved_at], ['dnf', t]);
  assert.equal(f.db.prepare('SELECT status FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT).status, 'dnf');
  // a start made later than that: still a DNF
  const no = await league(f, `/api/events/${id}/begin`, CAT, t + 2000, { no: 1, at: 5, serverAt: t + 1000 });
  assert.equal(no.body.status, 'dnf');
  // one made before it (in its last turn, still on its way): the DNF undone, the stage on
  const yes = await league(f, `/api/events/${id}/begin`, CAT, t + 3000, { no: 1, at: 6, serverAt: t - 5000 });
  assert.equal(yes.body.status, 'running');
  const e = f.db.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT);
  assert.deepEqual([e.status, e.reason, e.on_stage], ['running', null, 1]);
  const v = (await live(f, S(), CAT, t + 4000)).body;
  assert.deepEqual(v.queues[1].map((q) => [q.name, q.state, q.penaltyMs]), [['Cat', 'driving', 0]]);
});

test('publishing taken over after a stall makes no second event', async () => {
  const f = world();
  const id = await published(f);
  f.db.prepare('UPDATE live_sessions SET event_id = NULL, created = ?').run(H - MIN);   // (as if it had stalled)
  assert.equal(await publish(f.env, SERIES[0], H, H + 2 * MIN, seeded(3)), id);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_events').get().n, 1);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM live_slots WHERE stage_no = 0').get().n, 2);
});

test('the later stages: ready 3 minutes after the finish, whoever is ready first goes first', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + LIVE.firstStartMs;
  await start(f, id, CAT, t0, t0);
  await start(f, id, BEN, t0 + 3000, t0 + 3000);
  assert.equal((await live(f, `${S()}/queue`, CAT, t0 + 4000, { no: 2 })).status, 409);         // (SS2 not driven)
  // Ben finishes SS1 first (08:11:10), Cat just after (08:11:12): Ben ready 08:14:10, Cat 08:14:12
  const fin = t0 + 6 * MIN + 10000;
  const qb = await live(f, `${S()}/queue`, BEN, fin + 300, { no: 1, finishedAt: fin });
  assert.equal(qb.status, 200, JSON.stringify(qb.body));
  assert.equal(qb.body.slot.readyAt, fin + LIVE.breakMs);
  const qc = await live(f, `${S()}/queue`, CAT, fin + 2500, { no: 1, finishedAt: fin + 2000 });
  assert.equal(qc.body.slot.readyAt, fin + 2000 + LIVE.breakMs);
  assert.equal((await live(f, `${S()}/queue`, CAT, fin + 9000, { no: 1, finishedAt: fin + 8000 })).body.slot.readyAt, qc.body.slot.readyAt);   // (once)
  for (const who of [BEN, CAT]) {
    const s = await league(f, `/api/events/${id}/stage`, who, fin + 40000, { no: 0, timeMs: 370000, penaltyMs: 0 });
    assert.equal(s.status, 200, JSON.stringify(s.body));
  }
  // on the break: both, the turns in readiness order
  let v = (await live(f, S(), CAT, fin + MIN)).body;
  assert.deepEqual(v.queues[1].map((q) => [q.name, q.state, q.ahead, q.estAt - fin]),
    [['Ben', 'break', 0, LIVE.breakMs], ['Cat', 'break', 1, LIVE.breakMs + LIVE.turnMs]]);
  assert.deepEqual([v.me.next.no, v.me.next.state, v.pollS], [1, 'break', LIVE.pollS.wait]);
  const T = fin + LIVE.breakMs;
  v = (await live(f, S(), CAT, T + 3000)).body;
  assert.deepEqual(v.queues[1].map((q) => [q.name, q.state]), [['Ben', 'turn'], ['Cat', 'waiting']]);
  const bb = await league(f, `/api/events/${id}/begin`, BEN, T + 5500, { no: 1, at: 5, serverAt: T + 5000 });
  assert.equal(bb.status, 200, JSON.stringify(bb.body));
  const q0 = f.count.queries;
  v = (await live(f, S(), CAT, T + 6000)).body;
  assert.ok(f.count.queries - q0 <= 15, `a session's view: ${f.count.queries - q0} queries`);   // (the free plan: 50 a request)
  assert.deepEqual(v.queues[1].map((q) => [q.name, q.state, q.turnAt - T]), [['Ben', 'driving', 0], ['Cat', 'turn', 5000]]);
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.timeMs]), [['Cat', 'done', 370000], ['Ben', 'done', 370000]]);
  // Cat never starts SS2: her 4 turns, then a DNF
  await live(f, S(), BEN, T + 5000 + 4 * LIVE.turnMs + 1000);
  const entry = f.db.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT);
  assert.deepEqual([entry.status, entry.reason], ['dnf', 'did not start SS2']);
});

test('nobody there for a long while: the turns go by a few at a time, as they would have, then out', async () => {
  const f = world();
  const who = [CAT, BEN, ANN, DAN];
  for (let k = 5; k <= 12; k++) {
    f.db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(k), `P${k}`);
    who.push(sid(k));
  }
  const id = await published(f, who);
  const t0 = H + LIVE.firstStartMs;
  // 12 drivers, none in the game: 4 turns each, 20 s each, the last over at 08:21:00 (looks of 30 writes at most)
  let v;
  for (let k = 0; k < 10; k++) {
    const q0 = f.count.queries;
    v = (await live(f, S(), CAT, t0 + 30 * MIN)).body;
    assert.ok(f.count.queries - q0 <= 50, `${f.count.queries - q0} queries`);
  }
  assert.ok(v.queues[0].every((q) => q.state === 'dns'), JSON.stringify(v.queues[0].map((q) => q.state)));
  const ends = f.db.prepare('SELECT moved_at FROM live_slots WHERE event_id = ? ORDER BY moved_at').all(id).map((r) => r.moved_at - t0);
  assert.deepEqual(ends, Array.from({ length: 12 }, (_, k) => (36 + k + 1) * LIVE.turnMs));
  assert.equal(v.resultsOut, true);
});

test('the results are out when every driver is done', async () => {
  const f = world();
  const id = await published(f, [CAT, BEN]);
  const t0 = H + LIVE.firstStartMs;
  await start(f, id, CAT, t0, t0);
  let v = (await live(f, S(), CAT, t0 + 1000)).body;
  assert.equal(v.resultsOut, false);
  await live(f, `${S()}/dnf`, BEN, t0 + 2000, { no: 0, reason: 'SS1 driven outside the rally' });
  await live(f, `${S()}/dnf`, CAT, t0 + 3000, { no: 1, reason: 'SS2 driven outside the rally' });
  v = (await live(f, S(), CAT, t0 + 4000)).body;
  assert.deepEqual([v.resultsOut, v.pollS], [true, LIVE.pollS.idle]);
  // in the RESULTS list once it is over: who won (nobody finished: none) and where I came (from its standings)
  const o = (await live(f, '/api/liverallies', CAT, H + 3 * 3600000)).body;
  assert.deepEqual(o.recent.map((r) => [r.series, r.starts, r.drivers, r.mine, r.winner, r.me && r.me.status, r.me && r.me.rank]),
    [['rally2', H, 2, true, null, 'dnf', null]]);
  assert.equal((await live(f, '/api/liverallies', DAN, H + 3 * 3600000)).body.recent[0].me, null);    // (not in it)
  // its results page (/e/<id>, linked from /ranked): open to anyone, not only its drivers (it said "No such event")
  for (const who of [DAN, null]) {
    const e = await league(f, `/api/events/${id}`, who, H + 3 * 3600000);
    assert.equal(e.status, 200, String(who));
    assert.equal(e.body.league.kind, 'live');
  }
  // and on its drivers' own pages: their ranked rallies (src/drivers.js)
  const rows = (await driverRankedStmt(f.env, CAT, H + 3 * 3600000).all()).results;
  assert.deepEqual((await driverRanked(f.env, CAT, rows, H + 3 * 3600000)).map((r) => [r.series, r.starts, r.eventId, r.drivers,
    r.status, r.rank]), [['rally2', H, id, 2, 'dnf', null]]);
  assert.deepEqual((await driverRankedStmt(f.env, DAN, H + 3 * 3600000).all()).results, []);
});

test('the overview: the series, their sessions with sign-ups; off without LIVE_FROM', async () => {
  const f = world();
  await signUp(f, ANN);
  const o = (await live(f, '/api/liverallies', ANN, H - 10 * MIN)).body;
  assert.equal(o.on, true);
  assert.deepEqual(o.series.map((s) => [s.key, s.carClass, s.cars.length]),
    [['rally2', 'Rally2/R5', 3], ['junior', 'Rally4', 1], ['classic', 'H1', 3], ['sixties', 'H3', 3]]);
  // (the hour before's, which nobody registered for, is over at its hour: not listed as under way)
  assert.ok(!o.sessions.some((x) => x.starts < H), 'no empty session gone by');
  const first = o.sessions[0];
  assert.deepEqual([first.series, first.starts, first.phase, first.signups, first.signedUp, first.car],
    ['rally2', H, 'signup', 1, true, 'Skoda Fabia RS Rally2']);
  assert.deepEqual(o.sessions.slice(0, 5).map((s) => s.series), ['rally2', 'junior', 'classic', 'sixties', 'rally2']);
  // the series in the order of their next session: under way first for its driver; for the others, the next to
  // register for (rally2's next one, 4 hours on, last)
  assert.deepEqual((await live(f, '/api/liverallies', ANN, H + 5 * MIN)).body.series.map((s) => s.key), ['rally2', 'junior', 'classic', 'sixties']);
  assert.deepEqual((await live(f, '/api/liverallies', BEN, H + 5 * MIN)).body.series.map((s) => s.key), ['junior', 'classic', 'sixties', 'rally2']);
  // one with drivers stays under way after its hour, to its close (as long as a session lasts, longer than the hour)
  const mid = (await live(f, '/api/liverallies', BEN, H + 70 * MIN)).body;
  assert.deepEqual(mid.sessions.filter((x) => x.phase === 'running').map((x) => [x.series, x.starts, x.signups]), [['rally2', H, 1]]);
  assert.ok(!mid.sessions.some((x) => x.phase === 'empty'));
  // past the hour, the overview publishes it too
  const after = (await live(f, '/api/liverallies', ANN, H + 3 * MIN)).body;
  assert.ok(after.sessions.find((x) => x.starts === H).eventId);
  assert.deepEqual(after.recent, []);
  // over: among the ones with results, for a week
  const later = (await live(f, '/api/liverallies', ANN, H + 3 * 3600000)).body;
  assert.deepEqual(later.recent.map((r) => [r.series, r.starts, r.drivers, r.mine, r.eventId]),
    [['rally2', H, 1, true, after.sessions.find((x) => x.starts === H).eventId]]);
  assert.equal((await live(f, '/api/liverallies', BEN, H + 3 * 3600000)).body.recent[0].mine, false);
  assert.equal((await live(f, '/api/liverallies', ANN, H + 6 * 24 * 3600000)).body.recent.length, 1);
  assert.deepEqual((await live(f, '/api/liverallies', ANN, H + 8 * 24 * 3600000)).body.recent, []);
  const off = fakeD1();
  const url = new URL('https://acrdaily.com/api/liverallies');
  const r = await liveApi(new Request(url), off.env, url.pathname, null, H);
  assert.deepEqual((await r.json()).on, false);
});

test('a stage driven outside the rally (practice before the start, the wrong mode): a DNF, before the entry too', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + LIVE.firstStartMs;
  // Ben, not started yet, drives SS2 as a Single Rally Stage at 08:03: out, his entry a DNF with his car
  const r = await live(f, `${S()}/dnf`, BEN, t0 - 2 * MIN, { no: 1, reason: 'SS2 driven before its start' });
  assert.deepEqual(r.body, { status: 'dnf', reason: 'SS2 driven before its start' });
  const e = f.db.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, BEN);
  assert.deepEqual([e.status, e.car, e.done], ['dnf', 'Skoda Fabia RS Rally2', 0]);
  const v = (await live(f, S(), BEN, t0)).body;
  assert.deepEqual([v.queues[0].find((q) => q.name === 'Ben').state, v.me.next], ['dnf', null]);
  assert.equal(v.standings.find((x) => x.steamId === BEN).status, 'dnf');
  // his start after that: refused as a second start would be (the entry is over)
  const again = await league(f, `/api/events/${id}/start`, BEN, t0 + 31000, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: t0 + 30000 });
  assert.equal(again.status, 409);
  // once: an entry already over stays as it is; not in the session: refused
  assert.equal((await live(f, `${S()}/dnf`, BEN, t0, { no: 0, reason: 'again' })).body.reason, 'SS2 driven before its start');
  assert.equal((await live(f, `${S()}/dnf`, ANN, t0, { no: 0 })).status, 403);
  // Cat, under way: her running entry ends the same way
  await league(f, `/api/events/${id}/start`, CAT, t0, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: t0 });
  await live(f, `${S()}/dnf`, CAT, t0 + 3 * MIN, { no: 2, reason: 'SS3 driven before its start' });
  assert.equal(f.db.prepare('SELECT status FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT).status, 'dnf');
});

test('for the testers only: a release app, the website or anyone else is told nothing', async () => {
  const f = world();
  await signUp(f, ANN);
  const ask = async (path, ua, body = null) => {
    const url = new URL('https://acrdaily.com' + path);
    const req = new Request(url, { method: body ? 'POST' : 'GET', headers: ua ? { 'User-Agent': ua } : {},
      ...(body ? { body: JSON.stringify(body) } : {}) });
    const res = await liveApi(req, f.env, url.pathname, player(f.db, BEN), H - 5 * MIN, seeded());
    return { status: res.status, body: await res.json() };
  };
  for (const ua of ['ACR-Daily/0.1.6 public', 'ACR-Daily/0.1.5 public', 'Mozilla/5.0', null]) {
    assert.deepEqual((await ask('/api/liverallies', ua)).body, { now: H - 5 * MIN, on: false, series: [], sessions: [] }, ua);
    assert.equal((await ask(S(), ua)).status, 404, ua);
    assert.equal((await ask(`${S()}/signup`, ua, { car: 'VW Polo GTI R5' })).status, 404, ua);
  }
  assert.equal((await ask('/api/liverallies', 'ACR-Daily/0.1.5.32 public')).body.on, true);     // a test build
  f.env.LIVE_PUBLIC = '1';                                                                        // (opened to all)
  assert.equal((await ask('/api/liverallies', 'ACR-Daily/0.1.6 public')).body.on, true);
});

test('the first session at LIVE_FROM\'s time: every hour from it, Rally2 first (its sessions every 2 hours from before, where they were)', async () => {
  const at = Date.UTC(2026, 10, 17, 17, 30);
  assert.deepEqual(sessionsBetween(at - 30 * 60000, at + 4 * 3600000, at).map((x) => [new Date(x.starts).toISOString().slice(11, 16), x.series.key]),
    [['17:30', 'rally2'], ['18:30', 'junior'], ['19:30', 'classic'], ['20:30', 'sixties'], ['21:30', 'rally2']]);
  assert.equal(seriesAt(at + 2 * 3600000, at).key, 'classic');
  assert.equal(seriesAt(at + 30 * 60000, at), null);
  const f = fakeD1({ LIVE_FROM: '2026-11-17T17:30:00Z' });
  for (const r of ROUTES) f.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, \'[]\', ?, 0, ?)').run(r.track, r.length, r.stage_id);
  f.db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Ann', 0)").run(ANN);
  const ask = async (path, now, body = null) => {
    const url = new URL('https://acrdaily.com' + path);
    const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.5.34 public' },
      ...(body ? { body: JSON.stringify(body) } : {}) });
    const res = await liveApi(req, f.env, url.pathname, player(f.db, ANN), now, seeded());
    return { status: res.status, body: await res.json() };
  };
  const o = (await ask('/api/liverallies', at - 40 * 60000)).body;   // (16:50: the first one, registration from 17:00)
  assert.deepEqual([o.sessions[0].series, o.sessions[0].starts, o.sessions[0].phase], ['rally2', at, 'upcoming']);
  assert.equal((await ask(`/api/liverallies/rally2/${at}/signup`, at - 20 * 60000, { car: 'VW Polo GTI R5' })).status, 200);
  assert.equal((await ask(`/api/liverallies/rally2/${at - 1800000}`, at)).status, 404);   // (off the grid: none)
});
