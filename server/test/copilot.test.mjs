// COPILOT (src/copilot.js): the notes in words, the day's pick, and a whole day on a real SQLite (schema.sql,
// node:sqlite) through the D1 stand-in: lobbies, READY, once a day in each role, the hidden stage, runs and the board.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { COPILOT_RULES, CP, copilotApi, copilotTick, crewOf, noteText, notesOf, parseCpId, pickCopilot, pointsFor,
  tokenWord } from '../src/copilot.js';
import { PACENOTES } from '../src/pacenotes.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000, D = 24 * H;
const DAY = '2026-11-25', T0 = Date.parse(DAY + 'T00:00:00Z');
const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619) >>> 0; return h; };

test('the game\'s notes in the co-driver\'s words', () => {
  assert.equal(tokenWord('Right3'), 'right 3');
  assert.equal(tokenWord('LeftHP'), 'left hairpin');
  assert.equal(tokenWord('RightAcuteHP'), 'right acute hairpin');
  assert.equal(tokenWord('LeftFlat'), 'flat left');
  assert.equal(tokenWord('Dist60'), '60');
  assert.equal(tokenWord('Tighten2'), 'tightens 2');
  assert.equal(tokenWord('DontCut'), "don't cut");
  assert.equal(tokenWord('Pause0.5s_Reset'), '', 'the game voice\'s pauses are not read');
  assert.equal(tokenWord('SomethingNew3'), 'something new 3', 'one not known: its own name');
  assert.equal(noteText('Caution OverCrest Into Right4'), 'caution over crest into right 4');
  assert.equal(noteText('Pause0.1s_Reset And Right5'), 'and right 5');
});

test('every stage\'s notes come from the game\'s files, in order, ending at the finish', () => {
  const ids = Object.keys(PACENOTES);
  assert.ok(ids.length >= 50, 'the game\'s stages: ' + ids.length);
  for (const id of ids) {
    const n = notesOf(id);
    assert.ok(n.length > 10, id);
    assert.equal(n[0].at, 0, id + ': from its first note');
    assert.ok(n.every((x, i) => i === 0 || x.at >= n[i - 1].at), id + ': in order along the road');
    assert.ok(n.some((x) => /finish/.test(x.text)), id + ': a finish call');
  }
  assert.equal(notesOf('NoSuchStage'), null);
});

test('ids, crews', () => {
  assert.deepEqual(parseCpId('cp:2026-11-25/12'), { date: '2026-11-25', lobby: 12 });
  assert.equal(parseCpId('tt:2026-11-23/1'), null);
  assert.equal(parseCpId('cp:2026-13-01/1'), null);
  assert.deepEqual(crewOf({ host: 'a', guest: 'b', host_role: 'codriver' }), { driver: 'b', codriver: 'a' });
  assert.equal(COPILOT_RULES.hardcore, true);
  assert.equal(COPILOT_RULES.damageIntensity, 'realistic');
});

const NOTED = Object.keys(PACENOTES).slice(0, 3);       // stages with the game's notes
const TRACKS = ['Wales A', 'Wales B', 'Greece A', 'Alsace A'];

test('the day\'s pick: a stage with notes, never one of the day\'s dailies\' when it can', () => {
  const stageOf = new Map([['Wales A', NOTED[0]], ['Wales B', NOTED[1]], ['Greece A', 'NoNotes'], ['Alsace A', NOTED[2]]]);
  const pool = { tracks: TRACKS, byTrack: new Map(TRACKS.map((t) => [t, []])) };
  for (let d = 1; d <= 20; d++) {
    const date = `2026-12-${String(d).padStart(2, '0')}`;
    const p = pickCopilot(pool, stageOf, date, [{ track: 'Wales A', car: 'x' }], hash);
    assert.ok(['Wales B', 'Alsace A'].includes(p.track), date + ': ' + p.track);
    assert.ok(p.car && p.weather && p.time);
    assert.deepEqual(p, pickCopilot(pool, stageOf, date, [{ track: 'Wales A', car: 'x' }], hash), 'the same each time');
  }
  assert.equal(pickCopilot(pool, new Map(), DAY, [], hash), null, 'no stage with notes: none');
});

// ------------------------------------------------------------------ a whole day, on SQLite

const ROUTE = Array.from({ length: 301 }, (_, i) => [i * 10, 0]);

