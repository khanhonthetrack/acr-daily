// Drivers' comments on their stages (src/comments.js): on a daily and a time trial stage shown with the time on its
// board; on a league event's stage (cup and 1V1 matches too) read by whoever runs it, told in their inbox; only on a
// stage the driver has a result on; changed, taken back, taken down by the admin. Through the whole worker, on a real
// SQLite (schema.sql) standing in for D1.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import worker from '../src/index.js';
import { parseTarget } from '../src/comments.js';
import { weekOf } from '../src/timetrial.js';
import { fakeD1, sid } from './faked1.mjs';

const ADMIN = 'k'.repeat(32);
const [ANN, BEN, CAL, DEE] = [sid(1), sid(2), sid(3), sid(4)];
const tokenOf = (s) => s.slice(-8).repeat(8);
const DAY = 86400000;

function world() {
  const f = fakeD1({ ADMIN_KEY: ADMIN, TIME_TRIAL_FROM: '2026-01-05' });
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CAL, 'Cal'], [DEE, 'Dee']]) {
    db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
    db.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, 0)')
      .run(createHash('sha256').update(tokenOf(s)).digest('hex'), s);
  }
  return f;
}

async function call(env, method, path, who = null, body = null, key = null) {
  const headers = { 'Content-Type': 'application/json', 'User-Agent': 'ACR-Daily/0.1.6 public' };
  if (who) headers.Authorization = 'Bearer ' + tokenOf(who);
  if (key) headers.Authorization = 'Bearer ' + key;
  const r = await worker.fetch(new Request('https://acrdaily.com' + path, { method, headers,
    ...(body ? { body: JSON.stringify(body) } : {}) }), env, { waitUntil() {} });
  return { status: r.status, body: await r.json() };
}
const say = (env, who, on, text) => call(env, 'POST', '/api/comments', who, { on, text });

