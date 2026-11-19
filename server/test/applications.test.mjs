// Championships by application (0043, src/leaguesapi.js): every championship is listed and can be opened; a public one
// is joined straight away, a private one asked to join (with a word to its admins), which its owner or an admin accepts
// or declines, the driver told in their inbox; they can also add a driver straight away. Codes let nobody into a
// championship any more. On a real SQLite (schema.sql) through a stand-in for D1.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 15, 12, 0);
const DAY = 86400000;
const [OWN, ADM, ANN, BEN, CAT, DAN] = [sid(1), sid(2), sid(3), sid(4), sid(5), sid(6)];

function world() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n, org] of [[OWN, 'Olga', 1], [ADM, 'Adam', null], [ANN, 'Ann', null], [BEN, 'Ben', null], [CAT, 'Cat', null], [DAN, 'Dan', null]]) {
    db.prepare('INSERT INTO players (steam_id, name, created, organizer) VALUES (?, ?, 0, ?)').run(s, n, org);
  }
  return f;
}
const player = (db, s) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s);
const call = async ({ env, db }, path, me, body = null, at = NOW) => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.1.6 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, me ? { ...player(db, me) } : null, true, at);
  return { status: res.status, body: await res.json() };
};
/** A private championship of Olga's, Adam its admin. */
async function privateChamp(f) {
  const { id } = (await call(f, '/api/leagues', OWN, { name: 'Night Owls', about: 'Late rallies.', public: false })).body;
  f.db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, 0, 'admin')").run(id, ADM);
  return id;
}
const notices = (db, to) => db.prepare('SELECT kind, body, ref FROM messages WHERE to_id = ? ORDER BY id').all(to).map((m) => ({ ...m }));
const members = (db, id) => db.prepare('SELECT steam_id FROM league_members WHERE league_id = ? ORDER BY steam_id').all(id).map((r) => r.steam_id);

test('every championship is listed and opens, a private one too; no code anywhere', async () => {
  const f = world();
  const id = await privateChamp(f);
  const made = f.db.prepare('SELECT code FROM leagues WHERE id = ?').get(id);
  assert.ok(made.code, '(the column keeps one: it lets nobody in)');
  const list = (await call(f, '/api/leagues', ANN)).body;
  assert.deepEqual(list.public, [], 'not among the public ones: apps before 0043 offer those to JOIN');
  assert.deepEqual(list.private.map((x) => [x.id, x.name, x.public, x.members, x.owner]), [[id, 'Night Owls', false, 2, 'Olga']]);
  assert.deepEqual((await call(f, '/api/leagues', null)).body.private.map((x) => x.id), [id], 'signed out too');
  const page = await call(f, `/api/leagues/${id}`, ANN);
  assert.equal(page.status, 200);
  assert.deepEqual([page.body.name, page.body.code, page.body.applications, page.body.me.member, page.body.me.application],
    ['Night Owls', undefined, undefined, false, null]);
  assert.equal((await call(f, `/api/leagues/${id}`, null)).status, 200, 'signed out too');
  // a championship's code: no way in
  const j = await call(f, '/api/leagues/join', ANN, { code: made.code });
  assert.deepEqual([j.status, j.body.id], [410, id]);
  assert.deepEqual(members(f.db, id), [OWN, ADM].sort());
  assert.equal((await call(f, `/api/leagues/${id}/code`, OWN, {})).status, 404, 'no new codes either');
});

test('a private one: JOIN refused; asked to join with a word, the owner and admins told; a second ask only changes the word', async () => {
  const f = world();
  const id = await privateChamp(f);
  const join = await call(f, `/api/leagues/${id}/join`, ANN, {});
  assert.equal(join.status, 403);
  assert.match(join.body.error, /private: ask to join/);
  assert.deepEqual((await call(f, `/api/leagues/${id}/apply`, ANN, { message: '  Fast on gravel,\n slow on tarmac.  ' })).body, { applied: true });
  assert.deepEqual(members(f.db, id), [OWN, ADM].sort(), 'not in yet');
  for (const who of [OWN, ADM]) {
    assert.deepEqual(notices(f.db, who), [{ kind: 'apply', ref: `league:${id}`,
      body: 'Ann asks to join Night Owls: "Fast on gravel, slow on tarmac." Accept or decline on its page, or in the app under RALLIES.' }]);
  }
  const mine = (await call(f, `/api/leagues/${id}`, ANN)).body.me.application;
  assert.deepEqual(mine, { status: 'pending', message: 'Fast on gravel, slow on tarmac.', at: NOW, again: null });
  assert.deepEqual((await call(f, '/api/leagues', ANN)).body.applied, [{ id, status: 'pending', at: NOW, again: null }]);
  await call(f, `/api/leagues/${id}/apply`, ANN, { message: 'Gravel only.' });
  assert.equal(notices(f.db, OWN).length, 1, 'told once');
  // the staff's view: on its page and in the list (the app's RALLIES)
  const staff = (await call(f, `/api/leagues/${id}`, ADM)).body.applications;
  assert.deepEqual(staff.map((a) => [a.steamId, a.name, a.message]), [[ANN, 'Ann', 'Gravel only.']]);
  const lst = (await call(f, '/api/leagues', OWN)).body;
  assert.deepEqual(lst.applications.map((a) => [a.leagueId, a.league, a.steamId, a.message]), [[id, 'Night Owls', ANN, 'Gravel only.']]);
  assert.deepEqual(lst.mine.map((x) => [x.id, x.role, x.applications]), [[id, 'owner', 1]]);
  assert.deepEqual((await call(f, '/api/leagues', ADM)).body.mine.map((x) => [x.role, x.applications]), [['admin', 1]]);
  assert.equal((await call(f, `/api/leagues/${id}`, BEN)).body.applications, undefined, 'not to other drivers');
  assert.deepEqual((await call(f, '/api/leagues', BEN)).body.applications, []);
  // a word too long is cut
  await call(f, `/api/leagues/${id}/apply`, ANN, { message: 'x'.repeat(500) });
  assert.equal(f.db.prepare('SELECT message FROM league_applications WHERE steam_id = ?').get(ANN).message.length, 200);
});

