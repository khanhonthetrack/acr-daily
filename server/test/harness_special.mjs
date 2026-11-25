// A local look at the special event and the broadcast overlays (not a test: node test/harness_special.mjs [phase]): the
// worker (src/index.js) on the tests' SQLite (faked1.mjs), served at http://127.0.0.1:8799, its clock set to the phase's
// moment and running on from there. Phases: signup (Thursday: 14 registered), running (12:16 on the day: SS1 done by
// some, SS2 under way, the queues moving, cars on the stages), over (the results out, the prize paid).
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fakeD1, sid } from './faked1.mjs';
import { leaguesApi } from '../src/leaguesapi.js';
import { liveApi, SPECIALS, LIVE } from '../src/liverallies.js';
import { MENU_NAMES } from '../src/stages.js';

const phase = process.argv[2] || 'running';
const SP = SPECIALS[0];
const MIN = 60000;
const RALLY_OF = { Alsace: 'Alsace', Greece: 'Greece', MonteCarlo: 'Monte Carlo', Weles: 'Wales' };
const f = fakeD1({ LIVE_FROM: '2026-11-17T17:30:00Z', LIVE_PUBLIC: '1', CREDITS_FROM: '2026-10-12', LEAGUES_MIN_APP: '0.0.5',
  SITE_URL: 'http://127.0.0.1:8799', OFFICIAL_FROM: '2026-10-09' });
let k = 0;
for (const [id, name] of Object.entries(MENU_NAMES)) {
  const rally = RALLY_OF[id.match(/^[A-Z][a-z]+(?:Carlo)?/)[0]];
  f.db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, ?, 0, ?)')
    .run(`${rally} ${name}`, '[[0,0],[100,0]]', 6000 + (k++ % 7) * 1500, id);
}
// (Oxmod's Thierache routes, as the migration adds them)
f.db.exec(readFileSync(new URL('../migrations/0049_thierache_routes.sql', import.meta.url), 'utf8'));
const NAMES = [['Kalle Rovanperä-ish', 'fi'], ['Ott Tänak Jr', 'ee'], ['Petter S.', 'no'], ['Elfyn Fan', 'gb'], ['Thierry N', 'be'],
  ['Dani Sordo Lover', 'es'], ['Adrien F.', 'fr'], ['Takamoto K.', 'jp'], ['Gus G.', 'ie'], ['Sami P.', 'fi'],
  ['Oliver S.', 'se'], ['Nikolay G.', 'bg'], ['Jan Kopecký Fan', 'cz'], ['Andreas M.', 'no'], ['Yohan R.', 'fr'], ['Martins S.', 'lv']];
NAMES.forEach(([n, c], i) => f.db.prepare('INSERT INTO players (steam_id, name, country, created) VALUES (?, ?, ?, 0)').run(sid(i + 1), n, c));
NAMES.slice(0, 9).forEach((_x, i) => f.db.prepare('INSERT INTO ratings (steam_id, rating, races, peak, updated) VALUES (?, ?, 5, ?, 0)')
  .run(sid(i + 1), 1900 - i * 37, 1900 - i * 37));
