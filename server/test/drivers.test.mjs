// Driver pages, names, pictures, teams (src/drivers.js) and the rating with its results (src/rating.js): the rules,
// then the API and the cron's step on a real SQLite (test/faked1.mjs).
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkAvatar, checkName, checkTeam, driversApi, nameKey } from '../src/drivers.js';
import { cupMatchStmts, racePlaces, raceDeltas, RATING, resultsTick, takeDaily } from '../src/rating.js';
import { lookOfRow } from '../src/shop.js';
import { fakeD1, sid } from './faked1.mjs';

const fin = (steamId, totalMs) => ({ steamId, status: 'finished', totalMs, gapMs: 0, runId: 1 });
const dnf = (steamId) => ({ steamId, status: 'dnf', totalMs: null });

test('a race\'s places: by time, equal times share a place, every DNF last together', () => {
  assert.deepEqual(racePlaces([fin('b', 200), dnf('x'), fin('a', 100), fin('c', 200), dnf('y')]),
    [{ steamId: 'a', pos: 1 }, { steamId: 'b', pos: 2 }, { steamId: 'c', pos: 2 }, { steamId: 'x', pos: 4 }, { steamId: 'y', pos: 4 }]);
});

test('the rating: beating the field gains, equal ratings and places change nothing, new drivers move faster', () => {
  const est = (id, pos, rating = 1500) => ({ steamId: id, pos, rating, races: 50 });
  const d = raceDeltas([est('a', 1), est('b', 2), est('c', 3), est('d', 4)]);
  assert.ok(d.get('a') > 0 && d.get('d') < 0);
  assert.equal(Math.round(d.get('a') + d.get('b') + d.get('c') + d.get('d')), 0, 'established drivers: what one gains another loses');
  assert.equal(d.get('a'), -d.get('d'));
  // a 1V1 between equals: K / 2 each way; a driver's first races: kNew
  assert.deepEqual([...raceDeltas([est('a', 1), est('b', 2)])], [['a', RATING.k / 2], ['b', -RATING.k / 2]]);
  assert.deepEqual([...raceDeltas([{ steamId: 'n', pos: 1 }, { steamId: 'm', pos: 2 }])], [['n', RATING.kNew / 2], ['m', -RATING.kNew / 2]]);
  // a dead heat between equals: nothing; beating someone rated far above: much more than beating an equal
  assert.deepEqual([...raceDeltas([est('a', 1), est('b', 1)]).values()], [0, 0]);
  assert.ok(raceDeltas([est('a', 1, 1300), est('b', 2, 1900)]).get('a') > 1.8 * raceDeltas([est('a', 1), est('b', 2)]).get('a'));
  // a big field moves a rating more than a 1V1, but not field-size times more
  const big = raceDeltas(Array.from({ length: 30 }, (_, i) => est('d' + i, i + 1))).get('d0');
  assert.ok(big > RATING.k / 2 && big < RATING.k * 3, big);
  assert.equal(raceDeltas([est('a', 1)]).size, 0);
});

test('a name of one\'s own: 3 to 20 characters, no lookalikes, nothing kept for the site', () => {
  assert.deepEqual(checkName('  Ann   Smith '), { value: 'Ann Smith', key: 'annsmith' });
  assert.equal(checkName('Zoë_Ü').key, 'zoëü');
  assert.equal(nameKey('Ann.Smith'), nameKey('ann smith'));
  assert.equal(nameKey('ANN-SMITH'), nameKey("ann'smith"));
  for (const bad of ['ab', 'x'.repeat(21), '-dash', 'a<b>c', 'ACR Daily', 'Admin', 'a . _ -', 'a\u0000bc']) assert.ok(checkName(bad).error, bad);
});