test('accepted: in, the application gone, the driver told; declined: told, and asked again only a week later', async () => {
  const f = world();
  const id = await privateChamp(f);
  await call(f, `/api/leagues/${id}/apply`, ANN, {});
  await call(f, `/api/leagues/${id}/apply`, BEN, { message: 'please' });
  assert.equal(notices(f.db, OWN)[0].body, 'Ann asks to join Night Owls. Accept or decline on its page, or in the app under RALLIES.');
  assert.equal((await call(f, `/api/leagues/${id}/accept`, CAT, { steamId: ANN })).status, 403, 'a driver of no rank');
  assert.deepEqual((await call(f, `/api/leagues/${id}/accept`, ADM, { steamId: ANN })).body, { accepted: true });
  assert.deepEqual(members(f.db, id), [OWN, ADM, ANN].sort());
  assert.deepEqual(notices(f.db, ANN), [{ kind: 'league', ref: `league:${id}`, body: 'You are in Night Owls: its rounds are in the app, under RALLIES.' }]);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_applications WHERE steam_id = ?').get(ANN).n, 0);
  assert.equal((await call(f, `/api/leagues/${id}/accept`, ADM, { steamId: ANN })).status, 404, 'answered already');
  assert.deepEqual((await call(f, `/api/leagues/${id}/decline`, OWN, { steamId: BEN })).body, { declined: true });
  assert.deepEqual(notices(f.db, BEN), [{ kind: 'league', ref: `league:${id}`, body: 'Your request to join Night Owls was declined.' }]);
  assert.deepEqual(members(f.db, id), [OWN, ADM, ANN].sort());
  const page = (await call(f, `/api/leagues/${id}`, BEN)).body;
  assert.deepEqual(page.me.application, { status: 'declined', message: 'please', at: NOW, again: NOW + 7 * DAY });
  assert.deepEqual((await call(f, `/api/leagues/${id}`, OWN)).body.applications, [], 'nothing left to answer');
  const soon = await call(f, `/api/leagues/${id}/apply`, BEN, {}, NOW + DAY);
  assert.deepEqual([soon.status, soon.body.error], [409, 'declined: you can ask again from 2026-11-22']);
  assert.deepEqual((await call(f, `/api/leagues/${id}/apply`, BEN, { message: 'again' }, NOW + 7 * DAY)).body, { applied: true });
  assert.equal(f.db.prepare('SELECT status FROM league_applications WHERE steam_id = ?').get(BEN).status, 'pending');
  assert.equal(notices(f.db, OWN).length, 3, 'told of the new ask');
});

test('an application taken back; a ban takes it away and keeps the driver from asking', async () => {
  const f = world();
  const id = await privateChamp(f);
  await call(f, `/api/leagues/${id}/apply`, ANN, {});
  assert.deepEqual((await call(f, `/api/leagues/${id}/withdraw`, ANN, {})).body, { withdrawn: true });
  assert.equal((await call(f, `/api/leagues/${id}/withdraw`, ANN, {})).status, 404);
  assert.equal((await call(f, `/api/leagues/${id}/accept`, OWN, { steamId: ANN })).status, 404);
  // a member banned: out, and their asking refused with the reason
  await call(f, `/api/leagues/${id}/add`, OWN, { steamId: CAT });
  await call(f, `/api/leagues/${id}/remove`, OWN, { steamId: CAT, ban: true, reason: 'rude' });
  const no = await call(f, `/api/leagues/${id}/apply`, CAT, {});
  assert.deepEqual([no.status, no.body.error], [403, 'you can\'t join this league (rude)']);
  assert.deepEqual((await call(f, `/api/leagues/${id}`, CAT)).body.me.banned, { reason: 'rude' });
  // a pending application goes with a ban (the ban of someone who only asked)
  await call(f, `/api/leagues/${id}/apply`, BEN, {});
  f.db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, 0, 'member')").run(id, BEN);
  await call(f, `/api/leagues/${id}/remove`, OWN, { steamId: BEN, ban: true, reason: 'spam' });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_applications WHERE steam_id = ?').get(BEN).n, 0);
});

