import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { checkContribution, followsRoute } from '../src/index.js';

const FOLLOW_M = 30;   // (index.js's: every point of a driven route this close to the game's)

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

// a route from the game's files (est) and driven routes that may or may not replace it
const est = ober.route.map((p) => [...p]);
const bend = (pts, m) => pts.map(([x, z], i) => [x + m * Math.sin(Math.PI * i / (pts.length - 1)), z]);   // 0 at both ends

test('a driven line on the same road replaces the game\'s route: off the centre, ending before the stop control', () => {
  assert.equal(followsRoute(est.map(([x, z]) => [x + 4, z - 3]), est), null);
  assert.equal(followsRoute(est.slice(0, -15), est), null);                  // stops ~90 m before its end
  assert.equal(followsRoute(bend(est, FOLLOW_M - 5), est), null);            // wide lines, within the road's reach
});

test('made-up routes are refused: another road, a detour, the other way, half of it, a zigzag', () => {
  assert.match(followsRoute(bend(est, 60), est), /m off the road/);          // same start and finish, elsewhere between
  assert.match(followsRoute(est.map(([x, z]) => [x + 200, z]), est), /starts elsewhere/);
  assert.match(followsRoute([...est].reverse(), est), /starts elsewhere/);
  assert.match(followsRoute(est.slice(0, est.length >> 1), est), /ends elsewhere/);
  const zig = est.map(([x, z], i) => [x + (i % 2 ? 20 : -20), z]);         // on the road, but far longer
  assert.match(followsRoute(zig, est), /length/);
});
