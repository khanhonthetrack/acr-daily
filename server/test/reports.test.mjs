// Bug reports (src/reports.js): the form's rules, what a file may be, and the API on a real SQLite (test/faked1.mjs):
// sending a report with its files, the limits, the driver's own list, the admin's (and the reports key's) side.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync, gunzipSync } from 'node:zlib';
import { checkReport, para, REPORT, reportsApi, sniff, trimReports } from '../src/reports.js';
import { reportPage } from '../src/reportpage.js';
import { fakeD1, sid } from './faked1.mjs';

const GOOD = { title: 'Stuck on loading after SS2', body: 'I finished SS2.\n\nThen the loading screen never ended.', area: 'cup', appVersion: '0.0.24' };
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 1, 2, 3]);
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 1, 2]);

test('a report\'s fields: the title, what happened (its line breaks kept), where, the app version', () => {
  const c = checkReport(GOOD);
  assert.equal(c.value.body, GOOD.body);
  assert.deepEqual([c.value.area, c.value.appVersion, c.value.eventUrl], ['cup', '0.0.24', null]);
  assert.equal(para('a \r\nb\n\n\n\nc\u0000', 100), 'a\nb\n\nc');
  for (const bad of [{ ...GOOD, title: 'abc' }, { ...GOOD, body: 'short' }, { ...GOOD, area: 'mars' }, { ...GOOD, area: undefined },
    { ...GOOD, appVersion: 'latest' }, { ...GOOD, body: 'x'.repeat(REPORT.body[1] + 1) }]) {
    assert.ok(checkReport(bad).error, JSON.stringify(bad).slice(0, 80));
  }
  assert.equal(checkReport({ ...GOOD, appVersion: '' }).value.appVersion, null);
});

test('a file is a picture or gzipped, by its first bytes (whatever its name says)', () => {
  assert.equal(sniff(PNG), 'image/png');
  assert.equal(sniff(JPEG), 'image/jpeg');
  assert.equal(sniff(new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4, 0x57, 0x45, 0x42, 0x50, 0])), 'image/webp');
  assert.equal(sniff(gzipSync(Buffer.from('LogInit: ...'))), 'application/gzip');
  assert.equal(sniff(new TextEncoder().encode('<html><script>')), null);
  assert.equal(sniff(new Uint8Array([0x4d, 0x5a, 0x90, 0])), null);           // an exe
});

function setup(vars = {}) {
  const { env, db } = fakeD1(vars);
  for (let i = 1; i <= 3; i++) db.prepare('INSERT INTO players (steam_id, name, created, steam_name) VALUES (?, ?, 0, ?)').run(sid(i), 'Driver ' + i, 'Driver ' + i);
  return { env, db, me: (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i)) };
}

async function call(env, method, path, { me = null, body, raw, admin = false, same = true, now = Date.now() } = {}) {
  const url = new URL('https://acrdaily.test' + path);
  const req = new Request(url, { method, body: raw !== undefined ? raw : body !== undefined ? JSON.stringify(body) : undefined,
    headers: raw !== undefined ? { 'Content-Type': 'application/octet-stream', 'Content-Length': String(raw.length) } : { 'Content-Type': 'application/json' } });
  const json = (data, status = 200) => ({ status, data });
  const err = (error, status = 400) => ({ status, data: { error } });
  const r = await reportsApi(req, env, url.pathname, url, me, same, now, { json, err, admin });
  return r instanceof Response ? { status: r.status, bytes: new Uint8Array(await r.arrayBuffer()), headers: r.headers } : r;
}

