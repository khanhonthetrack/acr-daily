// Rallies and Community organizers (0033, src/leaguesapi.js): anyone makes a rally (one event, public or private);
// only Community organizers make championships; every app lists the public rallies and a driver joins one by driving
// it; a private one only with its invite link; its maker stewards it. On a real SQLite (schema.sql) through a
// stand-in for D1.
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 15, 12, 0);
const [ANN, BEN, CAT] = [sid(1), sid(2), sid(3)];
const DAY = 86400000;
const RALLY = { name: 'Friday Sprint', rally: 'Wales', car: 'Skoda Fabia RS Rally2', stages: [{ track: 'Wales Afon Biga', day: 1,
  weather: 'Clear', time: '09:00' }], opens: NOW, closes: NOW + 3 * DAY, about: 'Short and fast.' };

function world() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n, org] of [[ANN, 'Ann', 1], [BEN, 'Ben', null], [CAT, 'Cat', null]]) {
    db.prepare('INSERT INTO players (steam_id, name, created, organizer) VALUES (?, ?, 0, ?)').run(s, n, org);
  }
  db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Wales Afon Biga', '[]', 5000, 0, 'WelesS4HafrenSouthFullReverse')").run();
  return f;
}

const player = (db, s) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s);
const call = async ({ env, db }, path, me, body = null, app = '0.1.6') => {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: app ? { 'User-Agent': `ACR-Daily/${app} public` } : {},
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = await leaguesApi(req, env, url.pathname, url, me ? { ...player(db, me) } : null, true, NOW);
  return { status: res.status, body: await res.json() };
};
const myEvents = async (f, me, app = '0.1.6') => (await call(f, '/api/me/events', me, null, app)).body.events;

test('a championship is a Community organizer\'s to make; a rally anyone\'s', async () => {
  const f = world();
  const no = await call(f, '/api/leagues', BEN, { name: 'Ben League', public: true });
  assert.equal(no.status, 403);
  assert.match(no.body.error, /Community organizers/);
  assert.equal((await call(f, '/api/leagues', ANN, { name: 'Ann League', public: true })).status, 200);
  const r = await call(f, '/api/rallies', BEN, RALLY);
  assert.equal(r.status, 200, JSON.stringify(r.body));
  const holder = f.db.prepare('SELECT * FROM leagues WHERE id = ?').get(r.body.holder);
  assert.deepEqual([holder.kind, holder.owner, holder.public, holder.about, holder.name], ['event', BEN, 1, 'Short and fast.', 'Friday Sprint']);
  assert.equal((await call(f, '/api/me', ANN)).body.organizer, true);
  assert.equal((await call(f, '/api/leagues', BEN)).body.organizer, false);
});

test('a public rally: on the Rallies page and in every app, joined by driving it', async () => {
  const f = world();
  const { id } = (await call(f, '/api/rallies', BEN, RALLY)).body;
  const list = (await call(f, '/api/leagues', CAT)).body;
  assert.deepEqual(list.rallies.map((r) => [r.id, r.name, r.owner, r.rally, r.car, r.stages, r.drivers, r.status]),
    [[id, 'Friday Sprint', 'Ben', 'Wales', 'Skoda Fabia RS Rally2', 1, 0, 'open']]);
  assert.deepEqual(list.public, []);                                        // (no championship among them)
  assert.deepEqual((await call(f, '/api/leagues', BEN)).body.myRallies.map((r) => r.id), [id]);
  const ev = (await myEvents(f, CAT)).find((e) => e.id === id);             // Cat is in nothing: listed all the same
  assert.deepEqual([ev.kind, ev.organizer, ev.drivers], ['event', 'Ben', 0]);
  const old = (await myEvents(f, CAT, '0.1.5')).find((e) => e.id === id);   // an app before 0.1.6: as a league's event
  assert.deepEqual([old.kind, old.league], ['league', 'Ben']);
  const start = await call(f, `/api/events/${id}/start`, CAT, { car: 'Skoda Fabia RS Rally2', at: NOW });
  assert.equal(start.status, 200, JSON.stringify(start.body));
  assert.ok(f.db.prepare('SELECT 1 FROM league_members WHERE league_id = (SELECT league_id FROM league_events WHERE id = ?) AND steam_id = ?').get(id, CAT));
  assert.equal((await myEvents(f, ANN)).find((e) => e.id === id).drivers, 1);
});

