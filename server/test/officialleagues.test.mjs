// Official leagues (src/officialleagues.js) on a real SQLite (schema.sql, node:sqlite): the EXR Rally Championship's
// file (tools/leagues) made into a private official league, its weekly rounds drawn and hidden, a longer plan adding
// only the rounds not made yet, and what the website gets.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { adminLeague, drawWeather, planRounds } from '../src/officialleagues.js';
import { leaguesApi } from '../src/leaguesapi.js';
import { MENU_NAMES } from '../src/stages.js';
import { RALLY_WEATHER } from '../src/conditions.js';
import { fakeD1 } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 10, 12, 0);          // Tue 10 Nov 2026
const WEEK = 7 * 86400000;
const RALLY_OF = { Alsace: 'Alsace', Greece: 'Greece', MonteCarlo: 'Monte Carlo', Weles: 'Wales' };
// every stage of the game as a route with its id ("Monte Carlo Sisteron - Mézien"), 10 km each
const ROUTES = Object.entries(MENU_NAMES).map(([id, name]) => ({ track: `${RALLY_OF[id.match(/^[A-Z][a-z]+(?:Carlo)?/)[0]]} ${name}`,
  stage_id: id, length: 10000 }));

function seeded(seed = 1) {                          // the same draws every run
  let s = seed;
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
}
function setup() {
  const f = fakeD1();
  for (const r of ROUTES) f.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, \'[]\', ?, 0, ?)').run(r.track, r.length, r.stage_id);
  return f;
}
function exrFile() {                                  // as tools/admin.py league new sends it
  const dir = new URL('../../tools/leagues/', import.meta.url);
  const b = JSON.parse(readFileSync(new URL('exr-rally-championship.json', dir), 'utf8'));
  b.rounds.starts = Date.parse(b.rounds.starts);
  b.banner = readFileSync(new URL(b.banner, dir)).toString('base64');
  return b;
}
const roadOf = (track) => {
  const id = ROUTES.find((r) => r.track === track).stage_id;
  const m = /^(.*?)(Full|Cut\d+|Short\d+)(Forward|Reverse)$/.exec(id);
  return { base: m[1], cut: m[2], dir: m[3] };
};

test('the EXR Rally Championship: a private official league, 8 weekly rounds of 6 hidden stages over 2 days', async () => {
  const { env, db } = setup();
  const r = await adminLeague(env, exrFile(), NOW, seeded());
  assert.ok(!r.error, r.error);
  assert.equal(r.public, false);
  assert.match(r.invite, /^[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  const l = db.prepare('SELECT * FROM leagues WHERE id = ?').get(r.id);
  assert.equal(l.name, 'EXR Rally Championship');
  assert.equal(l.about, '');
  assert.equal(l.official, 1);
  assert.equal(l.owner, 'acr-daily');
  assert.equal(l.public, 0);
  assert.equal(l.kind, 'league');
  assert.ok(l.banner, 'the banner is kept');
  const banner = db.prepare('SELECT type FROM league_banners WHERE league_id = ?').get(r.id);
  assert.equal(banner.type, 'image/jpeg');
  const season = db.prepare('SELECT * FROM league_seasons WHERE league_id = ?').all(r.id);
  assert.equal(season.length, 1);
  assert.deepEqual(JSON.parse(season[0].power), [5, 4, 3, 2, 1]);

  const evs = db.prepare('SELECT * FROM league_events WHERE league_id = ? ORDER BY opens').all(r.id);
  assert.equal(evs.length, 8);
  assert.deepEqual(r.rounds.map((e) => e.name), ['Round 1 · Monte Carlo', 'Round 2 · Wales', 'Round 3 · Alsace', 'Round 4 · Greece',
    'Round 5 · Monte Carlo', 'Round 6 · Wales', 'Round 7 · Alsace', 'Round 8 · Greece']);
  assert.ok(r.rounds.every((e) => e.stages === 6 && !('track' in e)), 'the admin is told how many stages, not which');
  const monday = Date.UTC(2026, 10, 16);
  evs.forEach((ev, w) => {
    assert.equal(ev.season_id, season[0].id);
    assert.equal(ev.opens, monday + w * WEEK, 'Monday 00:00 UTC');
    assert.equal(ev.closes, ev.opens + WEEK, 'to the next Monday');
    assert.equal(ev.car_class, 'Rally2/R5');
    assert.deepEqual(JSON.parse(ev.hide), { weather: true, times: true, stages: true });
    const st = JSON.parse(ev.stages);
    assert.deepEqual(st.map((s) => s.day), [1, 1, 1, 2, 2, 2]);
    assert.deepEqual(st.map((s) => s.service), [true, false, false, true, false, false], 'a service park opens each day');
    assert.ok(st.every((s) => s.track.startsWith(ev.rally + ' ')), 'all in the round\'s rally');
    assert.ok(st.every((s) => s.weather in RALLY_WEATHER[ev.rally]), 'weather the rally can have');
    assert.equal(new Set(st.map((s) => s.track)).size, 6, 'no stage twice in a round');
    for (let i = 0; i < 6; i++) {
      for (let j = 0; j < i; j++) {                   // a road again only the other way
        const a = roadOf(st[i].track), b = roadOf(st[j].track);
        const same = a.base === b.base && (a.cut === b.cut || a.cut === 'Full' || b.cut === 'Full');
        assert.ok(!same || a.dir !== b.dir, `${ev.name}: ${st[i].track} and ${st[j].track} are the same road the same way`);
      }
    }
  });
  // the second visit to a rally isn't the first again (the stages the first didn't race come first, as far as the roads let)
  const mc = evs.filter((e) => e.rally === 'Monte Carlo').map((e) => JSON.parse(e.stages).map((s) => s.track));
  assert.ok(mc[1].filter((t) => !mc[0].includes(t)).length >= 3, `${mc[0]} / ${mc[1]}`);
});

test('sending the plan again adds only the rounds not made yet; a private official league is shown to its members only', async () => {
  const { env, db } = setup();
  const b = exrFile();
  const r = await adminLeague(env, b, NOW, seeded(7));
  const again = await adminLeague(env, { ...b, id: r.id }, NOW, seeded(8));
  assert.deepEqual(again.rounds, [], 'nothing new');
  const more = await adminLeague(env, { ...b, id: r.id, rounds: { ...b.rounds, weeks: 10 } }, NOW, seeded(9));
  assert.deepEqual(more.rounds.map((e) => e.name), ['Round 9 · Monte Carlo', 'Round 10 · Wales']);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM league_events WHERE league_id = ?').get(r.id).n, 10);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = ?').get(r.id).n, 1, 'the same season');
  // made public later; an admin named
  const pub = await adminLeague(env, { id: r.id, public: true, admins: ['76561190000000001'] }, NOW);
  assert.equal(pub.public, true);
  assert.equal(db.prepare('SELECT role FROM league_members WHERE league_id = ? AND steam_id = ?').get(r.id, '76561190000000001').role, 'admin');
  assert.equal(db.prepare('SELECT name FROM leagues WHERE id = ?').get(r.id).name, 'EXR Rally Championship', 'what isn\'t given stays');
  assert.deepEqual(await adminLeague(env, { id: 'zzzzzzzz' }, NOW), { error: 'no official league with that id', status: 404 });
});

