// Event sign-ups on Discord (src/discordrsvp.js): /event's form, the card and its Attending / Maybe / Not attending
// buttons, the signature check, the server Event and the command's registration; then the whole worker, signed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';
import { fakeD1 } from './faked1.mjs';
import { EVENT_COMMAND, eventCard, eventModal, handleInteraction, parseHours, parseWhen, rsvpApi, syncCommands,
  verifySignature } from '../src/discordrsvp.js';

const NOW = Date.UTC(2026, 10, 16, 12, 0);
const GUILD = '1556808894205141145';
const ANN = '100000000000000001', BEN = '100000000000000002', CAL = '100000000000000003';

test('start times: ISO in UTC, offsets, Discord timestamps, Unix seconds', () => {
  const at = Date.UTC(2026, 10, 22, 19, 0);
  assert.equal(parseWhen('2026-11-22 19:00', NOW).ms, at);
  assert.equal(parseWhen('2026-11-22 19:00 UTC', NOW).ms, at);
  assert.equal(parseWhen('2026-11-22T19:00Z', NOW).ms, at);
  assert.equal(parseWhen('2026-11-22 20:00 +01:00', NOW).ms, at);
  assert.equal(parseWhen('2026-11-22 20:00 UTC+1', NOW).ms, at);
  assert.equal(parseWhen('2026-11-22 14:00 -5', NOW).ms, at);
  assert.equal(parseWhen('2026-11-23 00:30 GMT+5:30', NOW).ms, at);
  assert.equal(parseWhen(`<t:${at / 1000}:F>`, NOW).ms, at);
  assert.equal(parseWhen(`<t:${at / 1000}>`, NOW).ms, at);
  assert.equal(parseWhen(String(at / 1000), NOW).ms, at);
  assert.match(parseWhen('next sunday', NOW).error, /couldn't read/);
  assert.match(parseWhen('2026-02-30 19:00', NOW).error, /real date/);
  assert.match(parseWhen('2026-11-22 25:00', NOW).error, /real date/);
  assert.match(parseWhen('2026-11-01 19:00', NOW).error, /past/);
  assert.match(parseWhen('2028-11-01 19:00', NOW).error, /year/);
});

test('length: hours, 2 by default', () => {
  assert.equal(parseHours('').ms, 2 * 3600000);
  assert.equal(parseHours('1.5').ms, 90 * 60000);
  assert.equal(parseHours('1,5').ms, 90 * 60000);
  assert.equal(parseHours('3h').ms, 3 * 3600000);
  assert.ok(parseHours('0').error && parseHours('100').error && parseHours('soon').error);
});

test('the command and its form fit Discord', () => {
  assert.equal(EVENT_COMMAND.default_member_permissions, String(1n << 33n));   // Manage Events by default
  const m = eventModal();
  assert.ok(m.title.length <= 45 && m.components.length <= 5);
  for (const row of m.components) {
    const c = row.components[0];
    assert.ok(c.label.length <= 45, c.label);
    assert.ok(!c.placeholder || c.placeholder.length <= 100, c.placeholder);
  }
});

const EV = { id: 7, guild_id: GUILD, title: 'Sunday night rally', description: 'Monte Carlo, Fabia', location: 'ACR',
  starts: Date.UTC(2026, 10, 22, 19, 0), ends: Date.UTC(2026, 10, 22, 21, 0), created_by_name: 'Ann' };

test('the card: who answered what, mentions that ping nobody, the buttons until it is over', () => {
  const c = eventCard(EV, [{ user_id: ANN, answer: 'yes' }, { user_id: BEN, answer: 'maybe' }, { user_id: CAL, answer: 'yes' }], NOW);
  const e = c.embeds[0], f = Object.fromEntries(e.fields.map((x) => [x.name, x.value]));
  assert.equal(f['✅ Attending (2)'], `<@${ANN}>, <@${CAL}>`);
  assert.equal(f['❔ Maybe (1)'], `<@${BEN}>`);
  assert.equal(f['❌ Not attending (0)'], '-');
  assert.match(f.When, /<t:\d+:F> to <t:\d+:t> · <t:\d+:R>/);
  assert.deepEqual(c.allowed_mentions, { parse: [] });
  assert.deepEqual(c.components[0].components.map((b) => b.custom_id), ['rsvp:7:yes', 'rsvp:7:maybe', 'rsvp:7:no']);
  const over = eventCard(EV, [], EV.ends);
  assert.deepEqual(over.components, []);
  assert.match(over.embeds[0].footer.text, /over/);
  const linked = eventCard({ ...EV, scheduled_id: '42' }, [], NOW).embeds[0].fields.find((x) => x.name === 'Reminder');
  assert.match(linked.value, new RegExp(`discord.com/events/${GUILD}/42`));
});

test('a crowd stays within a field: "+N more"', () => {
  const many = Array.from({ length: 80 }, (_, i) => ({ user_id: String(200000000000000000n + BigInt(i)), answer: 'yes' }));
  const v = eventCard(EV, many, NOW).embeds[0].fields.find((x) => x.name.startsWith('✅')).value;
  assert.ok(v.length <= 1024, v.length);
  assert.match(v, /\+\d+ more$/);
});

/** A store in memory, as index.js's rsvpStore keeps it in D1. */
function memStore() {
  const evs = new Map(), rs = [];
  let next = 1, tick = 0;
  return {
    evs, rs,
    create: async (ev) => { const id = next++; evs.set(id, { ...ev, id }); return id; },
    get: async (id) => evs.get(id) || null,
    setScheduled: async (id, sid) => { evs.get(id).scheduled_id = sid; },
    answer: async (id, user, name, answer) => {
      const i = rs.findIndex((r) => r.event_id === id && r.user_id === user);
      if (i >= 0) rs.splice(i, 1);
      if (answer) rs.push({ event_id: id, user_id: user, answer, at: tick++ });
    },
    rsvps: async (id) => rs.filter((r) => r.event_id === id),
  };
}

const submit = (values, user = ANN) => ({
  type: 5, guild_id: GUILD, channel_id: '300', application_id: '400', token: 'tok',
  member: { user: { id: user, username: 'ann', global_name: 'Ann' } },
  data: { custom_id: 'event:new', components: Object.entries(values).map(([custom_id, value]) =>
    ({ type: 1, components: [{ type: 4, custom_id, value }] })) },
});
const click = (id, answer, user) => ({ type: 3, guild_id: GUILD, member: { user: { id: user, username: user } },
  data: { custom_id: `rsvp:${id}:${answer}`, component_type: 2 } });

test('/event opens the form; the form posts the card; the buttons answer, change and take back', async () => {
  const store = memStore();
  assert.deepEqual((await handleInteraction({ type: 1 }, { store })).response, { type: 1 });
  const open = await handleInteraction({ type: 2, guild_id: GUILD, data: { name: 'event' } }, { store, now: NOW });
  assert.equal(open.response.type, 9);
  assert.equal(open.response.data.custom_id, 'event:new');

  const made = await handleInteraction(submit({ title: 'Sunday night rally', when: '2026-11-22 19:00 UTC', hours: '',
    where: 'Monte Carlo', description: 'Line one\nLine two' }), { store, now: NOW });
  assert.equal(made.response.type, 4);
  assert.equal(made.response.data.embeds[0].title, 'Sunday night rally');
  assert.equal(made.response.data.embeds[0].description, 'Line one\nLine two');
  assert.equal(made.after, null);                                   // no bot token: no server Event
  const ev = store.evs.get(1);
  assert.equal(ev.ends - ev.starts, 2 * 3600000);
  assert.equal(ev.channel_id, '300');

  const field = (r, prefix) => r.response.data.embeds[0].fields.find((x) => x.name.startsWith(prefix));
  let r = await handleInteraction(click(1, 'yes', ANN), { store, now: NOW });
  assert.equal(r.response.type, 7);
  assert.equal(field(r, '✅').name, '✅ Attending (1)');
  r = await handleInteraction(click(1, 'maybe', BEN), { store, now: NOW });
  r = await handleInteraction(click(1, 'no', ANN), { store, now: NOW });     // Ann changes her mind
  assert.equal(field(r, '✅').name, '✅ Attending (0)');
  assert.equal(field(r, '❌').value, `<@${ANN}>`);
  r = await handleInteraction(click(1, 'no', ANN), { store, now: NOW });     // the same button again: taken back
  assert.equal(field(r, '❌').name, '❌ Not attending (0)');
  assert.equal(store.rs.length, 1);

  r = await handleInteraction(click(1, 'yes', CAL), { store, now: ev.ends + 1 });   // over: no change, buttons gone
  assert.deepEqual(r.response.data.components, []);
  assert.equal(store.rs.length, 1);
  r = await handleInteraction(click(99, 'yes', CAL), { store, now: NOW });
  assert.equal(r.response.data.flags, 64);
});

test('a start time it can\'t read: nothing posted, told why, and what was typed to copy', async () => {
  const store = memStore();
  const r = await handleInteraction(submit({ title: 'Rally', when: 'sunday 7pm', description: 'Keep me' }), { store, now: NOW });
  assert.equal(r.response.data.flags, 64);                         // only the one who typed it sees it
  assert.match(r.response.data.content, /couldn't read the start time/);
  assert.match(r.response.data.content, /Keep me/);
  assert.equal(store.evs.size, 0);
});

test('with the bot: the server Event made after the answer, and the card edited to link it', async () => {
  const store = memStore(), calls = [];
  const api = {
    createScheduled: async (body) => { calls.push(['event', body]); return { ok: true, id: '555' }; },
    editOriginal: async (app, token, msg) => { calls.push(['edit', app, token, msg]); return { ok: true }; },
  };
  const made = await handleInteraction(submit({ title: 'Rally', when: '2026-11-22 19:00', hours: '3' }), { store, api, now: NOW, site: 'https://acrdaily.com' });
  assert.equal(calls.length, 0);                                   // nothing before the answer has gone
  assert.deepEqual(await made.after(), { scheduled: '555', card: 'linked' });
  const body = calls[0][1];
  assert.equal(body.entity_type, 3);
  assert.equal(body.scheduled_start_time, '2026-11-22T19:00:00.000Z');
  assert.equal(body.scheduled_end_time, '2026-11-22T22:00:00.000Z');
  assert.deepEqual(calls[1].slice(1, 3), ['400', 'tok']);
  assert.ok(calls[1][3].embeds[0].fields.some((f) => f.value.includes(`/events/${GUILD}/555`)));
  assert.equal(store.evs.get(1).scheduled_id, '555');
});

test('/event is registered once, and again when it changes', async () => {
  const calls = [], kept = new Map();
  const fetchFn = async (url, init) => {
    calls.push(`${init.method} ${url.replace('https://discord.com/api/v10', '')}`);
    return { ok: true, status: 200, json: async () => (url.endsWith('/@me') ? { id: '400' } : [{ id: '1' }]) };
  };
  const api = rsvpApi('x'.repeat(30), GUILD, fetchFn);
  const store = { get: async (k) => kept.get(k) || null, set: async (k, id, hash) => kept.set(k, { id, hash }) };
  const hashOf = async (s) => String(s.length);
  assert.equal(await syncCommands({ api, store, hashOf }), 'registered');
  assert.deepEqual(calls, ['GET /oauth2/applications/@me', `PUT /applications/400/guilds/${GUILD}/commands`]);
  assert.equal(await syncCommands({ api, store, hashOf }), 'unchanged');
  assert.equal(calls.length, 2);
});

// ------------------------------------------------------------------ signed, through the whole worker

async function keys() {
  const k = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  const pub = Buffer.from(await crypto.subtle.exportKey('raw', k.publicKey)).toString('hex');
  return { pub, sign: async (ts, body) => Buffer.from(await crypto.subtle.sign({ name: 'Ed25519' }, k.privateKey,
    new TextEncoder().encode(ts + body))).toString('hex') };
}

test('the signature: Discord\'s passes, anything else does not', async () => {
  const k = await keys(), body = '{"type":1}', ts = '1763300000';
  const sig = await k.sign(ts, body);
  assert.equal(await verifySignature(k.pub, sig, ts, body), true);
  assert.equal(await verifySignature(k.pub, sig, ts, body + ' '), false);
  assert.equal(await verifySignature(k.pub, sig, '1763300001', body), false);
  assert.equal(await verifySignature(k.pub, 'zz', ts, body), false);
  assert.equal(await verifySignature('', sig, ts, body), false);
});

test('the worker: unsigned calls refused, PING answered, a card posted and answered in D1', async () => {
  const k = await keys();
  const { env, db } = fakeD1({ DISCORD_PUBLIC_KEY: k.pub });
  const post = async (obj, signed = true) => {
    const body = JSON.stringify(obj), ts = String(Math.floor(Date.now() / 1000));
    const headers = { 'Content-Type': 'application/json', 'X-Signature-Timestamp': ts,
      'X-Signature-Ed25519': signed ? await k.sign(ts, body) : '00'.repeat(64) };
    return worker.fetch(new Request('https://acrdaily.com/discord/interactions', { method: 'POST', headers, body }), env,
      { waitUntil() {} });
  };
  assert.equal((await post({ type: 1 }, false)).status, 401);
  assert.deepEqual(await (await post({ type: 1 })).json(), { type: 1 });

  const when = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 16).replace('T', ' ');
  const made = await (await post(submit({ title: 'Club night', when, description: 'Bring a Fabia' }))).json();
  assert.equal(made.type, 4);
  const id = db.prepare('SELECT id FROM discord_events').get().id;
  assert.equal(made.data.components[0].components[0].custom_id, `rsvp:${id}:yes`);

  await post(click(id, 'yes', ANN));
  await post(click(id, 'maybe', BEN));
  const res = await (await post(click(id, 'yes', BEN))).json();
  assert.equal(res.type, 7);
  assert.equal(res.data.embeds[0].fields.find((f) => f.name.startsWith('✅')).value, `<@${ANN}>, <@${BEN}>`);
  assert.deepEqual(db.prepare('SELECT user_id, answer FROM discord_rsvps ORDER BY user_id').all().map((r) => [r.user_id, r.answer]),
    [[ANN, 'yes'], [BEN, 'yes']]);
  await post(click(id, 'yes', ANN));                                // taken back
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM discord_rsvps').get().n, 1);
});