test('a private rally: only with its invite link', async () => {
  const f = world();
  const { id, holder } = (await call(f, '/api/rallies', BEN, { ...RALLY, public: false })).body;
  assert.deepEqual((await call(f, '/api/leagues', CAT)).body.rallies, []);
  assert.equal((await myEvents(f, CAT)).length, 0);
  assert.equal((await call(f, `/api/events/${id}`, CAT)).status, 404);
  assert.equal((await call(f, `/api/events/${id}/start`, CAT, { car: 'Skoda Fabia RS Rally2', at: NOW })).status, 403);   // (not joined by driving)
  const page = (await call(f, `/api/events/${id}`, BEN)).body;              // its maker sees the invite code
  assert.ok(page.league.code && page.me.owner && page.me.staff);
  assert.equal(page.league.owner, 'Ben');
  const code = f.db.prepare('SELECT code FROM leagues WHERE id = ?').get(holder).code;
  const inv = (await call(f, `/api/leagues/code?code=${code}`, CAT)).body;
  assert.deepEqual([inv.kind, inv.eventId, inv.member], ['event', id, false]);
  const j = await call(f, '/api/leagues/join', CAT, { code });
  assert.deepEqual(j.body, { id: holder, joined: true, eventId: id });
  assert.deepEqual((await myEvents(f, CAT)).map((e) => e.id), [id]);
  assert.equal((await call(f, `/api/events/${id}`, CAT)).body.league.code, undefined);   // (not theirs to hand out)
});

test('its maker stewards it, edits it (its holder follows) and deletes it; nobody else', async () => {
  const f = world();
  const { id, holder } = (await call(f, '/api/rallies', BEN, RALLY)).body;
  await call(f, `/api/events/${id}/start`, CAT, { car: 'Skoda Fabia RS Rally2', at: NOW });
  assert.equal((await call(f, `/api/events/${id}/penalty`, CAT, { steamId: CAT, seconds: -5, reason: 'my own' })).status, 403);
  assert.equal((await call(f, `/api/events/${id}/penalty`, BEN, { steamId: CAT, seconds: 10, stage: 1, reason: 'cut at SS1' })).status, 200);
  const e = await call(f, `/api/events/${id}/edit`, BEN, { name: 'Friday Night Sprint', about: 'Now at night.', public: false, seasonId: 'new' });
  assert.equal(e.status, 200, JSON.stringify(e.body));
  const h = f.db.prepare('SELECT name, about, public FROM leagues WHERE id = ?').get(holder);
  assert.deepEqual({ ...h }, { name: 'Friday Night Sprint', about: 'Now at night.', public: 0 });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_seasons').get().n, 0);       // (a rally has no season)
  assert.equal((await call(f, `/api/events/${id}/delete`, CAT, {})).status, 403);
  assert.equal((await call(f, `/api/events/${id}/delete`, BEN, {})).status, 200);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM leagues WHERE id = ?').get(holder).n, 0);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM league_members WHERE league_id = ?').get(holder).n, 0);
});

test(`at most ${3} rallies open or coming a driver; one its maker turned a driver away from is not in their app`, async () => {
  const f = world();
  for (let i = 1; i <= 3; i++) assert.equal((await call(f, '/api/rallies', BEN, { ...RALLY, name: 'Rally ' + i })).status, 200);
  const fourth = await call(f, '/api/rallies', BEN, { ...RALLY, name: 'Rally 4' });
  assert.equal(fourth.status, 409);
  const ids = (await myEvents(f, CAT)).map((e) => e.id);
  assert.equal(ids.length, 3);
  const holder = f.db.prepare('SELECT league_id FROM league_events WHERE id = ?').get(ids[0]).league_id;
  f.db.prepare("INSERT INTO league_bans (league_id, steam_id, reason, by, created) VALUES (?, ?, 'rude', ?, 0)").run(holder, CAT, BEN);
  assert.deepEqual((await myEvents(f, CAT)).map((e) => e.id), ids.slice(1));
  assert.equal((await call(f, `/api/events/${ids[0]}/start`, CAT, { car: 'Skoda Fabia RS Rally2', at: NOW })).status, 403);
});
