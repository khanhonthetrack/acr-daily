// REPLAYS (src/replays.js): the app's replay file checked here as the app made it (a fixture signed by the Python
// app code), the run followed while driven (begin, commits on the server's clock), an upload that takes a lost DNF back
// (a daily's, an online rally's stage) on its own, the refusals (changed, someone else's, ahead of the server's clock),
// the road checks (a cut, off the road), and the stewards asking for a replay. On a real SQLite through faked1.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { canon, chainNext, chainStart, checkRoad, digestHex, readFile, replaysApi, verifyReplay, wanted } from '../src/replays.js';
import { leaguesApi, replayStageTime } from '../src/leaguesapi.js';
import { fakeD1, sid } from './faked1.mjs';

const NOW = Date.UTC(2026, 10, 26, 12, 0);
const [ANN, BEN, CAT] = [sid(1), sid(2), sid(3)];
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const err = (msg, status = 400) => json({ error: msg }, status);

// a road: 2 km east, a hairpin, 1 km back west 60 m north (points [x, z] m)
const ROAD = [];
for (let x = 0; x <= 2000; x += 20) ROAD.push([x, 0]);
for (let a = 1; a < 18; a++) ROAD.push([2000 + 30 * Math.sin(a * Math.PI / 18), 30 - 30 * Math.cos(a * Math.PI / 18)]);
for (let x = 2000; x >= 1000; x -= 20) ROAD.push([x, 60]);

/** Rows driving the road at ~25 m/s, every 100 ms of clock; cut: straight across the hairpin. */
function drive(points = ROAD, { cut = false, mps = 25 } = {}) {
  const pts = cut ? points.filter(([x, z]) => !(x > 1960 && z > 0 && z < 60)) : points;
  const rows = [];
  let clock = 100, left = 0;
  for (let i = 1; i < pts.length; i++) {
    const [ax, az] = pts[i - 1], [bx, bz] = pts[i], len = Math.hypot(bx - ax, bz - az);
    let s = left;
    while (s < len) {
      const u = s / len;
      rows.push([clock, Math.round((ax + (bx - ax) * u) * 100), 500, Math.round((az + (bz - az) * u) * 100), 0, 0, 0,
        Math.round(mps * 36), 5, 6000, 800, 0, 0, 0]);
      clock += 100;
      s += mps / 10;
    }
    left = s - len;
  }
  return rows;
}

async function keyPair() {
  const k = await crypto.subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
  const pub = Buffer.from(await crypto.subtle.exportKey('raw', k.publicKey)).toString('hex');
  return { priv: k.privateKey, pub };
}

async function makeDoc(key, head, rows, live = null) {
  const digest = await digestHex(head, rows, live ? live.rid : null);
  const sig = Buffer.from(await crypto.subtle.sign({ name: 'Ed25519' }, key.priv, Buffer.from(digest, 'hex'))).toString('hex');
  return { format: 'acr-replay', v: 1, head, cols: [], rows, live, sig: { alg: 'ed25519', key: key.pub, sig } };
}

function world() {
  const f = fakeD1({ ADMIN_KEY: 'k'.repeat(30) });
  const { db } = f;
  for (const [s, n] of [[ANN, 'Ann'], [BEN, 'Ben'], [CAT, 'Cat']]) db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0)').run(s, n);
  db.prepare("INSERT INTO routes (track, points, length, updated) VALUES ('Test Road', ?, 3100, 0)").run(JSON.stringify(ROAD));
  return f;
}

const deps = (env, extra = {}) => ({ json, err, admin: false, site: 'https://acrdaily.com',
  route: async (track) => { const r = await env.DB.prepare('SELECT points FROM routes WHERE track = ?').bind(track).first(); return r ? JSON.parse(r.points) : null; },
  reinstate: async () => json({ error: 'not here' }, 404),
  stageTime: (eventId, s, no, timeMs, penaltyMs, reason, now, damage) => replayStageTime(env, eventId, s, no, timeMs, penaltyMs, reason, now, damage),
  ...extra });

