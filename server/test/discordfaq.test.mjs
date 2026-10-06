// The FAQ on Discord (src/discordfaq.js): the message, and keeping it in #faq as the bot.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FAQ, faqMessage, faqApi, syncFaq } from '../src/discordfaq.js';

const SITE = 'https://acr-daily.example.dev';
const hashOf = async (s) => String(s.length) + ':' + s.slice(-40);

test('the message fits Discord and answers every question', () => {
  const m = faqMessage(SITE);
  assert.ok(m.embeds.length <= 10);
  const total = m.embeds.reduce((n, e) => n + (e.title || '').length + e.description.length + ((e.footer || {}).text || '').length, 0);
  assert.ok(total <= 6000, `total ${total}`);
  for (const e of m.embeds) assert.ok(e.description.length <= 4096);
  const text = m.embeds.map((e) => e.description).join('\n');
  for (const [q] of FAQ) assert.ok(text.includes(q), q);
  assert.ok(text.includes(SITE + '/guide'));
  assert.deepEqual(m.allowed_mentions, { parse: [] });        // never pings anyone
  assert.ok(!('username' in m) && !('avatar_url' in m));      // the bot's own name: not a person's
});

/** A fake Discord: channels, messages; records what was called. */
function fakeDiscord({ channels = [], canCreate = true, canOverwrite = true } = {}) {
  const calls = [], msgs = new Map();
  let next = 900;
  const fetchFn = async (url, init) => {
    const path = url.replace('https://discord.com/api/v10', ''), method = init.method;
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push(`${method} ${path}`);
    const res = (status, data) => ({ ok: status < 300, status, json: async () => data });
    if (path === '/users/@me') return res(200, { id: '555000000000000001' });
    if (path.endsWith('/channels') && method === 'GET') return res(200, channels);
    if (path.endsWith('/channels') && method === 'POST') {
      if (!canCreate || (body.permission_overwrites && !canOverwrite)) return res(403, {});
      const c = { id: String(next++), name: body.name, type: 0, overwrites: body.permission_overwrites };
      channels.push(c);
      return res(201, c);
    }
    let m = path.match(/^\/channels\/(\d+)\/messages$/);
    if (m && method === 'POST') { const id = String(next++); msgs.set(id, body); return res(200, { id }); }
    m = path.match(/^\/channels\/(\d+)\/messages\/(\d+)$/);
    if (m && method === 'PATCH') { if (!msgs.has(m[2])) return res(404, {}); msgs.set(m[2], body); return res(200, { id: m[2] }); }
    if (/\/pins\//.test(path)) return res(204, null);
    return res(404, {});
  };
  return { calls, msgs, channels, api: faqApi('x'.repeat(30), '123456789012345678', fetchFn) };
}

function memStore() {
  const m = new Map();
  return { m, get: async (k) => m.get(k) || null, set: async (k, id, hash) => { m.set(k, { id, hash }); } };
}

test('posts in an existing #faq, then leaves it alone until the text changes', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'general', type: 0 }, { id: '77', name: 'FAQ', type: 0 }] });
  const store = memStore();
  assert.equal(await syncFaq({ api: d.api, store, site: SITE, hashOf }), 'posted');
  assert.ok(d.calls.includes('POST /channels/77/messages'));
  assert.match(store.m.get('faq').id, /^77\/\d+$/);
  const n = d.calls.length;
  assert.equal(await syncFaq({ api: d.api, store, site: SITE, hashOf }), 'unchanged');
  assert.equal(d.calls.length, n);                             // no Discord call at all
  store.m.get('faq').hash = 'old text';
  assert.equal(await syncFaq({ api: d.api, store, site: SITE, hashOf }), 'edited');
});

test('makes a read-only #faq when there is none, or a plain one without Manage Roles', async () => {
  let d = fakeDiscord({ channels: [{ id: '42', name: 'general', type: 0 }] });
  assert.equal(await syncFaq({ api: d.api, store: memStore(), site: SITE, hashOf }), 'posted (made #faq)');
  const made = d.channels.find((c) => c.name === 'faq');
  assert.equal(made.overwrites[0].id, '123456789012345678');   // @everyone: may read, may not send
  assert.equal(made.overwrites[0].deny, String(1n << 11n));
  d = fakeDiscord({ channels: [], canOverwrite: false });
  assert.equal(await syncFaq({ api: d.api, store: memStore(), site: SITE, hashOf }), 'posted (made #faq)');
  assert.equal(d.channels[0].overwrites, undefined);
});

test('a deleted FAQ is posted again; no permission is an error, not a crash', async () => {
  const d = fakeDiscord({ channels: [{ id: '77', name: 'faq', type: 0 }] });
  const store = memStore();
  store.m.set('faq', { id: '77/123', hash: 'old' });           // the message was deleted
  assert.equal(await syncFaq({ api: d.api, store, site: SITE, hashOf }), 'posted');
  const none = fakeDiscord({ channels: [], canCreate: false });
  const st = memStore();
  const r = await syncFaq({ api: none.api, store: st, site: SITE, hashOf, now: 1000 });
  assert.match(r.error, /make a #faq text channel/);
  const n = none.calls.length;                                 // then it waits 15 minutes before asking again
  assert.match(await syncFaq({ api: none.api, store: st, site: SITE, hashOf, now: 1000 + 60000 }), /waiting/);
  assert.equal(none.calls.length, n);
  assert.ok((await syncFaq({ api: none.api, store: st, site: SITE, hashOf, now: 1000 + 16 * 60000 })).error);
});

test('no bot token: no API', () => {
  assert.equal(faqApi('', '123456789012345678'), null);
  assert.equal(faqApi('x'.repeat(30), 'nope'), null);
});
