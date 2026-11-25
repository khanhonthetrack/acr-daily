// CASUAL (src/casual.js): lobbies of up to 4, on a real SQLite (schema.sql) through the D1 stand-in; the notes page.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { CX, casualApi, casualPage, casualTick, notesFor } from '../src/casual.js';
import { copilotApi, parseLangs } from '../src/copilot.js';
import { PACENOTES } from '../src/pacenotes.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const DAY = '2026-11-25', T0 = Date.parse(DAY + 'T10:00:00Z');
const NOTED = Object.keys(PACENOTES).slice(0, 2);
const TRACKS = ['Wales A', 'Wales B', 'Greece A'];            // Greece A: no notes
const ROUTE = Array.from({ length: 301 }, (_, i) => [i * 10, 0]);
const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h; };

function world() {
  const f = fakeD1({ COPILOT_FROM: DAY });
  const { db } = f;
  TRACKS.forEach((t, i) => db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, 3000, 0, ?)')
    .run(t, JSON.stringify(ROUTE), i === 2 ? 'NoNotes' : NOTED[i]));
  for (let i = 1; i <= 6; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const deps = { json, err, hash, splits: [0.25, 0.5, 0.75], timing: { liveSendS: 5 },
    pool: async () => ({ tracks: TRACKS, byTrack: new Map() }) };
  const me = (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i));
  const call = (method, path, { who = null, body, now = T0, same = true } = {}) => {
    const url = new URL('https://acrdaily.test' + path);
    const req = new Request(url, { method, ...(body !== undefined ? { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } } : {}) });
    return casualApi(req, f.env, url.pathname, url, who ? me(who) : null, same, now, deps);
  };
  return { ...f, deps, call, me };
}

const NEW = { track: 'Wales A', car: 'Mini Cooper S 1275', weather: 'LightRain', time: 'evening', langs: ['en', 'de'], private: false };
const make = (w, who, extra = {}) => w.call('POST', '/api/casual/lobbies', { who, body: { ...NEW, ...extra } });

test('languages: at most 3, distinct, from the list', () => {
  assert.deepEqual(parseLangs(undefined), { langs: [] });
  assert.deepEqual(parseLangs(['en', 'DE', 'fr']), { langs: ['en', 'de', 'fr'] });
  for (const bad of [['en', 'de', 'fr', 'it'], ['en', 'en'], ['xx'], ['eng'], [1], 'en', [null]]) assert.ok(parseLangs(bad).error, JSON.stringify(bad));
});

test('options: what a lobby may use', async () => {
  const w = world();
  const o = (await w.call('GET', '/api/casual/options')).data;
  assert.deepEqual(o.stages.map((s) => s.track).sort(), ['Wales A', 'Wales B'], 'only stages with the game\'s notes');
  assert.deepEqual(Object.keys(o.stages[0]).sort(), ['lengthM', 'menuName', 'rally', 'stageName', 'track']);
  assert.ok(o.cars.length > 10 && o.cars.every((c) => c.id && c.name && c.cls));
  assert.ok(o.weather.some((x) => x.code === 'LightRain' && x.label === 'Light rain'));
  assert.deepEqual(o.times[0], { code: 'morning', label: 'Morning (08:00)' });
});

test('off without COPILOT_FROM, null for other paths', async () => {
  const { env } = fakeD1({});
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const url = new URL('https://acrdaily.test/api/casual');
  assert.equal((await casualApi(new Request(url), env, '/api/casual', url, null, true, T0, { json, err })).status, 404);
  assert.equal(await casualApi(new Request(url), env, '/api/copilot', url, null, true, T0, { json, err }), null);
  assert.equal((await casualPage(env, 'abcdefghijkl', T0)).status, 404);
});

