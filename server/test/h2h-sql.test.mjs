// A 1V1's settling by the cron (h2hTick) on a real SQLite (schema.sql, node:sqlite): paid as soon as both drivers
// have a final result (a time or a DNF), the match then closing; otherwise only once its window and grace are over.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { h2hTick } from '../src/h2h.js';
import { LIMITS } from '../src/leagues.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;
const NOW = Date.UTC(2026, 9, 12, 18, 30);
const CLOSES = NOW + 23 * H;
const [A, B] = [sid(1), sid(2)];
const SPEC = { name: 'Duel', rally: 'Wales', car: 'Mini Cooper S 1275', car_class: null, rules: {}, opens: NOW - H, closes: CLOSES,
  stages: [{ track: 'Wales Afon Biga', day: 1, service: false, weather: 'Clear', time: '09:00' }] };

/** A 1V1 of Ann (A) against Ben (B), 50 each, accepted and its match made; entries: {steamId: [status, totalMs]}. */
function duel(entries) {
  const f = fakeD1();
  const { db } = f;
  db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Ann', 0), (?, 'Ben', 0)").run(A, B);
  db.prepare("INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('hh000001', '1V1: Ann vs Ben', ?, 'CODE2345', 0, 'h2h')").run(A);
  const ev = db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, only_ids)
    VALUES ('hh000001', 'Duel', 'Wales', ?, '{}', ?, ?, ?, 0, ?)`).run(SPEC.car, JSON.stringify(SPEC.stages), SPEC.opens, CLOSES,
    JSON.stringify([A, B])).lastInsertRowid;
  db.prepare(`INSERT INTO h2h (challenger, opponent, stake, spec, status, holder, event_id, created, answer_by, answered)
    VALUES (?, ?, 50, ?, 'accepted', 'hh000001', ?, 0, ?, 1)`).run(A, B, JSON.stringify(SPEC), ev, NOW);
  for (const [who, [status, ms]] of Object.entries(entries)) {
    db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, reason, done, total_ms, started, updated)
      VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)`).run(ev, who, SPEC.car, status, status === 'dnf' ? 'no official result from the game' : null,
      status === 'finished' ? 1 : 0, ms || 0);
    if (status === 'finished') {
      db.prepare(`INSERT INTO league_stage_times (event_id, steam_id, stage_no, time_ms, penalty_ms, created)
        VALUES (?, ?, 0, ?, 0, 0)`).run(ev, who, ms);
    }
  }
  return { ...f, ev };
}

const h2hRow = (db) => ({ ...db.prepare('SELECT status, winner, note, settled FROM h2h').get() });
const credits = (db, who) => (db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(who) || { balance: 0 }).balance;
const closesOf = (db, ev) => db.prepare('SELECT closes FROM league_events WHERE id = ?').get(ev).closes;

test('both finished: settled at once, the faster paid both stakes, both told, the match closed now', async () => {
  const { env, db, ev } = duel({ [A]: ['finished', 302239], [B]: ['finished', 291407] });
  assert.deepEqual(await h2hTick(env, NOW), [{ id: 1, status: 'settled', winner: B }]);
  assert.deepEqual(h2hRow(db), { status: 'settled', winner: B, note: 'by 10.832 s', settled: NOW });
  assert.equal(credits(db, B), 100);
  assert.equal(credits(db, A), 0);
  const told = db.prepare('SELECT to_id, body FROM messages ORDER BY to_id').all();
  assert.deepEqual(told.map((m) => m.to_id), [A, B]);
  assert.ok(told.every((m) => m.body === 'Ben won Duel (by 10.832 s): 100 credits to Ben.'), told);
  assert.equal(closesOf(db, ev), NOW);
  assert.deepEqual(await h2hTick(env, NOW + 5 * 60000), [], 'once');
  assert.equal(credits(db, B), 100);
});

test('one finished, the other DNF: settled at once, the only finisher', async () => {
  const { env, db } = duel({ [A]: ['dnf'], [B]: ['finished', 291407] });
  assert.deepEqual(await h2hTick(env, NOW), [{ id: 1, status: 'settled', winner: B }]);
  assert.equal(h2hRow(db).note, 'the only finisher');
  assert.equal(credits(db, B), 100);
});

test('both DNF: settled at once, no contest, the stakes back', async () => {
  const { env, db } = duel({ [A]: ['dnf'], [B]: ['dnf'] });
  assert.deepEqual(await h2hTick(env, NOW), [{ id: 1, status: 'settled', winner: null }]);
  assert.equal(h2hRow(db).note, 'nobody finished');
  assert.deepEqual([credits(db, A), credits(db, B)], [50, 50]);
});

test('one still to drive (on a stage, or not started): left until the window and its grace are over', async () => {
  for (const entries of [{ [B]: ['finished', 291407] }, { [A]: ['running'], [B]: ['finished', 291407] }]) {
    const { env, db, ev } = duel(entries);
    assert.deepEqual(await h2hTick(env, NOW), []);
    assert.deepEqual(await h2hTick(env, CLOSES + LIMITS.graceMs - 1), []);
    assert.equal(h2hRow(db).status, 'accepted');
    assert.deepEqual(await h2hTick(env, CLOSES + LIMITS.graceMs), [{ id: 1, status: 'settled', winner: B }]);
    assert.equal(h2hRow(db).note, 'the only finisher');
    assert.equal(closesOf(db, ev), CLOSES, 'settled at its close: the close stays');
  }
});
