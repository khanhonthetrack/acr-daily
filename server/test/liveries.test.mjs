// Liveries (src/liveries.js, the /liveries page): the form's rules, which links the app can download itself, and the
// API on a real SQLite (test/faked1.mjs): a driver sends one, the admin publishes it, drivers rate it, download it and
// report a dead link; the sender's own list; the admin's side; the page builds.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkLivery, dataUrlBytes, directUrl, hostOf, LIVERY, liveriesApi } from '../src/liveries.js';
import { liveriesPage } from '../src/liverypage.js';
import { adminPage } from '../src/adminpage.js';
import { fakeD1, sid } from './faked1.mjs';

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70, 0, 1, 2, 3, 4, 5]);
const SHOT = 'data:image/jpeg;base64,' + Buffer.from(JPEG).toString('base64');
const GOOD = { car: 'Peugeot206', title: 'Martini 1983', author: 'Driver 1', link: 'https://www.overtake.gg/downloads/martini.123/',
  description: 'Stripes.\n\nLots of them.', shot: SHOT };

test('a livery\'s fields: the car (one of the game\'s), its name, the author, an https link or none', () => {
  const c = checkLivery(GOOD);
  assert.deepEqual(c.value, { car: 'Peugeot206', title: 'Martini 1983', author: 'Driver 1', description: 'Stripes.\n\nLots of them.',
    link: 'https://www.overtake.gg/downloads/martini.123/' });
  assert.equal(checkLivery({ ...GOOD, link: '', description: '' }).value.link, null);
  for (const bad of [{ ...GOOD, car: 'Batmobile' }, { ...GOOD, title: 'x' }, { ...GOOD, author: '' }, { ...GOOD, link: 'http://x.com/a.zip' },
    { ...GOOD, link: 'javascript:alert(1)' }, { ...GOOD, link: 'https://user:pw@x.com/a.zip' }, { ...GOOD, link: 'not a link' },
    { ...GOOD, description: 'x'.repeat(LIVERY.description + 1) }]) {
    assert.ok(checkLivery(bad).error, JSON.stringify(bad).slice(0, 90));
  }
  assert.equal(hostOf('https://www.Overtake.gg/x'), 'overtake.gg');
});

test('the links the app downloads itself (the zip, no page in the way) and the ones the browser opens', () => {
  assert.equal(directUrl('https://github.com/a/b/releases/download/v1/Martini.zip'), 'https://github.com/a/b/releases/download/v1/Martini.zip');
  assert.equal(directUrl('https://www.dropbox.com/scl/fi/abc/Martini.zip?rlkey=k&dl=0'), 'https://www.dropbox.com/scl/fi/abc/Martini.zip?rlkey=k&dl=1');
  assert.equal(directUrl('https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing'),
    'https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t');
  assert.equal(directUrl('https://drive.google.com/open?id=1AbCdEfGhIjKlMnOp'), 'https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t');
  assert.equal(directUrl('https://example.com/files/Martini.ZIP'), 'https://example.com/files/Martini.ZIP');
  for (const page of ['https://www.overtake.gg/downloads/martini.123/', 'https://mega.nz/file/abc#key', 'https://www.mediafire.com/file/x/M.zip/file',
    'https://github.com/a/b', 'https://www.dropbox.com/home', 'https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp', 'http://x.com/a.zip', 'nonsense']) {
    assert.equal(directUrl(page), null, page);
  }
  assert.deepEqual([...dataUrlBytes(SHOT)], [...JPEG]);
  assert.equal(dataUrlBytes('data:text/html;base64,PHNjcmlwdD4='), null);
});

function setup() {
  const { env, db } = fakeD1({});
  for (let i = 1; i <= 4; i++) db.prepare('INSERT INTO players (steam_id, name, created, steam_name) VALUES (?, ?, 0, ?)').run(sid(i), 'Driver ' + i, 'Driver ' + i);
  db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(sid(4));
  return { env, db, me: (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i)) };
}

async function call(env, method, path, { me = null, body, admin = false, same = true, now = Date.now() } = {}) {
  const url = new URL('https://acrdaily.test' + path);
  const req = new Request(url, { method, body: body !== undefined ? JSON.stringify(body) : undefined, headers: { 'Content-Type': 'application/json' } });
  const json = (data, status = 200) => ({ status, data });
  const err = (error, status = 400) => ({ status, data: { error } });
  const r = await liveriesApi(req, env, url.pathname, url, me, same, now, { json, err, admin });
  return r instanceof Response ? { status: r.status, bytes: new Uint8Array(await r.arrayBuffer()), headers: r.headers } : r;
}

