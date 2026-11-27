// #stream on Discord when ACR Daily goes live on Twitch (src/twitchdiscord.js): once per stream, in the channel found
// by name (emoji around it too), never a channel made, pings only as wrangler.toml says.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { KEY, streamChannel, streamMessage, syncStream } from '../src/twitchdiscord.js';

const NOW = Date.parse('2026-11-27T20:00:00Z');
const LIVE = { live: true, channel: 'acrdaily', url: 'https://www.twitch.tv/acrdaily', title: 'Dailies *live*',
  startedAt: '2026-11-27T19:50:00Z' };

function fakes(channels = [{ id: '11', name: '📺┃stream', type: 0 }, { id: '12', name: 'general', type: 0 }], postOk = true) {
  const posts = [], rows = new Map();
  const api = {
    channels: async () => ({ ok: true, status: 200, data: channels }),
    post: async (ch, msg) => { posts.push({ ch, msg }); return postOk ? { ok: true, status: 200, data: { id: '99' } } : { ok: false, status: 403 }; },
    createChannel: async () => { throw new Error('never makes a channel'); },
  };
  const store = { get: async (k) => rows.get(k) || null, set: async (k, id, hash, note) => { rows.set(k, { id, hash, note }); } };
  return { api, store, posts, rows };
}

test('a stream is posted once, in #stream found by its bare name; a new stream gets its own post', async () => {
  const f = fakes();
  assert.equal(await syncStream({ status: LIVE, api: f.api, store: f.store, now: NOW }), 'posted');
  assert.equal(f.posts.length, 1);
  assert.equal(f.posts[0].ch, '11');
  assert.match(f.posts[0].msg.content, /ACR DAILY is live on Twitch/);
  assert.match(f.posts[0].msg.content, /Dailies live\n/);                  // (Discord's markdown taken out of the title)
  assert.match(f.posts[0].msg.content, /https:\/\/www\.twitch\.tv\/acrdaily$/);
  assert.deepEqual(f.posts[0].msg.allowed_mentions, { parse: [] });
  assert.equal(f.rows.get(KEY).hash, '11/99');
  assert.equal(await syncStream({ status: LIVE, api: f.api, store: f.store, now: NOW + 300000 }), 'already posted');
  assert.equal(f.posts.length, 1);
  assert.equal(await syncStream({ status: { live: false }, api: f.api, store: f.store, now: NOW }), 'off air');
  const next = { ...LIVE, startedAt: '2026-11-28T18:00:00Z' };
  assert.equal(await syncStream({ status: next, api: f.api, store: f.store, now: Date.parse('2026-11-28T18:05:00Z') }), 'posted');
  assert.equal(f.posts.length, 2);
});

test('no #stream: an error, no channel made; Discord refusing: tried again on the next run', async () => {
  const none = fakes([{ id: '12', name: 'general', type: 0 }, { id: '13', name: 'stream', type: 2 }]);   // (a voice channel)
  const r = await syncStream({ status: LIVE, api: none.api, store: none.store, now: NOW });
  assert.match(r.error, /no #stream channel/);
  const no = fakes(undefined, false);
  assert.match((await syncStream({ status: LIVE, api: no.api, store: no.store, now: NOW })).error, /403: the bot needs/);
  assert.equal(no.rows.get(KEY), undefined);
  assert.deepEqual(await syncStream({ status: LIVE, api: null, store: no.store, now: NOW }),
    { skipped: 'the Discord bot is off (DISCORD_BOT_TOKEN)' });
});

test('a stream on for hours when first seen (a deploy mid-stream) is not posted', async () => {
  const f = fakes();
  const r = await syncStream({ status: LIVE, api: f.api, store: f.store, now: NOW + 7 * 3600000 });
  assert.ok(r.skipped);
  assert.equal(f.posts.length, 0);
  assert.equal(await syncStream({ status: LIVE, api: f.api, store: f.store, now: NOW + 7 * 3600000 }), 'already posted');
});

test('pings: nobody, everyone, here, a role', async () => {
  assert.doesNotMatch(streamMessage(LIVE, '').content, /@/);
  assert.match(streamMessage(LIVE, 'everyone').content, /^@everyone /);
  assert.deepEqual(streamMessage(LIVE, 'here').allowed_mentions, { parse: ['everyone'] });
  const role = streamMessage(LIVE, '1556808894205141145');
  assert.match(role.content, /^<@&1556808894205141145> /);
  assert.deepEqual(role.allowed_mentions, { parse: [], roles: ['1556808894205141145'] });
  assert.doesNotMatch(streamMessage(LIVE, 'nonsense').content, /@|<@/);
  assert.deepEqual(await streamChannel({ channels: async () => ({ ok: false, status: 500 }) }, 'stream'),
    { error: 'listing the channels: Discord answered 500' });
});
