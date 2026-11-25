// Claude's lines for the dailies' overlay (src/commentary.js), with a stand-in Claude and cache: asked only when
// something happens, at most once every 15 s, the events it is told, off without a key, nothing said on a decline.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { dailiesCommentary, events, snapshot } from '../src/commentary.js';
import { fakeD1 } from './faked1.mjs';
import worker from '../src/index.js';

const DAY = { date: '2026-11-25', dailies: [
  { slot: 1, stage: 'Col de Turini', rally: 'Monte Carlo', car: 'Lancia 037', lengthM: 9800, weather: 'Clear', time: 'Morning' },
  { slot: 2, stage: 'Ouninpohja', rally: 'Finland', car: 'Audi Quattro', lengthM: 11200, weather: 'LightRain', time: 'Noon' }] };

function world() {
  const w = { boards: { 1: [], 2: [] }, live: { 1: [], 2: [] } };
  w.ask = async (p) => {
    if (p === '/api/v1/dailies') return DAY;
    const m = p.match(/^\/api\/v1\/dailies\/2026-11-25\/(\d)(\/live)?$/);
    if (!m) return null;
    return m[2] ? { drivers: w.live[m[1]] } : { results: w.boards[m[1]] };
  };
  return w;
}
function fakeCache() {
  const m = new Map();
  return { m, match: async (r) => (m.has(r.url) ? new Response(m.get(r.url)) : undefined), put: async (r, res) => { m.set(r.url, await res.text()); } };
}
function fakeClaude(reply = (n) => `Line ${n}`) {
  const c = { calls: [] };
  c.beta = { messages: { create: async (body) => {
    c.calls.push(body);
    const r = typeof reply === 'function' ? reply(c.calls.length, body) : reply;
    return r.stop_reason ? r : { stop_reason: 'end_turn', content: [{ type: 'text', text: r }] };
  } } };
  return c;
}
const run = (w, o) => dailiesCommentary({ ANTHROPIC_API_KEY: 'k' }, w.ask, o);

test('off without a key or without a cache; nothing asked of Claude', async () => {
  const w = world(), client = fakeClaude();
  assert.deepEqual(await dailiesCommentary({}, w.ask, { cache: fakeCache() }), { on: false });
  assert.deepEqual(await run(w, { client, cache: null }), { on: false });
  assert.equal(client.calls.length, 0);
});

test('asked once per happening, at most every 15 s; what happened in between goes into the next line', async () => {
  const w = world(), client = fakeClaude(), cache = fakeCache();
  let t = 1_000_000;
  const a = await run(w, { client, cache, now: t });                 // the day's first line
  assert.equal(a.on, true);
  assert.equal(a.line, 'Line 1');
  assert.equal(client.calls[0].model, 'claude-haiku-5-5');            // (Haiku: no server-side fallback to ask for)
  assert.equal(client.calls[0].fallbacks, undefined);
  assert.equal(client.calls[0].betas, undefined);
  assert.deepEqual(client.calls[0].output_config, { effort: 'low' });
  assert.deepEqual(JSON.parse(client.calls[0].messages[0].content).events, []);
  assert.deepEqual(await run(w, { client, cache, now: t += 30000 }), a);   // nothing happened: the same line, no call
  assert.equal(client.calls.length, 1);

  w.live[1] = [{ steamId: 's1', name: 'Kalle', state: 'live', progress: 0.1, totalMs: 20000 }];
  const b = await run(w, { client, cache, now: t += 1000 });
  assert.equal(b.line, 'Line 2');
  assert.deepEqual(JSON.parse(client.calls[1].messages[0].content).events, [{ what: 'started the stage', stage: 'SS1', driver: 'Kalle' }]);

  // his clock runs: no new line; he finishes 5 s later: too soon, it waits
  w.live[1] = [{ steamId: 's1', name: 'Kalle', state: 'live', progress: 0.9, totalMs: 230000 }];
  assert.equal((await run(w, { client, cache, now: t += 2000 })).line, 'Line 2');
  w.live[1] = [];
  w.boards[1] = [{ steamId: 's1', name: 'Kalle', status: 'finished', totalMs: 251002 }];
  assert.equal((await run(w, { client, cache, now: t += 3000 })).line, 'Line 2');
  assert.equal(client.calls.length, 2);
  const c = await run(w, { client, cache, now: t += 15000 });
  assert.equal(c.line, 'Line 3');
  assert.deepEqual(c.names, []);
  const sent = JSON.parse(client.calls[2].messages[0].content);
  assert.deepEqual(sent.events, [{ what: 'first time on the board', stage: 'SS1', driver: 'Kalle', time: '4:11.002' }]);
  assert.deepEqual(sent.recentLines, ['Line 2', 'Line 1']);
  assert.deepEqual(sent.stages[0].board, [{ pos: 1, name: 'Kalle', time: '4:11.002', gap: null }]);
});