test('a team: a name, a 2-4 character tag in capitals, a colour from the list', () => {
  assert.deepEqual(checkTeam({ name: 'Gravel Foxes', tag: 'gfx', color: '#7BE07B' }).value, { name: 'Gravel Foxes', tag: 'GFX', color: '#7BE07B' });
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'G', color: '#7BE07B' }).error);
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'GF-X', color: '#7BE07B' }).error);
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'GFX', color: 'red' }).error);
  assert.ok(checkTeam({ name: 'GF', tag: 'GFX', color: '#7BE07B' }).error);
});

/** A PNG's first bytes (its size is all checkAvatar reads), padded. */
function png(w, h, size = 2000) {
  const b = new Uint8Array(size);
  b.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]);
  b.set([w >>> 24, (w >>> 16) & 255, (w >>> 8) & 255, w & 255, h >>> 24, (h >>> 16) & 255, (h >>> 8) & 255, h & 255], 16);
  return b;
}

test('a picture of one\'s own: square, 64 to 512 pixels, 60 KB at most', () => {
  assert.equal(checkAvatar(png(256, 256)).value.type, 'image/png');
  assert.equal(checkAvatar(png(600, 300)).status, 422);
  assert.equal(checkAvatar(png(32, 32)).status, 422);
  assert.equal(checkAvatar(png(256, 256, 70_000)).status, 413);
  assert.equal(checkAvatar(new Uint8Array(500)).status, 415);
});

test('a team\'s tag rides on the look, with the shop\'s', () => {
  assert.deepEqual(lookOfRow({ look_tag: 'GFX', look_tag_color: '#7BE07B' }), { tag: { text: 'GFX', color: '#7BE07B' } });
  assert.deepEqual(lookOfRow({ look_badge: 'badge:fire', look_tag: null }), { badge: '🔥' });
  assert.equal(lookOfRow({}), null);
});

// ------------------------------------------------------------------ on SQLite

const players = (db, n) => {
  for (let i = 0; i < n; i++) {
    db.prepare('INSERT INTO players (steam_id, name, created, steam_name, country) VALUES (?, ?, 0, ?, ?)').run(sid(i), 'Driver ' + i, 'Driver ' + i, i % 2 ? 'pl' : 'gb');
  }
};
const board = (n, dnfs = 0) => ({ entries: [...Array.from({ length: n }, (_, i) => fin(sid(i), 300000 + i * 1000)),
  ...Array.from({ length: dnfs }, (_, i) => dnf(sid(n + i)))] });

test('a daily taken once: its results kept; rated from RATING_FROM; a second go changes nothing', async () => {
  const { env, db, count } = fakeD1({ RATING_FROM: '2026-10-12' });
  players(db, 6);
  db.prepare("INSERT INTO runs (date, slot, steam_id, track, car, status, created) VALUES ('2026-10-12', 1, ?, 'wal_1', 'Ford Fiesta Rally2', 'finished', 0)").run(sid(0));
  count.queries = 0;
  const r = await takeDaily(env, '2026-10-12', 1, 1000, board(4, 2));
  assert.deepEqual(r, { date: '2026-10-12', slot: 1, drivers: 6, rated: true });
  assert.ok(count.queries <= 3, count.queries);
  const res = db.prepare("SELECT * FROM daily_results WHERE date = '2026-10-12' ORDER BY COALESCE(place, 99), steam_id").all();
  assert.deepEqual(res.map((x) => [x.place, x.status, x.field]), [[1, 'finished', 6], [2, 'finished', 6], [3, 'finished', 6], [4, 'finished', 6], [null, 'dnf', 6], [null, 'dnf', 6]]);
  assert.equal(res[0].track, 'wal_1');
  const rt = new Map(db.prepare('SELECT steam_id, rating, races FROM ratings').all().map((x) => [x.steam_id, x]));
  assert.equal(rt.size, 6);
  assert.ok(rt.get(sid(0)).rating > RATING.start && rt.get(sid(5)).rating < RATING.start);
  assert.equal(rt.get(sid(4)).rating, rt.get(sid(5)).rating, 'the DNFs share last place');
  assert.equal(res[0].delta, Math.round(10 * (rt.get(sid(0)).rating - RATING.start)) / 10);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM rating_history').get().n, 6);
  // again: nothing
  const again = await takeDaily(env, '2026-10-12', 1, 2000, board(4, 2));
  assert.equal(again.already, true);
  assert.equal(db.prepare('SELECT races FROM ratings WHERE steam_id = ?').get(sid(0)).races, 1);
  // the next daily builds on it
  await takeDaily(env, '2026-10-12', 2, 3000, board(2));
  assert.equal(db.prepare('SELECT races FROM ratings WHERE steam_id = ?').get(sid(0)).races, 2);
});

