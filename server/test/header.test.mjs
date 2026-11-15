// The website's header (src/header.js): one on every page, the parts of the game as the app names them, COMPETITIONS
// and COMMUNITY as drop-downs, the right side's links; its script parses.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { siteHeader } from '../src/header.js';
import { sitePage } from '../src/site.js';
import { guidePage } from '../src/guidepage.js';
import { statsPage } from '../src/statspage.js';
import { leaguesPage } from '../src/leaguepages.js';
import { liveriesPage } from '../src/liverypage.js';
import { rankingPage } from '../src/driverpages.js';
import { changelogPage } from '../src/changelogpage.js';
import { inboxPage } from '../src/socialpages.js';

const ENV = { LATEST_VERSION: '1.0.0', DOWNLOAD_URL: 'https://x/{version}/a.exe', DISCORD_URL: 'https://discord.gg/x' };
const PAGES = {
  home: () => sitePage(ENV), guide: () => guidePage(ENV), stats: () => statsPage('2026-11-15', 1, ENV), rallies: () => leaguesPage(ENV),
  liveries: () => liveriesPage(ENV), ranking: () => rankingPage(ENV), changelog: () => changelogPage(ENV), inbox: () => inboxPage(ENV),
};
const hrefs = (h) => [...h.matchAll(/ data-k="([a-z0-9]+)"/g)].map((m) => m[1]);

test('every page has the one header, and no other', () => {
  for (const [name, make] of Object.entries(PAGES)) {
    const h = make();
    assert.equal((h.match(/<header\b/g) || []).length, 1, `${name}: one header`);
    assert.match(h, /<header class="site">/, name);
    assert.deepEqual(hrefs(h), ['daily', 'tt', 'leagues', '1v1', 'cups', 'liveries', 'ranking', 'teams', 'discord', 'guide', 'inbox'], name);
    assert.match(h, /header\.site \.dd\{/, `${name}: the header's CSS`);
    assert.doesNotMatch(h, /class="hof|class="hnav"><a class="l home"/, `${name}: no old header`);
  }
});

test('the parts as the app names them; COMPETITIONS and COMMUNITY drop-downs; the right side', () => {
  const h = siteHeader(ENV);
  const top = [...h.matchAll(/<(?:a|button) class="l"[^>]*>([^<]+)/g)].map((m) => m[1]);
  assert.deepEqual(top, ['Dailies', 'Time trial', 'Competitions', 'Community']);
  const comp = h.slice(h.indexOf('data-g="comp"'), h.indexOf('data-g="comm"'));
  for (const k of ['leagues', '1v1', 'cups']) assert.match(comp, new RegExp(`data-k="${k}"`));
  const comm = h.slice(h.indexOf('data-g="comm"'));
  for (const k of ['liveries', 'ranking', 'teams', 'discord']) assert.match(comm, new RegExp(`data-k="${k}"`));
  assert.match(h, /aria-expanded="false" aria-haspopup="true">Competitions/);
  assert.match(h, /href="\/discord" data-k="discord"[^>]*target="_blank"/);
  assert.match(h, /href="\/guide" data-k="guide"/);
  assert.match(h, /id="nav-inbox"[^>]*hidden/, 'the inbox: signed in only');
  assert.match(h, /<a class="dl" href="https:\/\/x\/1\.0\.0\/a\.exe">Get the app<\/a>/);
  assert.match(h, /class="hburger"[^>]*aria-controls="hnav"/);
  assert.match(h, /class="langpick"/);
  assert.match(h, /HEADER_FIT|function fit\(\)/, 'fitted to the window');
});

test('no Discord, no download: their links go', () => {
  const h = siteHeader({});
  assert.doesNotMatch(h, /data-k="discord"/);
  assert.doesNotMatch(h, /class="dl"/);
});

test('a page with no sign-in of its own (the guide, a stage) has the header ask who is signed in', () => {
  assert.match(siteHeader(ENV, { me: true }), /fetch\('\/api\/me'[^]*\.then\(headerMe/);
  assert.doesNotMatch(siteHeader(ENV), /fetch\('\/api\/me'/);
  for (const h of [guidePage(ENV), statsPage('2026-11-15', 1, ENV)]) assert.match(h, /\.then\(headerMe,function\(\)\{headerMe\(null\)\}\)/);
});

test("the header's script parses and defines what the pages call", () => {
  for (const h of [siteHeader(ENV), siteHeader(ENV, { me: true }), siteHeader({})]) {
    const scripts = [...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
    assert.equal(scripts.length, 2, 'HEADER_FIT and the header');
    for (const s of scripts) assert.doesNotThrow(() => new Function(s));
    for (const f of ['function navOn(', 'function unread(', 'var headerMe=']) assert.ok(scripts[1].includes(f), f);
  }
});
