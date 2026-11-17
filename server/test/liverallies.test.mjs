// Live rallies (src/liverallies.js) on a real SQLite (schema.sql, node:sqlite): the two series in turn every 2 hours,
// sign-up in the 30 minutes before the hour, the rally drawn and the start list published once at the hour, SS1 every
// 30 s from the hour + 5 minutes, the queues of the later stages, the late sent to the end, the early given the seconds
// they jumped, and the session driven through the leagues' own start / begin / stage.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { drawSession, gridUp, LIVE, liveApi, phaseOf, publish, rallyOfWeek, SERIES, seriesAt, sessionsBetween } from '../src/liverallies.js';
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

test('the schedule: a session every 2 hours, the series in turn; one country a week each, never the same', () => {
  assert.equal(seriesAt(H).key, 'rally2');
  assert.equal(seriesAt(H + 2 * 3600000).key, 'classic');
  assert.equal(seriesAt(H + 4 * 3600000).key, 'rally2');
  assert.equal(seriesAt(H + 3600000), null);                      // (odd hours: none)
  const day = sessionsBetween(Date.UTC(2026, 10, 18), Date.UTC(2026, 10, 18, 23, 59));
  assert.equal(day.length, 12);
  assert.deepEqual(day.filter((x) => x.series.key === 'rally2').map((x) => new Date(x.starts).getUTCHours()), [0, 4, 8, 12, 16, 20]);
  assert.deepEqual(day.filter((x) => x.series.key === 'classic').map((x) => new Date(x.starts).getUTCHours()), [2, 6, 10, 14, 18, 22]);
  for (let w = 0; w < 4; w++) {
    const t = H + w * 7 * 86400000;
    assert.notEqual(rallyOfWeek(SERIES[0], t), rallyOfWeek(SERIES[1], t));
  }
  assert.equal(rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 16)), rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 22, 23)));   // Monday to Sunday
  assert.notEqual(rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 16)), rallyOfWeek(SERIES[0], Date.UTC(2026, 10, 23)));
  assert.deepEqual([phaseOf(H, H - 31 * MIN), phaseOf(H, H - 30 * MIN), phaseOf(H, H), phaseOf(H, H + 105 * MIN)],
    ['upcoming', 'signup', 'running', 'over']);
  assert.equal(gridUp(H + 1), H + 30000);
  assert.equal(gridUp(H + 30000), H + 30000);
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
  assert.equal((await live(f, `${S()}/signup`, null, H - 5 * MIN, { car: 'VW Polo GTI R5' })).status, 401);
  const w = await live(f, `${S()}/withdraw`, ANN, H - 5 * MIN, {});
  assert.deepEqual([w.body.me.signedUp, w.body.entrants.length], [false, 0]);
  assert.equal((await signUp(f, ANN, 'VW Polo GTI R5', H)).status, 409);                   // (closed at the hour)
  assert.equal((await live(f, `/api/liverallies/classic/${H}`, ANN, H - 5 * MIN)).status, 404);   // (08:00 is Rally2's)
  const holder = f.db.prepare("SELECT * FROM leagues WHERE id = 'liverly2'").get();
  assert.deepEqual([holder.kind, holder.public, holder.owner], ['live', 0, 'acr-daily']);
});

