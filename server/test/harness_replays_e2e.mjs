// End to end for REPLAYS (not a test of its own: node test/harness_replays_e2e.mjs <route.json>; the app's side drives
// it, client tests e2e_replays.py): the worker (src/index.js) on the tests' SQLite (faked1.mjs) at http://127.0.0.1:8797,
// its clock running SPEED times faster than the real one (a stage of 4 minutes in 25 s), with:
//   POST /__down {on}        the connection gone (true: every request dropped unanswered) or back
//   POST /__skip {ms}        the clock moved on (30 minutes for a result that never came)
//   POST /__sql {sql, args}  set-up and look-ups (rows)
//   GET  /__now              the clock
// One driver signed in (token 'e2e0' x 16), the stage's route (Wales Afon Bidno, from the file given), today's daily on
// it, and an online rally of two stages on it, started.
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fakeD1, sid } from './faked1.mjs';

const SPEED = Number(process.env.SPEED || 10);
const PORT = Number(process.env.PORT || 8797);
const f = fakeD1({ ADMIN_KEY: 'k'.repeat(30), SITE_URL: `http://127.0.0.1:${PORT}`, OFFICIAL_FROM: '2026-10-09', LEAGUES_MIN_APP: '0.0.5' });
const real0 = Date.now(), realNow = Date.now.bind(Date);
let skip = 0;
Date.now = () => real0 + (realNow() - real0) * SPEED + skip;
const today = new Date(Date.now()).toISOString().slice(0, 10);
const route = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const { db } = f;
const ME = sid(2);
db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0), (?, ?, 0)').run(sid(1), 'Steward', ME, 'Tester');
const hash = async (t) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)))].map((b) => b.toString(16).padStart(2, '0')).join('');
db.prepare('INSERT INTO sessions (token_hash, steam_id, created) VALUES (?, ?, 0)').run(await hash('e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0e2e0'), ME);
db.prepare('INSERT INTO routes (track, points, length, updated, stage_id) VALUES (?, ?, 5196, 0, ?)').run(route.track, JSON.stringify(route.route), 'WelesS4HafrenSouthFullForward');
db.prepare("INSERT INTO schedule (date, slot, track, car, weather, time) VALUES (?, 1, ?, 'Mini Cooper S 1275', 'Clear', '12:00')").run(today, route.track);
db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('club0001', 'E2E Club', ?, 1, 'CODE0001', 0, 'league')").run(sid(1));
db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('club0001', ?, 0, 'member')").run(ME);
const stages = [0, 1].map((i) => ({ track: route.track, day: 1, service: i === 0, weather: 'Clear', time: '09:00' }));
const ev = (name) => Number(db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
  VALUES ('club0001', ?, 'Wales', 'Mini Cooper S 1275', '{}', ?, ?, ?, 0, NULL)`).run(name, JSON.stringify(stages), Date.now() - 3600000, Date.now() + 7 * 86400000).lastInsertRowid);
const events = { lost: ev('Rally: result lost'), missing: ev('Rally: no result'), start: ev('Rally: late start'), late: ev('Rally: late finish') };
for (const id of Object.values(events)) {
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, done, on_stage, total_ms, started, updated)
    VALUES (?, ?, 'Mini Cooper S 1275', 'running', 0, 0, 0, ?, ?)`).run(id, ME, Date.now(), Date.now());
}
let down = false;
const worker = (await import('../src/index.js')).default;
const send = (res, status, obj) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks);
  if (req.url === '/__down') { down = !!JSON.parse(body).on; return send(res, 200, { down }); }
  if (req.url === '/__skip') { skip += Number(JSON.parse(body).ms) || 0; return send(res, 200, { now: Date.now() }); }
  if (req.url === '/__now') return send(res, 200, { now: Date.now(), today, events, me: ME });
  if (req.url === '/__sql') {
    const q = JSON.parse(body);
    const st = db.prepare(q.sql);
    return send(res, 200, st.columns().length ? st.all(...(q.args || [])) : { changes: Number(st.run(...(q.args || [])).changes) });
  }
  if (down) { req.socket.destroy(); return; }         // (the connection gone: nothing comes back)
  const r = await worker.fetch(new Request(`http://127.0.0.1:${PORT}` + req.url, { method: req.method, headers: req.headers,
    body: req.method === 'GET' || req.method === 'HEAD' ? undefined : body }), f.env, { waitUntil() {} });
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(PORT, () => console.log(JSON.stringify({ ready: true, port: PORT, today, events, speed: SPEED })));