async function call(env, path, me, body, now, d = deps(env), raw = null) {
  const url = new URL('https://acrdaily.com' + path);
  const req = new Request(url, { method: body || raw ? 'POST' : 'GET', ...(raw ? { body: raw } : body ? { body: JSON.stringify(body) } : {}) });
  const res = await replaysApi(req, env, url.pathname, url, me ? { steam_id: me, name: me === BEN ? 'Ben' : 'x' } : null, now, d);
  return { status: res.status, body: res.headers.get('Content-Type') === 'application/json' ? await res.json() : await res.arrayBuffer() };
}

/** A run followed by the server: begin, a commit every 10 s of the server's clock (at the pace the clock ran), the final
 *  one at the finish. -> {rid, live} */
async function followed(env, me, key, head, rows, { t0 = NOW, speed = 1, beginAt = 0, lateBy = () => 0, fin = true } = {}) {
  // beginAt: the stage clock the begin got there at (the connection down at the start); lateBy(clock): how much later
  // than the stage ran the server got the commit with that clock (a connection lost meanwhile); fin: the finish sent
  const b = await call(env, '/api/replays/begin', me, { kind: head.kind, ref: head.ref, track: head.track, car: head.car, clockMs: beginAt, key: key.pub },
    t0 + beginAt);
  assert.equal(b.status, 200, JSON.stringify(b.body));
  const { rid, nonce } = b.body;
  let h = await chainStart(rid, nonce), at = 0;
  const commits = [];
  const finMs = rows[rows.length - 1][0];
  for (let i = 0; i < rows.length; i++) {
    const last = i === rows.length - 1;
    if (rows[i][0] < beginAt) continue;
    if (!last && commits.length && (rows[i][0] - rows[commits[commits.length - 1][0] - 1][0]) < 10000) continue;
    const n = i + 1;
    h = await chainNext(h, rows.slice(at, n));
    at = n;
    commits.push([n, h]);
    const r = await call(env, '/api/replays/commit', me, { rid, n: commits.length, count: n, hash: h, clockMs: rows[i][0], fin: last && fin ? finMs : null },
      t0 + Math.round(rows[i][0] / speed) + 300 + lateBy(rows[i][0]));
    assert.equal(r.status, 200, JSON.stringify(r.body));
  }
  return { rid, live: { rid, nonce, commits } };
}

test('a replay made by the app (Python) is read and checked the same here: canon, digest, signature, chain', async () => {
  const bytes = readFileSync(new URL('./fixtures/replay-py.acrreplay', import.meta.url));
  const { doc } = await readFile(bytes);
  assert.equal(canon(doc.head), '{"app":"ACR DAILY","appVersion":"0.2.3","car":"\\u0160koda Fabia","clockMs":30000,"counted":true,"created":1795660000000,'
    + '"driver":{"name":"\\u0141ukasz \\"\\u0150\\" \\u6f22\\n","steamId":"76561198000000002"},"finMs":30000,"kind":"event","penaltyMs":0,"reason":"",'
    + '"ref":"event:1:0","resets":0,"rowMs":100,"status":"finished","title":null,"totalMs":30000,"track":"Test Road"}');
  assert.equal(await digestHex(doc.head, doc.rows, doc.live.rid), '7eb45f6f0fcdbdace44434ac1b5435f695f709d5b614c7c5e12a5581908d9656');
  const v = await verifyReplay(doc, {});
  assert.equal(v.report.signed, true);
  // its chain as the server would have kept it
  const run = { rid: doc.live.rid, nonce: doc.live.nonce, steam_id: '76561198000000002', key: doc.sig.key, track: 'Test Road', car: 'Škoda Fabia',
    kind: 'event', ref: 'event:1:0', begin_ms: 0, begin_clock: 0, fin_ms: 30000,
    commits: JSON.stringify(doc.live.commits.map(([n, h]) => [n, h, doc.rows[n - 1][0] + 500, 0])) };
  const w = await verifyReplay(doc, { run, uploader: '76561198000000002' });
  assert.equal(w.report.chain, true);
  assert.equal(w.report.timing, true);
  // one row changed: the signature no longer matches
  doc.rows[10][1] += 1;
  assert.equal((await verifyReplay(doc, {})).verdict, 'refused');
});

