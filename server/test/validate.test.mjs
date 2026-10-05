// node --test test/   (runs against real runs judged by the app, see fixtures/)
// The server has no run checks: what the app sends counts, as clock + 60 s per reset.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { routeInfo, validateRun } from '../src/validate.js';

const load = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url)));
const clone = (o) => JSON.parse(JSON.stringify(o));

for (const name of ['wales', 'obersteigen']) {
  const { route, result } = load(name);
  const R = routeInfo(route);

  test(`${name}: the real run is accepted with the right total and no flags`, () => {
    const v = validateRun(result, R);
    assert.equal(v.ok, true, v.reason);
    assert.equal(v.totalMs, result.clockMs + result.resets * 60000);
    assert.deepEqual(v.flags, []);
    assert.equal(v.trace.length, result.trace.length);
  });

  test(`${name}: a DNF is stored as an attempt`, () => {
    const v = validateRun({ status: 'dnf', reason: 'restarted', clockMs: 1000, resets: 0 }, R);
    assert.equal(v.ok, true);
    assert.equal(v.totalMs, null);
  });
}

test('obersteigen: a braking spike (e.g. a crash) is accepted with no flags', () => {
  const { route, result } = load('obersteigen');
  const r = clone(result);
  const i = Math.floor(r.trace.length / 2);
  for (let k = i; k < i + 8; k++) r.trace[k][3] = Math.max(0, r.trace[k][3] - 400 * (k - i + 1));
  const v = validateRun(r, routeInfo(route));
  assert.equal(v.ok, true);
  assert.equal(v.status, 'finished');
  assert.deepEqual(v.flags, []);
});

test('a finished run without a usable trace still counts', () => {
  const { route } = load('wales');
  const v = validateRun({ status: 'finished', clockMs: 300000, resets: 2, trace: [[1, 'x'], null] }, routeInfo(route));
  assert.equal(v.ok, true);
  assert.equal(v.totalMs, 420000);
  assert.deepEqual(v.trace, []);
});

test('nonsense numbers and statuses are still refused', () => {
  const { route } = load('wales');
  const R = routeInfo(route);
  assert.equal(validateRun({ status: 'won', clockMs: 1 }, R).ok, false);
  assert.equal(validateRun({ status: 'finished', clockMs: -5, resets: 0 }, R).ok, false);
});
