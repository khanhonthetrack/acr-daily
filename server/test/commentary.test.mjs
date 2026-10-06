// Live commentary without an API key: template lines, stored and capped.   node --test test/*.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { comment, recentLines, templateLine } from '../src/commentary.js';

/** Just enough of D1 for commentary.js: one table in memory. */
function fakeDb() {
  const rows = [];
  return {
    rows,
    prepare(sql) {
      let args = [];
      const st = {
        bind(...a) { args = a; return st; },
        async first() {
          if (/COUNT\(\*\)/.test(sql)) return { n: rows.filter((r) => r.date === args[0]).length };
          return null;
        },
        async all() {
          const [date, slot, limit] = args;
          return { results: rows.filter((r) => r.date === date && r.slot === slot).sort((a, b) => b.id - a.id).slice(0, limit) };
        },
        async run() {
          const [date, slot, created, kind, steam_id, text] = args;
          rows.push({ id: rows.length + 1, date, slot, created, kind, steam_id, text });
          return { meta: { changes: 1 } };
        },
      };
      return st;
    },
  };
}

test('template lines say what happened', () => {
  assert.match(templateLine({ kind: 'start', driver: 'osiek', stage: 'Forêt de Saverne', car: 'Hyundai i20 N Rally2' }), /osiek is away on Forêt de Saverne/);
  assert.match(templateLine({ kind: 'split', driver: 'osiek', split: 2, time: '2:19.809', place: 1, of: 3 }), /split 2: 2:19.809, P1 of 3/);
  assert.match(templateLine({ kind: 'finish', driver: 'MaybeIWill', time: '5:47.348', place: 2, leader: 'osiek', gapToLeader: '+57.711 s' }), /P2, \+57.711 s off osiek/);
  assert.match(templateLine({ kind: 'finish', driver: 'osiek', time: '4:49.637', place: 1, resets: 0 }), /goes fastest: 4:49.637\.$/);
  assert.match(templateLine({ kind: 'reset', driver: 'x', at: '62 % into the stage' }), /reset at 62 %/);
  assert.match(templateLine({ kind: 'dnf', driver: 'x', reason: 'restarted' }), /out: restarted/);
});

test('without a key a template line is stored, and the newest come first', async () => {
  const env = { DB: fakeDb() };
  await comment(env, '2026-10-05', 1, { kind: 'start', driver: 'a', stage: 'S' }, '1');
  await comment(env, '2026-10-05', 1, { kind: 'dnf', driver: 'a', reason: 'restarted' }, '1');
  await comment(env, '2026-10-05', 2, { kind: 'start', driver: 'b', stage: 'T' }, '2');
  const lines = await recentLines(env, '2026-10-05', 1);
  assert.equal(lines.length, 2);
  assert.match(lines[0].text, /a is out/);
  assert.match(lines[1].text, /a is away on S/);
});

test('a broken API key falls back to the template line', async () => {
  const env = { DB: fakeDb(), ANTHROPIC_API_KEY: 'sk-ant-not-a-real-key', COMMENTARY_MODEL: 'claude-haiku-4-5' };
  const orig = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ type: 'error', error: { type: 'authentication_error', message: 'invalid x-api-key' } }),
    { status: 401, headers: { 'content-type': 'application/json' } });
  const err = console.error; console.error = () => {};
  try {
    await comment(env, '2026-10-05', 1, { kind: 'start', driver: 'c', stage: 'S' }, '3');
  } finally { globalThis.fetch = orig; console.error = err; }
  assert.match(env.DB.rows[0].text, /c is away on S/);
});