test('sent, published by the admin, rated, downloaded, a dead link reported and mended; the sender told each time', async () => {
  const { env, db, me } = setup();
  assert.equal((await call(env, 'POST', '/api/liveries', { body: GOOD })).status, 401, 'signed in first');
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(1), body: GOOD, same: false })).status, 403, 'from this site only');
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(4), body: GOOD })).status, 403, 'not when banned');
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(1), body: { ...GOOD, shot: '' } })).status, 400, 'a preview needed');
  const html = 'data:image/jpeg;base64,' + Buffer.from('<html><script>').toString('base64');
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(1), body: { ...GOOD, shot: html } })).status, 415, 'a picture, by its bytes');
  const r = await call(env, 'POST', '/api/liveries', { me: me(1), body: GOOD });
  assert.equal(r.status, 200, JSON.stringify(r.data));
  const id = r.data.id;

  // waiting: not on the page, its preview not served, but in the sender's own list and the admin's
  assert.deepEqual((await call(env, 'GET', '/api/liveries')).data.liveries, []);
  assert.equal((await call(env, 'GET', `/api/liveries/${id}/shot`)).status, 404);
  assert.deepEqual((await call(env, 'GET', '/api/liveries/mine', { me: me(1) })).data.liveries.map((l) => [l.id, l.status]), [[id, 'pending']]);
  assert.equal((await call(env, 'GET', '/api/admin/liveries')).status, 403, 'not for drivers');
  const pend = await call(env, 'GET', '/api/admin/liveries?status=pending', { admin: true });
  assert.deepEqual(pend.data.liveries.map((l) => [l.id, l.title, l.by.name, l.carName, l.direct]), [[id, 'Martini 1983', 'Driver 1', 'Peugeot 206 WRC', false]]);
  const ashot = await call(env, 'GET', `/api/admin/liveries/${id}/shot`, { admin: true });
  assert.deepEqual([...ashot.bytes], [...JPEG]);

  // published: on the page with its preview (kept for good: its address has its version), the sender told
  assert.equal((await call(env, 'POST', `/api/admin/liveries/${id}`, { admin: true, body: { action: 'publish' } })).data.told, true);
  const list = (await call(env, 'GET', '/api/liveries')).data;
  const l = list.liveries[0];
  assert.deepEqual([l.id, l.car, l.title, l.author, l.host, l.hostName, l.direct, l.votes, l.stars, l.clicks],
    [id, 'Peugeot206', 'Martini 1983', 'Driver 1', 'overtake.gg', 'Overtake.gg', false, 0, 0, 0]);
  assert.match(l.shot, new RegExp(`^https://acrdaily\\.test/api/liveries/${id}/shot\\?v=\\w+$`));
  assert.equal(l.go, `https://acrdaily.test/api/liveries/${id}/go`);
  assert.equal(list.cars.find((c) => c.id === 'Peugeot206').count, 1);
  assert.equal(list.limits.perCar, 25);
  assert.deepEqual((await call(env, 'GET', '/api/liveries?car=CitroenXsaraWRC')).data.liveries, [], 'one car only');
  const pub = await call(env, 'GET', `/api/liveries/${id}/shot`);
  assert.equal(pub.status, 200);
  assert.match(pub.headers.get('Cache-Control'), /immutable/);
  const told = db.prepare("SELECT body, ref FROM messages WHERE to_id = ? AND kind = 'livery'").all(sid(1));
  assert.deepEqual(told.map((m) => m.ref), [`livery:${id}`]);
  assert.match(told[0].body, /Martini 1983 is published/);

  // stars: one vote a driver (a second changes it), never on one's own
  assert.equal((await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(1), body: { stars: 5 } })).status, 403);
  assert.equal((await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(2), body: { stars: 7 } })).status, 400);
  await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(2), body: { stars: 2 } });
  await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(2), body: { stars: 5 } });
  const v = await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(3), body: { stars: 4 } });
  assert.deepEqual(v.data, { votes: 2, stars: 4.5, mine: 4 });
  assert.equal((await call(env, 'GET', '/api/liveries', { me: me(2) })).data.liveries[0].mine, 5, 'my own vote comes with the list');

  // DOWNLOAD: to its link, counted; the app's direct=1 only where the link gives the zip itself
  const go = await call(env, 'GET', `/api/liveries/${id}/go`);
  assert.equal(go.status, 302);
  assert.equal(go.headers.get('Location'), GOOD.link);
  assert.equal((await call(env, 'GET', `/api/liveries/${id}/go?direct=1`)).status, 409, 'a page: the browser');
  assert.equal(db.prepare('SELECT clicks FROM liveries WHERE id = ?').get(id).clicks, 1);

  // "link not working?": once a driver; the admin mends the link (the reports go), now one the app downloads
  for (const i of [2, 2, 3]) assert.equal((await call(env, 'POST', `/api/liveries/${id}/flag`, { me: me(i), body: {} })).status, 200);
  const fl = (await call(env, 'GET', '/api/admin/liveries?status=flagged', { admin: true })).data.liveries;
  assert.deepEqual(fl.map((x) => [x.id, x.flags]), [[id, 2]]);
  const zip = 'https://www.dropbox.com/scl/fi/abc/Martini.zip?rlkey=k&dl=0';
  assert.equal((await call(env, 'POST', `/api/admin/liveries/${id}`, { admin: true, body: { action: 'clear', link: 'ftp://x' } })).status, 400);
  assert.equal((await call(env, 'POST', `/api/admin/liveries/${id}`, { admin: true, body: { action: 'clear', link: zip } })).data.told, false);
  assert.deepEqual((await call(env, 'GET', '/api/admin/liveries?status=flagged', { admin: true })).data.liveries, []);
  assert.equal((await call(env, 'GET', '/api/liveries')).data.liveries[0].direct, true);
  const direct = await call(env, 'GET', `/api/liveries/${id}/go?direct=1`);
  assert.equal(direct.headers.get('Location'), 'https://www.dropbox.com/scl/fi/abc/Martini.zip?rlkey=k&dl=1');

  // taken off: off the page, the sender sees why
  await call(env, 'POST', `/api/admin/liveries/${id}`, { admin: true, body: { action: 'hide', note: 'The file is gone' } });
  assert.deepEqual((await call(env, 'GET', '/api/liveries')).data.liveries, []);
  assert.equal((await call(env, 'GET', `/api/liveries/${id}/go`)).status, 404);
  assert.equal((await call(env, 'POST', `/api/liveries/${id}/vote`, { me: me(3), body: { stars: 1 } })).status, 404);
  const mine = (await call(env, 'GET', '/api/liveries/mine', { me: me(1) })).data.liveries[0];
  assert.deepEqual([mine.status, mine.note, mine.votes], ['hidden', 'The file is gone', 2]);
  assert.match(db.prepare("SELECT body FROM messages WHERE to_id = ? AND kind = 'livery' ORDER BY id DESC").get(sid(1)).body, /taken off.*The file is gone/);

  // deleted by its sender: everything of it goes; nobody else can
  assert.equal((await call(env, 'POST', `/api/liveries/${id}/delete`, { me: me(2), body: {} })).status, 404);
  assert.equal((await call(env, 'POST', `/api/liveries/${id}/delete`, { me: me(1), body: {} })).data.deleted, true);
  for (const t of ['liveries', 'livery_shots', 'livery_votes', 'livery_flags']) assert.equal(db.prepare(`SELECT COUNT(*) AS n FROM ${t}`).get().n, 0, t);
});