test('the staff add a driver straight away (told in their inbox); not twice, not a banned one, not a driver who isn\'t one', async () => {
  const f = world();
  const id = await privateChamp(f);
  await call(f, `/api/leagues/${id}/apply`, DAN, {});
  assert.equal((await call(f, `/api/leagues/${id}/add`, ANN, { steamId: BEN })).status, 403, 'a driver of no rank');
  assert.deepEqual((await call(f, `/api/leagues/${id}/add`, ADM, { steamId: DAN })).body, { added: true });
  assert.deepEqual(notices(f.db, DAN), [{ kind: 'league', ref: `league:${id}`, body: 'Adam added you to Night Owls: its rounds are in the app, under RALLIES.' }]);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_applications WHERE steam_id = ?').get(DAN).n, 0, 'their ask answered');
  assert.deepEqual([(await call(f, `/api/leagues/${id}/add`, ADM, { steamId: DAN })).status, (await call(f, `/api/leagues/${id}/add`, ADM, { steamId: OWN })).status], [409, 409]);
  assert.equal((await call(f, `/api/leagues/${id}/add`, ADM, { steamId: sid(99) })).status, 404, 'nobody of that id');
  f.db.prepare("INSERT INTO league_bans (league_id, steam_id, reason, by, created) VALUES (?, ?, 'rude', ?, 0)").run(id, BEN, OWN);
  assert.match((await call(f, `/api/leagues/${id}/add`, ADM, { steamId: BEN })).body.error, /unban them first/);
  f.db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(CAT);
  assert.equal((await call(f, `/api/leagues/${id}/add`, ADM, { steamId: CAT })).status, 404, 'banned from the site');
  assert.deepEqual(members(f.db, id), [OWN, ADM, DAN].sort());
});

test('a public one: joined straight away (asking joins too); an official one\'s applications go to its admins only', async () => {
  const f = world();
  const { id } = (await call(f, '/api/leagues', OWN, { name: 'Open Club', public: true })).body;
  assert.deepEqual((await call(f, `/api/leagues/${id}/join`, ANN, {})).body, { id, joined: true });
  assert.deepEqual((await call(f, `/api/leagues/${id}/apply`, BEN, { message: 'hi' })).body, { id, joined: true });
  assert.deepEqual((await call(f, `/api/leagues/${id}/join`, ANN, {})).body, { id, joined: true }, 'again: as it was');
  assert.deepEqual(members(f.db, id), [OWN, ANN, BEN].sort());
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM messages').get().n, 0, 'nobody to ask');
  // made private with an application waiting: it stays; made public again, the driver just joins (the ask goes)
  await call(f, `/api/leagues/${id}/edit`, OWN, { public: false });
  await call(f, `/api/leagues/${id}/apply`, CAT, {});
  await call(f, `/api/leagues/${id}/edit`, OWN, { public: true });
  assert.deepEqual((await call(f, `/api/leagues/${id}/join`, CAT, {})).body, { id, joined: true });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_applications').get().n, 0);
  // an official one (owner 'acr-daily', no driver): its admins are told
  f.db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind, official) VALUES ('offi0001', 'EXR', 'acr-daily', 0, 'ZZZZZZZZ', 0, 'league', 1)").run();
  f.db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('offi0001', ?, 0, 'admin')").run(ADM);
  await call(f, '/api/leagues/offi0001/apply', DAN, {});
  assert.equal(notices(f.db, ADM).length, 1);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM messages WHERE to_id = 'acr-daily'").get().n, 0);
  assert.deepEqual((await call(f, '/api/leagues/offi0001/accept', ADM, { steamId: DAN })).body, { accepted: true });
});

test('a private championship\'s events open to everyone (results too); DRIVE is for its members', async () => {
  const f = world();
  const id = await privateChamp(f);
  f.db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Wales Afon Biga', '[]', 5000, 0, 'WelesS4HafrenSouthFullReverse')").run();
  const ev = await call(f, `/api/leagues/${id}/events`, OWN, { name: 'Round 1', rally: 'Wales', car: 'Skoda Fabia RS Rally2',
    stages: [{ track: 'Wales Afon Biga', day: 1, weather: 'Clear', time: '09:00' }], opens: NOW, closes: NOW + 3 * DAY });
  assert.equal(ev.status, 200, JSON.stringify(ev.body));
  const v = await call(f, `/api/events/${ev.body.id}`, ANN);
  assert.deepEqual([v.status, v.body.locked, v.body.league.public, v.body.me.member], [200, undefined, false, false]);
  assert.equal((await call(f, `/api/events/${ev.body.id}/live`, ANN)).status, 200);
  const st = await call(f, `/api/events/${ev.body.id}/start`, ANN, { car: 'Skoda Fabia RS Rally2', at: NOW });
  assert.deepEqual([st.status, st.body.error], [403, 'join the league first']);
  assert.equal((await call(f, `/api/events/${ev.body.id}/join`, ANN, { code: 'ABCDEFGH' })).status, 404, 'no code for a championship\'s event');
});
