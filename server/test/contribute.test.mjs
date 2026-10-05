import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { checkContribution } from '../src/index.js';

const ober = JSON.parse(readFileSync(new URL('./fixtures/obersteigen.json', import.meta.url)));
const good = () => ({ track: 'Alsace Obersteigen', car: 'Peugeot 208 Rally4', clockMs: 153634, points: ober.route.map((p) => [...p]) });

test('a real clean route is accepted', () => assert.equal(checkContribution(good()), null));
test('a jump (reset) is refused', () => {
  const b = good(); b.points[300][0] += 80;
  assert.match(checkContribution(b), /jump/);
});
test('too short / too fast / bad name are refused', () => {
  const s = good(); s.points = s.points.slice(0, 150);
  assert.match(checkContribution(s), /short/);
  const f = good(); f.clockMs = 60000;
  assert.match(checkContribution(f), /speed/);
  const n = good(); n.track = '<script>';
  assert.match(checkContribution(n), /name/);
});