test('the limits: a few waiting at a time, a few a day; turned down with a reason', async () => {
  const { env, db, me } = setup();
  const ids = [];
  for (let i = 0; i < LIVERY.waiting; i++) ids.push((await call(env, 'POST', '/api/liveries', { me: me(2), body: { ...GOOD, title: 'Livery ' + i } })).data.id);
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(2), body: GOOD })).status, 429, 'enough waiting');
  const r = await call(env, 'POST', `/api/admin/liveries/${ids[0]}`, { admin: true, body: { action: 'reject', note: 'Not a livery' } });
  assert.equal(r.data.status, 'rejected');
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(2), body: GOOD })).status, 429, `${LIVERY.perDay} a day`);
  assert.equal((await call(env, 'POST', '/api/liveries', { me: me(2), body: GOOD, now: Date.now() + 86400000 + 1000 })).status, 200, 'the next day');
  assert.match(db.prepare("SELECT body FROM messages WHERE to_id = ? AND kind = 'livery'").get(sid(2)).body, /Livery 0 was not published: Not a livery/);
  assert.equal((await call(env, 'POST', `/api/admin/liveries/${ids[1]}`, { admin: true, body: { action: 'promote' } })).status, 400);
  assert.equal((await call(env, 'POST', `/api/admin/liveries/${ids[1]}`, { admin: true, body: { action: 'delete' } })).data.deleted, true);
});

test('through the router: the page and the list need no sign-in; the page builds and its script parses', async () => {
  const { default: worker } = await import('../src/index.js');
  const { env } = fakeD1({});
  const r = await worker.fetch(new Request('https://acrdaily.com/api/liveries'), env, { waitUntil() {} });
  assert.equal(r.status, 200);
  assert.deepEqual((await r.json()).liveries, []);
  const p = await worker.fetch(new Request('https://acrdaily.com/liveries'), env, { waitUntil() {} });
  assert.equal(p.status, 200);
  const page = await p.text();
  assert.match(page, /Documents\\My Games\\acr\\Liveries\\&lt;car&gt;\\/);
  assert.match(page, /href="\/liveries" data-k="liveries"/);   // (in the header's COMMUNITY: src/header.js)
  for (const h of [liveriesPage({}), adminPage()]) {
    for (const s of [...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1])) assert.doesNotThrow(() => new Function(s));
  }
  assert.match(adminPage(), /\/api\/admin\/liveries\?status=pending/);
});
