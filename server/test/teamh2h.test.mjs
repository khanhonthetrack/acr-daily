// Team 1V1s (src/teamh2h.js, teammatch.js) on a real SQLite (schema.sql, node:sqlite): a team's captain or manager
// challenges another team, theirs accepts, the drivers drive the match through the leagues' API (only those in the
// lineups), the cron settles it by the scoring; named lineups; who may do what.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { th2hApi, th2hTick } from '../src/teamh2h.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { LIMITS } from '../src/leagues.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const NOW = Date.UTC(2026, 10, 13, 12, 0);
const CAR = 'Hyundai i20 N Rally2';
// Red: Ann (captain), Ben (manager), Cid; Blue: Dot (captain), Eve, Fox; Gus in no team
const [ANN, BEN, CID, DOT, EVE, FOX, GUS] = [1, 2, 3, 4, 5, 6, 7].map(sid);
const NAMES = { [ANN]: 'Ann', [BEN]: 'Ben', [CID]: 'Cid', [DOT]: 'Dot', [EVE]: 'Eve', [FOX]: 'Fox', [GUS]: 'Gus' };
const EVENT = { name: 'Duel', rally: 'Alsace', car: CAR, rules: {}, opens: NOW, closes: NOW + 48 * H,
  stages: [{ track: 'Alsace Obersteigen', day: 1, service: true, weather: 'Clear', time: '14:00' }],
  hide: { weather: false, times: false, stages: false } };

function setup() {
  const f = fakeD1();
  const { db } = f;
  for (const [s, n] of Object.entries(NAMES)) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Alsace Obersteigen', '[]', 2000, 0, 'AlsaceS1ObersteigenFullForward')").run();
  db.prepare(`INSERT INTO teams (id, name, tag, tag_key, color, captain, code, created) VALUES
    ('tmred001', 'Red', 'RED', 'RED', '#E30613', ?, 'AAAA2222', 0), ('tmblu001', 'Blue', 'BLU', 'BLU', '#5BA8FF', ?, 'BBBB2222', 0)`).run(ANN, DOT);
  for (const [s, t, r] of [[ANN, 'tmred001', 'member'], [BEN, 'tmred001', 'manager'], [CID, 'tmred001', 'member'],
    [DOT, 'tmblu001', 'member'], [EVE, 'tmblu001', 'member'], [FOX, 'tmblu001', 'member']]) {
    db.prepare('INSERT INTO team_members (steam_id, team_id, joined, role) VALUES (?, ?, 0, ?)').run(s, t, r);
  }
  return f;
}
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const err = (error, status = 400) => json({ error }, status);
async function call(env, who, path, body = null, now = NOW) {
  const req = new Request(`https://acrdaily.com${path}`, body ? { method: 'POST', body: JSON.stringify(body) } : {});
  const res = await th2hApi(req, env, path, { steam_id: who, name: NAMES[who] }, true, now, { json, err });
  return { status: res.status, body: await res.json() };
}
const ok = async (p) => { const r = await p; assert.ok(r.status < 300, JSON.stringify(r.body)); return r.body; };
async function ev(env, who, eventId, action, body, now = NOW) {
  const url = new URL(`https://acrdaily.com/api/events/${eventId}/${action}`);
  const req = new Request(url, { method: 'POST', body: JSON.stringify(body), headers: { 'User-Agent': 'ACR-Daily/0.1.2 public' } });
  const res = await leaguesApi(req, env, url.pathname, url, { steam_id: who, name: NAMES[who] }, true, now);
  return { status: res.status, body: await res.json() };
}
async function drive(env, who, eventId, s, now = NOW + H) {
  await ok(ev(env, who, eventId, 'start', { car: CAR, at: now }, now));
  await ok(ev(env, who, eventId, 'stage', { no: 0, timeMs: s * 1000, penaltyMs: 0 }, now));
}
const row = (db) => ({ ...db.prepare('SELECT status, winner, note FROM team_h2h').get() });

