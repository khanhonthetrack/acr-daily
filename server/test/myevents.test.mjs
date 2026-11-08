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
