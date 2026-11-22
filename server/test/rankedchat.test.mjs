// A ranked session's chat (src/liverallies.js chatApi): its drivers write and read it, nobody else; one line, 200
// characters at most, no swearing; one line a driver every 2 s, 500 a session; read in pages by ?after=id.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { LIVE, liveApi } from '../src/liverallies.js';
import { fakeD1, sid } from './faked1.mjs';

const H = Date.UTC(2026, 10, 18, 8, 0);              // Wed 18 Nov 2026, 08:00 UTC: a Rally2 session
const MIN = 60000;
const [ANN, BEN, CAT] = [sid(1), sid(2), sid(3)];

function world() {
  const f = fakeD1({ LIVE_FROM: '2026-11-18' });
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CAT, 'Cat']]) {
    f.db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  }
  return f;
}
const player = (db, s) => (s ? { ...db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s) } : null);
const live = async (f, path, me, now, body = null) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.5.30 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await liveApi(req, f.env, url.pathname, player(f.db, me), now);
  return { status: res.status, body: await res.json() };
};
const S = `/api/liverallies/rally2/${H}`;
const say = (f, who, body, now) => live(f, `${S}/chat`, who, now, { body });
const read = (f, who, now, after) => live(f, `${S}/chat${after == null ? '' : `?after=${after}`}`, who, now);
/** Ann and Ben signed up to the 08:00 Rally2 session; Cat not. */
async function signedUp() {
  const f = world();
  for (const who of [ANN, BEN]) {
    const r = await live(f, `${S}/signup`, who, H - 10 * MIN, { car: 'Skoda Fabia RS Rally2' });
    assert.equal(r.status, 200, JSON.stringify(r.body));
  }
  return f;
}

test('its drivers write and read it, oldest first, with their names as they were', async () => {
  const f = await signedUp();
  const t = H - 5 * MIN;
  const a = await say(f, ANN, '  good luck   all ', t);
  assert.equal(a.status, 200, JSON.stringify(a.body));
  assert.deepEqual(a.body.message, { id: a.body.message.id, steamId: ANN, name: 'Ann', body: 'good luck all', at: t });
  assert.equal((await say(f, BEN, 'you too', t + 1000)).status, 200);
  f.db.prepare("UPDATE players SET name = 'Benjamin' WHERE steam_id = ?").run(BEN);   // (the chat keeps the old name)
  const r = await read(f, BEN, t + 2000);
  assert.equal(r.status, 200);
  assert.deepEqual(r.body.messages.map((x) => [x.steamId, x.name, x.body]), [[ANN, 'Ann', 'good luck all'], [BEN, 'Ben', 'you too']]);
  assert.equal(r.body.pollS, LIVE.chat.pollS);
  // once the rally runs too, and after its close read (the app asking slowly), not written
  assert.equal((await say(f, ANN, 'go go go', H + 10 * MIN)).status, 200);
  const closes = H + LIVE.openMs;
  assert.equal((await say(f, ANN, 'gg', closes)).status, 409);
  const after = await read(f, ANN, closes + MIN);
  assert.deepEqual([after.body.messages.length, after.body.pollS], [3, LIVE.pollS.idle]);
});

test('nobody else: not signed in 401, not signed up 403, withdrawn 403', async () => {
  const f = await signedUp();
  const t = H - 5 * MIN;
  assert.equal((await read(f, null, t)).status, 401);
  assert.equal((await say(f, null, 'hello', t)).status, 401);
  assert.equal((await read(f, CAT, t)).status, 403);
  assert.equal((await say(f, CAT, 'hello', t)).status, 403);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM live_chat').get().n, 0);
  await live(f, `${S}/withdraw`, BEN, t, {});
  assert.equal((await read(f, BEN, t + 1000)).status, 403);
  // another session's drivers don't read this one's
  assert.equal((await live(f, `/api/liverallies/junior/${H + 3600000}/chat`, ANN, t)).status, 403);
  f.db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(ANN);
  assert.equal((await say(f, ANN, 'hello', t + 5000)).status, 403);
});

