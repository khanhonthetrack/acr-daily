// The shop (credits): its catalogue, and a driver's look as the pages and the app draw it.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { ITEMS, itemOf, KINDS, lookOf, lookOfRow } from '../src/shop.js';

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
