// What's new (src/changelog.js): every version the app or the server names has its entry, the website's /changelog,
// the GitHub Release's notes and #changelog on Discord. A release without an entry fails here (and in the workflow).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CHANGELOG, changelogFor, changelogMessage, compareVersions, entryFor, POPUP, POPUP_FROM, published, releaseNotes, syncChangelog,
  syncChangelogs } from '../src/changelog.js';
import { changelogPage } from '../src/changelogpage.js';
import { botChannel, faqApi } from '../src/discordfaq.js';

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8');
const APP = read('../../client/acr_daily/__init__.py').match(/__version__ = '([\d.]+)'/)[1];
const LATEST = read('../wrangler.toml').match(/^LATEST_VERSION = "([\d.]+)"/m)[1];
const SITE = 'https://acr-daily.example.dev';
const hashOf = async (s) => String(s.length) + ':' + s.slice(-60);
/** fn run with a version written ahead of its release at the top of the list (taken off again after) */
async function withNext(fn) {
  const next = { version: '99.0.0', date: '2099-01-01', title: 'Not out yet', photo: 'dailies',
    changes: ['A change not out yet, for the tests.', 'And another one.'] };
  CHANGELOG.unshift(next);
  try { return await fn(next); } finally { CHANGELOG.shift(); }
}

test('the app\'s version has its changelog entry (add it at the top of server/src/changelog.js)', () => {
  assert.ok(entryFor(APP), `no changelog entry for the app's ${APP}`);
});

test('the version the server hands out has its changelog entry', () => {
  assert.ok(entryFor(LATEST), `no changelog entry for LATEST_VERSION ${LATEST}`);
});