test('a daily\'s DNF whose result the game lost is taken back by the driver\'s clean replay, by itself', async () => {
  const { env, db } = world();
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { created: NOW, driver: { steamId: BEN, name: 'Ben' }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1',
    status: 'finished', clockMs: fin, finMs: fin, resets: 0, penaltyMs: 0 };
  const { rid, live } = await followed(env, BEN, key, head, rows);
  // the app's result: a DNF, the game froze on its loading screen after the finish
  const runId = db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, created)
    VALUES ('2026-11-26', 1, ?, 'Test Road', 'Car', 'dnf', 'the game closed before saving its official result', ?, 0, ?)`).run(BEN, fin, NOW + fin + 60000).lastInsertRowid;
  // the server wants it
  assert.deepEqual(await wanted(env, BEN, NOW + fin + 90000), [{ rid, ref: '2026-11-26/1', why: 'dnf' }]);
  const doc = await makeDoc(key, head, rows, live);
  let asked = null;
  const d = deps(env, { reinstate: async (id, pen) => { asked = [id, pen]; return json({ ok: true, totalMs: fin, rank: 4 }); } });
  const up = await call(env, '/api/replays/upload', BEN, null, NOW + fin + 120000, d, gzipSync(JSON.stringify(doc)));
  assert.equal(up.status, 200, JSON.stringify(up.body));
  assert.equal(up.body.verdict, 'clean', JSON.stringify(up.body.report));
  assert.deepEqual(asked, [Number(runId), 0]);
  assert.match(up.body.action, /^DNF taken back: .*P4$/);
  assert.match(db.prepare('SELECT flags FROM runs WHERE id = ?').get(runId).flags, /reinstated by replay/);
  // once only: the same replay again gives the same answer, nothing more
  const again = await call(env, '/api/replays/upload', BEN, null, NOW + fin + 130000, d, gzipSync(JSON.stringify(doc)));
  assert.equal(again.body.again, true);
  assert.deepEqual(await wanted(env, BEN, NOW + fin + 140000), []);
  // the driver's note of it; the replay private (the daily's day not over), its driver sees it, another doesn't
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE to_id = ? AND kind = 'replay'").get(BEN).n, 1);
  assert.equal((await call(env, `/api/replays/${up.body.code}`, BEN, null, NOW + fin + 150000)).status, 200);
  assert.equal((await call(env, `/api/replays/${up.body.code}`, CAT, null, NOW + fin + 150000)).status, 404);
  const sh = await call(env, `/api/replays/${up.body.code}/share`, BEN, { public: true }, NOW + fin + 150000);
  assert.equal(sh.status, 409);           // (public once the day is over)
  assert.equal((await call(env, `/api/replays/${up.body.code}/share`, BEN, { public: true }, NOW + 86400000)).status, 200);
  assert.equal((await call(env, `/api/replays/${up.body.code}`, CAT, null, NOW + 86400000)).status, 200);
  const file = await call(env, `/api/replays/${up.body.code}/file`, CAT, null, NOW + 86400000);
  assert.ok(file.body.byteLength > 100);
});

test('refused: changed after it was made, someone else\'s, made faster than the stage ran, not the run followed', async () => {
  const { env } = world();
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 0 };
  // sent twice as fast as a stage runs (made up afterwards, or sped up): ahead of the server's clock
  const { live } = await followed(env, BEN, key, head, rows, { speed: 2 });
  const doc = await makeDoc(key, head, rows, live);
  let up = await call(env, '/api/replays/upload', BEN, null, NOW + fin, deps(env), gzipSync(JSON.stringify(doc)));
  assert.equal(up.status, 422);
  assert.match(up.body.report.notes.join(), /ahead of the server/);
  // someone else's file
  const f2 = await followed(env, BEN, key, head, rows, { t0: NOW + 3600000 });
  const doc2 = await makeDoc(key, head, rows, f2.live);
  up = await call(env, '/api/replays/upload', CAT, null, NOW + 2 * 3600000, deps(env), gzipSync(JSON.stringify(doc2)));
  assert.equal(up.status, 422);
  // a row changed after signing
  doc2.rows[50][1] += 300;
  up = await call(env, '/api/replays/upload', BEN, null, NOW + 2 * 3600000, deps(env), gzipSync(JSON.stringify(doc2)));
  assert.match(up.body.report.notes.join(), /signature/);
  // re-signed after the change (the driver's own key): the chain sent while driving no longer matches
  const doc3 = await makeDoc(key, head, doc2.rows, f2.live);
  up = await call(env, '/api/replays/upload', BEN, null, NOW + 2 * 3600000, deps(env), gzipSync(JSON.stringify(doc3)));
  assert.match(up.body.report.notes.join(), /not the ones sent while driving/);
  // commits out of order / twice: refused at once
  const b = await call(env, '/api/replays/begin', BEN, { kind: 'daily', ref: '2026-11-26/1', track: 'Test Road', car: 'Car', clockMs: 0, key: key.pub }, NOW);
  assert.equal((await call(env, '/api/replays/commit', BEN, { rid: b.body.rid, n: 2, count: 5, hash: 'a'.repeat(64), clockMs: 500 }, NOW + 600)).status, 409);
  // (a commit the server already has, its answer lost: the server says where it is, the app sends on from there)
  const st = await call(env, `/api/replays/run/${b.body.rid}`, BEN, null, NOW + 700);
  assert.deepEqual([st.body.have, st.body.open], [0, true]);
  // a begin late (the connection down at the start): taken, followed from there
  assert.equal((await call(env, '/api/replays/begin', BEN, { kind: 'daily', ref: '2026-11-26/1', track: 'Test Road', car: 'Car', clockMs: 60000, key: key.pub }, NOW)).status, 200);
});

test('the road checks: a corner cut across, off the road; a clean run is clean', () => {
  const clean = checkRoad(drive(), ROAD);
  assert.equal(clean.start, true);
  assert.equal(clean.finishNear, true);
  assert.equal(clean.checkpoints, 1);
  assert.deepEqual(clean.cuts, []);
  assert.equal(clean.offMs, 0);
  const cut = checkRoad(drive(ROAD, { cut: true }), ROAD);
  assert.equal(cut.cuts.length, 1);
  assert.ok(cut.cuts[0].m > 30, JSON.stringify(cut.cuts));
  // 80 m off the road for a while (a field), back on
  const rows = drive().map((r) => (r[1] > 50000 && r[1] < 70000 && r[3] === 0 ? [...r.slice(0, 3), 8000, ...r.slice(4)] : r));
  const off = checkRoad(rows, ROAD);
  assert.ok(off.offMs > 3000);
  assert.equal(off.maxOffM, 80);
});

test('an online rally: the stewards ask for a replay, the DNF on that stage is taken back and the rally goes on', async () => {
  const f = world();
  const { env, db } = f;
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('club0001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('club0001', ?, 0, 'member')").run(BEN);
  const stages = [{ track: 'Test Road', day: 1, service: true, weather: 'Clear', time: '09:00' }, { track: 'Test Road', day: 1, service: false, weather: 'Clear', time: '10:00' }];
  const id = Number(db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('club0001', 'Round 1', 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0, NULL)`).run(JSON.stringify(stages), NOW - 3600000, NOW + 86400000).lastInsertRowid);
  const lcall = async (path, me, body) => {
    const url = new URL('https://acrdaily.com' + path);
    const req = new Request(url, { method: 'POST', headers: { 'User-Agent': 'ACR-Daily/0.2.3 public' }, body: JSON.stringify(body) });
    const res = await leaguesApi(req, env, url.pathname, url, { steam_id: me, name: 'x' }, true, NOW);
    return { status: res.status, body: await res.json() };
  };
  const st = await lcall(`/api/events/${id}/start`, BEN, { car: 'Skoda Fabia RS Rally2', at: NOW - 600000 });
  assert.equal(st.status, 200, JSON.stringify(st.body));
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Skoda Fabia RS Rally2', kind: 'event', ref: `event:${id}:0`, status: 'finished', finMs: fin, resets: 0, penaltyMs: 10000 };
  const { live } = await followed(env, BEN, key, head, rows);
  await lcall(`/api/events/${id}/dnf`, BEN, { no: 0, reason: 'the game closed before saving its official result' });
  // a steward asks for SS1's replay: the driver's inbox, the app's wanted list
  assert.equal((await lcall(`/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'replay', stage: 1, reason: 'check the hairpin' })).status, 200);
  const w = await wanted(env, BEN, NOW + fin + 1000);
  assert.deepEqual(w.map((x) => x.why).sort(), ['dnf', 'steward']);
  const up = await call(env, '/api/replays/upload', BEN, null, NOW + fin + 60000, deps(env), gzipSync(JSON.stringify(await makeDoc(key, head, rows, live))));
  assert.equal(up.body.verdict, 'clean', JSON.stringify(up.body.report));
  assert.match(up.body.action, /^SS1: .*the rally goes on/);
  const e = db.prepare('SELECT status, done, total_ms FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, BEN);
  assert.deepEqual([e.status, e.done, e.total_ms], ['running', 1, fin + 10000]);
  const dec = db.prepare('SELECT op, by FROM league_decisions WHERE event_id = ? ORDER BY id').all(id).map((r) => `${r.op}:${r.by}`);
  assert.deepEqual(dec, [`replay:${ANN}`, 'time:replay']);
  // the steward told; the request answered; the steward may watch it (private), another driver may not
  assert.equal(db.prepare("SELECT state FROM replay_requests").get().state, 'sent');
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE to_id = ? AND kind = 'replay'").get(ANN).n, 1);
  assert.equal((await call(env, `/api/replays/${up.body.code}`, ANN, null, NOW + fin + 70000)).status, 200);
  assert.equal((await call(env, `/api/replays/${up.body.code}`, CAT, null, NOW + fin + 70000)).status, 404);
  // asked again for the same stage: it is here already
  assert.equal((await lcall(`/api/events/${id}/steward`, ANN, { steamId: BEN, op: 'replay', stage: 1, reason: 'again' })).body.sent, true);
});

test('not clean, not taken back: a cut goes to the stewards to look at', async () => {
  const { env, db } = world();
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('club0001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('club0001', ?, 0, 'member')").run(BEN);
  const stages = [{ track: 'Test Road', day: 1, service: true, weather: 'Clear', time: '09:00' }];
  const id = Number(db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('club0001', 'Round 1', 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0, NULL)`).run(JSON.stringify(stages), NOW - 3600000, NOW + 86400000).lastInsertRowid);
  db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, reason, done, started, updated) VALUES (?, ?, 'Skoda Fabia RS Rally2', 'dnf', 'no official result from the game', 0, ?, ?)`)
    .run(id, BEN, NOW, NOW);
  const key = await keyPair();
  const rows = drive(ROAD, { cut: true });
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Skoda Fabia RS Rally2', kind: 'event', ref: `event:${id}:0`, status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
  const { live } = await followed(env, BEN, key, head, rows);
  const up = await call(env, '/api/replays/upload', BEN, null, NOW + fin + 60000, deps(env), gzipSync(JSON.stringify(await makeDoc(key, head, rows, live))));
  assert.equal(up.body.verdict, 'review');
  assert.equal(up.body.action, 'sent to review');
  assert.equal(db.prepare('SELECT status FROM league_entries WHERE event_id = ?').get(id).status, 'dnf');
  assert.equal(db.prepare("SELECT COUNT(*) AS n FROM messages WHERE to_id = ? AND kind = 'replay'").get(ANN).n, 1);
});

// ------------------------------------------------------------------ the ways a finish gets lost (26 Nov 2026: "mitigate
// everything you can NOT to get the dnf": the game hanging on its loading, the result not sent, the connection lost)

function rally(f, stages = 2) {
  const { db } = f;
  db.prepare("INSERT INTO leagues (id, name, owner, public, code, created, kind) VALUES ('club0001', 'Club', ?, 1, 'CODE0001', 0, 'league')").run(ANN);
  db.prepare("INSERT INTO league_members (league_id, steam_id, joined, role) VALUES ('club0001', ?, 0, 'member')").run(BEN);
  const st = Array.from({ length: stages }, (_x, i) => ({ track: 'Test Road', day: 1, service: i === 0, weather: 'Clear', time: '09:00' }));
  return Number(db.prepare(`INSERT INTO league_events (league_id, name, rally, car, rules, stages, opens, closes, created, hide)
    VALUES ('club0001', 'Round 1', 'Wales', 'Skoda Fabia RS Rally2', '{}', ?, ?, ?, 0, NULL)`).run(JSON.stringify(st), NOW - 3600000, NOW + 86400000).lastInsertRowid);
}
const entry = (db, id, status, reason = null, done = 0, onStage = 0) => db.prepare(`INSERT INTO league_entries (event_id, steam_id, car, status, reason, done,
  on_stage, started, updated) VALUES (?, ?, 'Skoda Fabia RS Rally2', ?, ?, ?, ?, ?, ?)`).run(id, BEN, status, reason, done, onStage, NOW, NOW);
const dailyDnf = (db, reason, clock, at) => Number(db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, created)
  VALUES ('2026-11-26', 1, ?, 'Test Road', 'Car', 'dnf', ?, ?, 0, ?)`).run(BEN, reason, clock, at).lastInsertRowid);
