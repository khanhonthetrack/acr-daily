// Run traces in R2 (src/traces.js) and kept boards / weeks / stats (src/cache.js), on stand-ins for R2 and D1.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cached, dropCached, dropExpired } from '../src/cache.js';
import { getTrace, gunzip, gzip, putTrace, traceKey, traceText } from '../src/traces.js';

const wales = JSON.parse(readFileSync(new URL('./fixtures/wales.json', import.meta.url)));

/** R2 binding stand-in: put(key, bytes), get(key) -> {body: stream} | null */
function fakeR2() {
  const objects = new Map();
  return {
    objects,
    put: async (key, bytes) => { objects.set(key, bytes); },
    get: async (key) => (objects.has(key) ? { body: new Blob([objects.get(key)]).stream() } : null),
  };
}

/** D1 stand-in for the cache table: just the statements src/cache.js makes. */
function fakeDB({ failWrites = false } = {}) {
  const rows = new Map();
  const stmt = (sql, a = []) => ({
    bind: (...b) => stmt(sql, b),
    first: async () => {   // SELECT body FROM cache WHERE key = ? AND expires > ?
      const r = rows.get(a[0]);
      return r && r.expires > a[1] ? { body: r.body } : null;
    },
    run: async () => {
      if (sql.startsWith('INSERT')) {
        if (failWrites) throw new Error('D1 is down');
        rows.set(a[0], { body: a[1], expires: a[2] });
      } else if (sql.includes('expires <')) {
        for (const [k, r] of rows) if (r.expires < a[0]) rows.delete(k);
      } else if (sql.includes('IN (')) {
        for (const k of a) rows.delete(k);
      } else rows.clear();     // DELETE FROM cache
      return { meta: {} };
    },
  });
  return { rows, prepare: (sql) => stmt(sql) };
}

test('a trace survives gzip, and shrinks to well under half', async () => {
  const text = JSON.stringify(wales.result.trace);
  const z = await gzip(text);
  assert.equal(await gunzip(z), text);
  assert.ok(z.length < text.length / 2, `${z.length} of ${text.length} bytes`);
});

test('a trace goes to R2 under its run id and comes back', async () => {
  const env = { TRACES: fakeR2() };
  const text = JSON.stringify(wales.result.trace);    // as stored and served (JSON writes -0 as 0)
  await putTrace(env, 42, text);
  assert.ok(env.TRACES.objects.has(traceKey(42)));
  assert.equal(await traceText(env, { id: 42, trace: null }), text);
  assert.equal(JSON.stringify(await getTrace(env, { id: 42, trace: null })), text);
  assert.equal(await getTrace(env, { id: 43, trace: null }), null);                 // never stored
});

test('a run from before R2 still has its trace in its row, which wins', async () => {
  const env = { TRACES: fakeR2() };
  assert.equal(await traceText(env, { id: 7, trace: '[[1,2,3,4]]' }), '[[1,2,3,4]]');
  assert.equal(await traceText({}, { id: 7, trace: null }), null);                  // no bucket bound: nothing
});

test('a kept copy is built once, then used until its time is up', async () => {
  const env = { DB: fakeDB() };
  let builds = 0;
  const build = async () => ({ n: ++builds, entries: [{ name: 'osiek', totalMs: 313870 }] });
  const a = await cached(env, 'board:2026-10-07/1', 60000, build);
  const b = await cached(env, 'board:2026-10-07/1', 60000, build);
  assert.equal(builds, 1);
  assert.deepEqual(a, b);
  await cached(env, 'board:2026-10-07/2', -1, build);                              // kept already out of time...
  await cached(env, 'board:2026-10-07/2', 60000, build);                           // ...so this builds again
  assert.equal(builds, 3);
});

test('dropping copies: by key, all of them, and the ones out of time', async () => {
  const env = { DB: fakeDB() };
  let builds = 0;
  const build = async () => ++builds;
  await cached(env, 'board:d/1', 60000, build);
  await cached(env, 'board:d/2', 60000, build);
  await dropCached(env, ['board:d/1']);
  await cached(env, 'board:d/1', 60000, build);
  await cached(env, 'board:d/2', 60000, build);
  assert.equal(builds, 3);                                                         // only d/1 built again
  await dropCached(env);
  assert.equal(env.DB.rows.size, 0);
  await cached(env, 'old', -1, build);
  await cached(env, 'new', 60000, build);
  await dropExpired(env);
  assert.deepEqual([...env.DB.rows.keys()], ['new']);
});

test('a copy too big to keep, or one the database will not take, is still answered', async () => {
  const env = { DB: fakeDB() };
  const big = await cached(env, 'big', 60000, async () => 'x'.repeat(2_000_000));
  assert.equal(big.length, 2_000_000);
  assert.equal(env.DB.rows.size, 0);
  const down = { DB: fakeDB({ failWrites: true }) };
  assert.deepEqual(await cached(down, 'k', 60000, async () => ({ ok: 1 })), { ok: 1 });
});