test('at the hour: the rally drawn once, the start list by rating, SS1 every 30 s from 5 minutes on', async () => {
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
  assert.deepEqual(a.body.queues[0].map((q) => [q.name, q.at - H, q.state]),
    [['Cat', 5 * MIN, 'waiting'], ['Ben', 5 * MIN + 30000, 'waiting'], ['Dan', 5 * MIN + 60000, 'waiting'], ['Ann', 5 * MIN + 90000, 'waiting']]);
  assert.deepEqual(a.body.me.next, { no: 0, at: H + 5 * MIN + 90000, moved: 0, started: null, penaltyMs: 0, out: null });
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

async function published(f) {
  for (const [who, at] of [[CAT, 20], [BEN, 15]]) await signUp(f, who, 'Skoda Fabia RS Rally2', H - at * MIN);
  return (await live(f, S(), CAT, H + 1000)).body.eventId;      // Cat 08:05:00, Ben 08:05:30
}

test('starts: on time counts as it is; early, the seconds jumped are added to the stage', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + 5 * MIN;
  const cat = await league(f, `/api/events/${id}/start`, CAT, t0 + 1500, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: t0 + 1200 });
  assert.equal(cat.status, 200, JSON.stringify(cat.body));
  assert.deepEqual(cat.body.slot, { slotAt: t0, startedAt: t0 + 1200, penaltyMs: 0, late: false });
  const ben = await league(f, `/api/events/${id}/start`, BEN, t0 + 19000, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: t0 + 18200 });
  assert.equal(ben.body.slot.penaltyMs, 12000);                 // 08:05:18.2 for 08:05:30: 11.8 s early, 12 s
  const pen = f.db.prepare('SELECT * FROM league_penalties WHERE event_id = ?').all(id);
  assert.deepEqual(pen.map((p) => [p.steam_id, p.stage_no, p.ms, p.by]), [[BEN, 0, 12000, 'acr-daily']]);
  assert.match(pen[0].reason, /jump start: SS1 started 12 s before its slot \(08:05:30 UTC\)/);
  const v = (await live(f, S(), BEN, t0 + 20000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.penaltyMs]), [['Cat', 'driving', 0], ['Ben', 'driving', 12000]]);
  assert.equal(v.me.next, null);
  // in the standings: on the stage, as a steward's penalty
  await league(f, `/api/events/${id}/stage`, BEN, t0 + 7 * MIN, { no: 0, timeMs: 360000, penaltyMs: 0 });
  const row = v.standings.length ? (await live(f, S(), BEN, t0 + 7 * MIN)).body.standings.find((r) => r.steamId === BEN) : null;
  assert.deepEqual([row.stages[0].stewardMs, row.stages[0].totalMs], [12000, 372000]);
  // the same start sent again (the app's queue retried): no second penalty
  await league(f, `/api/events/${id}/start`, BEN, t0 + 25000, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: t0 + 18200 });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_penalties').get().n, 1);
});

test('late: sent to the end of the queue, no penalty; missed too often, out', async () => {
  const f = world();
  for (const [who, at] of [[CAT, 20], [BEN, 15], [ANN, 10]]) await signUp(f, who, 'Skoda Fabia RS Rally2', H - at * MIN);
  const id = (await live(f, S(), CAT, H + 1000)).body.eventId;
  const t0 = H + 5 * MIN;                                       // Cat 08:05:00, Ben 08:05:30, Ann 08:06:00
  await league(f, `/api/events/${id}/start`, BEN, t0 + 30500, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: t0 + 30200 });
  // Cat never starts: past 08:05:50 (the window and its grace) she goes after Ann, at least a minute on
  let v = (await live(f, S(), ANN, t0 + 51000)).body;
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.at - t0, q.moved, q.state]),
    [['Ben', 30000, 0, 'driving'], ['Ann', 60000, 0, 'waiting'], ['Cat', 120000, 1, 'waiting']]);
  // a start inside the window's grace still counts, late, without a penalty
  const ann = await league(f, `/api/events/${id}/start`, ANN, t0 + 101000, { car: 'Skoda Fabia RS Rally2', at: 3, serverAt: t0 + 100000 });
  assert.deepEqual([ann.body.slot.late, ann.body.slot.penaltyMs], [true, 0]);
  // Cat misses 08:07:00, then twice more: out (did not start)
  let t = t0 + 120000;
  for (let k = 1; k <= LIVE.maxMoves; k++) {
    const row = f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND steam_id = ?').get(id, CAT);
    t = row.slot_at + LIVE.windowMs + LIVE.graceMs + 1000;
    v = (await live(f, S(), CAT, t)).body;
  }
  const cat = v.queues[0].find((q) => q.name === 'Cat');
  assert.deepEqual([cat.state, cat.moved], ['dns', LIVE.maxMoves]);
  assert.equal(v.me.next, null);
  assert.equal(v.me.out.out, 'dns');
  // out is out: a start made after that is refused (the app stops following the session), and no entry is made
  const late = await league(f, `/api/events/${id}/start`, CAT, t + 1000, { car: 'Skoda Fabia RS Rally2', at: 9, serverAt: t + 500 });
  assert.deepEqual([late.status, late.body.status], [200, 'dnf']);
  assert.match(late.body.reason, /did not start: missed the start 4 times/);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_entries WHERE steam_id = ?').get(CAT).n, 0);
});