test('entries: newest first, one per version, dated, plain lines that fit Discord', () => {
  const seen = new Set();
  CHANGELOG.forEach((e, i) => {
    assert.match(e.version, /^\d+\.\d+\.\d+$/);
    assert.ok(!seen.has(e.version), `${e.version} twice`);
    seen.add(e.version);
    assert.match(e.date, /^\d{4}-\d{2}-\d{2}$/, e.version);
    if (i) {
      assert.equal(compareVersions(CHANGELOG[i - 1].version, e.version), 1, `${CHANGELOG[i - 1].version} before ${e.version}`);
      assert.ok(CHANGELOG[i - 1].date >= e.date, `${e.version}'s date`);
    }
    assert.ok(Array.isArray(e.changes) && e.changes.length, `${e.version}: no changes`);
    if (e.title != null) {
      assert.ok(typeof e.title === 'string' && e.title.length >= 10 && e.title.length <= 120, `${e.version}'s title`);
      assert.doesNotMatch(e.title, /[<>`*_@[\]]|https?:/, `${e.version}'s title: plain text`);
    }
    for (const c of e.changes) {
      assert.equal(typeof c, 'string');
      assert.ok(c.length >= 10 && c.length <= 300, `${e.version}: "${c}"`);
      assert.doesNotMatch(c, /[<>`*_@[\]]|https?:/, `${e.version}: plain text, no markdown, HTML or links: "${c}"`);
    }
    assert.ok(changelogMessage(e, SITE).embeds[0].description.length <= 4096, e.version);
  });
});

const PHOTOS = JSON.parse(read('../../client/acr_daily/photos/photos.json'));

test(`from ${POPUP_FROM} on, each version has what the app's popup needs: a headline, a photo and a few short lines`, () => {
  for (const e of CHANGELOG.filter((x) => compareVersions(x.version, POPUP_FROM) >= 0)) {
    assert.ok(e.title && e.title.length <= POPUP.title, `${e.version}: a title (the popup's headline), ${POPUP.title} characters at most`);
    assert.ok(e.photo && PHOTOS[e.photo], `${e.version}: photo must be a key of client/acr_daily/photos/photos.json ` +
      `(${Object.keys(PHOTOS).join(', ')}), or add a new photo there with its author and licence`);
    assert.ok(e.changes.length >= POPUP.lines[0] && e.changes.length <= POPUP.lines[1], `${e.version}: ${POPUP.lines.join(' to ')} lines`);
    for (const c of e.changes) assert.ok(c.length <= POPUP.line, `${e.version}: "${c}" is longer than ${POPUP.line} characters`);
  }
});

test('the app\'s popup gets its version\'s entry once that version is out', () => withNext((next) => {
  const cur = CHANGELOG[1];
  assert.deepEqual(Object.keys(changelogFor(cur.version, cur.version)).sort(), ['changes', 'date', 'photo', 'title', 'version']);
  assert.deepEqual(changelogFor(cur.version, cur.version).changes, cur.changes);
  assert.equal(changelogFor(next.version, cur.version), null, 'not out yet');
  assert.equal(changelogFor(next.version, next.version).version, next.version);
  assert.equal(changelogFor('8.8.8', next.version), null, 'no entry');
}));

test('versions compare as numbers', () => {
  assert.equal(compareVersions('0.0.10', '0.0.9'), 1);
  assert.equal(compareVersions('0.1.0', '0.0.30'), 1);
  assert.equal(compareVersions('0.0.30', '0.0.30'), 0);
  assert.equal(compareVersions('0.0.29', '0.0.30'), -1);
});

test('the release notes: the version\'s changes, none for a version without an entry', () => {
  const e = CHANGELOG[0];
  const n = releaseNotes(e.version);
  assert.match(n, new RegExp(`^## What's new in ${e.version.replace(/\./g, '\\.')}\n`));
  for (const c of e.changes) assert.ok(n.includes(`- ${c}\n`));
  assert.equal(releaseNotes('9.9.9'), null);
});

test('/changelog shows the versions that are out, not one written ahead of its release', () => withNext((next) => {
  const out = CHANGELOG[1];
  const h = changelogPage({ LATEST_VERSION: out.version, DOWNLOAD_URL: 'https://x/{version}/a.exe' });
  assert.ok(!h.includes(`id="v${next.version}"`), 'a version not out yet');
  assert.ok(!h.includes(next.changes[0]));
  assert.ok(h.includes(`id="v${out.version}"`));
  assert.match(h, /Current/);
  if (out.title) assert.ok(h.includes(out.title.replace(/'/g, "'")), 'its headline');
  assert.deepEqual(published(out.version).map((e) => e.version), CHANGELOG.slice(1).map((e) => e.version));
  const all = changelogPage({ LATEST_VERSION: next.version });
  for (const e of CHANGELOG) assert.ok(all.includes(`id="v${e.version}"`), e.version);
}));

test('a headline goes into the post\'s title and the release notes', () => {
  const e = { version: '1.2.3', date: '2026-01-01', title: 'Something big', changes: ['One change for the test.'] };
  const m = changelogMessage(e, SITE).embeds[0];
  assert.equal(m.title, 'Something big');
  assert.equal(m.author.name, 'ACR Daily 1.2.3 is out');
  assert.equal(changelogMessage({ ...e, title: undefined }, SITE).embeds[0].title, 'ACR Daily 1.2.3 is out');
  CHANGELOG.unshift(e);
  try { assert.match(releaseNotes('1.2.3'), /^## What's new in 1\.2\.3\n\n\*\*Something big\*\*\n\n- One change/); } finally { CHANGELOG.shift(); }
});

// ------------------------------------------------------------------ Discord

function fakeDiscord({ channels = [], failPost = false } = {}) {
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
      const c = { id: String(next++), name: body.name, type: 0, overwrites: body.permission_overwrites };
      channels.push(c);
      return res(201, c);
    }
    let m = path.match(/^\/channels\/(\d+)\/messages$/);
    if (m && method === 'POST') { if (failPost) return res(403, { message: 'Missing Access' }); const id = String(next++); msgs.set(id, body); return res(200, { id }); }
    m = path.match(/^\/channels\/(\d+)\/messages\/(\d+)$/);
    if (m && method === 'PATCH') { if (!msgs.has(m[2])) return res(404, {}); msgs.set(m[2], body); return res(200, { id: m[2] }); }
    return res(404, {});
  };
  return { calls, msgs, channels, api: faqApi('x'.repeat(30), '123456789012345678', fetchFn) };
}
function memStore() {
  const m = new Map();
  return { m, get: async (k) => m.get(k) || null, set: async (k, id, hash, note) => { m.set(k, { id, hash, note }); } };
}
const channel = (api) => botChannel(api, 'changelog', 'What\'s new');

test('Discord: the live version is posted once in #changelog (made read-only), then left alone', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'faq', type: 0 }] }), store = memStore();
  const v = CHANGELOG[0].version;
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf }), 'posted');
  const ch = d.channels.find((c) => c.name === 'changelog');
  assert.ok(ch, 'made #changelog');
  assert.equal(ch.overwrites[0].deny, String(1n << 11n), 'nobody but the bot writes there');
  const [msg] = [...d.msgs.values()];
  assert.ok(`${(msg.embeds[0].author || {}).name} ${msg.embeds[0].title}`.includes(`ACR Daily ${v}`));
  assert.equal(msg.embeds[0].url, `${SITE}/changelog#v${v}`);
  for (const c of CHANGELOG[0].changes) assert.ok(msg.embeds[0].description.includes(c));
  assert.deepEqual(msg.allowed_mentions, { parse: [] });
  assert.match(store.m.get(`changelog:${v}`).id, new RegExp(`^${ch.id}/\\d+$`));
  const n = d.calls.length;
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf }), 'unchanged');
  assert.equal(d.calls.length, n, 'no Discord call while nothing changed');
});

