// Supporters on Buy Me a Coffee (src/supporters.js): only signed webhooks kept, test events not kept, members and
// monthly supporters listed while on, one-time coffees for 30 days, refunds taken away, never an e-mail.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { fakeD1 } from './faked1.mjs';
import { bmcWebhook, currentSupporters, shownName, signatureOk } from '../src/supporters.js';

const SECRET = 'whsec_test';
const NOW = 1795000000000;
const sign = (raw, s = SECRET) => createHmac('sha256', s).update(raw).digest('hex');

function hook(env, ev, { secret = SECRET, sig } = {}) {
  const raw = JSON.stringify({ event_id: 1, live_mode: true, created: NOW / 1000, attempt: 1, ...ev });
  return bmcWebhook(new Request('https://x/api/bmc/webhook', { method: 'POST', body: raw,
    headers: { 'x-signature-sha256': sig ?? sign(raw, secret) } }), env);
}
const coffee = (id, name, at, extra = {}) => ({ type: 'donation.created', data: { id, supporter_name: name,
  supporter_email: 'x@example.com', support_note: 'hi', coffee_count: 3, status: 'succeeded', refunded: 'false', created_at: at, ...extra } });
const names = async (env) => (await currentSupporters(env, NOW)).supporters.map((s) => s.name);

test('the signature is checked', async () => {
  assert.equal(await signatureOk('{"a":1}', SECRET, sign('{"a":1}')), true);
  assert.equal(await signatureOk('{"a":2}', SECRET, sign('{"a":1}')), false);
  assert.equal(await signatureOk('{"a":1}', SECRET, ''), false);
  const { env, db } = fakeD1({ BMC_WEBHOOK_SECRET: SECRET });
  assert.equal((await hook(env, coffee(1, 'Alex', NOW / 1000), { sig: 'ab'.repeat(32) })).status, 401);
  assert.equal((await hook(env, coffee(1, 'Alex', NOW / 1000), { secret: 'other' })).status, 401);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM supporters').get().n, 0);
  const { env: none } = fakeD1();
  assert.equal((await hook(none, coffee(1, 'Alex', NOW / 1000))).status, 503);
});

test('coffees for 30 days, refunds gone, test events not kept, no e-mail kept', async () => {
  const { env, db } = fakeD1({ BMC_WEBHOOK_SECRET: SECRET });
  const day = 86400;
  assert.equal((await hook(env, coffee(1, 'Alex', NOW / 1000 - 2 * day))).status, 200);
  await hook(env, coffee(2, 'Old', NOW / 1000 - 31 * day));
  await hook(env, coffee(3, 'Sam', NOW / 1000 - day));
  await hook(env, { ...coffee(4, 'Test', NOW / 1000), live_mode: false });
  assert.deepEqual(await names(env), ['Sam', 'Alex']);
  await hook(env, { type: 'donation.refunded', data: { id: 3, supporter_name: 'Sam', status: 'refunded' } });
  assert.deepEqual(await names(env), ['Alex']);
  const all = JSON.stringify(db.prepare('SELECT * FROM supporters').all());
  assert.ok(!all.includes('example.com') && !all.includes('hi'), all);
  assert.equal((await currentSupporters(env, NOW)).url, 'https://buymeacoffee.com/acrdaily');
});

test('members and monthly supporters while on, first in the list', async () => {
  const { env } = fakeD1({ BMC_WEBHOOK_SECRET: SECRET });
  await hook(env, coffee(1, 'Alex', NOW / 1000));
  await hook(env, { type: 'membership.started', data: { id: 7, supporter_name: 'Kim', status: 'active', membership_level_name: 'Gold',
    started_at: NOW / 1000 - 90 * 86400 } });
  await hook(env, { type: 'recurring_donation.started', data: { id: 8, supporter_name: 'Lee', status: 'active', started_at: NOW / 1000 - 5 } });
  assert.deepEqual(await names(env), ['Lee', 'Kim', 'Alex']);
  const kim = (await currentSupporters(env, NOW)).supporters.find((s) => s.name === 'Kim');
  assert.equal(kim.level, 'Gold');
  await hook(env, { type: 'membership.cancelled', data: { id: 7, supporter_name: 'Kim', status: 'canceled', canceled: 'true' } });
  await hook(env, { type: 'recurring_donation.paused', data: { id: 8, supporter_name: 'Lee', status: 'paused', paused: 'true' } });
  assert.deepEqual(await names(env), ['Alex']);
  await hook(env, { type: 'recurring_donation.updated', data: { id: 8, supporter_name: 'Lee', status: 'active', paused: 'false' } });
  assert.deepEqual(await names(env), ['Lee', 'Alex']);
});

test('names: hidden or empty is Someone, kept short', () => {
  assert.equal(shownName(''), 'Someone');
  assert.equal(shownName(null), 'Someone');
  assert.equal(shownName('  Alex\n  B '), 'Alex B');
  assert.equal(shownName('x'.repeat(80)).length, 32);
});
