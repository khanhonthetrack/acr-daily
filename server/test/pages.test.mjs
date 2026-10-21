// The website's pages build, and the scripts in them parse (a slip in a page's inline JavaScript only shows in a
// browser otherwise).
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { adminPage } from '../src/adminpage.js';
import { driverPage, rankingPage, teamPage, teamsPage } from '../src/driverpages.js';
import { cupPage, cupsPage, h2hPage, inboxPage } from '../src/socialpages.js';
import { guidePage } from '../src/guidepage.js';
import { sitePage } from '../src/site.js';
import { labMapPage } from '../src/labmap.js';

const ENV = { SOURCE_URL: 'https://github.com/x/y', LATEST_VERSION: '1.0.0', DOWNLOAD_URL: 'https://x/{version}/a.exe', DISCORD_URL: 'https://discord.gg/x' };
const PAGES = {
  home: () => sitePage(ENV), guide: () => guidePage(ENV), admin: () => adminPage(),
  driver: () => driverPage('76561198000000001', ENV), ranking: () => rankingPage(ENV), teams: () => teamsPage(ENV), team: () => teamPage('abcdefgh', ENV),
  cup: () => cupPage('abcdefgh', ENV), cups: () => cupsPage(ENV), h2h: () => h2hPage(ENV), inbox: () => inboxPage(ENV),
  'live map': () => labMapPage(),
};

for (const [name, make] of Object.entries(PAGES)) {
  test(`the ${name} page builds and its scripts parse`, () => {
    const h = make();
    assert.match(h, /^<!doctype html>/i);
    const scripts = [...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
    for (const s of scripts) assert.doesNotThrow(() => new Function(s), `${name}: a script that doesn't parse`);
  });
}

test('a driver\'s own page picks their flag: every flag on offer, none of them the game\'s', () => {
  const h = driverPage('76561198000000001', ENV);
  assert.match(h, /Your flag/);
  assert.match(h, /'\/api\/me\/country'/);
  assert.match(h, /\["gb-sct","Scotland"\]/, 'the UK\'s nations are on offer too');
  assert.match(h, /\["vn","Vietnam"\]/);
});

test('the home page has no Live map button any more; the guide covers the parts of the game', () => {
  assert.doesNotMatch(sitePage(ENV), /class="hof livemap"/);
  const g = guidePage(ENV);
  for (const id of ['dailies', 'credits', '1v1', 'cups', 'leagues', 'rating', 'driver', 'shop', 'inbox', 'app', 'faq']) assert.match(g, new RegExp(`id="${id}"`));
  assert.match(g, /Can I buy credits\?/);
});
