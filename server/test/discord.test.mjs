// The Discord bot's messages and its webhook calls (no Discord needed).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { boardMessage, dayMessage, flag, sheetLines, webhook } from '../src/discord.js';
import { discordInvite, discordUrl } from '../src/release.js';
import { sitePage } from '../src/site.js';

const head = (slot, menuName) => ({ slot, track: 'x', menuName, car: 'Hyundai i20 N Rally2', weatherLabel: 'Light fog', timeLabel: 'Midday (12:00)' });
const fin = (rank, name, totalMs, extra = {}) => ({ status: 'finished', rank, name, country: 'fi', totalMs, gapMs: totalMs - 289637, resets: 0, ...extra });
// (the penalty shown is total - stage clock: here the game's +29 s)
const BOARD1 = [fin(1, 'osiek', 289637, { country: 'it', clockMs: 289637 }),
  fin(2, 'MaybeIWill', 347348, { resets: 1, country: null, clockMs: 318348 }),
  { status: 'dnf', name: 'Gone', rank: null }];

test('the Discord invite: only discord.gg / discord.com/invite links; the website links it when set', () => {
  assert.equal(discordUrl({ DISCORD_URL: 'https://discord.gg/AbC123' }), 'https://discord.gg/AbC123');
  assert.equal(discordUrl({ DISCORD_URL: ' https://discord.com/invite/xyz-9 ' }), 'https://discord.com/invite/xyz-9');
  assert.equal(discordUrl({ DISCORD_URL: 'https://evil.example/discord.gg/x' }), '');
  assert.equal(discordUrl({ DISCORD_URL: 'https://discord.gg/x"><script>' }), '');
  assert.equal(discordUrl({}), '');
  // the website links /discord, which picks the invite; no Discord set = no link
  assert.match(sitePage({ DISCORD_URL: 'https://discord.gg/AbC123' }), /href="\/discord"[^>]*><svg[\s\S]*?<span>Discord<\/span>/);
  assert.match(sitePage({ DISCORD_GUILD_ID: '1556808894205141145' }), /href="\/discord"/);
  assert.doesNotMatch(sitePage({}), /href="\/discord"|discord\.gg/);
});

test('the invite: the server widget\'s (names nobody) when it is on, else the fixed one', async () => {
  const env = { DISCORD_URL: 'https://discord.gg/Personal1', DISCORD_GUILD_ID: '1556808894205141145' };
  const on = async (url) => {
    assert.equal(url, 'https://discord.com/api/guilds/1556808894205141145/widget.json');
    return new Response(JSON.stringify({ instant_invite: 'https://discord.com/invite/Widget99' }), { status: 200 });
  };
  const off = async () => new Response('{"message":"Widget Disabled","code":50004}', { status: 403 });
  const down = async () => { throw new Error('offline'); };
  const bad = async () => new Response(JSON.stringify({ instant_invite: 'https://evil.example/x' }), { status: 200 });
  assert.equal(await discordInvite(env, on), 'https://discord.com/invite/Widget99');
  assert.equal(await discordInvite(env, off), 'https://discord.gg/Personal1');
  assert.equal(await discordInvite(env, down), 'https://discord.gg/Personal1');
  assert.equal(await discordInvite(env, bad), 'https://discord.gg/Personal1');
  assert.equal(await discordInvite({ DISCORD_URL: 'https://discord.gg/Personal1' }, on), 'https://discord.gg/Personal1');
});

test('the bot posts as ACR Daily with the logo; edits leave the sender alone', async () => {
  const m = boardMessage({ date: '2026-10-06', site: 'https://s', stages: [] });
  assert.equal(m.username, 'ACR Daily');
  assert.equal(m.avatar_url, 'https://s/brand/acr-daily-icon-512.png');
  assert.equal(m.embeds[0].footer.icon_url, 'https://s/brand/acr-daily-icon-512.png');
  assert.equal(dayMessage({ date: '2026-10-05', site: 'https://s', stages: [] }).avatar_url, 'https://s/brand/acr-daily-icon-512.png');
  const calls = [];
  const hook = webhook('https://discord.com/api/webhooks/1/a', async (url, init) => {
    calls.push(JSON.parse(init.body));
    return new Response(JSON.stringify({ id: '1' }), { status: 200 });
  });
  await hook.post(m);
  await hook.edit('1', m);
  assert.equal(calls[0].avatar_url, 'https://s/brand/acr-daily-icon-512.png');
  assert.equal('avatar_url' in calls[1] || 'username' in calls[1], false);
});

test('flags from country codes', () => {
  assert.equal(flag('it'), '🇮🇹 ');
  assert.equal(flag('FI'), '🇫🇮 ');
  assert.equal(flag(null), '');
  assert.equal(flag('xyz'), '');
});