test('create: validation', async () => {
  const w = world();
  assert.equal((await w.call('POST', '/api/casual/lobbies', { body: NEW })).status, 401);
  assert.equal((await w.call('POST', '/api/casual/lobbies', { who: 1, body: NEW, same: false })).status, 403);
  for (const bad of [{ track: 'Greece A' }, { track: 'Nowhere' }, { track: undefined }, { car: 'Ford Fiesta' }, { car: 5 }, { weather: 'Hail' },
    { time: 'night' }, { langs: ['en', 'de', 'fr', 'es'] }, { langs: ['en', 'en'] }, { langs: ['zz'] }, { langs: 'en' }]) {
    const r = await make(w, 1, bad);
    assert.equal(r.status, 400, JSON.stringify(bad) + ' ' + JSON.stringify(r.data));
  }
  assert.equal(w.db.prepare('SELECT COUNT(*) AS n FROM casual_lobbies').get().n, 0);
  const r = await make(w, 1);
  assert.equal(r.status, 200);
  const l = r.data.lobby;
  assert.deepEqual([l.state, l.private, l.max, l.count, l.free, l.langs], ['open', false, 4, 1, 3, ['en', 'de']]);
  assert.equal(l.stage.track, 'Wales A');
  assert.equal(l.car.name, 'Mini Cooper S 1275');
  assert.equal(l.car.id, 'MiniCooperS1275');
  assert.deepEqual(l.weather, { code: 'LightRain', label: 'Light rain' });
  assert.deepEqual(l.time, { code: 'evening', label: 'Evening (19:00)' });
  assert.deepEqual(l.host, { steamId: sid(1), name: 'Driver 1', avatar: null, country: null });
  assert.deepEqual(l.members.map((m) => [m.steamId, m.role, m.seat, m.ready]), [[sid(1), 'driver', 0, false]]);
  assert.deepEqual(l.me, { steamId: sid(1), role: 'driver', seat: 0 });
  assert.match(l.notesUrl, /^\/n\/[a-z0-9]{12}$/);
  assert.deepEqual(l.signals, {});
  assert.equal(l.code, undefined, 'public: no code');
  assert.equal(l.ch, undefined, 'not started: no stage yet');
  const p = (await make(w, 2, { private: true })).data.lobby;
  assert.match(p.code, /^[A-Z2-9]{6}$/);
  assert.equal(p.private, true);
});

test('one lobby at a time', async () => {
  const w = world();
  const a = (await make(w, 1)).data.lobby.id;
  const b = (await make(w, 2)).data.lobby.id;
  await w.call('POST', '/api/casual/join', { who: 2, body: { id: a } });
  assert.equal(w.db.prepare('SELECT state FROM casual_lobbies WHERE id = ?').get(b).state, 'closed', 'my own open one closed on joining');
  const c = (await make(w, 2)).data.lobby.id;   // creating leaves the one I joined
  assert.equal(w.db.prepare('SELECT COUNT(*) AS n FROM casual_members WHERE lobby_id = ?').get(a).n, 1);
  assert.equal((await w.call('GET', '/api/casual', { who: 2 })).data.lobby.id, c);
  await make(w, 1);                              // host 1 again: a closed, new open
  assert.equal(w.db.prepare('SELECT state FROM casual_lobbies WHERE id = ?').get(a).state, 'closed');
});

test('join: seats, full, private codes, started', async () => {
  const w = world();
  const l = (await make(w, 1)).data.lobby;
  const j2 = await w.call('POST', '/api/casual/join', { who: 2, body: { id: l.id } });
  assert.equal(j2.data.lobby.me.seat, 1);
  assert.equal(j2.data.lobby.me.role, 'codriver');
  assert.equal((await w.call('POST', '/api/casual/join', { who: 3, body: { id: l.id } })).data.lobby.me.seat, 2);
  assert.equal((await w.call('POST', '/api/casual/join', { who: 4, body: { id: l.id } })).data.lobby.me.seat, 3);
  const full = await w.call('POST', '/api/casual/join', { who: 5, body: { id: l.id } });
  assert.equal(full.status, 409, 'a 5th person');
  assert.match(full.data.error, /full/);
  assert.equal((await w.call('POST', '/api/casual/join', { who: 3, body: { id: l.id } })).data.lobby.count, 4, 'joining again: same');
  // a seat given up is free again, in the lowest seat
  await w.call('POST', `/api/casual/lobbies/${l.id}/leave`, { who: 3 });
  assert.equal((await w.call('POST', '/api/casual/join', { who: 5, body: { id: l.id } })).data.lobby.me.seat, 2);
  assert.deepEqual((await w.call('GET', `/api/casual/lobbies/${l.id}`, { who: 1 })).data.lobby.members.map((m) => [m.seat, m.name]),
    [[0, 'Driver 1'], [1, 'Driver 2'], [2, 'Driver 5'], [3, 'Driver 4']]);
  assert.equal((await w.call('POST', '/api/casual/join', { who: 6, body: { id: 999 } })).status, 404);

  // private: by its code, never listed for others
  const p = (await make(w, 6, { private: true })).data.lobby;
  const list = (await w.call('GET', '/api/casual', { who: 3 })).data;
  assert.deepEqual(list.lobbies.map((x) => x.id), [l.id], 'a private lobby is not listed');
  assert.equal((await w.call('POST', '/api/casual/join', { who: 3, body: { id: p.id } })).status, 403);
  assert.equal((await w.call('POST', '/api/casual/join', { who: 3, body: { id: p.id, code: 'ZZZZZZ' } })).status, 403);
  assert.equal((await w.call('POST', '/api/casual/join', { who: 3, body: { code: 'ZZZZZZ' } })).status, 404);
  const ok = await w.call('POST', '/api/casual/join', { who: 3, body: { code: p.code.toLowerCase() } });
  assert.equal(ok.data.lobby.id, p.id);
  assert.equal(ok.data.lobby.code, p.code, 'a member sees the code');
  assert.equal((await w.call('GET', '/api/casual', { who: 6 })).data.lobbies.some((x) => x.id === p.id), true, 'mine: listed to me');
  assert.equal((await w.call('GET', '/api/casual', { who: 6 })).data.lobbies.find((x) => x.id === p.id).code, undefined);

  // after the start: refused
  await w.call('POST', `/api/casual/lobbies/${p.id}/start`, { who: 6 });
  const late = await w.call('POST', '/api/casual/join', { who: 4, body: { code: p.code } });
  assert.equal(late.status, 409);
  assert.match(late.data.error, /started/);
});

