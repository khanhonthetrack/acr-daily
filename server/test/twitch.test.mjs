// ACR Daily live on Twitch (src/twitch.js): Twitch's own API with an app token, asked at most once a minute, nothing
// asked without a channel and credentials, a stale token asked again, Twitch down: no strip.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { twitchStatus } from '../src/twitch.js';

function fakeCache() {
  const m = new Map();
  return { m, match: async (req) => (m.has(req.url) ? new Response(m.get(req.url)) : undefined),
    put: async (req, res) => { m.set(req.url, await res.text()); } };
}
function twitch({ live = true, tokens = ['t1'], refuse = 0, down = false } = {}) {
  const calls = [];
  let n = 0, refused = 0;
  const fetcher = async (url, o = {}) => {
    calls.push(url);
    if (down) throw new Error('offline');
    if (url.startsWith('https://id.twitch.tv/oauth2/token')) {
      assert.match(o.body, /grant_type=client_credentials/);
      return new Response(JSON.stringify({ access_token: tokens[Math.min(n++, tokens.length - 1)], expires_in: 5000000 }));
    }
    assert.ok(url.startsWith('https://api.twitch.tv/helix/streams?user_login=acrdaily'), url);
    assert.equal(o.headers['Client-Id'], 'cid');
    if (refused < refuse) { refused++; return new Response('{}', { status: 401 }); }
    return new Response(JSON.stringify({ data: live ? [{ type: 'live', title: 'Skoda Saturday Challenge LIVE', game_name: 'Assetto Corsa Rally',
      viewer_count: 42, started_at: '2026-11-28T11:55:00Z' }] : [] }));
  };
  return { fetcher, calls };
}
const ENV = { TWITCH_CHANNEL: 'ACRDaily', TWITCH_CLIENT_ID: 'cid', TWITCH_CLIENT_SECRET: 'sec' };

test('live: the stream\'s title, game and viewers; Twitch asked once a minute', async () => {
  const cache = fakeCache(), t = twitch();
  const a = await twitchStatus(ENV, { fetcher: t.fetcher, cache });
  assert.deepEqual(a, { live: true, channel: 'acrdaily', url: 'https://www.twitch.tv/acrdaily', title: 'Skoda Saturday Challenge LIVE',
    game: 'Assetto Corsa Rally', viewers: 42, startedAt: '2026-11-28T11:55:00Z' });
  assert.deepEqual(await twitchStatus(ENV, { fetcher: t.fetcher, cache }), a);
  assert.equal(t.calls.length, 2, 'a token and the stream, once');
});

test('offline, Twitch down, no channel or credentials: no strip (and nothing asked without them)', async () => {
  assert.equal((await twitchStatus(ENV, { fetcher: twitch({ live: false }).fetcher, cache: fakeCache() })).live, false);
  assert.equal((await twitchStatus(ENV, { fetcher: twitch({ down: true }).fetcher, cache: fakeCache() })).live, false);
  for (const env of [{ ...ENV, TWITCH_CHANNEL: '' }, { ...ENV, TWITCH_CLIENT_SECRET: '' }, { ...ENV, TWITCH_CHANNEL: 'no spaces!' }]) {
    const t = twitch();
    assert.equal((await twitchStatus(env, { fetcher: t.fetcher, cache: fakeCache() })).live, false);
    assert.equal(t.calls.length, 0);
  }
});

test('a stale token: a new one, then the stream', async () => {
  const t = twitch({ refuse: 1, tokens: ['old', 'new'] });
  assert.equal((await twitchStatus(ENV, { fetcher: t.fetcher, cache: fakeCache() })).live, true);
  assert.equal(t.calls.filter((u) => u.startsWith('https://id.twitch.tv')).length, 2);
});

test('the home page with its strips: its scripts parse (a slash lost in the page template once broke them all)', async () => {
  const { default: worker } = await import('../src/index.js');
  const { fakeD1 } = await import('./faked1.mjs');
  const r = await worker.fetch(new Request('https://acrdaily.com/'), fakeD1({ SITE_URL: 'https://acrdaily.com' }).env, { waitUntil() {} });
  const html = await r.text();
  assert.match(html, /id="twstrip"/);
  for (const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) assert.doesNotThrow(() => new Function(m[1]));   // eslint-disable-line no-new-func
  const api = await worker.fetch(new Request('https://acrdaily.com/api/twitch'), fakeD1({}).env, { waitUntil() {} });
  assert.deepEqual(await api.json(), { live: false, channel: null, url: null });      // (no channel set: off)
});