test('a start on its way while the slot moves: judged against the slot it had then', async () => {
  const f = world();
  const id = await published(f);                                // Cat 08:05:00, Ben 08:05:30
  const t0 = H + 5 * MIN;
  await live(f, S(), BEN, t0 + 51000);                          // Cat moved to the end (her start not in yet)
  const moved = f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND steam_id = ?').get(id, CAT);
  assert.deepEqual([moved.moved, moved.prev_at, moved.moved_at], [1, t0, t0 + 51000]);
  // ...it was made at 08:05:10, on time, and comes in now: no jump start against her new slot
  const r = await league(f, `/api/events/${id}/start`, CAT, t0 + 70000, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: t0 + 10000 });
  assert.deepEqual(r.body.slot, { slotAt: t0, startedAt: t0 + 10000, penaltyMs: 0, late: false });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_penalties').get().n, 0);
  // out of the queue the same way: a start made before that still counts
  const g = world();
  const id2 = await published(g);
  let t = t0;
  for (let k = 0; k <= LIVE.maxMoves; k++) {
    const row = g.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND steam_id = ?').get(id2, CAT);
    t = row.slot_at + LIVE.windowMs + LIVE.graceMs + 1000;
    await live(g, S(), BEN, t);
  }
  const out = g.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND steam_id = ?').get(id2, CAT);
  assert.equal(out.out, 'dns');
  const inTime = await league(g, `/api/events/${id2}/start`, CAT, t + 5000, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: out.prev_at + 3000 });
  assert.deepEqual([inTime.body.status, inTime.body.slot.penaltyMs], ['running', 0]);
});

test('a later stage: a begin on its way when the queue made the entry a DNF undoes it', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + 5 * MIN;
  await league(f, `/api/events/${id}/start`, CAT, t0, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: t0 });
  const fin = t0 + 6 * MIN;
  const slot = (await live(f, `${S()}/queue`, CAT, fin + 300, { no: 1, finishedAt: fin })).body.slot;
  await league(f, `/api/events/${id}/stage`, CAT, fin + 40000, { no: 0, timeMs: 360000, penaltyMs: 0 });
  let t = slot.at;
  for (let k = 0; k <= LIVE.maxMoves; k++) {                    // SS2 never seen starting: out, a DNF
    const row = f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = 1 AND steam_id = ?').get(id, CAT);
    t = row.slot_at + LIVE.windowMs + LIVE.graceMs + 1000;
    await live(f, S(), BEN, t);
  }
  const row = f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = 1 AND steam_id = ?').get(id, CAT);
  assert.equal(f.db.prepare('SELECT status FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT).status, 'dnf');
  // a start made later than that: still a DNF
  const no = await league(f, `/api/events/${id}/begin`, CAT, t + 2000, { no: 1, at: 5, serverAt: t + 1000 });
  assert.equal(no.body.status, 'dnf');
  // one made before it (on its last slot, its start still on its way): the DNF undone, the stage on
  const yes = await league(f, `/api/events/${id}/begin`, CAT, t + 3000, { no: 1, at: 6, serverAt: row.prev_at + 2000 });
  assert.deepEqual([yes.body.status, yes.body.slot.penaltyMs], ['running', 0]);
  const e = f.db.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT);
  assert.deepEqual([e.status, e.reason, e.on_stage], ['running', null, 1]);
});