test('Discord: an announcement channel called changelog is used as it is', async () => {
  const d = fakeDiscord({ channels: [{ id: '77', name: 'changelog', type: 5 }] }), store = memStore();
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: CHANGELOG[0].version, site: SITE, hashOf }), 'posted');
  assert.ok(!d.calls.includes('POST /guilds/123456789012345678/channels'), 'no second channel made');
  assert.ok(d.calls.includes('POST /channels/77/messages'));
});

test('Discord: an entry worded again is edited in place; a deleted post stays deleted', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'changelog', type: 0 }] }), store = memStore();
  const v = CHANGELOG[0].version;
  await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf });
  const key = `changelog:${v}`;
  store.m.set(key, { ...store.m.get(key), hash: 'older words' });
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf }), 'edited');
  d.msgs.clear();                          // someone deleted it
  store.m.set(key, { ...store.m.get(key), hash: 'older words' });
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf }), 'unchanged (its post was deleted)');
  assert.ok(!d.calls.slice(-1)[0].startsWith('POST'), 'not posted again');
});

test('Discord: each new version gets its own post; a version without an entry posts nothing', () => withNext(async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'changelog', type: 0 }] }), store = memStore();
  const [a, b] = CHANGELOG;
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: b.version, site: SITE, hashOf }), 'posted');
  assert.equal(await syncChangelog({ api: d.api, channel, store, version: a.version, site: SITE, hashOf }), 'posted');
  assert.equal(d.msgs.size, 2);
  const r = await syncChangelog({ api: d.api, channel, store, version: '9.9.9', site: SITE, hashOf });
  assert.match(r.skipped, /no changelog entry/);
  assert.equal(d.msgs.size, 2);
}));

test('Discord: every version out that was never posted is, oldest first; then nothing more', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'changelog', type: 0 }] }), store = memStore();
  const [newest, middle, oldest] = CHANGELOG;
  await syncChangelog({ api: d.api, channel, store, version: oldest.version, site: SITE, hashOf });   // posted back then
  const r = await syncChangelogs({ api: d.api, channel, store, latest: newest.version, site: SITE, hashOf });
  assert.deepEqual(r, { [oldest.version]: 'unchanged', [middle.version]: 'posted', [newest.version]: 'posted' });
  const titles = [...d.msgs.values()].map((m) => m.embeds[0].author ? m.embeds[0].author.name : m.embeds[0].title);
  assert.deepEqual(titles.slice(1), [`ACR Daily ${middle.version} is out`, `ACR Daily ${newest.version} is out`], 'in order');
  const n = d.calls.length;
  assert.deepEqual(Object.values(await syncChangelogs({ api: d.api, channel, store, latest: newest.version, site: SITE, hashOf })),
    ['unchanged', 'unchanged', 'unchanged']);
  assert.equal(d.calls.length, n, 'no Discord call while nothing changed');
  // a version not out yet (newer than LATEST_VERSION) is not posted
  assert.ok(!(newest.version in await syncChangelogs({ api: memStore() && d.api, channel, store: memStore(), latest: middle.version, site: SITE, hashOf })));
});

test('Discord: refused for one version, the newer ones wait for it (the channel stays in order)', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'changelog', type: 0 }], failPost: true }), store = memStore();
  const r = await syncChangelogs({ api: d.api, channel, store, latest: CHANGELOG[0].version, site: SITE, hashOf });
  assert.match(r.error, /Missing Access/);
  assert.deepEqual(Object.keys(r).filter((k) => k !== 'error'), [CHANGELOG[CHANGELOG.length - 1].version], 'stopped at the oldest');
});

test('Discord: refused, it says why and waits 15 minutes before trying again', async () => {
  const d = fakeDiscord({ channels: [{ id: '42', name: 'changelog', type: 0 }], failPost: true }), store = memStore();
  const v = CHANGELOG[0].version, now = 1_800_000_000_000;
  const r = await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf, now });
  assert.match(r.error, /Missing Access/);
  assert.match(store.m.get('changelog:failed').note, /Missing Access/, 'what Discord said, kept');
  const n = d.calls.length;
  assert.match(await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf, now: now + 60000 }), /waiting/);
  assert.equal(d.calls.length, n);
  assert.ok((await syncChangelog({ api: d.api, channel, store, version: v, site: SITE, hashOf, now: now + 16 * 60000 })).error);
});