const player = (s) => (s ? { ...f.db.prepare('SELECT * FROM players WHERE steam_id = ?').get(s) } : null);
const call = async (fn, path, me, now, body) => {
  const url = new URL('http://127.0.0.1:8799' + path);
  const req = new Request(url, { method: body ? 'POST' : 'GET', headers: { 'User-Agent': 'ACR-Daily/0.2.2 public' },
    ...(body ? { body: JSON.stringify(body) } : {}) });
  const res = fn === 'live' ? await liveApi(req, f.env, url.pathname, player(me), now)
    : await leaguesApi(req, f.env, url.pathname, url, player(me), true, now);
  return res.json();
};
const P = `/api/liverallies/${SP.key}/${SP.starts}`;
const signupAt = Date.UTC(2026, 10, 26, 10);
const n = phase === 'signup' ? 14 : 12;
for (let i = 0; i < n; i++) await call('live', `${P}/signup`, sid(i + 1), signupAt + i * MIN, {});
let now0 = phase === 'signup' ? Date.UTC(2026, 10, 26, 18) : SP.starts + 16 * MIN;
if (phase !== 'signup') {
  const v = await call('live', P, sid(1), SP.starts + 1000);
  const id = v.eventId, t0 = SP.starts + LIVE.firstStartMs;
  const order = v.queues[0].map((q) => q.steamId);
  // SS1: everyone starts in turn, 15 s apart; the first eight finish (5:10 to 5:40)
  for (const [i, s] of order.entries()) {
    const at = t0 + i * 15000;
    await call('league', `/api/events/${id}/start`, s, at + 500, { car: SP.car, at: 1, serverAt: at });
    if (i < 8) {
      const fin = at + 310000 + ((i * 7919) % 30000);
      await call('league', `/api/events/${id}/stage`, s, fin + 1000, { no: 0, timeMs: fin - at, penaltyMs: 0 });
      await call('live', `${P}/queue`, s, fin + 2000, { no: 1, finishedAt: fin });
    }
  }
  // SS2: the first four away (their break over), the others waiting or on their break
  for (const [i, s] of order.slice(0, 4).entries()) {
    const at = t0 + 310000 + 180000 + 20000 + i * 18000;
    await call('league', `/api/events/${id}/begin`, s, at + 500, { no: 1, serverAt: at });
    if (phase === 'over' || i < 2) {
      await call('league', `/api/events/${id}/stage`, s, at + 330000 + i * 4000, { no: 1, timeMs: 328000 + i * 4000, penaltyMs: 0 });
    }
  }
  if (phase === 'over') now0 = SP.starts + SP.openMs + 5 * MIN;
  await call('live', P, sid(1), now0);
  // the cars on the stages now: two on SS2, the last two of SS1
  if (phase === 'running') {
    const put = (s, no, p, ms) => f.db.prepare(`INSERT OR REPLACE INTO event_live (event_id, steam_id, stage_no, x, z, progress, total_ms, state, updated)
      VALUES (?, ?, ?, 0, 0, ?, ?, 'live', ?)`).run(id, s, no, p, ms, now0);
    put(order[2], 1, 0.62, 201000); put(order[3], 1, 0.35, 118000); put(order[10], 0, 0.81, 262000); put(order[11], 0, 0.55, 171000);
  }
}
// (HARNESS_TWITCH=1: a stand-in Twitch, the channel live: the home page's strip)
if (process.env.HARNESS_TWITCH) {
  Object.assign(f.env, { TWITCH_CHANNEL: 'acrdaily', TWITCH_CLIENT_ID: 'x', TWITCH_CLIENT_SECRET: 'y' });
  const real = globalThis.fetch;
  globalThis.fetch = async (u, o) => (String(u).startsWith('https://id.twitch.tv') ? new Response(JSON.stringify({ access_token: 't', expires_in: 9999 }))
    : String(u).startsWith('https://api.twitch.tv') ? new Response(JSON.stringify({ data: [{ type: 'live', title: 'Skoda Saturday Challenge: SS2 under way', viewers: 1, viewer_count: 87 }] }))
      : real(u, o));
}
// the worker's clock: the phase's moment, running on (the cars' updated with it)
const start = Date.now(), realNow = Date.now.bind(Date);
Date.now = () => now0 + (realNow() - start);
setInterval(() => f.db.prepare("UPDATE event_live SET updated = ?, total_ms = total_ms + 1000, progress = MIN(0.99, progress + 0.003) WHERE state = 'live'").run(Date.now()), 1000);
const worker = (await import('../src/index.js')).default;
http.createServer(async (req, res) => {
  const body = req.method === 'POST' ? await new Promise((ok) => { let b = ''; req.on('data', (c) => { b += c; }); req.on('end', () => ok(b)); }) : undefined;
  const r = await worker.fetch(new Request('http://127.0.0.1:8799' + req.url, { method: req.method, headers: req.headers, body }), f.env,
    { waitUntil() {} });
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(8799, () => console.log(`ready: ${phase} at ${new Date(Date.now()).toISOString()}`));