function world() {
  const f = fakeD1({ COPILOT_FROM: DAY });
  const { db } = f;
  TRACKS.forEach((t, i) => {
    db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, 3000, 0, ?)')
      .run(t, JSON.stringify(ROUTE), i === 2 ? null : NOTED[i] || NOTED[0]);
    db.prepare("INSERT INTO pool (track, car, enabled) VALUES (?, '*', 1)").run(t);
  });
  for (let i = 1; i <= 6; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const deps = { json, err, hash, splits: [0.25, 0.5, 0.75], timing: { liveSendS: 5 },
    pool: async () => ({ tracks: TRACKS, byTrack: new Map(TRACKS.map((t) => [t, []])) }),
    tooOld: () => null, startedMs: (v, now) => (Number(v) > 0 ? Math.round(Number(v) * 1000) : now) };
  const me = (i) => db.prepare('SELECT * FROM players WHERE steam_id = ?').get(sid(i));
  const call = (method, path, { who = null, body, now = T0 + 10 * H, query = '' } = {}) => {
    const url = new URL('https://acrdaily.test' + path + query);
    const req = new Request(url, { method, ...(body !== undefined ? { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } } : {}) });
    return copilotApi(req, f.env, path, url, who ? me(who) : null, true, now, deps);
  };
  return { ...f, deps, call };
}

const finished = (ch, totalMs, penaltyMs = 0) => ({ challengeId: ch.id, track: ch.track, car: ch.car, status: 'finished',
  clockMs: totalMs - penaltyMs, resets: 0, official: { timeMs: totalMs - penaltyMs, penaltyMs }, startedAt: (T0 + 10 * H) / 1000,
  trace: Array.from({ length: 61 }, (_, i) => [Math.round((totalMs * i) / 60), i * 50, 0, 100, 0]) });

