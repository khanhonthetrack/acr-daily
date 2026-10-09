import { test } from 'node:test';
import assert from 'node:assert/strict';
import { STEAM_TRIES, verifySteam } from '../src/steam.js';

const ID = '76561198000000001';
const callback = (over = {}) => {
  const u = new URL('https://acrdaily.com/auth/steam/callback?state=abc');
  const q = { 'openid.ns': 'http://specs.openid.net/auth/2.0', 'openid.mode': 'id_res',
    'openid.claimed_id': `https://steamcommunity.com/openid/id/${ID}`, 'openid.identity': `https://steamcommunity.com/openid/id/${ID}`,
    'openid.return_to': 'https://acrdaily.com/auth/steam/callback?state=abc', 'openid.sig': 'x', ...over };
  for (const [k, v] of Object.entries(q)) if (v != null) u.searchParams.set(k, v);
  return u;
};
/** A fetch that answers with the given [status, text] pairs in turn, and records what it was sent. */
const steam = (...answers) => {
  const calls = [];
  const fetchFn = async (url, init) => {
    calls.push({ url, init });
    const a = answers[Math.min(calls.length, answers.length) - 1];
    if (a instanceof Error) throw a;
    return new Response(a[1], { status: a[0] });
  };
  return { fetchFn, calls, wait: async () => {} };
};
const VALID = 'ns:http://specs.openid.net/auth/2.0\nis_valid:true\n';
const NOT_VALID = 'ns:http://specs.openid.net/auth/2.0\nis_valid:false\n';

test('a genuine sign-in: Steam confirms it', async () => {
  const s = steam([200, VALID]);
  assert.deepEqual(await verifySteam(callback(), s), { steamId: ID });
  assert.equal(s.calls.length, 1);
  const sent = new URLSearchParams(s.calls[0].init.body);
  assert.equal(sent.get('openid.mode'), 'check_authentication');
  assert.match(s.calls[0].init.headers['User-Agent'], /ACR-Daily/);
});

test('Steam turning the check away (403) is asked again, and a later yes counts', async () => {
  const s = steam([403, '<html>Access Denied</html>'], [200, VALID]);
  assert.deepEqual(await verifySteam(callback(), s), { steamId: ID });
  assert.equal(s.calls.length, 2);
});

test('Steam turning it away every time: the error says so', async () => {
  const s = steam([403, '<html>Access Denied</html>']);
  assert.deepEqual(await verifySteam(callback(), s), { error: 'steam 403' });
  assert.equal(s.calls.length, STEAM_TRIES);
  const down = steam(new TypeError('network'));
  assert.deepEqual(await verifySteam(callback(), down), { error: 'steam unreachable' });
});

test('Steam saying no is final (not asked again)', async () => {
  const s = steam([200, NOT_VALID]);
  assert.deepEqual(await verifySteam(callback(), s), { error: 'invalid' });
  assert.equal(s.calls.length, 1);
});

test('cancelled on Steam, or a reply that is not ours: no check with Steam', async () => {
  const s = steam([200, VALID]);
  assert.deepEqual(await verifySteam(callback({ 'openid.mode': 'cancel' }), s), { error: 'cancelled' });
  assert.deepEqual(await verifySteam(callback({ 'openid.claimed_id': 'https://evil.example/id/1' }), s), { error: 'bad' });
  assert.deepEqual(await verifySteam(callback({ 'openid.return_to': 'https://evil.example/auth/steam/callback' }), s), { error: 'bad' });
  assert.equal(s.calls.length, 0);
});
