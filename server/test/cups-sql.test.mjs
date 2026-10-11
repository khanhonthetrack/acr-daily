// A cup's cron work on a real SQLite (schema.sql, node:sqlite) through a stand-in for D1 that counts the queries: a
// 100-driver cup from its start to its final. The free plan allows 50 D1 queries a cron run, so a round has to open,
// be decided and be paid with a handful of bulk statements, however big the cup.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { cupsTick } from '../src/cups.js';
import { LIMITS } from '../src/leagues.js';

/** env.DB as D1 has it (prepare/bind/first/all/run, batch all or nothing) on an in-memory SQLite; count.queries: the
 *  calls to D1 (a batch is one). */
function fakeD1() {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('../schema.sql', import.meta.url), 'utf8'));
  const count = { queries: 0 };
  const exec = (sql, args) => {
    const st = db.prepare(sql);
    if (st.columns().length) return { results: st.all(...args), meta: { changes: 0 } };
    const r = st.run(...args);
    return { results: [], meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  };
  const prepare = (sql) => {
    const mk = (args) => ({ sql, args, bind: (...a) => mk(a),
      first: async () => { count.queries++; return exec(sql, args).results[0] || null; },
      all: async () => { count.queries++; return exec(sql, args); },
      run: async () => { count.queries++; return exec(sql, args); } });
    return mk([]);
  };
  const batch = async (stmts) => {
    count.queries++;
    db.exec('BEGIN');
    try {
      const out = stmts.map((s) => exec(s.sql, s.args));
      db.exec('COMMIT');
      return out;
    } catch (e) {
      db.exec('ROLLBACK');
      throw e;
    }
  };
  return { env: { DB: { prepare, batch } }, db, count };
}

const sid = (i) => String(76561198000000000n + BigInt(i));
const SPEC = { rally: 'Wales', car: 'Ford Fiesta Rally2', car_class: null, rules: {},
  stages: [{ track: 'wal_1', day: 1, service: false, weather: 'clear', time: '12:00' }] };