test('top 2 times: a challenge, accepted, both teams drive, settled at the close; the faster team wins', async () => {
  const { env, db } = setup();
  assert.equal((await call(env, CID, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'top', best: 2 } })).status, 403,
    'a driver who is no captain or manager');
  assert.equal((await call(env, GUS, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'top' } })).status, 403, 'no team');
  assert.match((await call(env, BEN, '/api/th2h', { opponent: 'tmred001', event: EVENT, scoring: { preset: 'top' } })).body.error, /another team/);
  const { id } = await ok(call(env, BEN, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'top', best: 2 } }));
  // Blue's captain is told; Eve sees it in her team's list, can't answer it
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ?').get(DOT).body, /\[RED\] Red challenges your team/);
  const list = await ok(call(env, EVE, '/api/th2h'));
  assert.equal(list.incoming[0].id, id);
  assert.equal(list.team.runs, false);
  assert.equal((await call(env, EVE, `/api/th2h/${id}/accept`, {})).status, 403);
  assert.equal((await call(env, ANN, `/api/th2h/${id}/accept`, {})).status, 403, 'not the challenger');
  const { eventId } = await ok(call(env, DOT, `/api/th2h/${id}/accept`, {}));
  // open lineups: every driver of both teams; each told; Gus can't drive it
  assert.equal(JSON.parse(db.prepare('SELECT only_ids FROM league_events WHERE id = ?').get(eventId).only_ids).length, 6);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE '%accepted%'").get().n, 6);
  assert.equal((await ev(env, GUS, eventId, 'start', { car: CAR, at: NOW + H }, NOW + H)).status, 403);
  // Red 100 + 120 (Cid 300 not counted) = 220; Blue 105 + 110 = 215
  await drive(env, ANN, eventId, 100);
  await drive(env, BEN, eventId, 120);
  await drive(env, CID, eventId, 300);
  await drive(env, DOT, eventId, 105);
  await drive(env, EVE, eventId, 110);
  assert.deepEqual(await th2hTick(env, NOW + 2 * H), [], 'an open lineup: settled at the close');
  const mid = await ok(call(env, ANN, '/api/th2h', null, NOW + 2 * H));
  assert.deepEqual(mid.active[0].teams.map((t) => [t.name, t.score, t.rank]), [['Red', 220000, 2], ['Blue', 215000, 1]]);
  const close = NOW + 48 * H + LIMITS.graceMs;
  assert.deepEqual(await th2hTick(env, close), [{ id, status: 'settled', winner: 'tmblu001' }]);
  assert.deepEqual(row(db), { status: 'settled', winner: 'tmblu001', note: 'by 5.000 s' });
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE '[BLU] Blue won %'").get().n, 6);
  const past = await ok(call(env, ANN, '/api/th2h', null, close));
  assert.deepEqual(past.past[0].teams.map((t) => [t.name, t.rank, t.drivers.filter((d) => d.counted).length]), [['Red', 2, 2], ['Blue', 1, 2]]);
  // a rematch, from either team's runners
  await ok(call(env, ANN, `/api/th2h/${id}/rematch`, {}, close));
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM team_h2h WHERE status = 'sent'").get().n, 1);
});