test('one line, 1 to 200 characters, no swearing', async () => {
  const f = await signedUp();
  const t = H - 5 * MIN;
  for (const body of ['', '    ', '\n\t', undefined, 42]) {
    const r = await say(f, ANN, body, t);
    assert.deepEqual([r.status, r.body.error], [400, 'write something'], String(body));
  }
  const long = await say(f, ANN, 'x'.repeat(201), t);
  assert.deepEqual([long.status, long.body.error], [400, 'a line is 200 characters at most']);
  assert.equal((await say(f, ANN, `  ${'x'.repeat(200)}  `, t)).status, 200);              // (200 after the trim)
  for (const [i, body] of ['what the fuck', 'sh1t stage', 'kurwa mać'].entries()) {
    const r = await say(f, BEN, body, t + i * 3000);
    assert.equal(r.status, 400, body);
    assert.match(r.body.error, /swearing/);
  }
  assert.equal((await say(f, BEN, 'shiitake on the Wankel', t + 10000)).status, 200);   // (ordinary words)
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM live_chat').get().n, 2);
});

test('one line a driver every 2 seconds; 500 a session, then full', async () => {
  const f = await signedUp();
  const t = H - 5 * MIN;
  assert.equal((await say(f, ANN, 'one', t)).status, 200);
  const fast = await say(f, ANN, 'two', t + 1999);
  assert.deepEqual([fast.status, fast.body.error], [429, 'too fast']);
  assert.equal((await say(f, BEN, 'mine', t + 500)).status, 200);                         // (each driver their own)
  assert.equal((await say(f, ANN, 'two', t + 2001)).status, 200);
  // full: 500 lines (filled here directly), then 409 for everyone
  const ins = f.db.prepare('INSERT INTO live_chat (series, starts, steam_id, name, body, created) VALUES (?, ?, ?, ?, ?, ?)');
  for (let i = 3; i < LIVE.chat.maxLines; i++) ins.run('rally2', H, BEN, 'Ben', `line ${i}`, t);
  const full = await say(f, ANN, 'more', t + 60000);
  assert.deepEqual([full.status, full.body.error], [409, 'the chat is full (500 lines)']);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM live_chat').get().n, LIVE.chat.maxLines);
});

test('?after=id: the lines after it, 100 at most, oldest first; none: the latest 100', async () => {
  const f = await signedUp();
  const t = H - 5 * MIN;
  const ins = f.db.prepare('INSERT INTO live_chat (series, starts, steam_id, name, body, created) VALUES (?, ?, ?, ?, ?, ?)');
  for (let i = 1; i <= 250; i++) ins.run('rally2', H, i % 2 ? ANN : BEN, i % 2 ? 'Ann' : 'Ben', `line ${i}`, t + i);
  ins.run('junior', H + 3600000, CAT, 'Cat', 'another session', t);                       // (never in this one's)
  const latest = (await read(f, ANN, t + MIN)).body.messages;
  assert.deepEqual([latest.length, latest[0].body, latest[99].body], [100, 'line 151', 'line 250']);
  const ids = latest.map((x) => x.id);
  assert.deepEqual(ids, [...ids].sort((a, b) => a - b));
  const first = (await read(f, ANN, t + MIN, 0)).body.messages;                            // (after=0: as none)
  assert.equal(first[99].body, 'line 250');
  const from1 = (await read(f, ANN, t + MIN, latest[0].id - 151 + 1)).body.messages;       // after line 1
  assert.deepEqual([from1.length, from1[0].body, from1[99].body], [100, 'line 2', 'line 101']);
  const next = (await read(f, ANN, t + MIN, from1[99].id)).body.messages;
  assert.deepEqual([next.length, next[0].body], [100, 'line 102']);
  const tail = (await read(f, ANN, t + MIN, latest[99].id)).body.messages;
  assert.deepEqual(tail, []);
  // a new line comes in after the last one read
  const r = await say(f, BEN, 'new', t + MIN);
  assert.deepEqual((await read(f, ANN, t + MIN + 1000, latest[99].id)).body.messages.map((x) => [x.id, x.body]), [[r.body.message.id, 'new']]);
});