test('a 100-driver cup: 7 rounds (28 byes), each cron run a few queries, the top seed wins, the pot shared', async () => {
  const { env, db, count } = fakeD1();
  const now0 = Date.UTC(2026, 9, 12, 12, 0);
  const n = 100;
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  db.prepare(`INSERT INTO leagues (id, name, owner, code, created, kind) VALUES ('bigcup01', 'Big Cup', ?, 'CODE2345', 0, 'cup')`).run(sid(0));
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('bigcup01', 'Big Cup', ?, 128, 10, '[60,30,5,5]', ?, ?, 24, 'open', 0)`).run(sid(0), JSON.stringify(SPEC), now0 - 1);
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES (?, ?, 10, 0)').run('bigcup01', sid(i));

  // the start: seeds, round 1 (64 slots: 36 matches, 28 byes) and a notice to everyone, in a few queries
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now0), [{ cup: 'bigcup01', did: 'started' }]);
  assert.ok(count.queries <= 6, `the start took ${count.queries} queries`);
  const seeds = db.prepare('SELECT seed FROM cup_entries WHERE cup_id = ? ORDER BY seed').all('bigcup01').map((r) => r.seed);
  assert.deepEqual(seeds, Array.from({ length: n }, (_, i) => i + 1));
  const r1 = db.prepare('SELECT * FROM cup_matches WHERE cup_id = ? AND round = 1').all('bigcup01');
  assert.equal(r1.length, 64);
  assert.equal(r1.filter((m) => !m.b && m.winner === m.a && m.note === 'a bye').length, 28);
  const games = r1.filter((m) => m.a && m.b);
  assert.equal(games.length, 36);
  assert.ok(games.every((m) => m.event_id && !m.winner), 'every match has its event');
  const ev = db.prepare('SELECT * FROM league_events WHERE id = ?').get(games[0].event_id);
  assert.deepEqual(JSON.parse(ev.only_ids), [games[0].a, games[0].b]);
  assert.match(ev.name, /^Round of 128: Driver \d+ vs Driver \d+$/);
  assert.equal(ev.closes, now0 + 24 * 3600000);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM league_events WHERE league_id = 'bigcup01'").get().n, 36);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE kind = 'cup'").get().n, 100);

  // nothing to do until the round's matches close: no work at all
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now0 + 3600000), []);
  assert.ok(count.queries <= 2);

  // each round closes with nobody having driven: the higher seed goes through, the next round opens in the same run
  let now = now0;
  for (let round = 1; round <= 7; round++) {
    now += 25 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'bigcup01'").run(now - LIMITS.graceMs - 1);
    count.queries = 0;
    const did = await cupsTick(env, now);
    assert.ok(count.queries <= 8, `round ${round} took ${count.queries} queries`);
    assert.deepEqual(did.map((d) => d.did), [round < 7 ? `round ${round + 1}` : 'finished']);
  }
  const cup = db.prepare("SELECT * FROM cups WHERE id = 'bigcup01'").get();
  assert.equal(cup.status, 'finished');
  assert.equal(cup.round, 7);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM cup_matches WHERE cup_id = 'bigcup01'").get().n, 127);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM cup_matches WHERE cup_id = 'bigcup01' AND winner IS NULL").get().n, 0);

  // places: the top seed won, then 2, the losing semi-finalists 3 ...; the pot of 1000 as 60 / 30 / 5 / 5
  const seedOf = new Map(db.prepare("SELECT steam_id, seed FROM cup_entries WHERE cup_id = 'bigcup01'").all().map((r) => [r.steam_id, r.seed]));
  const placed = db.prepare("SELECT steam_id, place FROM cup_entries WHERE cup_id = 'bigcup01' AND place IS NOT NULL ORDER BY place").all();
  assert.equal(placed.length, n);
  assert.equal(seedOf.get(placed[0].steam_id), 1);
  assert.deepEqual(placed.slice(0, 4).map((p) => p.place), [1, 2, 3, 3]);
  const paid = db.prepare("SELECT steam_id, delta FROM credit_ledger WHERE kind = 'cup-prize' ORDER BY delta DESC").all();
  assert.deepEqual(paid.map((p) => p.delta), [600, 300, 50, 50]);
  assert.equal(paid[0].steam_id, placed[0].steam_id);
  assert.equal(db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(placed[0].steam_id).balance, 600);
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE body LIKE 'Big Cup is over:%'").get().n, n);

  // and nothing more to do
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, now + 3600000), []);
  assert.ok(count.queries <= 2);
});

test('a 128 cup with 63 drivers shrinks to a bracket of 64: a Round of 64, one bye (the top seed), 6 rounds', async () => {
  const { env, db } = fakeD1();
  const n = 63;
  for (let i = 0; i < n; i++) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(sid(i), 'Driver ' + i);
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('half0001', 'Half Cup', ?, 128, 0, '[100]', ?, 1, 24, 'open', 0)`).run(sid(0), JSON.stringify(SPEC));
  for (let i = 0; i < n; i++) db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('half0001', ?, 0, 0)").run(sid(i));
  await cupsTick(env, 1000);
  const r1 = db.prepare("SELECT * FROM cup_matches WHERE cup_id = 'half0001' AND round = 1 ORDER BY slot").all();
  assert.equal(r1.length, 32);
  const byes = r1.filter((m) => !m.b);
  assert.equal(byes.length, 1);
  assert.equal(db.prepare("SELECT seed FROM cup_entries WHERE cup_id = 'half0001' AND steam_id = ?").get(byes[0].a).seed, 1);
  assert.match(db.prepare("SELECT name FROM league_events WHERE league_id = 'half0001' LIMIT 1").get().name, /^Round of 64: /);
  let now = 1000;
  for (let round = 1; round <= 6; round++) {
    now += 25 * 3600000;
    db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'half0001'").run(now - LIMITS.graceMs - 1);
    await cupsTick(env, now);
  }
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'half0001'").get().status, 'finished');
  assert.equal(db.prepare("SELECT MAX(round) AS r FROM cup_matches WHERE cup_id = 'half0001'").get().r, 6);
});

test('a cup that does not fill: called off, every fee back, in a few queries', async () => {
  const { env, db, count } = fakeD1();
  db.prepare("INSERT INTO players (steam_id, name, created) VALUES (?, 'Ann', 0)").run(sid(1));
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('lonely01', 'Lonely Cup', ?, 8, 25, '[100]', ?, 1, 24, 'open', 0)`).run(sid(1), JSON.stringify(SPEC));
  db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('lonely01', ?, 25, 0)").run(sid(1));
  count.queries = 0;
  assert.deepEqual(await cupsTick(env, 1000), [{ cup: 'lonely01', did: 'called off' }]);
  assert.ok(count.queries <= 4);
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'lonely01'").get().status, 'cancelled');
  assert.equal(db.prepare('SELECT balance FROM credits WHERE steam_id = ?').get(sid(1)).balance, 25);
  assert.match(db.prepare('SELECT body FROM messages WHERE to_id = ?').get(sid(1)).body, /did not start: .*your entry fee is back\.$/);
});
