// Realism measurements (no longer applied to submitted runs).   node --test test/*.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { compareField, judgeRealism, sections } from '../src/realism.js';

const load = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url)));
const clone = (o) => JSON.parse(JSON.stringify(o));
const wales = load('wales');
const ober = load('obersteigen');
const ober1 = load('obersteigen-run1');

test('real runs: no fail, no physics/timing flags', () => {
  for (const f of [wales, ober, ober1]) {
    const r = judgeRealism(f.result.trace);
    assert.equal(r.fail, null);
    // the companion log has no steering data, the app does: that is the only flag allowed here
    assert.deepEqual(r.flags.filter((x) => x !== 'no steering input'), []);
  }
});

// ---- 1. timing
test('slow-motion / speed hack (stage clock slower than real time) fails', () => {
  const tr = clone(wales.result.trace).map((s) => { s[5] = Math.round(s[5] / 0.9); return s; });
  assert.match(judgeRealism(tr).fail, /real time/);
});

test('clock and PC time both edited, physics steps not: fails on the physics rate', () => {
  const tr = clone(ober.result.trace).map((s) => { s[0] = Math.round(s[0] * 0.92); s[5] = Math.round(s[5] * 0.92); return s; });
  assert.match(judgeRealism(tr).fail || '', /physics|speed/);
});

// ---- 2. physics
test('speeds that do not match the movement fail', () => {
  const tr = clone(ober.result.trace).map((s) => { s[3] = s[3] * 1.25; return s; });
  assert.match(judgeRealism(tr).fail, /speed readings/);
});

test('impossible acceleration fails', () => {
  // a trace generated at constant 2 g, positions consistent with the speeds
  const tr = [];
  let x = 0, v = 0;
  for (let i = 0; i < 80; i++) {
    const t = i * 250;
    tr.push([t, x, 0, v * 3.6, 0, t, Math.round(t / 1000 * 333), 1, 0, 0.05 * Math.sin(i), 3, 3000 + v * 40]);
    v += 2 * 9.81 * 0.25; x += v * 0.25;
  }
  assert.match(judgeRealism(tr).fail || '', /acceleration|speed/);
});

// ---- 3. inputs
test('no throttle at all fails', () => {
  const tr = clone(wales.result.trace).map((s) => { s[7] = 0; return s; });
  assert.match(judgeRealism(tr).fail, /throttle/);
});

test('made-up rpm is flagged', () => {
  let seed = 1;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const tr = clone(wales.result.trace).map((s) => { s[11] = Math.round(2000 + rnd() * 5000); return s; });
  assert.ok(judgeRealism(tr).flags.includes('rpm does not follow speed'));
});

test('no steering is flagged', () => {
  const tr = clone(wales.result.trace).map((s) => { s[9] = 0; return s; });
  assert.ok(judgeRealism(tr).flags.includes('no steering input'));
});

// ---- 4. the field
test('section times are measured along the route', () => {
  const s = sections(ober.result.trace, { points: ober.route });
  assert.equal(s.length, 10);
  assert.ok(s.every((v, i) => v != null && (i === 0 || v > s[i - 1])));
  assert.ok(Math.abs(s[9] - ober.result.clockMs) < 1500);
});

test('field: a normal run among others is not flagged', () => {
  const a = sections(ober.result.trace, { points: ober.route });
  const b = sections(ober1.result.trace, { points: ober.route });
  const field = [b, b.map((v) => v * 1.04), b.map((v) => v * 0.98)];
  assert.deepEqual(compareField(a, field, ober.result.clockMs, null), []);
});

test('field: evenly 10 % faster than everyone in every section is flagged', () => {
  const b = sections(ober1.result.trace, { points: ober.route });
  const field = [b, b.map((v) => v * 1.03), b.map((v) => v * 0.99)];
  const flags = compareField(b.map((v) => v * 0.9), field, b[9] * 0.9, null);
  assert.ok(flags.some((f) => /every section/.test(f)), flags);
});

test('own history: 20 % faster than your previous best is flagged, 5 % is not', () => {
  assert.deepEqual(compareField([], [], 153634, 162300), []);
  assert.ok(compareField([], [], 120000, 162300)[0].includes('own previous best'));
});