const send = async (env, key, head, rows, live, at, d = deps(env)) =>
  call(env, '/api/replays/upload', BEN, null, at, d, gzipSync(JSON.stringify(await makeDoc(key, head, rows, live))));
const okReinstate = (seen = []) => async (id, pen) => { seen.push([id, pen]); return json({ ok: true, totalMs: 123456, rank: 2 }); };

test('the connection lost for a while: commits that reach the server late still prove the finish, taken back by itself', async () => {
  const { env, db } = world();
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
  // 40 s with no connection in the middle: those commits (and the ones after, queued behind them) come 40 s late
  const { live } = await followed(env, BEN, key, head, rows, { lateBy: (c) => (c > 30000 && c < 70000 ? 70000 - c : 0) });
  dailyDnf(db, 'no official result from the game', fin, NOW + fin + 60000);
  const seen = [];
  const up = await send(env, key, head, rows, live, NOW + fin + 90000, deps(env, { reinstate: okReinstate(seen) }));
  assert.equal(up.body.auto, true, JSON.stringify(up.body.report));
  assert.match(up.body.action, /^DNF taken back/);
});

test('the connection down at the start: followed from a minute in, taken back; from later, the admin looks', async () => {
  for (const [beginAt, auto] of [[45000, true], [100000, false]]) {
    const { env, db } = world();
    const key = await keyPair();
    const rows = drive();
    const fin = rows[rows.length - 1][0];
    const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
    const { live } = await followed(env, BEN, key, head, rows, { beginAt });
    dailyDnf(db, 'the game closed before saving its official result', fin, NOW + fin + 60000);
    const up = await send(env, key, head, rows, live, NOW + fin + 90000, deps(env, { reinstate: okReinstate() }));
    assert.equal(up.body.verdict, 'clean', JSON.stringify(up.body.report));
    assert.equal(up.body.auto, auto, `begin at ${beginAt}: ${JSON.stringify(up.body.report.notes)}`);
    assert.equal(/^DNF taken back/.test(up.body.action), auto, up.body.action);
  }
});