test('timing sheet: rank, time, gap, reset penalty, DNFs; names cannot format or mention', () => {
  const lines = sheetLines(BOARD1);
  assert.equal(lines[0], '` 1` 🇮🇹 **osiek**  `4:49.637`');
  assert.equal(lines[1], '` 2` **MaybeIWill**  `5:47.348`  +57.711  (+29 s)');
  assert.equal(lines[2], '*1 DNF*');
  assert.deepEqual(sheetLines([]), ['No times yet.']);
  const many = Array.from({ length: 13 }, (_, i) => fin(i + 1, 'D' + i, 300000 + i));
  assert.equal(sheetLines(many).at(-1), '*3 more*');
  assert.match(sheetLines([fin(1, '@everyone *x*', 1000)])[0], /\*\*everyone x\*\*/);
});

test('live board: who is on stage, then both timing sheets', () => {
  const m = boardMessage({ date: '2026-10-06', site: 'https://s', stages: [
    { slot: 1, head: head(1, 'St. Geniez - Sisteron'), board: BOARD1,
      live: [{ state: 'live', name: 'Kalle', country: 'fi', progress: 0.42, totalMs: 133400, resets: 1 }, { state: 'finished', name: 'Old' }] },
    { slot: 2, head: head(2, 'Cwmbiga - Fedw Fain'), board: [], live: [] }] });
  assert.match(m.content, /Today · Tue 06 Oct/);
  assert.equal(m.embeds[0].title, 'LIVE · 1 on stage');
  assert.equal(m.embeds[0].description, '🔴 SS1  🇫🇮 **Kalle**  42 %  `2:13.400`');   // the stage clock
  assert.equal(m.embeds[1].title, 'SS1 · St. Geniez - Sisteron');
  assert.equal(m.embeds[1].url, 'https://s/stage/2026-10-06/1');
  assert.match(m.embeds[1].description, /^\*Hyundai i20 N Rally2 · Light fog · Midday \(12:00\)\*\n` 1` 🇮🇹 \*\*osiek\*\*/);
  assert.match(m.embeds[2].description, /No times yet\./);
  const empty = boardMessage({ date: '2026-10-06', stages: [{ slot: 1, head: head(1, 'X'), board: [], live: [] }] });
  assert.equal(empty.embeds[0].title, 'LIVE · nobody on stage');
});

test('day wrap-up: finals with the winner and the hall of fame; empty stages left out', () => {
  const m = dayMessage({ date: '2026-10-05', site: 'https://s',
    stages: [{ slot: 1, head: head(1, 'Forêt de Saverne'), board: BOARD1 }, { slot: 2, head: head(2, 'Obersteigen'), board: [] }],
    week: { week: 41, standings: [{ rank: 1, name: 'osiek', country: 'it', total: 43, wins: 1 }, { rank: 3, name: 'Zero', total: 0 }] } });
  assert.equal(m.content, '**Mon 05 Oct · results**');
  assert.deepEqual(m.embeds.map((e) => e.title), ['SS1 · Forêt de Saverne · final', 'Hall of fame · week 41']);
  assert.match(m.embeds[0].description, /🏆 🇮🇹 \*\*osiek\*\*/);
  assert.equal(m.embeds[1].description, '` 1` 🇮🇹 **osiek**  43 pts  ·  1 win');
});

test('webhook: only Discord webhook URLs; posts wait for the id, nobody is ever mentioned', async () => {
  assert.equal(webhook('https://evil.example/api/webhooks/1/x'), null);
  assert.equal(webhook(''), null);
  const calls = [];
  const fake = async (url, init) => {
    calls.push({ url, method: init.method, body: init.body && JSON.parse(init.body) });
    if (init.method === 'POST') return new Response(JSON.stringify({ id: '777' }), { status: 200 });
    if (init.method === 'PATCH') return new Response('{"message":"Unknown Message"}', { status: 404 });
    return new Response(null, { status: 204 });
  };
  const hook = webhook('https://discord.com/api/webhooks/123/abc-DEF_9', fake);
  assert.deepEqual(await hook.post({ content: 'hi' }), { ok: true, status: 200, id: '777', data: { id: '777' } });
  assert.equal((await hook.edit('777', { content: 'x' })).status, 404);
  assert.equal((await hook.remove('777')).status, 204);
  assert.deepEqual(calls.map((c) => [c.method, c.url]), [
    ['POST', 'https://discord.com/api/webhooks/123/abc-DEF_9?wait=true'],
    ['PATCH', 'https://discord.com/api/webhooks/123/abc-DEF_9/messages/777'],
    ['DELETE', 'https://discord.com/api/webhooks/123/abc-DEF_9/messages/777']]);
  assert.deepEqual(calls[0].body.allowed_mentions, { parse: [] });
});