test('the cron takes the days in order, a few a run, rating only from RATING_FROM', async () => {
  const { env, db } = fakeD1({ RATING_FROM: '2026-10-03' });
  players(db, 3);
  const asked = [];
  const b = (date, slot) => { asked.push(`${date}/${slot}`); return board(3); };
  const now = Date.parse('2026-10-04T01:10:00Z');   // 2026-10-03 is settled; 2026-10-04 is not
  assert.deepEqual((await resultsTick(env, now, b, { first: '2026-10-01', perRun: 4 })).map((x) => [x.date, x.slot, x.rated]),
    [['2026-10-01', 1, false], ['2026-10-01', 2, false], ['2026-10-02', 1, false], ['2026-10-02', 2, false]]);
  assert.deepEqual((await resultsTick(env, now, b, { first: '2026-10-01', perRun: 4 })).map((x) => [x.date, x.slot, x.rated]),
    [['2026-10-03', 1, true], ['2026-10-03', 2, true]]);
  assert.deepEqual(await resultsTick(env, now, b, { first: '2026-10-01', perRun: 4 }), []);
  assert.equal(asked.length, 6);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM daily_results').get().n, 18);
  assert.equal(db.prepare('SELECT races FROM ratings WHERE steam_id = ?').get(sid(0)).races, 2);
});

test('cup matches rated once: a win against a finisher; not a no contest', async () => {
  const { env, db } = fakeD1({ RATING_FROM: '2026-10-01' });
  players(db, 4);
  const decided = [{ id: 1, a: sid(0), b: sid(1), winner: sid(1), note: 'by 1.200 s' },
    { id: 2, a: sid(2), b: sid(3), winner: sid(2), note: 'nobody finished: the higher seed goes through' },
    { id: 3, a: sid(2), b: null, winner: sid(2), note: 'a bye' }];
  await env.DB.batch(await cupMatchStmts(env, decided, 5));
  const rt = new Map(db.prepare('SELECT steam_id, rating FROM ratings').all().map((x) => [x.steam_id, x.rating]));
  assert.deepEqual([...rt.keys()].sort(), [sid(0), sid(1)]);
  assert.ok(rt.get(sid(1)) > RATING.start);
  await assert.rejects(env.DB.batch(await cupMatchStmts(env, decided, 6)), /UNIQUE|constraint/);   // (rated already)
});

/** driversApi as index.js calls it, for a driver signed in (me: their players row) or nobody. */
async function call(env, method, path, me = null, body = undefined, headers = {}) {
  const url = new URL('https://acrdaily.test' + path);
  const req = new Request(url, { method, headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : body instanceof Uint8Array ? body : JSON.stringify(body) });
  const row = me && await env.DB.prepare('SELECT * FROM players WHERE steam_id = ?').bind(me).first();
  const json = (data, status = 200) => ({ status, data });
  const err = (error, status = 400) => ({ status, data: { error } });
  let dropped = 0;
  const r = await driversApi(req, env, url.pathname, url, row, true, Date.now(), { json, err, site: 'https://acrdaily.test', namesChanged: async () => { dropped++; } });
  return r && { ...r, dropped };
}