test('the finish on the server very late (the app closed with the connection down): never by itself, the admin looks', async () => {
  const { env, db } = world();
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
  // the last minute and the finish sent from the file at the next start, an hour later
  const { live } = await followed(env, BEN, key, head, rows, { lateBy: (c) => (c > fin - 60000 ? 3600000 : 0) });
  dailyDnf(db, 'the game closed before saving its official result', fin, NOW + fin + 60000);
  const up = await send(env, key, head, rows, live, NOW + fin + 4000000, deps(env, { reinstate: okReinstate() }));
  assert.equal(up.body.verdict, 'clean');
  assert.equal(up.body.auto, false);
  assert.equal(up.body.action, 'sent to review');
  assert.match(up.body.report.notes.join(), /reached the server 60 min late/);
});

test('the game frozen at the finish line before the app saw its finish: the road says it, taken back', async () => {
  const { env, db } = world();
  const key = await keyPair();
  const rows = drive();
  const frozeAt = rows[rows.length - 1][0];
  // the app's judge: no telemetry for 30 s -> "lost the game"; no finish sent, the run's rows all committed
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'dnf',
    reason: 'lost the game (closed or frozen)', resets: 0 };
  const { live } = await followed(env, BEN, key, head, rows, { fin: false });
  dailyDnf(db, 'lost the game (closed or frozen)', frozeAt, NOW + frozeAt + 40000);
  assert.deepEqual((await wanted(env, BEN, NOW + frozeAt + 50000)).map((w) => w.why), ['dnf']);
  const seen = [];
  const up = await send(env, key, head, rows, live, NOW + frozeAt + 60000, deps(env, { reinstate: okReinstate(seen) }));
  assert.equal(up.body.auto, true, JSON.stringify(up.body.report));
  assert.match(up.body.report.notes.join(), /finish line reached as the road says/);
  assert.equal(seen.length, 1);
  // a run that stopped short of the line, the same DNF: not finished, nothing taken back
  const f2 = world();
  const short = rows.slice(0, rows.length - 40);
  const l2 = await followed(f2.env, BEN, key, head, short, { fin: false });
  dailyDnf(f2.db, 'lost the game (closed or frozen)', short[short.length - 1][0], NOW + 400000);
  const up2 = await send(f2.env, key, head, short, l2.live, NOW + 500000, deps(f2.env, { reinstate: okReinstate() }));
  assert.notEqual(up2.body.auto, true);
  assert.doesNotMatch(String(up2.body.action), /taken back/);
});

