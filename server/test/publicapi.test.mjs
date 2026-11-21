// The public API (/api/v1, src/publicapi.js): through the whole worker, on a real SQLite (schema.sql, node:sqlite) through
// a stand-in for D1. What a championship's organizers read to put its results on their own page: exactly what the
// website shows anyone (a private championship too: readable by its link), a private rally's results with its code, a
// hidden event's results not before it closes; JSON and CSV, every origin, kept at the edge for a while.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';
import { csv, fmtMs } from '../src/publicapi.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const STAGE = (track, day, time) => ({ track, day, service: true, weather: 'Clear', time });
const STAGES = [STAGE('Wales Afon Biga', 1, '09:00'), STAGE('Wales Cwmbiga', 1, '13:00')];

function seed() {
  const { env, db } = fakeD1();
  Object.assign(env, { SITE_URL: 'https://acrdaily.test' });
  const now = Date.now();
  for (const [i, name, cc] of [[1, 'Ann', 'pl'], [2, 'Bob', 'gb'], [3, 'Cid', 'fr']]) {
    db.prepare('INSERT INTO players (steam_id, name, country, created) VALUES (?, ?, ?, 0)').run(sid(i), name, cc);
  }
  for (const [track, len] of [['Wales Afon Biga', 6100], ['Wales Cwmbiga', 4300]]) {
    db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, 0, ?)")
      .run(track, JSON.stringify([[0, 0], [100, 50], [200, 80]]), len, track === 'Wales Afon Biga' ? 'WelesS4HafrenSouthFullForward' : 'WelesS3HafrenNorthFullForward');
  }
  // a private championship (by application): readable by its link, as on the website
  db.prepare(`INSERT INTO leagues (id, name, about, owner, public, code, created, kind) VALUES ('champ001', 'Club Rally', 'Fridays', ?, 0, 'CHAMPAAA', 0, 'league')`).run(sid(1));
  for (const i of [1, 2, 3]) db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('champ001', ?, 0, 'member')").run(sid(i));
  const season = db.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created) VALUES ('champ001', 'Season 1',
    '{"table":[25,18,15],"finisher":1}', '[]', 0, 0)`).run().lastInsertRowid;
  const ev = (name, opens, closes, hide = null) => db.prepare(`INSERT INTO league_events (league_id, season_id, name, rally, car, rules, stages, opens,
    closes, created, hide) VALUES ('champ001', ?, ?, 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0, ?)`)
    .run(season, name, JSON.stringify(STAGES), opens, closes, hide ? JSON.stringify(hide) : null).lastInsertRowid;
  const done = ev('Round 1', now - 72 * H, now - 24 * H);
  const hidden = ev('Round 2', now - 2 * H, now + 48 * H, { times: true, weather: false, stages: false });
  const drive = (e, i, times, status = 'finished') => {
    db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, total_ms, started, updated) VALUES (?, ?, 'Skoda Fabia RS Rally2', ?, ?, ?, 0, 0)`)
      .run(e, sid(i), status, times.length, times.reduce((a, t) => a + t, 0));
    times.forEach((t, k) => db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, created) VALUES (?, ?, ?, ?, 0, 0)`)
      .run(e, sid(i), k, t));
  };
  drive(done, 1, [200000, 150000]);
  drive(done, 2, [201000, 152500]);
  drive(done, 3, [210000], 'dnf');
  drive(hidden, 2, [190000, 140000]);              // (Bob leads the hidden round: nobody may know yet)
  // a private rally (its code: its password)
  db.prepare(`INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('rally001', 'Secret rally', ?, 0, 'K7Q2M9XP', 0, 'event')`).run(sid(2));
  const rally = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created)
    VALUES ('rally001', 'Secret rally', 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0)`).run(JSON.stringify(STAGES), now - 72 * H, now - 24 * H).lastInsertRowid;
  drive(rally, 3, [199000, 149000]);
  return { env, db, done, hidden, rally, season };
}

const get = async (env, path, init = {}) => {
  const res = await worker.fetch(new Request('https://acrdaily.test' + path, init), env, { waitUntil() {} });
  const type = res.headers.get('Content-Type') || '';
  return { res, status: res.status, body: type.includes('json') ? await res.json() : await res.text() };
};