test('a day: a lobby, its partner, READY, the stage for both (the notes for the co-driver), the run, the board', async () => {
  const w = world();
  // off before its first day, and signed out sees the day without the stage
  assert.deepEqual((await w.call('GET', '/api/copilot', { now: T0 - 2 * D })).data.on, false);
  let day = (await w.call('GET', '/api/copilot')).data;
  assert.equal(day.on, true);
  assert.equal(day.ready, true, 'the day has its stage');
  assert.equal(day.revealed, false);
  assert.equal(day.stage, undefined, 'hidden');
  const pick = w.db.prepare('SELECT * FROM copilot_days WHERE date = ?').get(DAY);
  assert.notEqual(pick.track, 'Greece A', 'a stage without notes is never picked');

  // driver 1 sets up a public lobby as the driver; driver 2 sees it and joins (as the co-driver)
  const made = await w.call('POST', '/api/copilot/lobbies', { who: 1, body: { role: 'driver' } });
  assert.equal(made.status, 200);
  const id = made.data.lobby.id;
  assert.equal(made.data.lobby.myRole, 'driver');
  assert.equal(made.data.lobby.wants, 'codriver');
  day = (await w.call('GET', '/api/copilot', { who: 2 })).data;
  assert.deepEqual(day.lobbies.map((l) => l.id), [id]);
  assert.equal(day.lobbies[0].host.name, 'Driver 1');
  assert.equal(day.lobbies[0].code, undefined);
  const joined = await w.call('POST', '/api/copilot/join', { who: 2, body: { id } });
  assert.equal(joined.data.lobby.myRole, 'codriver');
  assert.equal((await w.call('POST', '/api/copilot/join', { who: 3, body: { id } })).status, 409, 'full');
  const full = (await w.call('GET', '/api/copilot', { who: 3 })).data.lobbies;
  assert.deepEqual(full.map((l) => [l.id, l.guest && l.guest.name, l.wants]), [[id, 'Driver 2', null]], 'listed, full');
  assert.equal((await w.call('GET', '/api/copilot', { who: 1 })).data.lobbies[0].mine, true);

  // the link details: each side's, the other's given back
  await w.call('POST', `/api/copilot/lobbies/${id}/signal`, { who: 1, body: { data: { addr: ['1.2.3.4:5000'] } } });
  assert.equal((await w.call('GET', `/api/copilot/lobbies/${id}`, { who: 2 })).data.lobby.signal, '{"addr":["1.2.3.4:5000"]}');
  assert.equal((await w.call('GET', `/api/copilot/lobbies/${id}`, { who: 3 })).status, 404, 'not a member');

  // READY: one is not enough; both: started, the stage given to both, the notes only to the co-driver
  let r = await w.call('POST', `/api/copilot/lobbies/${id}/ready`, { who: 1, body: { ready: true } });
  assert.equal(r.data.lobby.state, 'open');
  assert.equal(r.data.lobby.ch, undefined);
  r = await w.call('POST', `/api/copilot/lobbies/${id}/ready`, { who: 2, body: { ready: true } });
  assert.equal(r.data.lobby.state, 'started');
  const ch = r.data.lobby.ch;
  assert.equal(ch.id, `cp:${DAY}/${id}`);
  assert.equal(ch.track, pick.track);
  assert.equal(ch.weekend.hardcore, true);
  assert.ok(ch.route.length > 100);
  assert.ok(r.data.lobby.notes.length > 10, 'the co-driver\'s notes');
  assert.equal((await w.call('GET', `/api/copilot/lobbies/${id}`, { who: 1 })).data.lobby.notes, undefined, 'none for the driver');

  // only the driver sends the run: on the board as the crew's; the stage revealed to both now
  assert.equal((await w.call('POST', '/api/copilot/runs', { who: 2, body: finished(ch, 200000) })).status, 403);
  const wrong = finished(ch, 200000);
  wrong.car = 'Another car';
  assert.equal((await w.call('POST', '/api/copilot/runs', { who: 1, body: wrong })).status, 422);
  r = await w.call('POST', '/api/copilot/runs', { who: 1, body: finished(ch, 200000, 5000) });
  assert.equal(r.status, 200);
  assert.equal(r.data.rank, 1);
  assert.equal(r.data.totalMs, 200000);
  r = await w.call('POST', '/api/copilot/runs', { who: 1, body: finished(ch, 150000) });
  assert.equal(r.data.already, true, 'a lobby has one run');
  const board = (await w.call('GET', '/api/copilot/board', { who: 2 })).data;
  assert.equal(board.entries.length, 1);
  assert.equal(board.entries[0].driver.name, 'Driver 1');
  assert.equal(board.entries[0].codriver.name, 'Driver 2');
  assert.equal(board.stage.track, pick.track, 'revealed to the crew');
  assert.equal((await w.call('GET', '/api/copilot/board', { who: 3 })).data.stage, undefined, 'hidden from the others');
  day = (await w.call('GET', '/api/copilot', { who: 2 })).data;
  assert.equal(day.revealed, true);
  assert.equal(day.stage.track, pick.track);
  assert.deepEqual(day.tries, { driver: null, codriver: id });

  // once a day in each role: driver 1 can't drive again, but can be a co-driver; driver 2 can still drive
  assert.equal((await w.call('POST', '/api/copilot/lobbies', { who: 1, body: { role: 'driver' } })).status, 409);
  assert.equal((await w.call('POST', '/api/copilot/lobbies', { who: 2, body: { role: 'codriver' } })).status, 409);
  const second = await w.call('POST', '/api/copilot/lobbies', { who: 2, body: { role: 'driver', private: true } });
  assert.equal(second.status, 200);
  assert.match(second.data.lobby.code, /^[A-Z2-9]{6}$/);
  const listed = (await w.call('GET', '/api/copilot', { who: 1 })).data.lobbies.find((l) => l.id === second.data.lobby.id);
  assert.equal(listed.private, true, 'a private lobby is listed, locked');
  assert.equal(listed.code, undefined, 'its code never shown');
  const sid2 = second.data.lobby.id;
  assert.equal((await w.call('POST', '/api/copilot/join', { who: 1, body: { id: sid2 } })).status, 403, 'only with its code');
  assert.equal((await w.call('POST', '/api/copilot/join', { who: 1, body: { id: sid2, code: 'ZZZZZZ' } })).status, 403, 'wrong code');
  const j = await w.call('POST', '/api/copilot/join', { who: 1, body: { id: sid2, code: second.data.lobby.code.toLowerCase() } });
  assert.equal(j.data.lobby.myRole, 'codriver');
  await w.call('POST', `/api/copilot/lobbies/${sid2}/leave`, { who: 1 });
  const k = await w.call('POST', '/api/copilot/join', { who: 1, body: { code: second.data.lobby.code } });
  assert.equal(k.data.lobby.id, sid2, 'or by its code alone');
});

