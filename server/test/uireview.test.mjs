// The UI review of Nov 2026, on the website: pages that aren't there answer 404 with a page, a shared link names what it
// is, text is readable (WCAG AA), the list of rallies has one address, and the phone layouts are in the pages.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import worker from '../src/index.js';
import { fakeD1 } from './faked1.mjs';
import { describe, metaTags } from '../src/pagemeta.js';
import { inLang } from '../src/i18n.js';
import { eventPage, leaguePage } from '../src/leaguepages.js';
import { cupPage } from '../src/socialpages.js';
import { liveriesPage } from '../src/liverypage.js';

const SITE = { SITE_URL: 'https://acrdaily.com' };
const get = (env, path, init = {}) => worker.fetch(new Request('https://acrdaily.com' + path, init), env, { waitUntil() {} });

function withRows() {
  const f = fakeD1(SITE);
  f.db.exec(`INSERT INTO leagues (id, name, about, owner, public, code, created, kind, banner) VALUES
    ('pubchamp', 'Sunday Gravel Club', 'Weekly gravel rallies.', 'x', 1, 'AAAAAAAA', 0, 'league', 1700000000000),
    ('hidechmp', 'Secret Club', 'Members only.', 'x', 0, 'BBBBBBBB', 0, 'league', NULL)`);
  f.db.exec(`INSERT INTO league_events (id, league_id, name, rally, car, rules, stages, opens, closes, created) VALUES
    (7, 'pubchamp', 'Round 1 · Wales', 'Wales', 'Hyundai i20 N Rally2', '{}', '[{"track":"a"},{"track":"b"}]', 0, 99999999999999, 0),
    (8, 'hidechmp', 'Secret Round', 'Wales', NULL, '{}', '[]', 0, 1, 0)`);
  f.db.exec(`INSERT INTO players (steam_id, name, created) VALUES ('76561198000000001', 'Ann <b>Fast</b>', 0)`);
  return f.env;
}

test('an address that is no page: 404 with a page, not {"error":"not found"}; the API still answers in JSON', async () => {
  const env = withRows();
  const r = await get(env, '/no/such/page');
  assert.equal(r.status, 404);
  assert.match(r.headers.get('Content-Type'), /text\/html/);
  const h = await r.text();
  assert.match(h, /<title>Page not found · ACR Daily<\/title>/);
  assert.match(h, /href="\/rallies"/);
  const api = await get(env, '/api/no-such-thing');
  assert.equal(api.status, 404);
  assert.match(api.headers.get('Content-Type'), /json/);
  assert.equal((await get(env, '/no/such/page', { method: 'POST' })).status, 404);   // (not a GET: JSON, as before)
});

test("an event, a championship, a driver, a cup or a team that doesn't exist: 404 (it was 200, its sections empty)", async () => {
  const env = withRows();
  for (const [path, title] of [['/e/99999', 'No such event'], ['/l/zzzzzzzz', 'No such championship'],
    ['/d/76561198000000999', 'No such driver'], ['/cup/zzzzzzzz', 'No such cup'], ['/t/zzzzzzzz', 'No such team']]) {
    const r = await get(env, path);
    assert.equal(r.status, 404, path);
    assert.match(await r.text(), new RegExp(`<title>${title} · ACR Daily</title>`), path);
  }
  assert.equal((await get(env, '/e/7')).status, 200);
});

test('a shared link names what it is: the title, a line on it and a picture (Open Graph, Twitter)', async () => {
  const env = withRows();
  const h = await (await get(env, '/e/7')).text();
  assert.match(h, /<title>Round 1 · Wales · ACR Daily<\/title>/);
  assert.match(h, /<meta property="og:title" content="Round 1 · Wales · ACR Daily">/);
  assert.match(h, /<meta property="og:description" content="Sunday Gravel Club · Wales · Hyundai i20 N Rally2 · 2 stages · Closes \d{4}-\d\d-\d\d">/);
  assert.match(h, /<meta property="og:image" content="https:\/\/acrdaily.com\/l\/pubchamp\/banner\?v=1700000000000">/);
  assert.match(h, /<meta name="twitter:card" content="summary_large_image">/);
  // a driver's name is theirs to choose: escaped, in the title and the tags alike
  const d = await (await get(env, '/d/76561198000000001')).text();
  assert.match(d, /<title>Ann &lt;b&gt;Fast&lt;\/b&gt; · ACR Daily<\/title>/);
  assert.doesNotMatch(d, /<b>Fast<\/b>/);
  // the home page and every shell page have the tags too
  for (const path of ['/', '/rallies', '/tt', '/cups']) assert.match(await (await get(env, path)).text(), /property="og:title"/, path);
});

test("a private championship and its events are named in a shared link, as every one is listed (0043); a private match's are not", async () => {
  const env = withRows();
  for (const path of ['/e/8', '/l/hidechmp']) assert.match(await (await get(env, path)).text(), /<title>Secret (Round|Club) · ACR Daily<\/title>/, path);
  assert.equal(describe('league', { id: 'x', public: 0, name: 'Secret', kind: 'league' }).title, 'Secret');
  assert.equal(describe('event', { id: 9, public: 0, name: 'Night run', league_kind: 'event', stages: '[]' }).title, 'Night run');
  assert.deepEqual(describe('league', { id: 'x', public: 0, name: 'Secret', kind: 'cup' }), { url: '/l/x' });
  assert.deepEqual(describe('event', { id: 9, public: 0, name: 'Secret', league_kind: 'h2h' }), { url: '/e/9' });
});

