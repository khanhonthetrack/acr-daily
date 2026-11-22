// The app's list of my events (GET /api/me/events, src/leaguesapi.js): each with its league's banner, or its cup's
// (the app shows it on the event's card), none when the league has none.
// On a real SQLite (schema.sql, node:sqlite) through a stand-in for D1.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaguesApi } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 8, 18, 0);
const ME = sid(1);
const STAGES = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' }];

test('each event with its league\'s banner (a cup match: the cup\'s), or none', async () => {
  const { env, db } = fakeD1();
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(ME, 'Me');
  for (const [id, kind, banner] of [['pub00001', 'league', 1700000000000], ['cup00001', 'cup', 1700000000001], ['plain001', 'league', null]]) {
    db.prepare(`INSERT INTO leagues (id, name, owner, public, code, created, kind, banner) VALUES (?, ?, ?, 1, ?, 0, ?, ?)`)
      .run(id, id, ME, 'C' + id, kind, banner);
    db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, 0, 'member')").run(id, ME);
    db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created)
      VALUES (?, ?, 'Wales', 'Ford Fiesta Rally2', '{}', ?, ?, ?, 0)`).run(id, 'Round of ' + id, JSON.stringify(STAGES), NOW - 3600000, NOW + 86400000);
  }
  const url = new URL('https://acrdaily.com/api/me/events');
  const res = await leaguesApi(new Request(url, { headers: { 'User-Agent': 'ACR-Daily/0.0.25 public' } }), env, url.pathname, url,
    { steam_id: ME, name: 'Me' }, true, NOW);
  const evs = (await res.json()).events;
  assert.deepEqual(Object.fromEntries(evs.map((e) => [e.leagueId, e.leagueBanner])), {
    pub00001: '/l/pub00001/banner?v=1700000000000', cup00001: '/l/cup00001/banner?v=1700000000001', plain001: null });
});

test('a rally over the days the game takes at once (3): only for an app that drives it in legs; 14 stages over 2 days for every app', async () => {
  const { env, db } = fakeD1();
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(ME, 'Me');
  db.prepare(`INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('long0001', 'Long', ?, 1, 'CLONG', 0, 'league')`).run(ME);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('long0001', ?, 0, 'member')").run(ME);
  const stages = (n, days) => Array.from({ length: n }, (_x, k) => ({ ...STAGES[0], day: 1 + Math.floor(k * days / n), service: true }));
  for (const [name, list] of [['Short', stages(9, 3)], ['Long', stages(14, 2)], ['Four days', stages(4, 4)]]) {
    db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created)
      VALUES ('long0001', ?, 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0)`).run(name, JSON.stringify(list), NOW - 3600000, NOW + 86400000);
  }
  const ask = async (path, legs, body = null) => {
    const url = new URL('https://acrdaily.com' + path);
    const headers = { 'User-Agent': 'ACR-Daily/0.1.5.39 public', ...(legs ? { 'X-ACR-Legs': '1' } : {}) };
    const res = await leaguesApi(new Request(url, { method: body ? 'POST' : 'GET', headers, ...(body ? { body: JSON.stringify(body) } : {}) }),
      env, url.pathname, url, { steam_id: ME, name: 'Me' }, true, NOW);
    return { status: res.status, body: await res.json() };
  };
  assert.deepEqual((await ask('/api/me/events', true)).body.events.map((e) => e.name), ['Short', 'Long', 'Four days']);
  assert.deepEqual((await ask('/api/me/events', false)).body.events.map((e) => e.name), ['Short', 'Long']);
  const id = db.prepare("SELECT id FROM league_events WHERE name = 'Four days'").get().id;
  const old = await ask(`/api/events/${id}/start`, false, { car: 'Skoda Fabia RS Rally2', at: 1 });
  assert.equal(old.status, 426);
  assert.match(old.body.error, /driven in legs, which needs a newer ACR Daily/);
  assert.equal((await ask(`/api/events/${id}/start`, true, { car: 'Skoda Fabia RS Rally2', at: 1 })).status, 200);
  // its entry over: listed again, for its result
  db.prepare("UPDATE league_entries SET status = 'finished' WHERE event_id = ?").run(id);
  assert.deepEqual((await ask('/api/me/events', false)).body.events.map((e) => e.name), ['Short', 'Long', 'Four days']);
});