test('list: public open + started lobbies, newest first, a started one too', async () => {
  const w = world();
  const a = (await make(w, 1, { time: 'morning' })).data.lobby.id;
  const b = (await make(w, 2)).data.lobby.id;
  await w.call('POST', `/api/casual/lobbies/${b}/start`, { who: 2, now: T0 + 1000 });
  const c = (await make(w, 3, { track: 'Wales B' }) ).data.lobby.id;
  w.db.prepare('UPDATE casual_lobbies SET created = created + id WHERE id = ?').run(c);
  const l = (await w.call('GET', '/api/casual', { who: null, now: T0 + 2000 })).data;
  assert.equal(l.on, true);
  assert.deepEqual(l.lobbies.map((x) => x.id), [c, b, a]);
  assert.deepEqual(l.lobbies.map((x) => x.state), ['open', 'started', 'open']);
  assert.equal(l.lobby, null);
  assert.equal(l.lobbies[0].me, undefined);
  assert.equal(l.lobbies[0].notesUrl, undefined, 'the notes link is for members');
  assert.ok(l.lobbies[1].members && l.lobbies[1].stage && l.lobbies[1].host);
});

test('ready, start (host only, alone too), the stage and notes for every member, leave', async () => {
  const w = world();
  const l = (await make(w, 1)).data.lobby;
  const id = l.id;
  await w.call('POST', `/api/casual/join`, { who: 2, body: { id } });
  await w.call('POST', `/api/casual/join`, { who: 3, body: { id } });
  assert.equal((await w.call('POST', `/api/casual/lobbies/${id}/ready`, { who: 2, body: { ready: true } })).data.lobby.members[1].ready, true);
  assert.equal((await w.call('POST', `/api/casual/lobbies/${id}/ready`, { who: 2, body: { ready: false } })).data.lobby.members[1].ready, false);
  await w.call('POST', `/api/casual/lobbies/${id}/ready`, { who: 2, body: { ready: true } });
  assert.equal((await w.call('POST', `/api/casual/lobbies/${id}/ready`, { who: 5, body: {} })).status, 404, 'not a member');
  assert.equal((await w.call('POST', `/api/casual/lobbies/${id}/start`, { who: 2 })).status, 403, 'only the host starts');
  assert.equal((await w.call('GET', `/api/casual/lobbies/${id}`, { who: 6 })).status, 404);
  assert.equal((await w.call('GET', `/api/casual/lobbies/${id}`, { who: 2 })).data.lobby.ch, undefined);

  const s = await w.call('POST', `/api/casual/lobbies/${id}/start`, { who: 1, now: T0 + 5000 });
  assert.equal(s.status, 200);
  assert.equal(s.data.lobby.state, 'started');
  assert.equal(s.data.lobby.started, T0 + 5000);
  for (const who of [1, 2, 3]) {
    const m = (await w.call('GET', `/api/casual/lobbies/${id}`, { who, now: T0 + 6000 })).data.lobby;
    assert.equal(m.ch.id, `cx:${id}`);
    assert.equal(m.ch.kind, 'casual');
    assert.equal(m.ch.mode, 'weekend');
    assert.equal(m.ch.hardcore, false);
    assert.equal(m.ch.track, 'Wales A');
    assert.equal(m.ch.car, 'Mini Cooper S 1275');
    assert.equal(m.ch.carId, 'MiniCooperS1275');
    assert.equal(m.ch.weather, 'LightRain');
    assert.equal(m.ch.time, 'evening');
    assert.equal(m.ch.startSeconds, 19 * 3600);
    assert.ok(m.ch.route.length > 100);
    assert.ok(m.notes.length > 10 && m.notes[0].text && m.notes[0].n === 1, 'the notes for every member');
  }
  assert.equal((await w.call('POST', `/api/casual/join`, { who: 4, body: { id } })).status, 409);
  // a member leaves: out, the lobby goes on; the host leaves a started lobby: finished
  await w.call('POST', `/api/casual/lobbies/${id}/leave`, { who: 3 });
  assert.equal((await w.call('GET', `/api/casual/lobbies/${id}`, { who: 3 })).status, 404);
  assert.equal((await w.call('GET', `/api/casual/lobbies/${id}`, { who: 1 })).data.lobby.count, 2);
  await w.call('POST', `/api/casual/lobbies/${id}/leave`, { who: 1, now: T0 + H });
  assert.equal(w.db.prepare('SELECT state FROM casual_lobbies WHERE id = ?').get(id).state, 'finished');

  // an open one: the host leaving closes it; alone: start works
  const o = (await make(w, 4)).data.lobby.id;
  await w.call('POST', `/api/casual/lobbies/${o}/leave`, { who: 4 });
  assert.equal(w.db.prepare('SELECT state FROM casual_lobbies WHERE id = ?').get(o).state, 'closed');
  const solo = (await make(w, 5)).data.lobby.id;
  const r = await w.call('POST', `/api/casual/lobbies/${solo}/start`, { who: 5 });
  assert.deepEqual([r.data.lobby.state, r.data.lobby.count, r.data.lobby.free], ['started', 1, 3]);
  assert.equal((await w.call('POST', `/api/casual/lobbies/${solo}/start`, { who: 5 })).data.lobby.state, 'started', 'again: the same');
  assert.equal((await w.call('POST', `/api/casual/lobbies/${o}/start`, { who: 4 })).status, 409, 'a closed one');
});