test('a driver sends a report with a screenshot and a gzipped log; the admin reads both back; the driver is told', async () => {
  const { env, me } = setup();
  assert.equal((await call(env, 'POST', '/api/reports', { body: GOOD })).status, 401, 'signed in first');
  assert.equal((await call(env, 'POST', '/api/reports', { me: me(1), body: GOOD, same: false })).status, 403, 'from this site only');
  const r = await call(env, 'POST', '/api/reports', { me: me(1), body: { ...GOOD, eventUrl: 'acrdaily.com/e/24' } });
  assert.equal(r.status, 200);
  const id = r.data.id;
  const log = 'LogInit: Build: ++acr\n'.repeat(500);
  const files = [[PNG, 'screenshot', 'shot.png'], [gzipSync(Buffer.from(log)), 'log', 'acr.log']];
  for (const [bytes, kind, name] of files) {
    const f = await call(env, 'POST', `/api/reports/${id}/files?kind=${kind}&name=${name}&size=${kind === 'log' ? log.length : bytes.length}`, { me: me(1), raw: bytes });
    assert.equal(f.status, 200, JSON.stringify(f.data));
  }
  // not a picture nor gzipped; someone else's report; too late
  assert.equal((await call(env, 'POST', `/api/reports/${id}/files?kind=other&name=x.exe`, { me: me(1), raw: new Uint8Array([0x4d, 0x5a, 1, 2]) })).status, 415);
  assert.equal((await call(env, 'POST', `/api/reports/${id}/files?kind=log&name=a.log`, { me: me(2), raw: gzipSync(Buffer.from('x')) })).status, 404);
  assert.equal((await call(env, 'POST', `/api/reports/${id}/files?kind=log&name=a.log`, { me: me(1), raw: gzipSync(Buffer.from('x')), now: Date.now() + REPORT.uploadMs + 1000 })).status, 409);

  const mine = await call(env, 'GET', '/api/reports/mine', { me: me(1) });
  assert.deepEqual(mine.data.reports.map((x) => [x.id, x.status, x.files]), [[id, 'new', 2]]);
  assert.deepEqual((await call(env, 'GET', '/api/reports/mine', { me: me(2) })).data.reports, [], 'only your own');

  assert.equal((await call(env, 'GET', '/api/admin/reports', { me: me(1) })).status, 403, 'not for drivers');
  const list = await call(env, 'GET', '/api/admin/reports?status=new', { admin: true });
  const rep = list.data.reports[0];
  assert.deepEqual([rep.id, rep.name, rep.steamId, rep.area, rep.eventUrl, rep.body], [id, 'Driver 1', sid(1), 'cup', 'acrdaily.com/e/24', GOOD.body]);
  assert.deepEqual(rep.files.map((f) => [f.kind, f.type, f.name, f.size]), [['screenshot', 'image/png', 'shot.png', PNG.length], ['log', 'application/gzip', 'acr.log', log.length]]);
  const dl = await call(env, 'GET', rep.files[1].url, { admin: true });
  assert.equal(dl.headers.get('Content-Type'), 'application/gzip');
  assert.match(dl.headers.get('Content-Disposition'), /filename="acr\.log\.gz"/);
  assert.equal(gunzipSync(dl.bytes).toString(), log);
  assert.deepEqual((await call(env, 'GET', rep.files[0].url, { admin: true })).bytes, PNG);

  // a fix proposed: the status, the note and the PR; the driver is told once
  const prUrl = 'https://github.com/khanhonthetrack/acr-daily/pull/9';
  assert.equal((await call(env, 'POST', `/api/admin/reports/${id}`, { admin: true, body: { status: 'pr', prUrl: 'https://evil.test/x' } })).status, 400);
  const u = await call(env, 'POST', `/api/admin/reports/${id}`, { admin: true, body: { status: 'pr', note: 'Found it: the save was read while the game wrote it.', prUrl } });
  assert.deepEqual(u.data, { id, status: 'pr', told: true });
  await call(env, 'POST', `/api/admin/reports/${id}`, { admin: true, body: { status: 'pr', note: 'Same again.' } });
  const notes = (await env.DB.prepare("SELECT to_id, kind, body, ref FROM messages WHERE kind = 'report'").all()).results;
  assert.equal(notes.length, 1, 'told once: the status did not change the second time');
  assert.deepEqual([notes[0].to_id, notes[0].ref], [sid(1), `report:${id}`]);
  assert.match(notes[0].body, /^Your report #\d+ \(Stuck on loading after SS2\) has a fix on the way: Found it/);
  const after = (await call(env, 'GET', '/api/reports/mine', { me: me(1) })).data.reports[0];
  assert.deepEqual([after.status, after.note, after.prUrl], ['pr', 'Same again.', prUrl]);
  assert.deepEqual((await call(env, 'GET', '/api/admin/reports?status=new', { admin: true })).data.reports, [], 'no longer new');
  assert.equal((await call(env, 'GET', '/api/admin/reports', { admin: true })).data.reports.length, 1, 'still open (a PR is not a release)');
  assert.equal((await call(env, 'POST', `/api/admin/reports/${id}`, { admin: true, body: { status: 'done' } })).status, 400);
});

test('the limits: reports a day, files a report, the store\'s size; old files go, the text stays', async () => {
  const { env, me, db } = setup();
  const ids = [];
  for (let k = 0; k < REPORT.perDay; k++) ids.push((await call(env, 'POST', '/api/reports', { me: me(1), body: GOOD })).data.id);
  assert.equal((await call(env, 'POST', '/api/reports', { me: me(1), body: GOOD })).status, 429, 'a day\'s reports');
  assert.equal((await call(env, 'POST', '/api/reports', { me: me(2), body: GOOD })).status, 200, 'another driver\'s are their own');
  for (let k = 0; k < REPORT.maxFiles; k++) assert.equal((await call(env, 'POST', `/api/reports/${ids[0]}/files?kind=screenshot`, { me: me(1), raw: JPEG })).status, 200);
  assert.equal((await call(env, 'POST', `/api/reports/${ids[0]}/files?kind=screenshot`, { me: me(1), raw: JPEG })).status, 409, 'files a report');
  const big = new Uint8Array(REPORT.maxFileBytes + 1); big.set(JPEG);
  assert.equal((await call(env, 'POST', `/api/reports/${ids[1]}/files?kind=screenshot`, { me: me(1), raw: big })).status, 413);
  // the store nearly full: a file that doesn't fit is refused, the report stays
  db.prepare("UPDATE bug_files SET stored = ? WHERE id = (SELECT MIN(id) FROM bug_files)").run(REPORT.maxStoredBytes - 10);
  assert.equal((await call(env, 'POST', `/api/reports/${ids[1]}/files?kind=screenshot`, { me: me(1), raw: JPEG })).status, 507);
  // 91 days on: the files are gone, the reports are not
  await trimReports(env, Date.now() + (REPORT.keepDays + 1) * 86400000);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM bug_files').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM bug_reports').get().n, REPORT.perDay + 1);
});

test('the page: signed-in form, the version from the app\'s link, where the files are', () => {
  const h = reportPage({ LATEST_VERSION: '0.0.24' });
  assert.match(h, /<title>Report a problem · ACR Daily<\/title>/);
  assert.ok(h.includes('data-copy="%LOCALAPPDATA%\\acr\\Saved\\Logs"'), 'the log folder, one backslash a level');
  assert.ok(h.includes('data-copy="%LOCALAPPDATA%\\acr\\Saved\\SaveGames"'));
  assert.ok(h.includes('data-copy="%APPDATA%\\ACR Daily\\save-backups"'));
  assert.match(h, /before you start the game again/);
  const script = h.slice(h.indexOf('<script>') + 8, h.lastIndexOf('</script>'));
  assert.doesNotThrow(() => new Function(script), 'its script parses');
});
