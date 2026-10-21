// Driver pages, names, pictures, teams (src/drivers.js) and the rating with its results (src/rating.js): the rules,
// then the API and the cron's step on a real SQLite (test/faked1.mjs).
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkAvatar, checkName, checkTeam, driversApi, nameKey, withTeams } from '../src/drivers.js';
import { chance, cupMatchStmts, racePlaces, raceDeltas, RATING, resultsTick, takeDaily } from '../src/rating.js';
import { ACHIEVEMENTS } from '../src/achievements.js';
import { lookOfRow } from '../src/shop.js';
import { tmPlain, tmSpans, tmStyled } from '../src/tmtext.js';
import { fakeD1, sid } from './faked1.mjs';

const fin = (steamId, totalMs) => ({ steamId, status: 'finished', totalMs, gapMs: 0, runId: 1 });
const dnf = (steamId) => ({ steamId, status: 'dnf', totalMs: null });

test('a race\'s places: by time, equal times share a place, every DNF last together', () => {
  assert.deepEqual(racePlaces([fin('b', 200), dnf('x'), fin('a', 100), fin('c', 200), dnf('y')]),
    [{ steamId: 'a', pos: 1 }, { steamId: 'b', pos: 2 }, { steamId: 'c', pos: 2 }, { steamId: 'x', pos: 4 }, { steamId: 'y', pos: 4 }]);
});

test('the rating, iRacing\'s: beating the field gains, who you beat (or lose to) matters, the fudge', () => {
  const est = (id, pos, rating = 1500) => ({ steamId: id, pos, rating });
  const d = raceDeltas([est('a', 1), est('b', 2), est('c', 3), est('d', 4)]);
  assert.deepEqual([...d.values()], [74.5, 25, -24.5, -74]);
  assert.equal(Math.round(d.get('a') + d.get('b') + d.get('c') + d.get('d')), 1, 'the fudge: about a point a race in all');
  // a race of two between equals (a cup match): +50 / -49; someone new counts at RATING.start
  assert.deepEqual([...raceDeltas([est('a', 1), est('b', 2)])], [['a', 50], ['b', -49]]);
  assert.deepEqual([...raceDeltas([{ steamId: 'n', pos: 1 }, { steamId: 'm', pos: 2 }])], [['n', 50], ['m', -49]]);
  // at 1500: beating a 2000 gains more than beating a 1200; losing to a 1200 costs more than losing to a 2000
  const vs = (opp, won) => raceDeltas([est('me', won ? 1 : 2), est('o', won ? 2 : 1, opp)]).get('me');
  assert.deepEqual([vs(1200, true), vs(2000, true), vs(1200, false), vs(2000, false)], [42.7, 60.1, -56.3, -38.9]);
  assert.equal(chance(1500, 1500), 0.5);
  assert.ok(Math.abs(chance(3200, 1600) - 0.75) < 1e-9, '1600 apart: 3 to 1 here...');
  assert.ok(Math.abs(chance(10000, 8400) - 2 / 3) < 0.01, '...nearer 2 to 1 the higher both are');
  // a dead heat between equals: next to nothing
  assert.ok([...raceDeltas([est('a', 1), est('b', 1)]).values()].every((x) => Math.abs(x) <= 0.5));
  // a big field moves a rating more than a race of two, but not field-size times more
  const big = raceDeltas(Array.from({ length: 30 }, (_, i) => est('d' + i, i + 1))).get('d0');
  assert.ok(big > 50 && big < 110, big);
  // the DNFs, last together, share the places they take (in the fudge): 3 finishers, 2 DNFs at places 4 and 5
  const dn = raceDeltas([est('a', 1), est('b', 2), est('c', 3), est('x', 4), est('y', 4)]);
  assert.equal(dn.get('x'), dn.get('y'));
  assert.equal(dn.get('x'), Math.round(10 * (0.5 - 2 - (2.5 - 4.5) / 100) * 200 / 5) / 10);
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
  assert.deepEqual(checkTeam({ name: 'Gravel Foxes', tag: 'gfx', color: '#7BE07B' }).value,
    { name: 'Gravel Foxes', tag: 'GFX', color: '#7BE07B', nameFmt: null, tagFmt: null });
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'G', color: '#7BE07B' }).error);
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'GF-X', color: '#7BE07B' }).error);
  assert.ok(checkTeam({ name: 'Gravel Foxes', tag: 'GFX', color: 'red' }).error);
  assert.ok(checkTeam({ name: 'GF', tag: 'GFX', color: '#7BE07B' }).error);
});