test('signals: addressed to one member', async () => {
  const w = world();
  const id = (await make(w, 1)).data.lobby.id;
  await w.call('POST', '/api/casual/join', { who: 2, body: { id } });
  await w.call('POST', '/api/casual/join', { who: 3, body: { id } });
  const sig = (who, to, data) => w.call('POST', `/api/casual/lobbies/${id}/signal`, { who, body: { to, data } });
  assert.equal((await sig(1, sid(2), 'offer-1-2')).status, 200);
  assert.equal((await sig(1, sid(3), { sdp: 'x' })).status, 200);
  assert.equal((await sig(2, sid(1), 'answer-2-1')).status, 200);
  assert.equal((await sig(1, sid(2), 'offer-1-2-b')).status, 200, 'replaced');
  const get = async (who) => (await w.call('GET', `/api/casual/lobbies/${id}`, { who })).data.lobby.signals;
  assert.deepEqual(await get(2), { [sid(1)]: 'offer-1-2-b' });
  assert.deepEqual(await get(3), { [sid(1)]: '{"sdp":"x"}' });
  assert.deepEqual(await get(1), { [sid(2)]: 'answer-2-1' });
  assert.equal((await sig(1, sid(1), 'x')).status, 400, 'not to myself');
  assert.equal((await sig(1, sid(5), 'x')).status, 404, 'not to a stranger');
  assert.equal((await sig(5, sid(1), 'x')).status, 404, 'not from a stranger');
  assert.equal((await sig(1, sid(2), 'x'.repeat(CX.signalMax + 1))).status, 413);
  assert.equal((await w.call('GET', '/api/casual', { who: 2 })).data.lobby.signals[sid(1)], 'offer-1-2-b');
  await w.call('POST', `/api/casual/lobbies/${id}/leave`, { who: 2 });
  assert.deepEqual(await get(1), {}, 'a member who left takes their signals');
});

test('the cron closes stale lobbies', async () => {
  const w = world();
  const a = (await make(w, 1)).data.lobby.id;
  const b = (await make(w, 2)).data.lobby.id;
  await w.call('POST', `/api/casual/lobbies/${b}/start`, { who: 2, now: T0 + H });
  await casualTick(w.env, T0 + 2 * H);
  const st = (id) => w.db.prepare('SELECT state FROM casual_lobbies WHERE id = ?').get(id).state;
  assert.deepEqual([st(a), st(b)], ['open', 'started']);
  await casualTick(w.env, T0 + CX.openMs + 1000);
  assert.deepEqual([st(a), st(b)], ['closed', 'started']);
  await casualTick(w.env, T0 + H + CX.liveMs + 1000);
  assert.equal(st(b), 'finished');
  await casualTick(w.env, T0 + 10 * 86400000);
  assert.equal(w.db.prepare('SELECT COUNT(*) AS n FROM casual_lobbies').get().n, 0, 'old rows dropped');
});