test('names of one\'s own: unique, not another\'s, once a week; back to Steam\'s', async () => {
  const { env, db } = fakeD1();
  players(db, 3);
  assert.equal((await call(env, 'POST', '/api/me/name', null, { name: 'Speedy' })).status, 401);
  let r = await call(env, 'POST', '/api/me/name', sid(0), { name: 'Speedy Ann' });
  assert.deepEqual([r.status, r.data, r.dropped], [200, { name: 'Speedy Ann', custom: true }, 1]);
  assert.equal(db.prepare('SELECT name FROM players WHERE steam_id = ?').get(sid(0)).name, 'Speedy Ann');
  assert.equal((await call(env, 'POST', '/api/me/name', sid(1), { name: 'speedy_ann' })).status, 409, 'a lookalike');
  assert.equal((await call(env, 'POST', '/api/me/name', sid(1), { name: 'Driver 2' })).status, 409, 'another driver\'s Steam name');
  assert.equal((await call(env, 'POST', '/api/me/name', sid(0), { name: 'Faster Ann' })).status, 429, 'once a week');
  db.prepare('UPDATE players SET name_set = 0 WHERE steam_id = ?').run(sid(0));
  r = await call(env, 'POST', '/api/me/name', sid(0), { name: '' });
  assert.deepEqual(r.data, { name: 'Driver 0', custom: false });
  assert.equal((await call(env, 'POST', '/api/me/name', sid(1), { name: 'Speedy Ann' })).status, 200, 'free again');
});

test('pictures of one\'s own: up, served, back to Steam\'s', async () => {
  const { env, db } = fakeD1();
  players(db, 1);
  db.prepare("UPDATE players SET avatar = 'https://steam/a.jpg', steam_avatar = 'https://steam/a.jpg'").run();
  let r = await call(env, 'POST', '/api/me/avatar', sid(0), png(256, 256), { 'Content-Type': 'image/png' });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.match(r.data.avatar, new RegExp(`^https://acrdaily.test/avatar/${sid(0)}\\?v=\\d+$`));
  assert.equal(db.prepare('SELECT avatar FROM players').get().avatar, r.data.avatar);
  assert.equal((await call(env, 'POST', '/api/me/avatar', sid(0), png(256, 256), { 'Content-Type': 'image/png' })).status, 429);
  db.prepare('UPDATE players SET avatar_set = 1').run();
  assert.equal((await call(env, 'POST', '/api/me/avatar', sid(0), png(900, 300), { 'Content-Type': 'image/png' })).status, 422);
  r = await call(env, 'POST', '/api/me/avatar', sid(0), { remove: true });
  assert.equal(r.data.avatar, 'https://steam/a.jpg');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM player_avatars').get().n, 0);
});

test('teams: made, joined with the code, one each, the captaincy handed on, closed by the last one out', async () => {
  const { env, db } = fakeD1();
  players(db, 4);
  let r = await call(env, 'POST', '/api/teams', sid(0), { name: 'Gravel Foxes', tag: 'gfx', color: '#7BE07B' });
  assert.equal(r.status, 200);
  const id = r.data.id;
  assert.equal((await call(env, 'POST', '/api/teams', sid(1), { name: 'Copycats', tag: 'GFX', color: '#5BA8FF' })).status, 409, 'the tag is taken');
  assert.equal((await call(env, 'POST', '/api/teams', sid(0), { name: 'Second', tag: 'SEC', color: '#5BA8FF' })).status, 409, 'one team each');
  const t = (await call(env, 'GET', '/api/teams/' + id, sid(0))).data;
  assert.equal(t.tag, 'GFX');
  assert.match(t.code, /^[A-Z0-9]{4}-[A-Z0-9]{4}$/);
  assert.equal((await call(env, 'GET', '/api/teams/' + id, sid(1))).data.code, null, 'the code: members only');
  assert.equal((await call(env, 'POST', '/api/teams/join', sid(1), { code: 'nope' })).status, 404);
  assert.equal((await call(env, 'POST', '/api/teams/join', sid(1), { code: t.code })).status, 200);
  assert.equal((await call(env, 'POST', '/api/teams/join', sid(2), { code: t.code.toLowerCase().replace('-', ' ') })).status, 200);
  assert.equal((await call(env, 'POST', `/api/teams/${id}/kick`, sid(1), { steamId: sid(2) })).status, 403, 'only the captain');
  assert.equal((await call(env, 'POST', `/api/teams/${id}/kick`, sid(0), { steamId: sid(2) })).status, 200);
  // the captain leaves: the longest in it takes over; the last one out closes it
  assert.equal((await call(env, 'POST', `/api/teams/${id}/leave`, sid(0))).status, 200);
  assert.equal(db.prepare('SELECT captain FROM teams').get().captain, sid(1));
  assert.deepEqual((await call(env, 'POST', `/api/teams/${id}/leave`, sid(1))).data, { left: true, closed: true });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM teams').get().n, 0);
  // the list
  await call(env, 'POST', '/api/teams', sid(3), { name: 'Lone Wolves', tag: 'LW', color: '#F4F4F5' });
  const all = (await call(env, 'GET', '/api/teams', sid(3))).data;
  assert.deepEqual(all.teams.map((x) => [x.tag, x.members]), [['LW', 1]]);
  assert.equal(all.mine, all.teams[0].id);
});