test('another model set in COMMENTARY_MODEL: it is used, with the API\'s fallback where the model has one', async () => {
  const w = world(), client = fakeClaude();
  await dailiesCommentary({ ANTHROPIC_API_KEY: 'k', COMMENTARY_MODEL: 'claude-opus-5-5' }, w.ask, { client, cache: fakeCache(), now: 0 });
  assert.equal(client.calls[0].model, 'claude-opus-5-5');
  assert.equal(client.calls[0].fallbacks, 'default');
  assert.deepEqual(client.calls[0].betas, ['server-side-fallback-2026-07-01']);
});

test('the events: a new fastest time, a finish with its place and gap, a better time, a driver out', () => {
  const live = { 1: {}, 2: {} };
  const before = snapshot(DAY, { 1: { results: [
    { steamId: 'a', name: 'uzuramcrae', status: 'finished', totalMs: 252158 },
    { steamId: 'b', name: 'osiek', status: 'finished', totalMs: 260000 }] }, 2: { results: [] } }, live);
  const now = snapshot(DAY, { 1: { results: [
    { steamId: 'a', name: 'uzuramcrae', status: 'finished', totalMs: 252158 },
    { steamId: 'b', name: 'osiek', status: 'finished', totalMs: 255000 },
    { steamId: 'c', name: 'Kalle', status: 'finished', totalMs: 251002 },
    { steamId: 'd', name: 'Mia', status: 'finished', totalMs: 270500 },
    { steamId: 'e', name: 'MaybeIWill', status: 'dnf' }] }, 2: { results: [] } }, live);
  assert.deepEqual(events(before, now), [
    { what: 'new fastest time', stage: 'SS1', driver: 'Kalle', time: '4:11.002', beat: 'uzuramcrae', by: '1.156' },
    { what: 'improved', stage: 'SS1', driver: 'osiek', time: '4:15.000', pos: 3, by: '5.000' },
    { what: 'finished', stage: 'SS1', driver: 'Mia', time: '4:30.500', pos: 4, behindLeader: '19.498', leader: 'Kalle' },
    { what: 'out of the stage (DNF)', stage: 'SS1', driver: 'MaybeIWill' }]);
});

test('a decline or Claude not answering: no new line, tried again after 15 s; names in the line are marked', async () => {
  const w = world(), cache = fakeCache();
  w.boards[1] = [{ steamId: 'x', name: 'osiek', status: 'finished', totalMs: 535000 }];
  const refuse = fakeClaude({ stop_reason: 'refusal', content: [] });
  assert.deepEqual(await run(w, { client: refuse, cache, now: 0 }), { on: true, id: null, line: null, names: [], at: null });
  const down = fakeClaude(() => { throw new Error('overloaded'); });
  assert.equal((await run(w, { client: down, cache, now: 5000 })).line, null);
  assert.equal(down.calls.length, 0);                                // (within 15 s of the last try)
  const ok = fakeClaude('  "osiek owns SS1 with an 8:55.000 nobody has touched."  ');
  const r = await run(w, { client: ok, cache, now: 20000 });
  assert.equal(r.line, 'osiek owns SS1 with an 8:55.000 nobody has touched.');
  assert.deepEqual(r.names, ['osiek']);
  assert.deepEqual(JSON.parse(ok.calls[0].messages[0].content).events, []);   // (still the day's first line)
});

test('SS1 only: SS2\'s board, its cars and what happens on it never reach Claude', async () => {
  const w = world(), client = fakeClaude(), cache = fakeCache();
  w.boards[2] = [{ steamId: 'x', name: 'osiek', status: 'finished', totalMs: 535000 }];
  await run(w, { client, cache, now: 0 });
  w.live[2] = [{ steamId: 'y', name: 'Mia', state: 'live', progress: 0.2, totalMs: 60000 }];
  w.boards[2] = [...w.boards[2], { steamId: 'z', name: 'Kalle', status: 'finished', totalMs: 520000 }];
  await run(w, { client, cache, now: 30000 });
  assert.equal(client.calls.length, 1);                              // (nothing on SS1 happened: no second line)
  const sent = JSON.parse(client.calls[0].messages[0].content);
  assert.deepEqual(sent.stages.map((s) => s.stage), ['SS1']);
  assert.doesNotMatch(client.calls[0].messages[0].content, /osiek|Mia|Kalle/);
});

test('the endpoint: off without a key, and off on another address than the site\'s', async () => {
  const get = async (url, extra = {}) => (await worker.fetch(new Request(url),
    fakeD1({ SITE_URL: 'https://acrdaily.com', ...extra }).env, { waitUntil() {} })).json();
  assert.deepEqual(await get('https://acrdaily.com/api/broadcast/dailies/commentary'), { on: false });
  assert.deepEqual(await get('https://acr-daily.acr-daily-server.workers.dev/api/broadcast/dailies/commentary', { ANTHROPIC_API_KEY: 'k' }), { on: false });
});