test('named lineups: each team names its 2; only they drive; settled as soon as all four are done', async () => {
  const { env, db } = setup();
  const { id } = await ok(call(env, ANN, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'named', size: 2 } }));
  const { eventId } = await ok(call(env, DOT, `/api/th2h/${id}/accept`, {}));
  assert.equal(db.prepare('SELECT only_ids FROM league_events WHERE id = ?').get(eventId).only_ids, '[]', 'nobody until named');
  assert.match((await call(env, ANN, `/api/th2h/${id}/lineup`, { steamIds: [ANN, BEN, CID] })).body.error, /2 drivers at most/);
  assert.match((await call(env, ANN, `/api/th2h/${id}/lineup`, { steamIds: [ANN, EVE] })).body.error, /team's drivers/);
  assert.equal((await call(env, CID, `/api/th2h/${id}/lineup`, { steamIds: [CID] })).status, 403);
  await ok(call(env, BEN, `/api/th2h/${id}/lineup`, { steamIds: [ANN, CID] }));
  await ok(call(env, DOT, `/api/th2h/${id}/lineup`, { steamIds: [EVE, FOX] }));
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ? ORDER BY rowid DESC').get(CID).body, /you drive Duel for the team/);
  assert.equal((await ev(env, BEN, eventId, 'start', { car: CAR, at: NOW + H }, NOW + H)).status, 403, 'Ben is not named');
  await drive(env, ANN, eventId, 100);
  // Ann has started: she stays in the lineup
  assert.match((await call(env, BEN, `/api/th2h/${id}/lineup`, { steamIds: [BEN, CID] })).body.error, /stays/);
  await ok(call(env, BEN, `/api/th2h/${id}/lineup`, { steamIds: [ANN, BEN] }));
  await drive(env, BEN, eventId, 100);
  await drive(env, EVE, eventId, 90);
  assert.deepEqual(await th2hTick(env, NOW + 2 * H), [], 'Fox still to drive');
  await ok(ev(env, FOX, eventId, 'start', { car: CAR, at: NOW + H }, NOW + H));
  await ok(ev(env, FOX, eventId, 'dnf', { reason: 'retired' }, NOW + H));
  // Red 200; Blue 90 and a DNF: the slowest (100) + 60 s = 160 -> 250
  assert.deepEqual(await th2hTick(env, NOW + 2 * H), [{ id, status: 'settled', winner: 'tmred001' }]);
  assert.deepEqual(row(db), { status: 'settled', winner: 'tmred001', note: 'by 50.000 s' });
  assert.equal(db.prepare('SELECT closes FROM league_events WHERE id = ?').get(eventId).closes, NOW + 2 * H, 'the match closes');
  // the match's page: both teams, who counted, their scores
  const url = new URL(`https://acrdaily.com/api/events/${eventId}`);
  const page = await (await leaguesApi(new Request(url), env, url.pathname, url, { steam_id: GUS, name: 'Gus' }, true, NOW + 3 * H)).json();
  assert.deepEqual(page.match.teams.map((t) => [t.name, t.score, t.rank]), [['Red', 200000, 1], ['Blue', 250000, 2]]);
  assert.equal(page.match.page, '/team1v1');
});

test('declined, cancelled, expired: told; the app lists a team match in its 1V1 tab against the other team', async () => {
  const { env, db } = setup();
  const a = await ok(call(env, ANN, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'top' } }));
  assert.equal((await call(env, ANN, `/api/th2h/${a.id}/decline`, {})).status, 403);
  await ok(call(env, DOT, `/api/th2h/${a.id}/decline`, {}));
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ? ORDER BY rowid DESC').get(BEN).body, /Blue declined/);
  const b = await ok(call(env, ANN, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'top' } }));
  await ok(call(env, BEN, `/api/th2h/${b.id}/cancel`, {}));
  const c = await ok(call(env, ANN, '/api/th2h', { opponent: 'tmblu001', event: EVENT, scoring: { preset: 'average' } }));
  assert.deepEqual(await th2hTick(env, NOW + 47 * H), [{ id: c.id, status: 'expired' }]);
  const d = await ok(call(env, ANN, '/api/th2h', { opponent: 'tmblu001', event: { ...EVENT, opens: NOW + 47 * H, closes: NOW + 96 * H },
    scoring: { preset: 'top' } }, NOW + 47 * H));
  const { eventId } = await ok(call(env, EVE === DOT ? EVE : DOT, `/api/th2h/${d.id}/accept`, {}, NOW + 47 * H));
  const url = new URL('https://acrdaily.com/api/me/events');
  const mine = await (await leaguesApi(new Request(url, { headers: { 'User-Agent': 'ACR-Daily/0.1.2 public' } }), env, url.pathname, url,
    { steam_id: CID, name: 'Cid' }, true, NOW + 47 * H)).json();
  const e = mine.events.find((x) => x.id === eventId);
  assert.equal(e.kind, 'h2h');
  assert.deepEqual(e.opponent, { steamId: null, name: '[BLU] Blue' });
  assert.equal(e.teamMatch.mine.name, 'Red');
});
