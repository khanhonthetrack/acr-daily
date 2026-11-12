// Hidden events (src/hidden.js): a league event's weather, times and stage names kept from the drivers until it ends;
// shown to the league's staff, and to a driver once their app asks for them on DRIVE (POST /api/events/:id/reveal).
// On a real SQLite (schema.sql, node:sqlite) through a stand-in for D1.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkHide } from '../src/leagues.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { maskRows, viewHide } from '../src/hidden.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 8, 18, 0);
const [ANN, BEN, CID] = [sid(1), sid(2), sid(3)];   // Ann runs the league, Ben drives in it, Cid is not in it
const STAGES = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' },
  { track: 'Wales Sweet Lamb', day: 1, service: false, weather: 'LightRain', time: '10:00' }];
const ALL = { weather: true, times: true, stages: true };

function world(hide = ALL) {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CID, 'Cid']]) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('pub00001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('pub00001', ?, 0, 'member'), ('pub00001', ?, 0, 'member')").run(ANN, BEN);
  db.prepare(`INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Wales Sweet Lamb', '[[0,0],[1,0]]', 4321.4, 0, NULL),
    ('Wales Afon Biga', '[[0,0],[1,0]]', 9876.2, 0, NULL)`).run();
  const id = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('pub00001', 'Round 1', 'Wales', 'Ford Fiesta Rally2', '{}', ?, ?, ?, 0, ?)`).run(JSON.stringify(STAGES), NOW - 3600000,
    NOW + 86400000, hide ? JSON.stringify(hide) : null).lastInsertRowid;
  // Ann has finished it; she is on the live map just after the finish
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated)
    VALUES (?, ?, 'Ford Fiesta Rally2', 'finished', 2, NULL, 400000, 0, 0)`).run(id, ANN);
  db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, splits, started, created)
    VALUES (?1, ?2, 0, 250000, 0, NULL, 0, 0), (?1, ?2, 1, 150000, 0, NULL, 0, 0)`).run(id, ANN);
  db.prepare(`INSERT INTO event_live (event_id, steam_id, stage_no, x, z, progress, total_ms, state, updated)
    VALUES (?, ?, 1, 5, 6, 1, 400000, 'finished', ?)`).run(id, ANN, NOW - 1000);
  return { ...f, id };
}

const call = async (env, path, me, { post = false, app = null, now = NOW } = {}) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: post ? 'POST' : 'GET', headers: app ? { 'User-Agent': `ACR-Daily/${app} public` } : {},
    ...(post ? { body: '{}' } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, me && { steam_id: me, name: 'x' }, true, now);
  return { status: res.status, body: await res.json() };
};

test('the form: everything hidden unless the maker says otherwise', () => {
  assert.deepEqual(checkHide(undefined), ALL);
  assert.deepEqual(checkHide({ weather: false }), { weather: false, times: true, stages: true });
  assert.equal(checkHide({ weather: false, times: false, stages: false }), null);
  assert.equal(viewHide(ALL, { staff: true }), null);
  assert.deepEqual(viewHide(ALL, { knows: true }), { weather: false, time: false, stages: false, results: true });
});

test('the event page: hidden from a stranger, shown in full to the league\'s owner', async () => {
  const { env, id } = world();
  const out = (await call(env, `/api/events/${id}`, CID)).body;
  assert.deepEqual(out.hidden, ALL);
  assert.equal(out.revealed, false);
  assert.equal(out.lengthM, null);
  assert.deepEqual(out.stages.map((s) => [s.no, s.name, s.track, s.weather, s.time, s.lengthM]),
    [[1, null, null, null, null, null], [2, null, null, null, null, null]]);
  const ann = out.standings.find((r) => r.steamId === ANN);
  assert.equal(ann.status, 'finished');
  assert.equal(ann.totalMs, null);
  assert.equal(ann.rank, null);
  assert.deepEqual(out.stageResults, []);
  const own = (await call(env, `/api/events/${id}`, ANN)).body;          // the owner (and its own time)
  assert.equal(own.revealed, true);
  assert.equal(own.stages[1].name, 'Sweet Lamb');
  assert.equal(own.standings[0].totalMs, 400000);
  assert.equal(own.standings[0].rank, 1);
});

test('the app: masked in the list, in full once DRIVE asks for it; an old app doesn\'t list it', async () => {
  const { env, id, db } = world();
  assert.equal((await call(env, '/api/me/events', BEN, { app: '0.0.24' })).body.events.length, 0);
  const listed = (await call(env, '/api/me/events', BEN, { app: '0.0.25' })).body.events[0];
  assert.equal(listed.revealed, false);
  assert.equal(listed.stages[0].stageId, null);
  assert.equal((await call(env, `/api/events/${id}/reveal`, BEN, { post: true, app: '0.0.24' })).status, 426);
  const full = await call(env, `/api/events/${id}/reveal`, BEN, { post: true, app: '0.0.25' });
  assert.equal(full.status, 200);
  assert.equal(full.body.stages[1].weather, 'LightRain');
  assert.equal(full.body.stages[0].time, '09:00');
  assert.ok(db.prepare('SELECT 1 FROM event_reveals WHERE event_id = ? AND steam_id = ?').get(id, BEN));
  const again = (await call(env, '/api/me/events', BEN, { app: '0.0.25' })).body.events[0];   // (from now on)
  assert.equal(again.revealed, true);
  assert.equal(again.stages[0].track, 'Wales Afon Biga');
  const page = (await call(env, `/api/events/${id}`, BEN)).body;   // the set-up, but still not Ann's time
  assert.equal(page.stages[0].name, 'Afon Biga');
  assert.equal(page.standings[0].totalMs, null);
});

test('over: everything shown; an event made before hidden events shows everything', async () => {
  const { env, id } = world();
  const after = (await call(env, `/api/events/${id}`, CID, { now: NOW + 86400000 + 31 * 60000 })).body;
  assert.equal(after.hidden, null);
  assert.equal(after.stages[0].name, 'Afon Biga');
  assert.equal(after.standings[0].totalMs, 400000);
  const old = world(null);
  const shown = (await call(old.env, `/api/events/${old.id}`, CID)).body;
  assert.equal(shown.hidden, null);
  assert.equal(shown.stages[1].weather, 'LightRain');
  assert.equal((await call(old.env, '/api/me/events', BEN, { app: '0.0.24' })).body.events.length, 1);
});

test('the results kept: by name, only my own time', () => {
  const rows = [{ steamId: 'b', name: 'Zed', status: 'finished', rank: 1, gapMs: 0, totalMs: 1, penaltyMs: 0, stewardMs: 0, stages: [{ timeMs: 1, totalMs: 1, pos: 1, cumPos: 1 }] },
    { steamId: 'a', name: 'Amy', status: 'finished', rank: 2, gapMs: 5, totalMs: 6, penaltyMs: 0, stewardMs: 0, stages: [{ timeMs: 6, totalMs: 6, pos: 2, cumPos: 2 }] }];
  const m = maskRows(rows, 'b');
  assert.deepEqual(m.map((r) => [r.name, r.rank, r.totalMs, r.stages[0].totalMs, r.stages[0].pos]), [['Amy', null, null, null, null], ['Zed', null, 1, 1, null]]);
});

test('a cup: its matches hidden until the whole cup is over (every round races the same stages)', async () => {
  const { cupsApi, cupsTick } = await import('../src/cups.js');
  const { LIMITS } = await import('../src/leagues.js');
  const { env, db } = fakeD1();
  const now0 = Date.UTC(2026, 10, 9, 12, 0);
  const D = [sid(11), sid(12), sid(13), sid(14)];
  D.forEach((s, i) => db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, 'Driver ' + i));
  const spec = { rally: 'Wales', car: 'Ford Fiesta Rally2', car_class: null, rules: {}, hide: ALL,
    stages: [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '12:00' }] };
  db.prepare("INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('hidcup01', 'Mini Cup', ?, 'CODE2346', 0, 'cup')").run(D[0]);
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('hidcup01', 'Mini Cup', ?, 4, 0, '[100]', ?, ?, 24, 'open', 0)`).run(D[0], JSON.stringify(spec), now0 - 1);
  D.forEach((s) => db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('hidcup01', ?, 0, 0)").run(s));
  await cupsTick(env, now0);
  const evs = db.prepare("SELECT id, hide FROM league_events WHERE league_id = 'hidcup01'").all();
  assert.equal(evs.length, 2);
  assert.ok(evs.every((e) => JSON.parse(e.hide).stages), 'every match carries the cup\'s hide');
  const view = async (me, now) => {
    const url = new URL('https://acrdaily.com/api/cups/hidcup01');
    const res = await cupsApi(new Request(url), env, url.pathname, me && { steam_id: me }, true, now,
      { json: (d) => new Response(JSON.stringify(d)), err: (m, s = 400) => new Response(JSON.stringify({ error: m }), { status: s }) });
    return res.json();
  };
  const stranger = await view(sid(99), now0 + 1000);
  assert.equal(stranger.revealed, false);
  assert.deepEqual([stranger.stages[0].name, stranger.stages[0].weather, stranger.stages[0].time], [null, null, null]);
  assert.equal((await view(D[0], now0 + 1000)).stages[0].name, 'Afon Biga');   // (its maker)
  // round 1 closes: still hidden (round 2 races the same); the final closes: shown to everyone
  let now = now0;
  for (let round = 1; round <= 2; round++) {
    now += 25 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'hidcup01'").run(now - LIMITS.graceMs - 1);
    await cupsTick(env, now);
    if (round === 1) assert.equal((await view(sid(99), now)).revealed, false);
  }
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'hidcup01'").get().status, 'finished');
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM league_events WHERE league_id = 'hidcup01' AND hide IS NOT NULL").get().n, 0);
  const over = await view(sid(99), now);
  assert.equal(over.hidden, null);
  assert.equal(over.stages[0].name, 'Afon Biga');
});