test('the website: a private official league hidden from outsiders, "official" and run by ACR Daily for its members', async () => {
  const { env, db } = setup();
  const r = await adminLeague(env, exrFile(), NOW, seeded(3));
  const get = async (path, me = null) => {
    const url = new URL('https://acrdaily.com' + path);
    const res = await leaguesApi(new Request(url), env, url.pathname, url, me, true, NOW);
    return { status: res.status, body: await res.json() };
  };
  assert.equal((await get(`/api/leagues/${r.id}`)).status, 404, 'private: not to outsiders');
  assert.deepEqual((await get('/api/leagues')).body.public, [], 'not listed');
  const sid = '76561190000000002';
  db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid, 'Driver');
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, 0, 'member')").run(r.id, sid);
  const me = { steam_id: sid, name: 'Driver' };
  const l = (await get(`/api/leagues/${r.id}`, me)).body;
  assert.equal(l.official, true);
  assert.deepEqual(l.owner, { steamId: null, name: 'ACR Daily' });
  assert.equal(l.me.staff, false);
  assert.equal(l.events.length, 8);
  assert.ok(l.events.every((e) => e.hidden), 'every round hidden');
  const mine = (await get('/api/leagues', me)).body.mine;
  assert.equal(mine[0].official, true);
  assert.equal(mine[0].owner, 'ACR Daily');
  const ev = (await get(`/api/events/${l.events[0].id}`, me)).body;
  assert.ok(ev.stages.every((s) => !s.track && !s.weather), 'a member sees no stage or weather before DRIVE');
});

test('plans that can\'t be: a rally without the stages, weeks out of range, an unknown rally', () => {
  const plan = { starts: Date.UTC(2026, 10, 16), weeks: 2, rallies: ['Wales'], carClass: 'Rally2/R5',
    stages: Array.from({ length: 6 }, (_, k) => ({ day: k < 3 ? 1 : 2, time: `${10 + (k % 3)}:00` })) };
  const few = ROUTES.filter((x) => x.track.startsWith('Wales')).slice(0, 3);
  assert.match(planRounds(plan, few, { now: NOW }).error, /round 1: Wales hasn't the stages for 6 a round/);
  assert.match(planRounds({ ...plan, weeks: 0 }, ROUTES, { now: NOW }).error, /weeks: 1 to 52/);
  assert.match(planRounds({ ...plan, rallies: ['Finland'] }, ROUTES, { now: NOW }).error, /rallies/);
  assert.match(planRounds({ ...plan, starts: NOW + 90 * 86400000 }, ROUTES, { now: NOW }).error, /within 60 days/);
  // weeks already over aren't made
  assert.equal(planRounds({ ...plan, starts: NOW - 10 * 86400000 }, ROUTES, { now: NOW }).value.length, 1);
  assert.ok(Object.keys(RALLY_WEATHER.Greece).includes(drawWeather('Greece', seeded(5))));
});
