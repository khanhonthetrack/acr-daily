// The live maps' cars (src/glide.js): along the route, played back late and steadily. The source the pages run
// (GLIDE_JS) is what is tested.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GLIDE_JS } from '../src/glide.js';

const { routeTrack, livePlayback } = new Function(GLIDE_JS + '; return { routeTrack, livePlayback };')();
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} vs ${b}`);

test('a point along the route follows the road round a corner, by distance', () => {
  const trk = routeTrack([[0, 0], [100, 0], [100, 100]]);   // 100 m east, then 100 m north
  assert.equal(trk.len, 200);
  assert.deepEqual(trk.at(0), [0, 0]);
  assert.deepEqual(trk.at(1), [100, 100]);
  assert.deepEqual(trk.at(0.5), [100, 0]);                   // halfway is the corner, not across it
  assert.deepEqual(trk.at(0.75), [100, 50]);
  assert.deepEqual(trk.at(-1), [0, 0]);
  assert.deepEqual(trk.at(2), [100, 100]);
  assert.equal(routeTrack([]).at(0.5), null);
  assert.deepEqual(routeTrack([[3, 4]]).at(0.5), [3, 4]);
});

// a driver whose app sends every 5 s; the website asks every 3 s and plays back 9 s late
const SEND = 5000, DELAY = 9000, GAP = 15000;
const drv = (t, p, state = 'live') => ({ steamId: '7', progress: p, state, updated: t });

test('between two updates the car moves steadily, however the checks fall', () => {
  const pb = livePlayback(DELAY, GAP);
  // the server's clock 1 s ahead of the browser's; the driver at 2 % every second (10 % per update)
  const ahead = 1000, seen = [];
  let sent = [];
  for (let now = 0; now <= 40000; now += 100) {
    const srv = now + ahead;
    if (srv % SEND === 0) sent = [drv(srv, srv / 50000)];
    if (now % 3000 === 0) pb.feed(sent, srv, now);
    const st = pb.at('7', now);
    if (now >= 20000 && st) seen.push(st.p);
    if (now === 30000) near(st.p, (30000 + ahead - DELAY) / 50000);                 // DELAY behind the server
  }
  assert.equal(seen.length, 201);
  for (let i = 1; i < seen.length; i++) near(seen[i] - seen[i - 1], 0.002, 1e-9);   // 100 ms = 0.2 %: never a stop or a jump
});

test('before its first update is due the car waits where it was first seen', () => {
  const pb = livePlayback(DELAY, GAP);
  pb.feed([drv(50000, 0.4)], 50000, 50000);
  assert.deepEqual(pb.at('7', 50000), { p: 0.4, state: 'live' });
  assert.equal(pb.at('8', 50000), null);
});

test('a finish shows when the car gets there, not before', () => {
  const pb = livePlayback(DELAY, GAP);
  pb.feed([drv(0, 0.9)], 0, 0);
  pb.feed([drv(5000, 1, 'finished')], 5000, 5000);
  assert.equal(pb.at('7', 11500).state, 'live');      // playing 2.5 s: on its way
  near(pb.at('7', 11500).p, 0.95);
  assert.deepEqual(pb.at('7', 14000), { p: 1, state: 'finished' });
});

test('back along the route (a new run) or a long silence: a jump, never a drive between', () => {
  const pb = livePlayback(DELAY, GAP);
  pb.feed([drv(0, 0.6)], 0, 0);
  pb.feed([drv(5000, 0.05)], 5000, 5000);
  near(pb.at('7', 9000 + 4000).p, 0.6);                // waits...
  near(pb.at('7', 9000 + 5000).p, 0.05);               // ...then is at the new run's place
  const pb2 = livePlayback(DELAY, GAP);
  pb2.feed([drv(0, 0.2)], 0, 0);
  pb2.feed([drv(60000, 0.8)], 60000, 60000);
  near(pb2.at('7', 9000 + 30000).p, 0.2);
  near(pb2.at('7', 9000 + 60000).p, 0.8);
});

test('a driver off the list stays until all their updates are shown', () => {
  const pb = livePlayback(DELAY, GAP);
  pb.feed([drv(0, 0.1)], 0, 0);
  pb.feed([drv(5000, 0.2)], 5000, 5000);
  pb.feed([], 6000, 6000);                             // dropped by the server
  near(pb.at('7', 11500).p, 0.15);                     // still driven to its last place...
  assert.ok(pb.at('7', 13900));
  assert.equal(pb.at('7', 14001), null);               // ...then gone
  assert.equal(pb.at('7', 0), null);                   // for good
  pb.feed([drv(20000, 0.3)], 20000, 20000);            // back on the list: shown again
  assert.ok(pb.at('7', 20000));
});

test('a slow answer does not set the cars back', () => {
  const pb = livePlayback(DELAY, GAP);
  pb.feed([drv(0, 0.1)], 0, 0);
  pb.feed([drv(5000, 0.2)], 5000, 5000);
  const before = pb.at('7', 12000).p;
  pb.feed([drv(5000, 0.2)], 6000, 8000);               // took 2 s to come back: the clock is not moved back
  near(pb.at('7', 12000).p, before);
  pb.feed([drv(5000, 0.2)], 3600000, 9000);            // this computer's clock was an hour out: taken afresh
  near(pb.at('7', 9000).p, 0.2);
});