test('Trackmania\'s $ codes: colours per letter, bold, italic, wide, capitals; dark colours lightened, links dropped', () => {
  assert.deepEqual(tmSpans('$f00G$fffF$00fX').map((x) => [x.t, x.c]), [['G', '#FF1C1C'], ['F', '#FFFFFF'], ['X', '#3F3FFF']]);
  assert.deepEqual(tmSpans('$fa0$0c0x').map((x) => x.c), ['#00CC00'], 'bright enough: as is; only the last colour counts');
  assert.deepEqual(tmSpans('$oBold$z plain').map((x) => [x.t, x.b]), [['Bold', 1], [' plain', 0]]);
  assert.deepEqual(tmSpans('$i$wa$nb').map((x) => [x.t, x.i, x.w, x.n]), [['a', 1, 1, 0], ['b', 1, 0, 1]]);
  assert.deepEqual(tmSpans('$000dark$g back').map((x) => x.c), ['#4D4D4D', null]);
  assert.equal(tmPlain('$tgfx'), 'GFX');
  assert.equal(tmPlain('$$5 $l[https://x.y]Link$l'), '$5 Link');
  assert.equal(tmPlain('$h[a]b'), 'b');
  assert.equal(tmPlain('end$'), 'end');
  assert.equal(tmPlain('$q?'), '?', 'an unknown code: dropped');
  assert.deepEqual([tmStyled('$f00G'), tmStyled('Plain'), tmStyled('5$$')], [true, false, false]);
});

