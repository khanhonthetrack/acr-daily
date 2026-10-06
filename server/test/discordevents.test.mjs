// Discord server Events for the dailies: the payload, and a day of the minute loop (no Discord needed).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { eventPayload, eventsApi, syncEvents } from '../src/discordevents.js';

const head = (slot, menuName) => ({ slot, track: 'x', menuName, car: 'Hyundai i20 N Rally2', weatherLabel: 'Light fog',
  timeLabel: 'Midday (12:00)', lengthM: 6370, rally: 'Wales', surface: 'Gravel' });
const T0 = Date.parse('2026-10-07T00:00:30Z');

test('the event: name, details, a link, all day', () => {
  const e = eventPayload(head(2, 'Cwmbiga - Fedw Fain'), '2026-10-07', 'https://s', 'data:image/png;base64,AA', T0);
  assert.equal(e.name, 'SS2 · Cwmbiga - Fedw Fain');
  assert.match(e.description, /^Wales · Gravel · 6\.4 km\nCar: Hyundai i20 N Rally2\nConditions: Light fog, Midday \(12:00\)\n/);
  assert.match(e.description, /Timing sheet and live map: https:\/\/s$/);
  assert.equal(e.entity_type, 3);
  assert.equal(e.entity_metadata.location, 'https://s');
  assert.equal(e.scheduled_start_time, '2026-10-07T00:02:00.000Z');   // in the future, as Discord requires
  assert.equal(e.scheduled_end_time, '2026-10-07T23:59:00.000Z');
  assert.equal(e.image, 'data:image/png;base64,AA');
});

test('only with a bot token and a server id', () => {
  assert.equal(eventsApi('', '1556808894205141145'), null);
  assert.equal(eventsApi('abcdefghijklmnopqrstuvwxyz.123', 'x'), null);
  assert.ok(eventsApi('abcdefghijklmnopqrstuvwxyz.123', '1556808894205141145', async () => new Response('{}')));
});

test('a day: created at midnight, live a minute later, ended the next day; a deleted one is not made again', async () => {
  const db = new Map(), calls = [];
  let clock = T0, next = 100;
  const store = {
    get: async (k) => db.get(k) || null,
    set: async (k, id, hash, date) => { db.set(k, { id, hash, date, updated: clock }); },
  };
  const api = {
    create: async (b) => { calls.push(['create', b.name]); return { ok: true, status: 200, id: String(next++) }; },
    status: async (id, st) => { calls.push(['status', id, st]); return id === '101' && st === 3 ? { ok: false, status: 404 } : { ok: true, status: 200 }; },
  };
  const heads = async (date) => [head(1, date === '2026-10-07' ? 'Forêt de Saverne' : 'Old 1'), head(2, 'Cwmbiga - Fedw Fain')];
  const run = (now) => syncEvents({ api, store, heads, site: 'https://s', image: null, now: (clock = now) });

  assert.deepEqual(await run(T0), { 'event:2026-10-07/1': 'created', 'event:2026-10-07/2': 'created' });
  assert.deepEqual(await run(T0 + 60000), {});                         // not yet: its start time is still ahead
  assert.deepEqual(await run(T0 + 120000), { 'event:2026-10-07/1': 'live', 'event:2026-10-07/2': 'live' });
  assert.deepEqual(await run(T0 + 180000), {});                        // nothing to do all day
  const out = await run(T0 + 86400000);                                // next day
  assert.equal(out['event:2026-10-07/1'], 'ended');
  assert.equal(out['event:2026-10-07/2'], 'gone');                     // someone deleted it: not made again
  assert.equal(out['event:2026-10-08/1'], 'created');
  assert.deepEqual(await run(T0 + 86400000 + 30000), {});
  assert.deepEqual(calls.slice(0, 4), [['create', 'SS1 · Forêt de Saverne'], ['create', 'SS2 · Cwmbiga - Fedw Fain'],
    ['status', '100', 2], ['status', '101', 2]]);
});
