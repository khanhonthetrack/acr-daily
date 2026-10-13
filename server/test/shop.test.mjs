// The shop (credits): its catalogue, and a driver's look as the pages and the app draw it.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { balanceOf } from '../src/credits.js';
import { checkDailySet, DAILY_SET, ITEMS, itemOf, KINDS, lookOf, lookOfRow, shopApi } from '../src/shop.js';
import { fakeD1, sid } from './faked1.mjs';

test('the catalogue: unique ids of the three kinds, a price, and what each kind needs to be drawn', () => {
  assert.equal(new Set(ITEMS.map((i) => i.id)).size, ITEMS.length);
  const hex = /^#[0-9A-F]{6}$/i;
  for (const i of ITEMS) {
    assert.ok(KINDS.includes(i.kind) && i.id.startsWith(i.kind + ':'), i.id);
    assert.ok(Number.isInteger(i.price) && i.price > 0 && i.name, i.id);
    if (i.kind === 'color') assert.ok(hex.test(i.color) && (!i.grad || (i.grad.length >= 2 && i.grad.every((c) => hex.test(c)))), i.id);
    if (i.kind === 'badge') assert.ok(i.badge && [...i.badge].length <= 2, i.id);
    if (i.kind === 'frame') assert.ok(hex.test(i.ring) && i.width > 0, i.id);
  }
  // ACR red is the site's own (P1, the active stage): not for sale
  assert.ok(!ITEMS.some((i) => /E30613|FF453A/i.test(JSON.stringify(i))));
});

test('a look: what is worn, drawn; ids of the wrong kind or gone from the shop are left out', () => {
  assert.equal(lookOf(null), null);
  assert.equal(lookOf({ color: null, badge: null, frame: null }), null);
  assert.deepEqual(lookOf({ color: 'color:gold', badge: 'badge:fire', frame: 'frame:carbon' }),
    { color: '#FFD60A', badge: '🔥', frame: { color: '#8A8F98', width: 3, dash: true } });
  assert.deepEqual(lookOf({ color: 'color:sunset' }), { color: '#FF9F43', grad: ['#FF9F43', '#FF7AB6'] });
  assert.equal(lookOf({ color: 'badge:fire', badge: 'color:gold', frame: 'frame:nope' }), null);
  assert.deepEqual(lookOfRow({ look_color: 'color:sky', look_badge: null, look_frame: 'frame:gold' }),
    { color: '#5BA8FF', frame: { color: '#FFD60A', width: 3 } });
  assert.equal(itemOf('color:gold').price, 400);
});

// ---- a daily of one's own (DAILY_SET)
const NOW = Date.parse('2026-10-12T15:00:00Z');
const TRACKS = [{ track: 'Wales Afon Bidno', rally: 'Wales', name: 'Afon Bidno' }];
const day = (n) => new Date(NOW + n * 86400000).toISOString().slice(0, 10);
const form = (over = {}) => ({ date: day(10), track: 'Wales Afon Bidno', car: 'Hyundai i20 N Rally2', weather: 'LightRain', time: 'evening', ...over });

test('a daily of one\'s own from its form: a day two days ahead or more, a stage of the pool, a car, the conditions', () => {
  assert.deepEqual(checkDailySet(form(), TRACKS, NOW).value,
    { date: day(10), track: 'Wales Afon Bidno', car: 'Hyundai i20 N Rally2', weather: 'LightRain', time: 'evening' });
  assert.equal(checkDailySet(form({ date: day(2) }), TRACKS, NOW).value.date, day(2));
  for (const [over, why] of [[{ date: day(0) }, /pick a day/], [{ date: day(1) }, /pick a day/], [{ date: day(61) }, /pick a day/],
    [{ date: '2026-02-31' }, /pick a day/], [{ track: 'Greece Elatia' }, /stage/], [{ car: 'Trabant' }, /car/],
    [{ weather: 'Sunny' }, /weather/], [{ time: 'night' }, /time/]]) {
    assert.match(checkDailySet(form(over), TRACKS, NOW).error, why, JSON.stringify(over));
  }
  assert.ok(DAILY_SET.price >= 10000 && DAILY_SET.minDays === 2 && DAILY_SET.slot === 1);
});