test('the notes page: token, content, escaping, expiry', async () => {
  const w = world();
  const l = (await make(w, 1)).data.lobby;
  const token = l.notesUrl.slice(3);
  const api = await w.call('GET', `/api/n/${token}`);
  assert.equal(api.status, 200);
  assert.equal(api.data.stage.track, 'Wales A');
  assert.equal(api.data.car.name, 'Mini Cooper S 1275');
  assert.ok(api.data.notes.length > 10);
  assert.equal(api.data.members, undefined);
  const pg = await casualPage(w.env, token, T0);
  assert.equal(pg.status, 200);
  assert.match(pg.body, /^<!doctype html>/i);
  assert.match(pg.body, /ACR DAILY/);
  assert.match(pg.body, /id="next"/);
  assert.equal((pg.body.match(/<li class="n">/g) || []).length, api.data.notes.length);
  const first = api.data.notes[0];
  assert.ok(pg.body.includes(String(first.text).toUpperCase().replace(/&/g, '&amp;').replace(/</g, '&lt;')));
  for (const s of [...pg.body.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1])) assert.doesNotThrow(() => new Function(s));
  // markup in a name never gets through
  const xss = await import('../src/casualpage.js');
  const hostile = xss.notesPage('abcdefghijkl', { stage: { menuName: '<img src=x onerror=alert(1)>' }, car: { name: '"><script>x</script>' },
    notes: [{ n: 1, at: 0, text: '<b>&' }] });
  assert.ok(!/<img|"><script>x/.test(hostile));
  assert.ok(hostile.includes('&lt;img src=x onerror=alert(1)&gt;') && hostile.includes('&lt;B&gt;&amp;'));
  // bad tokens, unknown tokens
  assert.equal((await w.call('GET', '/api/n/short')).status, 404);
  assert.equal((await w.call('GET', '/api/n/aaaaaaaaaaaa')).status, 404);
  assert.equal((await casualPage(w.env, 'aaaaaaaaaaaa', T0)).status, 404);
  assert.match((await casualPage(w.env, 'aaaaaaaaaaaa', T0)).body, /no longer available/);
  // valid while on, and 2 h after it ends; then gone
  await w.call('POST', `/api/casual/lobbies/${l.id}/start`, { who: 1, now: T0 + 1000 });
  assert.ok(await notesFor(w.env, token, T0 + 9 * H), 'on: valid');
  await w.call('POST', `/api/casual/lobbies/${l.id}/leave`, { who: 1, now: T0 + 4 * H });
  assert.ok(await notesFor(w.env, token, T0 + 4 * H + CX.noteMs - 1000), 'ended: still 2 h');
  assert.equal(await notesFor(w.env, token, T0 + 4 * H + CX.noteMs + 1000), null);
  assert.equal((await w.call('GET', `/api/n/${token}`, { now: T0 + 4 * H + CX.noteMs + 1000 })).status, 404);
  assert.equal((await casualPage(w.env, token, T0 + 4 * H + CX.noteMs + 1000)).status, 404);
});

test('COPILOT lobbies carry languages too', async () => {
  const w = world();
  const f = w.env;
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const deps = { json, err, hash, splits: [0.25], timing: {}, pool: async () => ({ tracks: TRACKS, byTrack: new Map(TRACKS.map((t) => [t, []])) }) };
  const call = (body) => {
    const url = new URL('https://acrdaily.test/api/copilot/lobbies');
    return copilotApi(new Request(url, { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }),
      f, url.pathname, url, w.me(1), true, T0, deps);
  };
  const a = await call({ role: 'driver', langs: ['pl', 'EN'] });
  assert.equal(a.status, 200, JSON.stringify(a.data));
  assert.deepEqual(a.data.lobby.langs, ['pl', 'en']);
  assert.deepEqual((await call({ role: 'driver' })).data.lobby.langs, [], 'optional');
  assert.equal((await call({ role: 'driver', langs: ['en', 'de', 'fr', 'es'] })).status, 400);
  assert.equal((await call({ role: 'driver', langs: ['qq'] })).status, 400);
});