test("a championship's old invite link opens its page (asked to join there, 0043); a rally's is still its invite", async () => {
  const env = withRows();
  for (const code of ['BBBBBBBB', 'bbbb-bbbb']) {
    const r = await get(env, '/join/' + code, { redirect: 'manual' });
    assert.equal(r.status, 302, code);
    assert.equal(r.headers.get('Location'), 'https://acrdaily.com/l/hidechmp');
  }
  const r = await get(env, '/join/CCCC-CCCC');
  assert.equal(r.status, 200);
  assert.match(await r.text(), /<title>[^<]*ACR Daily<\/title>/);
});

test('metaTags: everything escaped, whole addresses', () => {
  const m = metaTags({ title: 'A "quoted" <name>', description: 'x & y', image: '/a.png', site: 'https://acrdaily.com/' });
  assert.match(m, /content="A &quot;quoted&quot; &lt;name&gt;"/);
  assert.match(m, /content="x &amp; y"/);
  assert.match(m, /og:image" content="https:\/\/acrdaily.com\/a.png"/);
});

test('one address for the rallies: /rallies; /leagues sends on to it', async () => {
  const env = withRows();
  const r = await get(env, '/leagues?x=1', { redirect: 'manual' });
  assert.equal(r.status, 301);
  assert.equal(r.headers.get('Location'), 'https://acrdaily.com/rallies?x=1');
  const h = await (await get(env, '/rallies')).text();
  assert.match(h, /href="\/rallies" data-k="leagues"/);
  assert.doesNotMatch(h, /href="\/leagues"/);
});

test('the championship pages say championship, not league', () => {
  for (const page of [leaguePage('abcdefgh', SITE), eventPage(3, SITE)]) {
    const words = [...page.matchAll(/"([^"\\]*(?:\\.[^"\\]*)*)"/g)].map((m) => m[1]).filter((s) => /\b[Ll]eague\b/.test(s) && / /.test(s));
    assert.deepEqual(words.filter((s) => !/^[a-z]+:|\/api\//.test(s)), [], 'words that still say league');
  }
});

// WCAG's contrast ratio of two #RRGGBB colours
function ratio(a, b) {
  const lum = (h) => { const c = [0, 2, 4].map((i) => parseInt(h.slice(1 + i, 3 + i), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

test('text is readable (WCAG AA, 4.5:1): the grey and the red as text, on the page and on its panels', () => {
  const dir = new URL('../src/', import.meta.url);
  for (const f of readdirSync(dir).filter((n) => n.endsWith('.js'))) {
    const src = readFileSync(new URL(f, dir), 'utf8');
    for (const m of src.matchAll(/--fg3:(#[0-9A-Fa-f]{6})/g)) {
      for (const bg of ['#0A0A0B', '#111113', '#141417']) assert.ok(ratio(m[1], bg) >= 4.5, `${f}: --fg3 ${m[1]} on ${bg}: ${ratio(m[1], bg).toFixed(2)}`);
    }
    for (const m of src.matchAll(/--acct:(#[0-9A-Fa-f]{6})/g)) assert.ok(ratio(m[1], '#111113') >= 4.5, `${f}: --acct`);
    // ACR red stays for fills and borders: as the colour of words, the lighter one
    assert.doesNotMatch(src, /(?<![-\w])color:var\(--acc\)/, `${f}: words in ACR red`);
  }
});

test('the phone layouts are in the pages: standings totals first, the bracket a round at a time, liveries a page at a time', () => {
  const ev = eventPage(3, SITE);
  assert.match(ev, /var NARROW=/);
  assert.match(ev, /phone\?\[c\.pos,c\.drv,c\.tot,c\.gp,c\.car\]/);
  assert.match(ev, /table\.phone td\.drv\{position:sticky/);
  assert.match(cupPage('abcdefgh', SITE), /function phoneBracket\(c,box\)/);
  assert.match(liveriesPage(SITE), /paginate\(g,'lv\|'\+L\.car\+'\|'\+L\.sort,g,30,/);   // (30 a page, src/pager.js)
  assert.match(liveriesPage(SITE), /function paginate\(/);
});

test('a hidden event says when it shows everything, and the Gap column holds gaps only', () => {
  const ev = inLang('en', () => eventPage(3, SITE));
  assert.match(ev, /Everything shows on \{0\}\./);
  assert.match(ev, /Hidden for now: \{0\}\./);
  assert.doesNotMatch(ev, /gp\.textContent=r\.reason/);
});

test('touch screens: 44 px to tap (SIGN IN was 44 x 13, the menu button 30, the stage chips 30)', () => {
  const h = readFileSync(new URL('../src/header.js', import.meta.url), 'utf8');
  assert.match(h, /header\.site \.signin\{[^}]*min-height:44px/);
  assert.match(h, /header\.site \.hburger\{[^}]*min-width:44px;min-height:44px/);
  assert.match(readFileSync(new URL('../src/eventlive.js', import.meta.url), 'utf8'), /@media \(pointer:coarse\)\{\.evlive \.sst button\{min-height:44px/);
});