test('what there is, and only reading', async () => {
  const { env } = seed();
  const r = await get(env, '/api/v1');
  assert.equal(r.status, 200);
  assert.equal(r.body.version, 1);
  assert.ok(r.body.endpoints.includes('https://acrdaily.test/api/v1/events/{id}'));
  assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), '*');
  assert.match(r.res.headers.get('Cache-Control'), /public, max-age=\d+/);
  assert.equal((await get(env, '/api/v1/nothing')).status, 404);
  assert.equal((await get(env, '/api/v1/events/1', { method: 'POST' })).status, 405);
});

test('a championship: its events, the winner of a round over, none named for a hidden round still running', async () => {
  const { env, done, hidden } = seed();
  const r = await get(env, '/api/v1/championships/champ001');
  assert.equal(r.status, 200);
  assert.equal(r.body.private, true);
  assert.equal(r.body.url, 'https://acrdaily.test/l/champ001');
  assert.deepEqual(r.body.members.map((m) => m.name).sort(), ['Ann', 'Bob', 'Cid']);
  const byId = Object.fromEntries(r.body.events.map((e) => [e.id, e]));
  assert.equal(byId[done].winner, 'Ann');
  assert.equal(byId[hidden].winner, null, 'the hidden round\'s leader is not told while it runs');
  // the internal page's endpoint too (the leak, 21 Nov 2026)
  const raw = await get(env, '/api/leagues/champ001');
  assert.equal(raw.body.events.find((e) => e.id === hidden).winner, null);
  const list = await get(env, '/api/v1/championships');
  assert.ok(list.body.championships.some((c) => c.id === 'champ001' && c.private));
});

test('the season\'s table, JSON and CSV; a hidden round counts only once it is over', async () => {
  const { env, done, season } = seed();
  const r = await get(env, `/api/v1/championships/champ001/standings?season=${season}`);
  assert.equal(r.status, 200);
  const s = r.body.seasons[0];
  assert.deepEqual(s.drivers.map((d) => [d.rank, d.name, d.points]), [[1, 'Ann', 25], [2, 'Bob', 18], [3, 'Cid', 0]]);
  assert.equal(s.drivers[2].events[done].dnf, true);
  const c = await get(env, `/api/v1/championships/champ001/standings?season=${season}&format=csv`);
  assert.match(c.res.headers.get('Content-Type'), /text\/csv/);
  const lines = c.body.replace(/^﻿/, '').trim().split('\r\n');
  assert.equal(lines[0], 'Pos,Driver,Country,Team,Points,Wins,Finished,Round 1,Round 2');
  assert.equal(lines[1], '1,Ann,PL,,25,1,1,25,');
  assert.equal((await get(env, '/api/v1/championships/champ001/standings?season=999')).status, 404);
});

test('an event\'s results: times by stage, CSV; a hidden one\'s times kept until it closes', async () => {
  const { env, done, hidden } = seed();
  const r = await get(env, `/api/v1/events/${done}`);
  assert.equal(r.status, 200);
  assert.equal(r.body.holder.kind, 'championship');
  assert.deepEqual(r.body.stages.map((s) => [s.no, s.track, s.lengthM, s.time]), [[1, 'Wales Afon Biga', 6100, '09:00'], [2, 'Wales Cwmbiga', 4300, '13:00']]);
  assert.ok(r.body.stages.every((s) => typeof s.name === 'string' && s.name.length));
  const [ann, bob, cid] = r.body.results;
  assert.deepEqual([ann.rank, ann.name, ann.totalMs, ann.stages.map((s) => s.timeMs)], [1, 'Ann', 350000, [200000, 150000]]);
  assert.deepEqual([bob.rank, bob.gapMs], [2, 3500]);
  assert.equal(cid.status, 'dnf');
  const c = await get(env, `/api/v1/events/${done}?format=csv`);
  const lines = c.body.replace(/^﻿/, '').trim().split('\r\n');
  assert.equal(lines[0], 'Pos,Driver,Country,Team,Car,Class,Division,Status,Total,Gap,Total (ms),SS1,SS2,Game penalties (ms),Steward (ms)');
  assert.ok(lines[1].startsWith('1,Ann,PL,,Skoda Fabia RS Rally2,'), lines[1]);
  assert.ok(lines[2].includes(',+0:03.500,'), lines[2]);
  const h = await get(env, `/api/v1/events/${hidden}`);
  assert.equal(h.status, 200);
  assert.ok(h.body.hidden && h.body.hidden.times);
  assert.ok(h.body.results.every((x) => x.totalMs == null && x.rank == null), 'no times, no order while it runs');
});