test('a driver\'s page and the world ranking, in one look each', async () => {
  const { env, db, count } = fakeD1({ RATING_FROM: '2026-10-01' });
  players(db, 5);
  await takeDaily(env, '2026-10-01', 1, 1000, board(4, 1));
  await call(env, 'POST', '/api/teams', sid(0), { name: 'Gravel Foxes', tag: 'GFX', color: '#7BE07B' });
  db.prepare("INSERT INTO routes (track, points, length, updated) VALUES ('wal_1', '[]', 12345, 0)").run();
  db.prepare("INSERT INTO runs (date, slot, steam_id, track, car, status, created) VALUES ('2026-10-01', 1, ?, 'wal_1', 'Ford Fiesta Rally2', 'finished', 0)").run(sid(0));
  count.queries = 0;
  const p = (await call(env, 'GET', '/api/drivers/' + sid(0))).data;
  assert.ok(count.queries <= 2, count.queries);
  assert.equal(p.name, 'Driver 0');
  assert.deepEqual(p.team && [p.team.tag, p.team.captain], ['GFX', true]);
  assert.deepEqual(p.look, { tag: { text: 'GFX', color: '#7BE07B' } });
  assert.equal(p.rating.rank, 1);
  assert.equal(p.rating.of, 5);
  assert.deepEqual([p.stats.dailies, p.stats.wins, p.stats.podiums, p.stats.km, p.stats.runs], [1, 1, 1, 12.3, 1]);
  assert.deepEqual(p.stats.cars, [{ car: 'Ford Fiesta Rally2', runs: 1 }]);
  assert.equal(p.recent[0].place, 1);
  assert.equal(p.history.length, 1);
  assert.equal(p.me, null);
  assert.equal((await call(env, 'GET', '/api/drivers/' + sid(0), sid(0))).data.me.steamName, 'Driver 0');
  assert.equal((await call(env, 'GET', '/api/drivers/76561198999999999')).status, 404);
  const rk = (await call(env, 'GET', '/api/ranking', sid(3))).data;
  assert.deepEqual(rk.rows.map((x) => x.steamId), [sid(0), sid(1), sid(2), sid(3), sid(4)]);
  assert.equal(rk.rows[0].team.tag, 'GFX');
  assert.equal(rk.me.rank, 4);
  assert.deepEqual(rk.countries.map((c) => c.code).sort(), ['gb', 'pl']);
  const pl = (await call(env, 'GET', '/api/ranking?country=pl')).data;
  assert.deepEqual(pl.rows.map((x) => [x.rank, x.steamId]), [[1, sid(1)], [2, sid(3)]]);
});