test('a daily of one\'s own: paid with the day, one per day, one at a time, changed for free, never without the credits', async () => {
  const { env, db } = fakeD1({ CREDITS_FROM: '2026-10-01' });
  db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Wales Afon Bidno', '[]', 4793, 0, 'WelesS4HafrenSouthFullForward')").run();
  db.prepare("INSERT INTO pool (track, car) VALUES ('Wales Afon Bidno', '*')").run();
  const me = (i) => ({ steam_id: sid(i), name: 'D' + i, banned: 0 });
  const fund = (i, n) => db.prepare('INSERT OR REPLACE INTO credits (steam_id, balance, streak, last_day) VALUES (?, ?, 0, NULL)').run(sid(i), n);
  const json = (data, status = 200) => ({ status, data });
  const err = (error, status = 400) => ({ status, data: { error } });
  const call = async (i, path, body) => shopApi(new Request('https://x' + path, { method: body ? 'POST' : 'GET', body: body && JSON.stringify(body) }),
    env, path, me(i), true, NOW, { json, err, balanceOf, lookChanged: async () => {} });
  const row = (date) => db.prepare('SELECT * FROM schedule WHERE date = ? AND slot = 1').get(date);
  // not enough credits: nothing set, nothing taken
  fund(1, DAILY_SET.price - 1);
  assert.equal((await call(1, '/api/shop/daily', form())).status, 402);
  assert.equal(row(day(10)), undefined);
  // enough: the day set, the price taken, a line in the history
  fund(1, DAILY_SET.price + 500);
  const r = await call(1, '/api/shop/daily', form());
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.deepEqual([row(day(10)).set_by, row(day(10)).car, row(day(10)).weather], [sid(1), 'Hyundai i20 N Rally2', 'LightRain']);
  assert.equal((await balanceOf(env, sid(1))).balance, 500);
  assert.deepEqual(db.prepare('SELECT delta, kind, ref FROM credit_ledger WHERE steam_id = ?').all(sid(1)).map((x) => ({ ...x })),
    [{ delta: -DAILY_SET.price, kind: 'daily-set', ref: `${day(10)}/1` }]);
  // the same day by someone else: taken; another day by me: one at a time (and neither costs a thing)
  fund(2, 50000);
  assert.equal((await call(2, '/api/shop/daily', form())).status, 409);
  fund(1, 50000);
  assert.match((await call(1, '/api/shop/daily', form({ date: day(20) }))).data.error, /one at a time/);
  assert.equal((await balanceOf(env, sid(1))).balance, 50000);
  assert.equal(row(day(20)), undefined);
  // mine changed for free
  assert.equal((await call(1, '/api/shop/daily', form({ car: 'Peugeot 208 Rally4', time: 'morning' }))).data.changed, true);
  assert.deepEqual([row(day(10)).car, row(day(10)).time], ['Peugeot 208 Rally4', 'morning']);
  assert.equal((await balanceOf(env, sid(1))).balance, 50000);
  // the shop tells me mine, and what a daily can be
  const s = (await call(1, '/api/shop')).data.daily;
  assert.deepEqual([s.price, s.from, s.mine.map((x) => [x.date, x.editable])], [DAILY_SET.price, day(2), [[day(10), true]]]);
  assert.deepEqual(s.tracks.map((t) => t.track), ['Wales Afon Bidno']);
  assert.ok(s.cars.length > 10 && s.weathers.some((w) => w.id === 'Storm') && s.times.some((t) => t.id === 'evening'));
});

test('a day the cron fixed already (two days ahead): the bought daily takes its pick\'s place; another driver\'s never', async () => {
  const { env, db } = fakeD1({ CREDITS_FROM: '2026-10-01' });
  for (const [t, id] of [['Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'], ['Wales Severn', 'WelesS4HafrenSouthFullReverse']]) {
    db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, '[]', 4793, 0, ?)").run(t, id);
    db.prepare("INSERT INTO pool (track, car) VALUES (?, '*')").run(t);
  }
  const fixed = (date, slot, track, by = null) => db.prepare(`INSERT INTO schedule (date, slot, track, car, weather, time, set_by)
    VALUES (?, ?, ?, 'Mini Cooper S 1275', 'Clear', 'midday', ?)`).run(date, slot, track, by);
  const at = (date, slot) => db.prepare('SELECT track, car, set_by FROM schedule WHERE date = ? AND slot = ?').get(date, slot);
  // the cron's picks for the coming days: SS1 Severn, SS2 Afon Bidno
  for (const n of [1, 2, 3]) { fixed(day(n), 1, 'Wales Severn'); fixed(day(n), 2, 'Wales Afon Bidno'); }
  const me = (i) => ({ steam_id: sid(i), name: 'D' + i, banned: 0 });
  for (const i of [1, 2]) db.prepare('INSERT INTO credits (steam_id, balance, streak, last_day) VALUES (?, 50000, 0, NULL)').run(sid(i));
  const call = (i, body) => shopApi(new Request('https://x/api/shop/daily', { method: 'POST', body: JSON.stringify(body) }), env,
    '/api/shop/daily', me(i), true, NOW, { json: (data, status = 200) => ({ status, data }), err: (error, status = 400) => ({ status, data: { error } }),
      balanceOf, lookChanged: async () => {} });
  // tomorrow: too soon, nothing changes, nothing paid
  assert.equal((await call(1, form({ date: day(1) }))).status, 400);
  assert.deepEqual({ ...at(day(1), 1) }, { track: 'Wales Severn', car: 'Mini Cooper S 1275', set_by: null });
  // two days ahead: mine in place of the cron's pick, paid; the day's SS2 on that same stage goes, to be picked again
  const r = await call(1, form({ date: day(2) }));
  assert.equal(r.status, 200, JSON.stringify(r.data));
  assert.deepEqual({ ...at(day(2), 1) }, { track: 'Wales Afon Bidno', car: 'Hyundai i20 N Rally2', set_by: sid(1) });
  assert.equal(at(day(2), 2), undefined);
  assert.equal((await balanceOf(env, sid(1))).balance, 50000 - DAILY_SET.price);
  // the day another driver set stays theirs: refused, nothing paid
  assert.match((await call(2, form({ date: day(2) }))).data.error, /someone has set that day/);
  assert.equal((await balanceOf(env, sid(2))).balance, 50000);
  // a change of mine to the other stage: SS2 on it goes too; SS2 on another stage stays
  fixed(day(2), 2, 'Wales Severn');
  assert.equal((await call(1, form({ date: day(2), track: 'Wales Severn' }))).data.changed, true);
  assert.equal(at(day(2), 2), undefined);
  assert.equal(at(day(3), 2).track, 'Wales Afon Bidno');
});