test('a styled team: the rules on what it reads as, the codes kept as written', () => {
  const v = checkTeam({ name: '$f90Gravel $fffFoxes', tag: '$f00G$ffff$00fx', color: '#7BE07B' }).value;
  assert.deepEqual(v, { name: 'Gravel Foxes', tag: 'Gfx', color: '#7BE07B', nameFmt: '$f90Gravel $fffFoxes', tagFmt: '$f00G$ffff$00fx' });
  assert.equal(checkTeam({ name: 'Foxes', tag: '$tgfx', color: '#7BE07B' }).value.tag, 'GFX');
  assert.ok(checkTeam({ name: 'Foxes', tag: '$f00G', color: '#7BE07B' }).error, 'one letter, however styled');
  assert.ok(checkTeam({ name: 'Foxes', tag: '$f00G-X', color: '#7BE07B' }).error);
  assert.ok(checkTeam({ name: '$o$f00Ab', tag: 'GFX', color: '#7BE07B' }).error, 'a 2-letter name');
  assert.ok(checkTeam({ name: 'Foxes', tag: '$f00A$fffcr', color: '#7BE07B' }).error, 'ACR is kept for the site');
  assert.ok(checkTeam({ name: 'Foxes', tag: '$f00' + 'a'.repeat(70), color: '#7BE07B' }).error, 'cut at 60 characters, still too long');
  assert.deepEqual(lookOfRow({ look_tag: 'Gfx', look_tag_color: '#7BE07B', look_tag_fmt: '$f00Gfx' }), { tag: { text: 'Gfx', color: '#7BE07B', fmt: '$f00Gfx' } });
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

test('flags of one\'s own: picked on the page, nothing from the game, taken off again', async () => {
  const { env, db } = fakeD1();
  players(db, 2);                                    // Driver 0 starts with 'gb' (an old flag the game gave them)
  assert.equal((await call(env, 'POST', '/api/me/country', null, { country: 'fi' })).status, 401);
  let r = await call(env, 'POST', '/api/me/country', sid(0), { country: 'FI' });
  assert.deepEqual([r.status, r.data, r.dropped], [200, { country: 'fi' }, 1], 'the boards show it, so they are built again');
  assert.equal(db.prepare('SELECT country FROM players WHERE steam_id = ?').get(sid(0)).country, 'fi');
  assert.equal((await call(env, 'POST', '/api/me/country', sid(0), { country: 'fi' })).dropped, 0, 'the same flag again: nothing to do');
  assert.equal((await call(env, 'POST', '/api/me/country', sid(0), { country: 'gb-sct' })).data.country, 'gb-sct', 'the UK\'s nations too');
  for (const bad of ['Finland', 'zz', 'constructor', 'f']) {
    assert.equal((await call(env, 'POST', '/api/me/country', sid(0), { country: bad })).status, 400, bad);
  }
  r = await call(env, 'POST', '/api/me/country', sid(0), { country: null });
  assert.deepEqual([r.status, r.data], [200, { country: null }]);
  assert.equal(db.prepare('SELECT country FROM players WHERE steam_id = ?').get(sid(0)).country, null);
  assert.equal(db.prepare('SELECT country FROM players WHERE steam_id = ?').get(sid(1)).country, 'pl', 'nobody else is touched');
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

test('a styled team: its codes kept, the tag taken whatever its styles, cleared by saving it plain', async () => {
  const { env, db } = fakeD1({ RATING_FROM: '2026-10-01' });
  players(db, 3);
  let r = await call(env, 'POST', '/api/teams', sid(0), { name: '$f90Gravel $fffFoxes', tag: '$f00G$fffF$00fX', color: '#7BE07B' });
  assert.equal(r.status, 200);
  const id = r.data.id;
  assert.equal((await call(env, 'POST', '/api/teams', sid(1), { name: 'Copycats', tag: '$o$0f0gfx', color: '#5BA8FF' })).status, 409, 'the tag is taken');
  let t = (await call(env, 'GET', '/api/teams/' + id, sid(0))).data;
  assert.deepEqual([t.name, t.tag, t.nameFmt, t.tagFmt], ['Gravel Foxes', 'GFX', '$f90Gravel $fffFoxes', '$f00G$fffF$00fX']);
  const lite = (await call(env, 'GET', '/api/drivers/' + sid(0), null, undefined, { 'User-Agent': 'ACR-Daily/0.0.14 public' })).data;
  assert.deepEqual([lite.team.tag, lite.team.tagFmt], ['GFX', '$f00G$fffF$00fX']);
  const p = (await call(env, 'GET', '/api/drivers/' + sid(0))).data;
  assert.deepEqual([p.team.nameFmt, p.look.tag.fmt], ['$f90Gravel $fffFoxes', '$f00G$fffF$00fX']);
  await takeDaily(env, '2026-10-01', 1, 1000, board(2, 1));
  assert.equal((await call(env, 'GET', '/api/ranking')).data.rows.find((x) => x.steamId === sid(0)).team.tagFmt, '$f00G$fffF$00fX');
  // the captain saves it plain again
  assert.equal((await call(env, 'POST', `/api/teams/${id}/edit`, sid(0), { name: 'Gravel Foxes', tag: 'gfx', color: '#7BE07B' })).status, 200);
  t = (await call(env, 'GET', '/api/teams/' + id, sid(0))).data;
  assert.deepEqual([t.tag, t.nameFmt, t.tagFmt], ['GFX', null, null]);
});

test('withTeams: every driver in an answer with their team\'s tag, one query; routes not looked into', async () => {
  const { env, db, count } = fakeD1();
  players(db, 3);
  await call(env, 'POST', '/api/teams', sid(0), { name: 'Gravel Foxes', tag: '$f00G$fffF$00fX', color: '#7BE07B' });
  await call(env, 'POST', '/api/teams', sid(1), { name: 'Lone Wolves', tag: 'LW', color: '#F4F4F5' });
  const route = Array.from({ length: 1000 }, (_, i) => [i, i]);
  const data = { owner: { steamId: sid(0), name: 'Driver 0' }, stages: [{ track: 'x', route }],
    standings: [{ steamId: sid(1), name: 'Driver 1', cells: { 1: { steamId: sid(0), name: 'Driver 0' } } }, { steamId: sid(2), name: 'Driver 2' }],
    ids: [sid(0)], me: { steamId: sid(2) } };
  count.queries = 0;
  assert.equal(await withTeams(env, data), data);
  assert.equal(count.queries, 1);
  assert.deepEqual(data.owner.team, { tag: 'GFX', color: '#7BE07B', tagFmt: '$f00G$fffF$00fX' });
  assert.deepEqual(data.standings.map((x) => x.team && x.team.tag), ['LW', undefined]);
  assert.equal(data.standings[0].cells[1].team.tag, 'GFX');
  assert.equal(data.me.team, undefined, 'no name: not a driver shown');
  count.queries = 0;
  await withTeams(env, { stages: [{ route }], ok: true });
  assert.equal(count.queries, 0, 'nobody in it: no query');
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
  assert.ok(count.queries <= 4, count.queries);         // (the achievements' rarity: counted once an hour, kept)
  count.queries = 0;
  await call(env, 'GET', '/api/drivers/' + sid(0));
  assert.ok(count.queries <= 2, count.queries);
  assert.equal(p.achievements.length, ACHIEVEMENTS.length);
  assert.ok(p.achievements.every((a) => a.at === null), 'nothing unlocked before a check');
  // the app's driver strip: the light answer (the name, the team's tag, the ratings), one look
  count.queries = 0;
  const lite = (await call(env, 'GET', '/api/drivers/' + sid(0), null, undefined, { 'User-Agent': 'ACR-Daily/0.0.11 public' })).data;
  assert.equal(count.queries, 1);
  assert.deepEqual([lite.lite, lite.name, lite.team.tag, lite.rating.rank, lite.stats, lite.achievements], [true, 'Driver 0', 'GFX', 1, undefined, undefined]);
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

test('one ranking, never reset: the rating carries on from month to month', async () => {
  const { env, db } = fakeD1({ RATING_FROM: '2026-09-01' });
  players(db, 3);
  await takeDaily(env, '2026-09-29', 1, 1000, board(3));
  await takeDaily(env, '2026-09-30', 1, 2000, board(3));
  const sept = db.prepare('SELECT rating FROM ratings WHERE steam_id = ?').get(sid(0)).rating;
  await takeDaily(env, '2026-10-01', 1, 3000, { entries: [fin(sid(2), 300000), fin(sid(1), 301000), fin(sid(0), 302000)] });
  const after = db.prepare('SELECT rating, races FROM ratings WHERE steam_id = ?').get(sid(0));
  assert.equal(after.races, 3);
  assert.ok(after.rating < sept && after.rating > RATING.start, 'October goes on from September\'s rating');
  const rk = (await call(env, 'GET', '/api/ranking')).data;
  assert.deepEqual(rk.rows.map((x) => x.steamId), [sid(0), sid(1), sid(2)]);   // (two good days outweigh one bad)
  assert.equal(rk.season, undefined);
});