test('no result ever came from the app (a crash past the line): after 30 min the replay stands in for it', async () => {
  const { env, db } = world();
  db.prepare("INSERT INTO schedule (date, slot, track, car, weather, time) VALUES ('2026-11-26', 1, 'Test Road', 'Skoda Fabia RS Rally2', 'Clear', '12:00')").run();
  db.prepare('INSERT INTO attempts (steam_id, date, slot, started) VALUES (?, ?, 1, ?)').run(BEN, '2026-11-26', NOW - 2000);
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 1, penaltyMs: 10000 };
  const { live } = await followed(env, BEN, key, head, rows);
  assert.deepEqual(await wanted(env, BEN, NOW + 20 * 60000), []);                 // (its own result may still come)
  assert.deepEqual((await wanted(env, BEN, NOW + 31 * 60000)).map((w) => w.why), ['missing']);
  const seen = [];
  const up = await send(env, key, head, rows, live, NOW + 32 * 60000, deps(env, { reinstate: okReinstate(seen) }));
  assert.match(up.body.action, /^Result put in from the replay/);
  const r = db.prepare('SELECT id, status, reason, clock_ms, car, started_at FROM runs').get();
  assert.deepEqual([r.status, r.clock_ms, r.car, r.started_at], ['dnf', fin, 'Skoda Fabia RS Rally2', NOW - 2000]);   // (reinstated: the stub)
  assert.match(r.reason, /^no official result from the game/);
  assert.deepEqual(seen, [[r.id, 10000]]);
  // a result of the app's own in meanwhile: nothing stands in
  const f2 = world();
  const l2 = await followed(f2.env, BEN, key, head, rows);
  f2.db.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, clock_ms, total_ms, created) VALUES ('2026-11-26', 1, ?, 'Test Road', 'Car', 'finished', ?, ?, ?)`)
    .run(BEN, fin, fin, NOW + fin + 600000);
  assert.deepEqual(await wanted(f2.env, BEN, NOW + 31 * 60000), []);
  void l2;
});

test('an online rally: no result from the app for a stage, the replay stands in, with the car as it crossed the line', async () => {
  const f = world();
  const { env, db } = f;
  const id = rally(f);
  entry(db, id, 'running', null, 0, 0);
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Skoda Fabia RS Rally2', kind: 'event', ref: `event:${id}:0`, status: 'finished',
    finMs: fin, resets: 0, penaltyMs: 5000, damage: { Engine: 405, Radiator: 1000, Suspension: 873 }, damageScale: 10 };
  const { live } = await followed(env, BEN, key, head, rows);
  assert.deepEqual((await wanted(env, BEN, NOW + 31 * 60000)).map((w) => w.why), ['missing']);
  const up = await send(env, key, head, rows, live, NOW + 32 * 60000);
  assert.match(up.body.action, /^SS1: .*the rally goes on/, JSON.stringify(up.body));
  const e = db.prepare('SELECT status, done, total_ms, damage FROM league_entries WHERE event_id = ? AND steam_id = ?').get(id, BEN);
  assert.deepEqual([e.status, e.done, e.total_ms], ['running', 1, fin + 5000]);
  // (only the parts below 100: the next stage starts with this car, leagues.recover)
  assert.deepEqual(JSON.parse(e.damage), { no: 0, parts: { Engine: 40.5, Suspension: 87.3 } });
});

test('a DNF the driver earned is never taken back: a restart after the finish, settings changed, disqualified', async () => {
  for (const reason of ["SS1 restarted after its finish: a restart doesn't count, the entry ends", 'the event\'s damage changed in the game',
    'disqualified by the game', 'retired by the stewards: cut']) {
    const f = world();
    const id = rally(f);
    entry(f.db, id, 'dnf', reason, 0, 0);
    const key = await keyPair();
    const rows = drive();
    const fin = rows[rows.length - 1][0];
    const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Skoda Fabia RS Rally2', kind: 'event', ref: `event:${id}:0`, status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
    const { live } = await followed(f.env, BEN, key, head, rows);
    assert.deepEqual(await wanted(f.env, BEN, NOW + fin + 60000), [], reason);
    const up = await send(f.env, key, head, rows, live, NOW + fin + 60000);
    assert.equal(up.body.action, null, reason);
    assert.equal(f.db.prepare('SELECT status FROM league_entries').get().status, 'dnf', reason);
  }
});

test('only the first start of a stage: a second attempt\'s replay never stands in for it', async () => {
  const f = world();
  const id = rally(f);
  entry(f.db, id, 'dnf', 'no official result from the game', 0, 0);
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Skoda Fabia RS Rally2', kind: 'event', ref: `event:${id}:0`, status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
  await followed(f.env, BEN, key, { ...head, status: 'dnf', finMs: undefined }, rows.slice(0, 300), { fin: false });   // (the first: a crash)
  const second = await followed(f.env, BEN, key, head, rows, { t0: NOW + 600000 });
  assert.deepEqual(await wanted(f.env, BEN, NOW + 900000), []);
  const up = await send(f.env, key, head, rows, second.live, NOW + 900000);
  assert.equal(up.body.action, null);
});

test('a replay only shared leaves its run open: the DNF that comes later is still taken back by it', async () => {
  const { env, db } = world();
  const key = await keyPair();
  const rows = drive();
  const fin = rows[rows.length - 1][0];
  const head = { driver: { steamId: BEN }, track: 'Test Road', car: 'Car', kind: 'daily', ref: '2026-11-26/1', status: 'finished', finMs: fin, resets: 0, penaltyMs: 0 };
  const { live } = await followed(env, BEN, key, head, rows);
  const shared = await send(env, key, head, rows, live, NOW + fin + 10000);
  assert.equal(shared.body.why, 'share');
  dailyDnf(db, 'no official result from the game', fin, NOW + fin + 600000);
  const up = await send(env, key, head, rows, live, NOW + fin + 700000, deps(env, { reinstate: okReinstate() }));
  assert.match(up.body.action, /^DNF taken back/);
});