const today = () => new Date().toISOString().slice(0, 10);
function dailyRun(db, who, status, totalMs, date = today(), slot = 1) {
  db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, total_ms, created, started_at)
    VALUES (?, ?, ?, 'Wales Sweet Lamb', 'Ford Fiesta Rally2', ?, ?, ?, 0, ?, ?, ?)`)
    .run(date, slot, who, status, status === 'dnf' ? 'retired' : null, totalMs, totalMs, Date.now() - 60000, Date.now() - 400000);
}

test('what a comment can be on', () => {
  assert.deepEqual(parseTarget('2026-11-15/1'), { kind: 'daily', date: '2026-11-15', slot: 1, target: '2026-11-15/1' });
  assert.deepEqual(parseTarget('tt:2026-11-09/2'), { kind: 'tt', week: '2026-11-09', slot: 2, target: 'tt:2026-11-09/2' });
  assert.deepEqual(parseTarget('event:12/0'), { kind: 'event', eventId: 12, no: 0, target: 'event:12/0' });
  for (const bad of ['2026-02-30/1', '2026-11-15/0', 'tt:2026-11-10/1', 'event:0/1', 'event:12/x', '', null, 'x']) {
    assert.equal(parseTarget(bad), null, String(bad));
  }
});

test('a daily: shown with the time and with a DNF; only by who drove it, until the next day ends; changed, taken back', async () => {
  const { env, db } = world();
  dailyRun(db, ANN, 'finished', 200000);
  dailyRun(db, BEN, 'dnf', null);
  const on = `${today()}/1`;
  let r = await say(env, ANN, on, '  Lost the rear\nin the hairpin before the split  ');
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.equal(r.body.comment.text, 'Lost the rear in the hairpin before the split');   // one line
  assert.equal((await say(env, BEN, on, 'Gearbox gone on the climb')).status, 200);
  const board = async () => (await call(env, 'GET', `/api/leaderboard?date=${today()}&slot=1`)).body.entries;
  assert.deepEqual((await board()).map((e) => [e.name, e.status, e.comment]),
    [['Ann', 'finished', 'Lost the rear in the hairpin before the split'], ['Ben', 'dnf', 'Gearbox gone on the climb']]);
  // nobody else's: Cal hasn't driven it; nor daily 2, nor a day already gone
  assert.equal((await say(env, CAL, on, 'Nice stage')).status, 409);
  assert.equal((await say(env, ANN, `${today()}/2`, 'x')).status, 409);
  const old = new Date(Date.now() - 2 * DAY).toISOString().slice(0, 10);
  dailyRun(db, ANN, 'finished', 210000, old);
  assert.match((await say(env, ANN, `${old}/1`, 'late')).body.error, /too late/);
  // changed, then taken back ('')
  assert.equal((await say(env, ANN, on, 'Clean run, happy')).body.comment.text, 'Clean run, happy');
  assert.equal((await board())[0].comment, 'Clean run, happy');
  assert.deepEqual((await say(env, ANN, on, '')).body, { comment: null });
  assert.equal((await board())[0].comment, undefined);
  // 200 characters at most; signed in; not banned
  assert.equal((await say(env, BEN, on, 'x'.repeat(201))).status, 400);
  assert.equal((await say(env, null, on, 'hello')).status, 401);
  db.prepare('UPDATE players SET banned = 1 WHERE steam_id = ?').run(BEN);
  assert.equal((await say(env, BEN, on, 'hello')).status, 403);
});

test('mine: the app starts its box from what I wrote', async () => {
  const { env, db } = world();
  dailyRun(db, ANN, 'finished', 200000);
  const on = `${today()}/1`;
  await say(env, ANN, on, 'Foggy, went slow');
  const r = await call(env, 'GET', `/api/comments/mine?on=${encodeURIComponent(on + ',event:9/0,junk')}`, ANN);
  assert.deepEqual(r.body, { comments: { [on]: 'Foggy, went slow' } });
  assert.deepEqual((await call(env, 'GET', `/api/comments/mine?on=${encodeURIComponent(on)}`, BEN)).body, { comments: {} });
});

test('a time trial stage: with the best on its board, only after a finished run', async () => {
  const { env, db } = world();
  const week = weekOf(Date.now()), on = `tt:${week}/1`;
  assert.equal((await say(env, ANN, on, 'First go')).status, 409);
  db.prepare(`INSERT INTO tt_runs (week, slot, steam_id, track, car, status, clock_ms, resets, total_ms, created)
    VALUES (?, 1, ?, 'Wales Sweet Lamb', 'Ford Fiesta Rally2', 'finished', 200000, 0, 200000, ?)`).run(week, ANN, Date.now());
  assert.equal((await say(env, ANN, on, 'Found two seconds in the forest')).status, 200);
  const b = (await call(env, 'GET', `/api/tt/board?week=${week}&slot=1`)).body;
  assert.equal(b.entries[0].comment, 'Found two seconds in the forest');
});

function league(db, kind = 'league', owner = ANN) {
  const lid = kind === 'cup' ? 'cup00001' : kind === 'h2h' ? 'h2h00001' : 'pub00001';
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES (?, 'Club', ?, 1, ?, 0, ?)")
    .run(lid, owner, 'CODE' + lid.slice(-4), kind);
  for (const [s, role] of [[ANN, 'member'], [BEN, 'admin'], [CAL, 'member'], [DEE, 'member']]) {
    db.prepare('INSERT INTO league_members (league_id, steam_id, joined, role) VALUES (?, ?, 0, ?)').run(lid, s, role);
  }
  const stages = [{ track: 'Wales Afon Biga', day: 1, service: true, weather: 'Clear', time: '09:00' },
    { track: 'Wales Sweet Lamb', day: 1, service: false, weather: 'Clear', time: '10:00' }];
  const id = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created)
    VALUES (?, 'Round 1', 'Wales', 'Ford Fiesta Rally2', '{}', ?, ?, ?, 0)`)
    .run(lid, JSON.stringify(stages), Date.now() - 3600000, Date.now() + DAY).lastInsertRowid;
  // Cal drove SS1 and is on SS2; Dee went out on SS1 (a DNF)
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, total_ms, started, updated)
    VALUES (?, ?, 'Ford Fiesta Rally2', 'running', 1, 250000, 0, 0)`).run(id, CAL);
  db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, created) VALUES (?, ?, 0, 250000, 0, 0)`).run(id, CAL);
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, reason, done, total_ms, started, updated)
    VALUES (?, ?, 'Ford Fiesta Rally2', 'dnf', 'retired', 0, 0, 0, 0)`).run(id, DEE);
  return id;
}
const inbox = (db, who) => db.prepare("SELECT kind, body, ref FROM messages WHERE to_id = ? AND kind = 'comment'").all(who)
  .map((m) => ({ ...m }));

test('a league event: whoever runs it reads them all and is told once; a driver sees only their own', async () => {
  const { env, db } = world();
  const id = league(db);
  assert.equal((await say(env, CAL, `event:${id}/0`, 'Puncture at the split, drove it home')).status, 200);
  assert.equal((await say(env, DEE, `event:${id}/0`, 'Into a tree on the second corner')).status, 200);   // its DNF stage
  assert.equal((await say(env, CAL, `event:${id}/1`, 'not driven yet')).status, 409);
  assert.equal((await say(env, DEE, `event:${id}/1`, 'never got there')).status, 409);
  // the owner (Ann) and the admin (Ben) are told, each once per comment, in their inbox
  for (const who of [ANN, BEN]) {
    assert.deepEqual(inbox(db, who).map((m) => m.body), ['Cal on Round 1, SS1: “Puncture at the split, drove it home”',
      'Dee on Round 1, SS1: “Into a tree on the second corner”']);
    assert.equal(inbox(db, who)[0].ref, `event:${id}`);
  }
  assert.equal(inbox(db, CAL).length + inbox(db, DEE).length, 0);
  await say(env, CAL, `event:${id}/0`, 'Puncture at the split, lost 20 s');   // changed: nobody told again
  await say(env, CAL, `event:${id}/0`, '');
  await say(env, CAL, `event:${id}/0`, 'Puncture at the split');
  assert.equal(inbox(db, ANN).length, 2);
  // the event's page: all of them for the owner and admins, a driver's own for them, none for the others
  const view = async (who) => (await call(env, 'GET', `/api/events/${id}`, who)).body;
  const ann = await view(ANN);
  assert.equal(ann.me.readsComments, true);
  assert.deepEqual(ann.comments.map((c) => [c.name, c.no, c.text]), [['Cal', 0, 'Puncture at the split'],
    ['Dee', 0, 'Into a tree on the second corner']]);
  assert.equal((await view(BEN)).comments.length, 2);
  assert.deepEqual((await view(CAL)).comments.map((c) => c.name), ['Cal']);
  assert.equal((await view(CAL)).me.readsComments, false);
  assert.deepEqual((await view(null)).comments, []);
});

test('a cup match: its maker reads and is told; a 1V1: nobody but the site\'s admin', async () => {
  const { env, db } = world();
  const cup = league(db, 'cup', ANN);
  await say(env, CAL, `event:${cup}/0`, 'Good fight');
  assert.equal(inbox(db, ANN).length, 1);
  assert.equal(inbox(db, BEN).length, 0);           // (a cup's holder has no admins)
  assert.equal((await call(env, 'GET', `/api/events/${cup}`, ANN)).body.comments.length, 1);
  assert.equal((await call(env, 'GET', `/api/events/${cup}`, BEN)).body.comments.length, 0);
  const { env: env2, db: db2 } = world();
  const h = league(db2, 'h2h', DEE);
  await say(env2, CAL, `event:${h}/0`, 'GG');
  assert.equal(db2.prepare("SELECT COUNT(*) AS n FROM messages WHERE kind = 'comment'").get().n, 0);
  const list = (await call(env2, 'GET', '/api/admin/comments', null, null, ADMIN)).body.comments;
  assert.deepEqual(list.map((c) => [c.name, c.text, c.kind, c.leagueKind]), [['Cal', 'GG', 'event', 'h2h']]);
  // an official one ('acr-daily' runs it): no driver to tell
  const { env: env3, db: db3 } = world();
  const off = league(db3, 'league', 'acr-daily');
  db3.prepare("DELETE FROM league_members WHERE role = 'admin'").run();
  await say(env3, CAL, `event:${off}/0`, 'Lovely stage');
  assert.equal(db3.prepare("SELECT COUNT(*) AS n FROM messages WHERE kind = 'comment'").get().n, 0);
});

test('the admin: every comment, taken down (off the board, but its driver still sees it) and put back', async () => {
  const { env, db } = world();
  dailyRun(db, ANN, 'finished', 200000);
  const id = league(db);
  const on = `${today()}/1`;
  await say(env, ANN, on, 'something rude');
  await say(env, CAL, `event:${id}/0`, 'also rude');
  assert.equal((await call(env, 'GET', '/api/admin/comments')).status, 403);
  assert.equal((await call(env, 'GET', '/api/admin/comments', ANN)).status, 403);
  const list = (await call(env, 'GET', '/api/admin/comments', null, null, ADMIN)).body.comments;
  assert.deepEqual(list.map((c) => c.text).sort(), ['also rude', 'something rude']);
  const daily = list.find((c) => c.kind === 'daily'), ev = list.find((c) => c.kind === 'event');
  assert.deepEqual((await call(env, 'POST', `/api/admin/comments/${daily.id}`, null, { action: 'hide' }, ADMIN)).body,
    { id: daily.id, hidden: true });
  await call(env, 'POST', `/api/admin/comments/${ev.id}`, null, { action: 'hide' }, ADMIN);
  const board = async () => (await call(env, 'GET', `/api/leaderboard?date=${today()}&slot=1`)).body.entries;
  assert.equal((await board())[0].comment, undefined);
  assert.equal((await call(env, 'GET', `/api/events/${id}`, ANN)).body.comments.length, 0);
  assert.deepEqual((await call(env, 'GET', `/api/events/${id}`, CAL)).body.comments.map((c) => [c.text, c.hidden]),
    [['also rude', true]]);
  await call(env, 'POST', `/api/admin/comments/${daily.id}`, null, { action: 'show' }, ADMIN);
  assert.equal((await board())[0].comment, 'something rude');
  assert.equal((await call(env, 'POST', `/api/admin/comments/${daily.id}`, null, { action: 'nuke' }, ADMIN)).status, 400);
  assert.equal((await call(env, 'POST', '/api/admin/comments/999', null, { action: 'hide' }, ADMIN)).status, 404);
});
