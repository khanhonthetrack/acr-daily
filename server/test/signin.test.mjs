// Sign-in tickets (index.js signInTicket / readTicket): what a sign-in needs until Steam answers travels in the address
// Steam sends the browser back to, signed, for ten minutes; opening a sign-in (app or website) writes nothing.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { readTicket, signInTicket } from '../src/index.js';
import { fakeD1 } from './faked1.mjs';

const ENV = { ADMIN_KEY: 'k'.repeat(32) };
const C = 'a'.repeat(64);

test('a ticket carries the sign-in, signed, for ten minutes', async () => {
  const t = await signInTicket(ENV, { s: 'state-1234567890abcd', p: 51234, c: C }, 1000);
  assert.deepEqual(await readTicket(ENV, t, 2000), { s: 'state-1234567890abcd', p: 51234, c: C, e: 601000 });
  assert.equal(await readTicket(ENV, t, 601000), null, 'over ten minutes old');
  assert.equal(await readTicket({ ADMIN_KEY: 'x'.repeat(32) }, t, 2000), null, 'not signed with our key');
  const [, sig] = t.split('.');
  const mine = Buffer.from(JSON.stringify({ s: 'state-1234567890abcd', p: 6666, c: C, e: 9e15 })).toString('base64url');
  assert.equal(await readTicket(ENV, `${mine}.${sig}`, 2000), null, 'changed (another port, no end), its old signature');
  for (const bad of ['', 'garbage', `${t}.x`, t.split('.')[0]]) assert.equal(await readTicket(ENV, bad, 2000), null, bad);
  const web = await signInTicket(ENV, { s: 'w'.repeat(40), n: '/leagues' }, 1000);
  assert.equal((await readTicket(ENV, web, 2000)).n, '/leagues');
  assert.equal(await readTicket(ENV, await signInTicket(ENV, { s: 'w'.repeat(40) }, 1000), 2000), null, 'neither the app\'s nor a page');
});

test('opening a sign-in writes nothing: the app\'s or the website\'s, however often', async () => {
  const { env, db } = fakeD1(ENV);
  const paths = ['/auth/steam/start?state=state-1234567890abcd&port=51234&challenge=' + C, '/login?next=/leagues'];
  for (let k = 0; k < 20; k++) {
    for (const path of paths) {
      const r = await worker.fetch(new Request('https://acrdaily.com' + path), env, { waitUntil() {} });
      assert.equal(r.status, 302);
      const to = new URL(r.headers.get('Location'));
      assert.equal(to.origin + to.pathname, 'https://steamcommunity.com/openid/login');
      assert.match(to.searchParams.get('openid.return_to'), /^https:\/\/acrdaily\.com\/auth\/steam\/callback\?t=[\w-]+\.[\w-]+$/);
    }
  }
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM logins').get().n, 0);
});

test('Steam says yes: the website gets its cookie, the app is sent home; once only; never with another ticket', async () => {
  const { env, db } = fakeD1(ENV);
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (u) => {                       // Steam: the check says genuine; the profile has a name
    const s = String(u);
    if (s.startsWith('https://steamcommunity.com/openid/login')) return new Response('ns:http://specs.openid.net/auth/2.0\nis_valid:true\n');
    if (s.includes('?xml=1')) return new Response('<profile><steamID><![CDATA[Ann]]></steamID></profile>');
    throw new Error('unexpected fetch ' + s);
  };
  try {
    const answer = (ticket, signedBack = null) => {         // Steam's redirect back, signing `signedBack` (else this one)
      const cb = `https://acrdaily.com/auth/steam/callback?t=${ticket}`;
      const q = new URLSearchParams({ 'openid.ns': 'http://specs.openid.net/auth/2.0', 'openid.mode': 'id_res',
        'openid.claimed_id': 'https://steamcommunity.com/openid/id/76561198000000001', 'openid.return_to': signedBack || cb, 'openid.sig': 'x' });
      return worker.fetch(new Request(`${cb}&${q}`), env, { waitUntil() {} });
    };
    const web = await signInTicket(ENV, { s: 'w'.repeat(40), n: '/leagues' });
    let r = await answer(web);
    assert.equal(r.status, 302);
    assert.equal(r.headers.get('Location'), '/leagues');
    assert.match(r.headers.get('Set-Cookie'), /^acr_session=[0-9a-f]{64};/);
    assert.match(await (await answer(web)).text(), /Sign-in expired/, 'the same answer again');
    const app = await signInTicket(ENV, { s: 'state-1234567890abcd', p: 51234, c: C });
    assert.match(await (await answer(app, `https://acrdaily.com/auth/steam/callback?t=${web}`)).text(), /did not confirm/,
      'Steam signed another sign-in\'s address');
    r = await answer(app);
    assert.match(r.headers.get('Location'), /^http:\/\/127\.0\.0\.1:51234\/signed-in\?state=state-1234567890abcd&code=[0-9a-f]{64}$/);
    const row = db.prepare('SELECT steam_id, name, token, challenge FROM logins WHERE state = ?').get('state-1234567890abcd');
    assert.equal(row.steam_id, '76561198000000001');
    assert.equal(row.name, 'Ann');
    assert.match(row.token, /^[0-9a-f]{64}$/);              // waiting for the app's code and verifier
    assert.equal(row.challenge, C);
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM sessions').get().n, 2);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a callback without a good ticket goes no further (nothing asked of Steam, nothing written)', async () => {
  const { env, db } = fakeD1(ENV);
  for (const q of ['', '?t=garbage', '?state=abcdefghijklmnop1234']) {
    const r = await worker.fetch(new Request('https://acrdaily.com/auth/steam/callback' + q), env, { waitUntil() {} });
    assert.match(await r.text(), /Sign-in expired/);
  }
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM logins').get().n, 0);
});
