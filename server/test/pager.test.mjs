// A long list 30 at a time (src/pager.js): run in a small stand-in for the browser's page, and put into the pages with
// long lists (the user, 20 Nov 2026: the daily and time trial boards, a league's standings and drivers, an event's
// results, the teams, the liveries).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PAGER_JS } from '../src/pager.js';
import worker from '../src/index.js';
import { fakeD1 } from './faked1.mjs';

// just enough of the DOM for paginate(): children, siblings, attributes, style, buttons with onclick
class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.parentNode = null; this.style = {}; this.attrs = {};
    this.textContent = ''; this.className = ''; this.disabled = false; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  insertBefore(c, ref) { c.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; }
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; }
  get nextSibling() { const s = this.parentNode && this.parentNode.children; return s ? s[s.indexOf(this) + 1] || null : null; }
  get nextElementSibling() { return this.nextSibling; }
  set innerHTML(_v) { this.children = []; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  hasAttribute(k) { return k in this.attrs; }
  getBoundingClientRect() { return { top: 10 }; }
  scrollIntoView() {}
}
const document = { createElement: (t) => new Node(t) };
// eslint-disable-next-line no-new-func
const paginate = new Function('document', PAGER_JS() + '; return paginate;')(document);

function list(n, head) {
  const page = new Node('div'), table = page.appendChild(new Node('table'));
  if (head) table.appendChild(new Node('tr')).setAttribute('data-nopage', '');
  for (let i = 0; i < n; i++) table.appendChild(new Node('tr')).textContent = 'row ' + (i + 1);
  return { page, table, rows: table.children.filter((r) => !r.hasAttribute('data-nopage')) };
}
const shown = (rows) => rows.filter((r) => r.style.display !== 'none').map((r) => r.textContent);
const buttons = (nav) => nav.children.filter((b) => b.tagName === 'button');
const labels = (nav) => nav.children.map((b) => b.textContent);

test('a list of 90: the top 30, then a page for every 30 named by its places; the header row always', () => {
  const { page, table, rows } = list(90, true);
  paginate(table, 'k90', table);
  const nav = page.children[1];
  assert.equal(nav.className, 'pager');
  assert.deepEqual(labels(nav), ['‹', '1–30', '31–60', '61–90', '›']);
  assert.deepEqual(shown(rows), rows.slice(0, 30).map((r) => r.textContent));
  assert.notEqual(table.children[0].style.display, 'none', 'the header row');
  assert.equal(buttons(nav)[0].disabled, true, 'no page before the first');
  buttons(nav).find((b) => b.textContent === '61–90').onclick();
  assert.deepEqual(shown(rows), ['row 61'].concat(rows.slice(61, 90).map((r) => r.textContent)));
  assert.equal(page.children[1].children.at(-1).disabled, true, 'no page after the last');
});

test('30 or fewer: no buttons; the page kept when the list is drawn again (a board every minute); my row found', () => {
  const small = list(30);
  paginate(small.table, 'k30', small.table);
  assert.equal(small.page.children.length, 1);
  assert.equal(shown(small.rows).length, 30);
  const a = list(75);
  paginate(a.table, 'kept', a.table);
  buttons(a.page.children[1]).find((b) => b.textContent === '31–60').onclick();
  // drawn again: rows rebuilt, the same key: still on 31-60, one set of buttons
  a.table.children = []; for (let i = 0; i < 75; i++) a.table.appendChild(new Node('tr')).textContent = 'row ' + (i + 1);
  paginate(a.table, 'kept', a.table);
  assert.equal(a.page.children.filter((x) => x.className === 'pager').length, 1);
  assert.equal(shown(a.table.children)[0], 'row 31');
  a.table.pageTo(a.table.children[70]);
  assert.equal(shown(a.table.children)[0], 'row 61');
});

test('many pages: the first two, the last two, mine and its neighbours, the rest as …', () => {
  const { page, table } = list(600);
  paginate(table, 'k600', table);
  assert.deepEqual(labels(page.children[1]), ['‹', '1–30', '31–60', '…', '541–570', '571–600', '›']);
  buttons(page.children[1]).find((b) => b.textContent === '571–600').onclick();
  buttons(page.children[1])[1].onclick();   // (back to 1-30, then to the middle)
  table.pageTo(table.children[300]);
  assert.deepEqual(labels(page.children[1]),
    ['‹', '1–30', '31–60', '…', '271–300', '301–330', '331–360', '…', '541–570', '571–600', '›']);
});

test('the pages with long lists page them', async () => {
  const { env } = fakeD1({ SITE_URL: 'https://acrdaily.com', TIME_TRIAL_FROM: '2026-11-09' });
  const page = async (p) => (await worker.fetch(new Request('https://acrdaily.com' + p), env, { waitUntil() {} })).text();
  assert.match(await page('/'), /paginate\(tb,'ss'\+b\.date/);              // the dailies' timing sheets
  assert.match(await page('/'), /tb\.pageTo\(tr\)/);                         // "You: P12" turns to my page
  assert.match(await page('/tt'), /paginate\(body,'tt'\+b\.week/);
  assert.match(await page('/teams'), /paginate\(t,'teams'/);
  assert.match(await page('/liveries'), /paginate\(g,'lv\|'/);
  for (const p of ['/', '/tt', '/teams', '/liveries']) assert.match(await page(p), /\.pager button\{/, p + ': its look');
});
