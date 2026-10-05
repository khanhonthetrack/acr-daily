// node --test test/   (runs against real runs judged by the app, see fixtures/)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { routeInfo, validateRun } from '../src/validate.js';

const load = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url)));
const clone = (o) => JSON.parse(JSON.stringify(o));

for (const name of ['wales', 'obersteigen']) {
  const { route, result } = load(name);
  const R = routeInfo(route);

  test(`${name}: the real run is accepted with the right total`, () => {
    const v = validateRun(result, R);
    assert.equal(v.ok, true, v.reason);
    assert.equal(v.totalMs, result.clockMs + result.resets * 60000);
  });

  test(`${name}: a faster claimed time is refused`, () => {
    const r = clone(result);
    r.clockMs -= 10000; r.totalMs -= 10000;
    assert.equal(validateRun(r, R).ok, false);
  });

  test(`${name}: a wrong total is refused`, () => {
    const r = clone(result);
    r.totalMs -= 1000;
    assert.equal(validateRun(r, R).ok, false);
  });

  test(`${name}: cutting out the middle of the stage is refused`, () => {
    const r = clone(result);
    const n = r.trace.length;
    r.trace = r.trace.slice(0, Math.floor(n * 0.3)).concat(r.trace.slice(Math.floor(n * 0.7)));
    assert.equal(validateRun(r, R).ok, false);
  });

  test(`${name}: a run on another stage's route is refused`, () => {
    const other = name === 'wales' ? load('obersteigen') : load('wales');
    assert.equal(validateRun(result, routeInfo(other.route)).ok, false);
  });

  test(`${name}: a DNF is stored as an attempt`, () => {
    const v = validateRun({ status: 'dnf', reason: 'restarted', clockMs: 1000, resets: 0 }, R);
    assert.equal(v.ok, true);
    assert.equal(v.totalMs, null);
  });
}

test('wales: hiding the reset is refused', () => {
  const { route, result } = load('wales');
  assert.equal(result.resets, 1);
  const r = clone(result);
  r.resets = 0; r.totalMs = r.clockMs;
  r.trace.forEach((s) => { s[4] = 0; });
  assert.equal(validateRun(r, routeInfo(route)).ok, false);
});
