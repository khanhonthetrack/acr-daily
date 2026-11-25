// The cars on a stage followed between looks (src/commentary.js observe): a stop, moving again, a reset, a sudden loss
// against the leader's pace, the splits with the place they make; and the leader's clock along the route.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { leaderAt, observe, dailiesCommentary } from '../src/commentary.js';

const DAY = { date: '2026-11-25', dailies: [{ slot: 1, stage: 'Col de Turini', rally: 'Monte Carlo', car: 'Lancia 037', lengthM: 10000 }] };
const LEAD = { steamId: 'L', name: 'uzuramcrae', status: 'finished', totalMs: 400000, splits: [100000, 200000, 300000] };
const SECOND = { steamId: 'S', name: 'osiek', status: 'finished', totalMs: 410000, splits: [102000, 205000, 307000] };
const boards = { 1: { results: [LEAD, SECOND] } };
const car = (progress, totalMs, extra = {}) => ({ 1: { drivers: [{ steamId: 'K', name: 'Kalle', state: 'live', progress, totalMs, updated: totalMs, ...extra }] } });
const fresh = () => ({ date: DAY.date, cars: {}, pending: [] });
const look = (track, progress, ms) => observe(track, DAY, boards, car(progress, ms), 1_000_000 + ms);

test('the leader\'s clock along the route, from its splits', () => {
  assert.equal(leaderAt(LEAD, 0), 0);
  assert.equal(leaderAt(LEAD, 0.125), 50000);
  assert.equal(leaderAt(LEAD, 0.5), 200000);
  assert.equal(leaderAt(LEAD, 0.875), 350000);
  assert.equal(leaderAt({ totalMs: 1, splits: null }, 0.5), null);
});

test('a split: up or down on the leader and the place it makes; splits already behind at first sight aren\'t news', () => {
  const t = fresh();
  assert.deepEqual(look(t, 0.47, 189000).moments, []);              // (first seen past split 1: not told)
  const { moments, onStage } = look(t, 0.51, 199000);              // the leader was at 204000 here: 5 s up; 400 m in 10 s
  assert.equal(moments.length, 1);
  assert.deepEqual(moments[0], { what: 'split 2 of 3', stage: 'SS1', driver: 'Kalle', where: '5.1 km in', clock: '3:19.0',
    vsLeader: '-5.000', leader: 'uzuramcrae', onCourseFor: 'P1' });
  assert.deepEqual(onStage[1][0], { name: 'Kalle', where: '5.1 km in', of: '10.0 km', clock: '3:19.0', speedKmh: 144, stopped: false,
    vsLeaderHere: '-5.000', onCourseFor: 'P1' });
});

test('a stop: told once; moving again: told with the time it cost, not again as a sudden loss', () => {
  const t = fresh();
  look(t, 0.40, 160000);
  assert.deepEqual(look(t, 0.4005, 165000).moments, []);           // (5 s: not yet a stop)
  const stop = look(t, 0.4008, 170000).moments;                    // 10 s, 8 m: stopped
  assert.equal(stop.length, 1);
  assert.match(stop[0].what, /^stopped on the stage/);
  assert.equal(stop[0].where, '4.0 km in');
  assert.equal(look(t, 0.4009, 176000).moments.length, 0);         // (still stopped: not told again)
  assert.equal(look(t, 0.4010, 180000).onStage[1][0].stopped, true);
  const go = look(t, 0.4100, 186000).moments;                      // 91 m in 10 s: 33 km/h
  assert.equal(go.length, 1);
  assert.equal(go[0].what, 'moving again after the stop');
  assert.equal(go[0].lost, '20.000 s stopped');                    // (standing from 160000 to its last still look, 180000)
  assert.deepEqual(look(t, 0.4200, 192000).moments, []);           // (the loss is told: no "sudden loss" after it)
});

test('a reset (the car put back): progress going backwards', () => {
  const t = fresh();
  look(t, 0.60, 250000);
  const m = look(t, 0.58, 256000).moments;
  assert.equal(m.length, 1);
  assert.match(m[0].what, /^put back on the road/);
});

test('a sudden loss against the leader\'s pace: 4 s more within a look', () => {
  const t = fresh();
  look(t, 0.20, 80000);                                            // leader 80000 here: level
  assert.deepEqual(look(t, 0.21, 83000).moments, []);              // leader 84000: 1 s up
  const m = look(t, 0.215, 92000).moments;                         // leader 86000: 6 s down, 7 s lost; still moving (45 km/h)
  assert.equal(m.length, 1);
  assert.match(m[0].what, /^lost time suddenly/);
  assert.equal(m[0].lost, '7.000 s in the last few seconds');
  assert.equal(m[0].nowVsLeader, '+6.000');
});

test('the moments reach Claude as events, and are cleared once told', async () => {
  const m = new Map(), cache = { match: async (r) => (m.has(r.url) ? new Response(m.get(r.url)) : undefined), put: async (r, x) => { m.set(r.url, await x.text()); } };
  let live = car(0.40, 160000);
  const ask = async (p) => (p === '/api/v1/dailies' ? DAY : p.endsWith('/live') ? live[1] : boards[1]);
  const calls = [];
  const client = { beta: { messages: { create: async (b) => { calls.push(JSON.parse(b.messages[0].content)); return { stop_reason: 'end_turn', content: [{ type: 'text', text: `Line ${calls.length}` }] }; } } } };
  const env = { ANTHROPIC_API_KEY: 'k' };
  await dailiesCommentary(env, ask, { client, cache, now: 1_000_000 });           // the day's first line
  live = car(0.4008, 170000);
  await dailiesCommentary(env, ask, { client, cache, now: 1_020_000 });           // stopped
  assert.equal(calls.length, 2);
  assert.match(calls[1].events[0].what, /^stopped on the stage/);
  assert.equal(calls[1].stages[0].onStageNow[0].stopped, true);
  await dailiesCommentary(env, ask, { client, cache, now: 1_040_000 });           // nothing new: no call
  assert.equal(calls.length, 2);
});