test('a try is used as the lobby starts: a driver who leaves is a DNF, a start with no run a DNF later', async () => {
  const w = world();
  const a = (await w.call('POST', '/api/copilot/lobbies', { who: 3, body: { role: 'codriver' } })).data.lobby.id;
  await w.call('POST', '/api/copilot/join', { who: 4, body: { id: a } });
  await w.call('POST', `/api/copilot/lobbies/${a}/ready`, { who: 3, body: {} });
  await w.call('POST', `/api/copilot/lobbies/${a}/ready`, { who: 4, body: {} });
  // the driver (4, the guest) quits: a DNF, the crew on the board as one
  await w.call('POST', `/api/copilot/lobbies/${a}/leave`, { who: 4 });
  let board = (await w.call('GET', '/api/copilot/board')).data;
  assert.equal(board.entries.length, 1);
  assert.equal(board.entries[0].status, 'dnf');
  assert.equal(board.entries[0].driver.steamId, sid(4));
  assert.equal((await w.call('POST', '/api/copilot/lobbies', { who: 4, body: { role: 'driver' } })).status, 409, 'that try is used');

  // a lobby that starts and never sends a run: a DNF once CP.driveMs has passed (the cron)
  const b = (await w.call('POST', '/api/copilot/lobbies', { who: 5, body: { role: 'driver' } })).data.lobby.id;
  await w.call('POST', '/api/copilot/join', { who: 6, body: { id: b } });
  await w.call('POST', `/api/copilot/lobbies/${b}/ready`, { who: 5, body: {} });
  await w.call('POST', `/api/copilot/lobbies/${b}/ready`, { who: 6, body: {} });
  await copilotTick(w.env, T0 + 10 * H + CP.driveMs + 1000, w.deps);
  board = (await w.call('GET', '/api/copilot/board')).data;
  assert.equal(board.entries.length, 2);
  assert.ok(board.entries.every((e) => e.status === 'dnf'));

  // a lobby left open too long is closed; the guest leaving an open one frees its place
  const c = (await w.call('POST', '/api/copilot/lobbies', { who: 1, body: { role: 'driver' } })).data.lobby.id;
  await w.call('POST', '/api/copilot/join', { who: 2, body: { id: c } });
  await w.call('POST', `/api/copilot/lobbies/${c}/leave`, { who: 2 });
  assert.equal(w.db.prepare('SELECT guest FROM copilot_lobbies WHERE id = ?').get(c).guest, null);
  await copilotTick(w.env, T0 + 10 * H + CP.openMs + 1000, w.deps);
  assert.equal(w.db.prepare('SELECT state FROM copilot_lobbies WHERE id = ?').get(c).state, 'closed');
});

test('the month\'s ranking: points for each day\'s place, drivers and co-drivers apart', async () => {
  assert.deepEqual([1, 2, 3, 10, 11, 40].map(pointsFor), [25, 18, 15, 1, 1, 1]);
  const w = world();
  const add = (date, lobby, driver, codriver, totalMs, status = 'finished') => w.db.prepare(`INSERT INTO copilot_runs
      (date, lobby_id, driver, codriver, status, total_ms, created) VALUES (?, ?, ?, ?, ?, ?, ?)`)
    .run(date, lobby, sid(driver), sid(codriver), status, totalMs, lobby);
  add('2026-11-24', 1, 1, 2, 200000);           // day 1: crew 1+2 wins, 3+4 second, 5+6 a DNF
  add('2026-11-24', 2, 3, 4, 210000);
  add('2026-11-24', 3, 5, 6, null, 'dnf');
  add('2026-11-25', 4, 3, 1, 190000);           // day 2: 3 drives again (wins), 1 as the co-driver
  add('2026-11-25', 5, 2, 5, 195000);
  add('2026-10-30', 6, 6, 5, 100000);           // another month: not counted
  const r = (await w.call('GET', '/api/copilot/ranking', { query: '?month=2026-11', now: T0 + 30 * H })).data;
  assert.deepEqual(r.drivers.map((x) => [x.name, x.points, x.days, x.wins, x.best]),
    [['Driver 3', 43, 2, 1, 1], ['Driver 1', 25, 1, 1, 1], ['Driver 2', 18, 1, 0, 2]]);
  assert.deepEqual(r.codrivers.map((x) => [x.name, x.points]), [['Driver 2', 25], ['Driver 1', 25], ['Driver 4', 18], ['Driver 5', 18]],
    'all even: who scored first ahead');
  assert.deepEqual(r.drivers.map((x) => x.rank), [1, 2, 3]);
  assert.equal((await w.call('GET', '/api/copilot/ranking', { query: '?month=2026-13' })).status, 400);
});

test('off on a server without COPILOT_FROM', async () => {
  const { env } = fakeD1({});
  const json = (data, status = 200) => ({ status, data });
  const err = (msg, status = 400) => ({ status, data: { error: msg } });
  const url = new URL('https://acrdaily.test/api/copilot');
  assert.deepEqual((await copilotApi(new Request(url), env, '/api/copilot', url, null, true, Date.now(), { json, err })).data, { on: false });
  assert.equal(await copilotApi(new Request(url), env, '/api/copilotx', url, null, true, Date.now(), { json, err }), null);
});