test('publishing taken over after a stall makes no second event', async () => {
  const f = world();
  const id = await published(f);
  f.db.prepare('UPDATE live_sessions SET event_id = NULL, created = ?').run(H - MIN);   // (as if it had stalled)
  assert.equal(await publish(f.env, SERIES[0], H, H + 2 * MIN, seeded(3)), id);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_events').get().n, 1);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM live_slots WHERE stage_no = 0').get().n, 2);
});

test('the later stages: a queue in finishing order, 2 minutes on at least, on the 30-s grid', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + 5 * MIN;
  await league(f, `/api/events/${id}/start`, CAT, t0, { car: 'Skoda Fabia RS Rally2', at: 1, serverAt: t0 });
  await league(f, `/api/events/${id}/start`, BEN, t0 + 30000, { car: 'Skoda Fabia RS Rally2', at: 2, serverAt: t0 + 30000 });
  assert.equal((await live(f, `${S()}/queue`, CAT, t0 + 1000, { no: 2 })).status, 409);         // (SS2 not driven)
  // Ben finishes SS1 first (08:11:10), Cat just after (08:11:12): Ben 08:13:30, Cat 08:14:00
  const fin = t0 + 6 * MIN + 10000;
  const qb = await live(f, `${S()}/queue`, BEN, fin + 300, { no: 1, finishedAt: fin });
  assert.equal(qb.status, 200, JSON.stringify(qb.body));
  assert.equal(qb.body.slot.at, gridUp(fin + LIVE.turnaroundMs));
  const qc = await live(f, `${S()}/queue`, CAT, fin + 2500, { no: 1, finishedAt: fin + 2000 });
  assert.equal(qc.body.slot.at, qb.body.slot.at + 30000);
  assert.equal((await live(f, `${S()}/queue`, CAT, fin + 9000, { no: 1, finishedAt: fin + 8000 })).body.slot.at, qc.body.slot.at);   // (once)
  // the official times, then SS2's starts through begin: Cat 3 s late is on time... inside the window
  for (const who of [BEN, CAT]) {
    const s = await league(f, `/api/events/${id}/stage`, who, fin + 40000, { no: 0, timeMs: 370000, penaltyMs: 0 });
    assert.equal(s.status, 200, JSON.stringify(s.body));
  }
  const bb = await league(f, `/api/events/${id}/begin`, BEN, qb.body.slot.at + 1000, { no: 1, at: 5, serverAt: qb.body.slot.at + 800 });
  assert.deepEqual([bb.status, bb.body.slot.penaltyMs, bb.body.slot.late], [200, 0, false]);
  const q0 = f.count.queries;
  const v = (await live(f, S(), CAT, qb.body.slot.at + 2000)).body;
  assert.ok(f.count.queries - q0 <= 15, `a session's view: ${f.count.queries - q0} queries`);   // (the free plan: 50 a request)
  assert.deepEqual(v.queues[1].map((q) => [q.name, q.state]), [['Ben', 'driving'], ['Cat', 'waiting']]);
  assert.deepEqual(v.queues[0].map((q) => [q.name, q.state, q.timeMs]), [['Cat', 'done', 370000], ['Ben', 'done', 370000]]);
  assert.equal(v.me.next.no, 1);
  // Cat never starts SS2: moved on, and after the last move a DNF
  let t = qc.body.slot.at;
  for (let k = 0; k <= LIVE.maxMoves; k++) {
    const row = f.db.prepare('SELECT * FROM live_slots WHERE event_id = ? AND stage_no = 1 AND steam_id = ?').get(id, CAT);
    t = row.slot_at + LIVE.windowMs + LIVE.graceMs + 1000;
    await live(f, S(), BEN, t);
  }
  const entry = f.db.prepare('SELECT * FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, CAT);
  assert.deepEqual([entry.status, entry.reason], ['dnf', 'did not start SS2']);
});

