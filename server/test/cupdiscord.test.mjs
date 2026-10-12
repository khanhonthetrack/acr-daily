// ACR Daily's own cups on Discord (src/cupdiscord.js): what is due when, and a 4-driver official cup from its sign-ups
// to its results on a real SQLite (faked1.mjs), with Discord a stand-in that keeps what it was sent.
// node --test test/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { cupDiscordTick, duePost } from '../src/cupdiscord.js';
import { cupsTick } from '../src/cups.js';
import { LIMITS } from '../src/leagues.js';
import { fakeD1, sid } from './faked1.mjs';

const H = 3600000;

test('what is due: the most recent news only, what went by marked done', () => {
  const t0 = Date.UTC(2026, 9, 25, 18);
  const open = { status: 'open', starts: t0, posted: [] };
  assert.deepEqual(duePost(open, t0 - 10 * 86400000), { post: 'open', mark: ['open'] });
  assert.deepEqual(duePost(open, t0 - 2 * H), { post: 'open', mark: ['open', 'start24h'] });   // made late: one post
  assert.deepEqual(duePost({ ...open, posted: ['open'] }, t0 - 30 * H), { post: null, mark: [] });
  assert.deepEqual(duePost({ ...open, posted: ['open'] }, t0 - 20 * H), { post: 'start24h', mark: ['start24h'] });
  const run = { status: 'running', starts: t0, round: 1, round_hours: 168, closes: t0 + 168 * H, posted: ['open', 'start24h'] };
  assert.deepEqual(duePost(run, t0 + 5 * 60000), { post: 'round', mark: ['r1'] });
  assert.deepEqual(duePost({ ...run, posted: [] }, t0 + 5 * 60000), { post: 'round', mark: ['open', 'start24h', 'r1'] });
  assert.deepEqual(duePost({ ...run, posted: ['open', 'start24h', 'r1'] }, t0 + 100 * H), { post: null, mark: [] });
  assert.deepEqual(duePost({ ...run, posted: ['open', 'start24h', 'r1'] }, t0 + 150 * H), { post: 'round24h', mark: ['r1:24h'] });
  // a short round: no "24 hours left" post (it would come right after the round's own)
  assert.deepEqual(duePost({ ...run, round_hours: 24, closes: t0 + 24 * H, posted: ['r1'] }, t0 + 2 * H), { post: null, mark: ['r1:24h'] });
  assert.deepEqual(duePost({ status: 'finished', posted: ['r2'] }, t0), { post: 'done', mark: ['done'] });
  assert.deepEqual(duePost({ status: 'finished', posted: ['done'] }, t0), { post: null, mark: [] });
});