test('a private rally: its results only with its code', async () => {
  const { env, rally } = seed();
  const locked = await get(env, `/api/v1/events/${rally}`);
  assert.equal(locked.status, 200);
  assert.equal(locked.body.locked, true);
  assert.deepEqual(locked.body.results, []);
  assert.equal((await get(env, `/api/v1/events/${rally}?code=ABCD-EFGH`)).body.locked, true);
  const open = await get(env, `/api/v1/events/${rally}?code=k7q2-m9xp`);
  assert.equal(open.body.locked, false);
  assert.deepEqual(open.body.results.map((x) => [x.name, x.totalMs]), [['Cid', 348000]]);
  assert.equal((await get(env, `/api/v1/events/${rally}/live`)).status, 404);
  assert.equal((await get(env, `/api/v1/events/${rally}/live?code=K7Q2M9XP`)).status, 200);
});

test('live timing and the map\'s lines', async () => {
  const { env, done } = seed();
  const live = await get(env, `/api/v1/events/${done}/live`);
  assert.equal(live.status, 200);
  assert.deepEqual(live.body.drivers, []);
  assert.equal(live.body.stages.length, 2);
  assert.ok(live.body.pollSeconds >= 5);
  const map = await get(env, `/api/v1/events/${done}/map`);
  assert.equal(map.status, 200);
  // (its length along its points: 100,50 then 100,30 from the start: 111.8 + 104.4)
  assert.deepEqual(map.body.stages.map((s) => [s.no, s.lengthM, s.points.length]), [[1, 216, 3], [2, 216, 3]]);
});

test('the other tables answer: ranking (CSV too), a driver, a day\'s dailies, a week\'s time trials, a cup', async () => {
  const { env, db } = seed();
  db.prepare('INSERT INTO ratings (steam_id, rating, races, peak, updated) VALUES (?, 1712.4, 9, 1750, 0)').run(sid(1));
  const rk = await get(env, '/api/v1/ranking');
  assert.equal(rk.status, 200);
  assert.deepEqual(rk.body.rows.map((x) => [x.rank, x.name, x.rating]), [[1, 'Ann', 1712]]);
  // (text() drops the byte-order mark the CSV starts with: csv() keeps it, below)
  assert.match((await get(env, '/api/v1/ranking?format=csv')).body, /^﻿?Rank,Driver,Country,Team,Rating,Races,Peak\r\n1,Ann,PL,,1712,9,1750\r\n$/);
  const d = await get(env, `/api/v1/drivers/${sid(1)}`);
  assert.equal(d.status, 200);
  assert.equal(d.body.name, 'Ann');
  assert.equal(d.body.url, `https://acrdaily.test/d/${sid(1)}`);
  assert.equal((await get(env, '/api/v1/dailies')).status, 200);
  assert.equal((await get(env, '/api/v1/dailies/2026-11-20/1')).status, 200);
  assert.equal((await get(env, '/api/v1/timetrials')).status, 200);
  assert.equal((await get(env, '/api/v1/cups/nocup001')).status, 404);
});

test('CSV and time helpers', () => {
  assert.equal(fmtMs(350000), '5:50.000');
  assert.equal(fmtMs(3500), '0:03.500');
  assert.equal(fmtMs(3723456), '1:02:03.456');
  assert.equal(fmtMs(null), '');
  assert.equal(csv([['a', 'b,c', 'say "hi"', '=SUM(A1)', '+0:03.500', '-cmd']]), '﻿a,"b,c","say ""hi""","\'=SUM(A1)",+0:03.500,"\'-cmd"\r\n');
});