test('a cup that draws each round\'s stages: a round over, its stage names and weather shown; the times until the cup is over', async () => {
  const { cupsApi, cupsTick } = await import('../src/cups.js');
  const { LIMITS } = await import('../src/leagues.js');
  const { env, db } = fakeD1();
  for (const id of ['S2MunsterFullForward', 'S2MunsterFullReverse', 'S2MunsterShort1Forward', 'S2MunsterShort1Reverse', 'S4SaverneFullForward',
    'S4SaverneFullReverse']) db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, '[]', 6000, 0, ?)").run(`Alsace ${id}`, `Alsace${id}`);
  const now0 = Date.UTC(2026, 10, 22, 18, 0);
  const D = Array.from({ length: 8 }, (_, i) => sid(30 + i));
  D.forEach((s, i) => db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, 'Driver ' + i));
  const slot = (time) => ({ track: 'Alsace S2MunsterFullForward', day: 1, service: false, weather: 'Clear', time });
  const spec = { rally: 'Alsace', car: 'Mini Cooper S 1275', car_class: null, rules: {}, hide: ALL, stages: [slot('09:00'), slot('13:00')],
    draw: { maxKm: 40 } };
  db.prepare("INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('drawcup1', 'Mini', 'acr-daily', 'CODE4567', 0, 'cup')").run();
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created, official)
    VALUES ('drawcup1', 'Mini', 'acr-daily', 8, 0, '[100]', ?, ?, 168, 'open', 0, 1)`).run(JSON.stringify(spec), now0);
  D.forEach((s) => db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('drawcup1', ?, 0, 0)").run(s));
  await cupsTick(env, now0);
  const view = async (now) => {
    const url = new URL('https://acrdaily.com/api/cups/drawcup1');
    const res = await cupsApi(new Request(url), env, url.pathname, { steam_id: sid(99) }, true, now,
      { json: (d) => new Response(JSON.stringify(d)), err: (m, s = 400) => new Response(JSON.stringify({ error: m }), { status: s }) });
    return res.json();
  };
  const hideOfRound = (r) => db.prepare(`SELECT DISTINCT e.hide FROM cup_matches m JOIN league_events e ON e.id = m.event_id
    WHERE m.cup_id = 'drawcup1' AND m.round = ?`).all(r).map((x) => JSON.parse(x.hide));
  let v = await view(now0 + 1000);
  assert.equal(v.byRound, true);
  assert.deepEqual(v.roundStages[0].stages.map((s) => [s.name, s.weather, s.time]), [[null, null, null], [null, null, null]], 'round 1 under way: hidden');
  // round 1 over: its names and weather for everyone (round 2 draws its own); its times, and round 2, still hidden
  const now1 = now0 + 169 * 3600000;
  db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'drawcup1'").run(now1 - LIMITS.graceMs - 1);
  assert.deepEqual((await cupsTick(env, now1)).map((d) => d.did), ['round 2']);
  assert.deepEqual(hideOfRound(1), [{ weather: false, times: true, stages: false }]);
  assert.deepEqual(hideOfRound(2), [ALL]);
  v = await view(now1 + 1000);
  const [r1, r2] = v.roundStages;
  assert.ok(r1.stages.every((s) => s.name && s.weather && s.time === null), `round 1 shown, its times not: ${JSON.stringify(r1.stages)}`);
  assert.ok(r2.stages.every((s) => s.name === null && s.weather === null && s.time === null), 'round 2 still hidden');
  assert.equal(v.revealed, false);
  // a cup racing the same stages every round: nothing shown before the end (the test above)
});
