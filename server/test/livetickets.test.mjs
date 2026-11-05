// Live relay tickets (src/livetickets.js): the app's driver, signed for the relay; the relay (live/relay.py) checks
// them with liveKey. node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import worker from '../src/index.js';
import { LIVE_TICKET_MS, liveKey, liveTicket, readLiveTicket } from '../src/livetickets.js';
import { fakeD1, sid } from './faked1.mjs';

const ENV = { ADMIN_KEY: 'k'.repeat(32) };

test('a ticket carries the driver, signed, for a few hours', async () => {
  const t = await liveTicket(ENV, { steam_id: sid(1), name: 'Khanh' }, 1000);
  assert.deepEqual(await readLiveTicket(ENV, t.ticket, 2000), { k: 'live', s: sid(1), n: 'Khanh', e: 1000 + LIVE_TICKET_MS });
  assert.equal(t.expires, 1000 + LIVE_TICKET_MS);
  assert.equal(await readLiveTicket(ENV, t.ticket, 1000 + LIVE_TICKET_MS), null, 'out of date');
  assert.equal(await readLiveTicket({ ADMIN_KEY: 'x'.repeat(32) }, t.ticket, 2000), null, 'another key');
  const [, s] = t.ticket.split('.');
  const other = Buffer.from(JSON.stringify({ k: 'live', s: sid(2), n: 'Someone', e: 9e15 })).toString('base64url');
  assert.equal(await readLiveTicket(ENV, `${other}.${s}`, 2000), null, 'another driver under its signature');
  for (const bad of ['', 'x', `${t.ticket}.x`]) assert.equal(await readLiveTicket(ENV, bad, 2000), null, bad);
});

test('the relay checks it with the hashed key alone, as relay.py does', async () => {
  const key = Buffer.from(await liveKey(ENV));
  assert.deepEqual(key, createHash('sha256').update('live-relay|' + 'k'.repeat(32)).digest());
  const { ticket } = await liveTicket(ENV, { steam_id: sid(3), name: 'Ana' });
  const [payload, s] = ticket.split('.');
  assert.equal(createHmac('sha256', key).update(payload).digest('base64url'), s);
  assert.notEqual(key.toString('hex'), Buffer.from('k'.repeat(32)).toString('hex'));
});

test('POST /api/live/ticket: signed-in drivers only, not banned ones', async () => {
  const { env, db } = fakeD1(ENV);
  const tok = 'a'.repeat(64), tok2 = 'b'.repeat(64);
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(1), 'Khanh');
  db.prepare('INSERT INTO players (steam_id, name, created, banned) VALUES (?, ?, 0, 1)').run(sid(2), 'Banned');
  for (const [t, s] of [[tok, sid(1)], [tok2, sid(2)]]) {
    db.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, 0)').run(createHash('sha256').update(t).digest('hex'), s);
  }
  const call = (token) => worker.fetch(new Request('https://acrdaily.com/api/live/ticket', {
    method: 'POST', headers: token ? { Authorization: 'Bearer ' + token } : {} }), env, { waitUntil() {} });
  assert.equal((await call(null)).status, 401);
  assert.equal((await call(tok2)).status, 403);
  const r = await call(tok);
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.name, 'Khanh');
  assert.equal((await readLiveTicket(ENV, j.ticket)).s, sid(1));
});