test('the overview: the series, their sessions with sign-ups; off without LIVE_FROM', async () => {
  const f = world();
  await signUp(f, ANN);
  const o = (await live(f, '/api/liverallies', ANN, H - 10 * MIN)).body;
  assert.equal(o.on, true);
  assert.deepEqual(o.series.map((s) => [s.key, s.carClass, s.cars.length]), [['rally2', 'Rally2/R5', 3], ['classic', 'H1', 3]]);
  const first = o.sessions[0];
  assert.deepEqual([first.series, first.starts, first.phase, first.signups, first.signedUp, first.car],
    ['rally2', H, 'signup', 1, true, 'Skoda Fabia RS Rally2']);
  assert.deepEqual(o.sessions.slice(0, 3).map((s) => s.series), ['rally2', 'classic', 'rally2']);
  // past the hour, the overview publishes it too
  const after = (await live(f, '/api/liverallies', ANN, H + 3 * MIN)).body;
  assert.ok(after.sessions[0].eventId);
  const off = fakeD1();
  const url = new URL('https://acrdaily.com/api/liverallies');
  const r = await liveApi(new Request(url), off.env, url.pathname, null, H);
  assert.deepEqual((await r.json()).on, false);
});

test('a stage driven outside the rally (practice before the start, the wrong mode): a DNF, before the entry too', async () => {
  const f = world();
  const id = await published(f);
  const t0 = H + 5 * MIN;
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

test('a session never draws the dailies\' or the time trial\'s stages when its country has others', () => {
  const rally = rallyOfWeek(SERIES[0], H);
  const own = ROUTES.filter((r) => r.track.startsWith(rally));
  const avoid = new Set(own.slice(0, 4).map((r) => r.track));          // (more than a day's dailies and a week's TT)
  for (let seed = 1; seed <= 25; seed++) {
    const v = drawSession(SERIES[0], H, ROUTES, seeded(seed), avoid);
    assert.equal(v.rally, rally);
    assert.ok(v.stages.every((st) => !avoid.has(st.track)), `seed ${seed}: ${v.stages.map((st) => st.track)}`);
  }
  // all of them to avoid: drawn all the same (avoided ones last), never no rally
  const all = drawSession(SERIES[0], H, ROUTES, seeded(2), new Set(own.map((r) => r.track)));
  assert.deepEqual([all.rally, all.stages.length], [rally, 3]);
});

test('publishing asks which stages to avoid', async () => {
  const f = world();
  await signUp(f, ANN);
  const own = ROUTES.filter((r) => r.track.startsWith(rallyOfWeek(SERIES[0], H)));
  const asked = [];
  const avoid = async (starts) => { asked.push(starts); return new Set(own.slice(0, 5).map((r) => r.track)); };
  const url = new URL(`https://acrdaily.com${S()}`);
  const res = await liveApi(new Request(url), f.env, url.pathname, player(f.db, ANN), H + 1000, seeded(4), { avoid });
  const ev = (await res.json()).event;
  assert.deepEqual(asked, [H]);
  assert.ok(ev.stages.every((st) => !own.slice(0, 5).some((r) => r.track === st.track)));
});

test('the stages to avoid: the session day\'s dailies, the day before\'s and the week\'s time trial', async () => {
  const { liveDeps } = await import('../src/index.js');
  const f = world();
  for (const r of ROUTES.slice(0, 12)) f.db.prepare("INSERT INTO pool (track, car, enabled) VALUES (?, '*', 1)").run(r.track);
  f.db.prepare("INSERT INTO schedule (date, slot, track, car) VALUES ('2026-11-18', 1, ?, 'Peugeot 208 Rally4')").run(ROUTES[20].track);
  f.db.prepare("INSERT INTO tt_schedule (week, slot, track, car) VALUES ('2026-11-16', 1, ?, 'Lancia Stratos HF')").run(ROUTES[30].track);
  const avoid = await liveDeps(f.env).avoid(H);
  assert.ok(avoid.has(ROUTES[20].track));                     // today's SS1, set by hand
  assert.ok(avoid.has(ROUTES[30].track));                     // the week's TT1
  assert.ok(avoid.size >= 5, [...avoid].join(', '));          // + today's SS2 and the day before's two, from the pool
});