test('an official cup on Discord: sign-ups, a day to go, each round with its stages, a day left, the results', async () => {
  const sent = [];
  const fetchFn = async (url, init) => {
    sent.push({ url, body: JSON.parse(init.body) });
    return new Response(JSON.stringify({ id: String(1000 + sent.length) }), { status: 200 });
  };
  const { env, db } = fakeD1({ DISCORD_CUPS_WEBHOOK_URL: 'https://discord.com/api/webhooks/1/abc', SITE_URL: 'https://acrdaily.com' });
  const t0 = Date.UTC(2026, 9, 25, 18);
  const names = ['Ann', 'Bob', 'Cat', 'Dan'];
  names.forEach((n, i) => db.prepare("INSERT INTO players (steam_id, name, created, country) VALUES (?, ?, 0, 'fi')").run(sid(i), n));
  const spec = { rally: 'Monte Carlo', car: null, car_class: 'Rally2/R5', rules: {}, draw: { maxKm: 40 },
    stages: [{ track: 'mc_1', day: 1, service: false, weather: 'Clear', time: '09:00' }] };
  db.prepare(`INSERT INTO leagues (id, name, owner, code, created, kind, banner) VALUES ('official', 'Test Cup (beta)', 'acr-daily', 'CODE2345', 0, 'cup', 3)`).run();
  db.prepare(`INSERT INTO cups (id, name, about, owner, size, fee, split, spec, starts, round_hours, status, created, official, prize)
    VALUES ('official', 'Test Cup (beta)', 'The first one.', 'acr-daily', 8, 0, '[60,30,5,5]', ?, ?, 168, 'open', 0, 1, 1000)`).run(JSON.stringify(spec), t0);

  // sign-ups open: the post, with its banner; nothing more until a day before the start
  assert.deepEqual(await cupDiscordTick(env, t0 - 10 * 86400000, fetchFn), { posted: 'open', cup: 'official' });
  const open = sent[0].body.embeds[0];
  assert.equal(open.title, 'Test Cup (beta): sign-ups are open');
  assert.equal(open.image.url, 'https://acrdaily.com/l/official/banner?v=3');
  assert.match(open.description, /\*\*Prize\*\* 1,000 credits from ACR Daily \(60 \/ 30, 5 each to the losing semi-finalists\)/);
  assert.match(open.description, /Monte Carlo · 1 stage, a new draw each round · Rally2\/R5 class/);
  assert.deepEqual(sent[0].body.allowed_mentions, { parse: [] });
  assert.deepEqual(await cupDiscordTick(env, t0 - 9 * 86400000, fetchFn), {});
  for (let i = 0; i < 4; i++) db.prepare("INSERT INTO cup_entries (cup_id, steam_id, fee, joined) VALUES ('official', ?, 0, 0)").run(sid(i));
  assert.deepEqual(await cupDiscordTick(env, t0 - 20 * H, fetchFn), { posted: 'start24h', cup: 'official' });
  assert.match(sent[1].body.embeds[0].description, /^4 drivers are in, room for 4 more\./);

  // the start: round 1 (the semi-finals) open, with the stage drawn
  db.prepare("INSERT INTO routes (track, points, length, updated, stage_id) VALUES ('Monte Carlo Col de Turini', '[]', 12000, 0, 'MonteCarloS1TuriniFullForward')").run();
  await cupsTick(env, t0 + 60000);
  assert.deepEqual(await cupDiscordTick(env, t0 + 10 * 60000, fetchFn), { posted: 'round', cup: 'official' });
  const r1 = sent[2].body.embeds[0];
  assert.equal(r1.title, 'Test Cup (beta): the semi-final is open');
  assert.match(r1.description, /^2 matches\. \*\*The stages:\*\* /);
  assert.match(r1.description, new RegExp(`by <t:${(t0 + 168 * H) / 1000}:F>`));
  assert.match(r1.description, /🇫🇮 Ann vs 🇫🇮 Dan|🇫🇮 \w+ vs 🇫🇮 \w+/);
  assert.deepEqual(await cupDiscordTick(env, t0 + H, fetchFn), {});
  assert.deepEqual(await cupDiscordTick(env, t0 + 150 * H, fetchFn), { posted: 'round24h', cup: 'official' });
  assert.match(sent[3].body.embeds[0].description, /^0 of 4 drivers have driven their match\./);

  // nobody drives: the higher seeds go through, the final opens, then is decided: the results
  db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'official'").run(t0 + 168 * H - LIMITS.graceMs - 1);
  await cupsTick(env, t0 + 168 * H + 60000);
  assert.deepEqual(await cupDiscordTick(env, t0 + 168 * H + 10 * 60000, fetchFn), { posted: 'round', cup: 'official' });
  assert.equal(sent[4].body.embeds[0].title, 'Test Cup (beta): the final is open');
  db.prepare("UPDATE league_events SET closes = ? WHERE league_id = 'official'").run(t0 + 336 * H - LIMITS.graceMs - 1);
  await cupsTick(env, t0 + 336 * H + 60000);
  assert.equal(db.prepare("SELECT status FROM cups WHERE id = 'official'").get().status, 'finished');
  assert.deepEqual(await cupDiscordTick(env, t0 + 336 * H + 10 * 60000, fetchFn), { posted: 'done', cup: 'official' });
  const done = sent[5].body.embeds[0];
  assert.match(done.title, /^\w+ wins Test Cup \(beta\)$/);
  assert.match(done.description, /^`1` 🇫🇮 \*\*\w+\*\* · 600 credits\n`2` 🇫🇮 \*\*\w+\*\* · 300 credits\n`3` .*50 credits, .*50 credits/);
  assert.deepEqual(await cupDiscordTick(env, t0 + 337 * H, fetchFn), {});
  assert.equal(sent.length, 6);
  assert.ok(sent.every((s) => s.url === 'https://discord.com/api/webhooks/1/abc?wait=true'));
});

test('a driver\'s cup is not posted; no webhook: nothing', async () => {
  const { env, db } = fakeD1({ DISCORD_WEBHOOK_URL: 'https://discord.com/api/webhooks/1/abc' });
  db.prepare(`INSERT INTO cups (id, name, owner, size, fee, split, spec, starts, round_hours, status, created)
    VALUES ('drivers1', 'Mine', ?, 8, 0, '[100]', '{"rally":"Wales","stages":[]}', ?, 24, 'open', 0)`).run(sid(1), Date.now() + 86400000 * 3);
  assert.deepEqual(await cupDiscordTick(env, Date.now(), async () => { throw new Error('no call expected'); }), {});
  assert.deepEqual(await cupDiscordTick(fakeD1().env, Date.now()), { skipped: 'no Discord webhook for the cups' });
});
