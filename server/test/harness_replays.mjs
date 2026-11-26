// A local look at the replay pages (not a test: node test/harness_replays.mjs): the worker (src/index.js) on the tests'
// SQLite (faked1.mjs), served at http://127.0.0.1:8798, with two public replays of one stage: /r/clean23456 (a clean
// run) and /r/cutcut2345 (the hairpin cut across): put one's code in the other's ADD box to race them.
import http from 'node:http';
import { gzipSync } from 'node:zlib';
import { fakeD1, sid } from './faked1.mjs';

const f = fakeD1({ SITE_URL: 'http://127.0.0.1:8798' });
const ROAD = [];
for (let x = 0; x <= 2000; x += 20) ROAD.push([x, 0]);
for (let a = 1; a < 18; a++) ROAD.push([2000 + 30 * Math.sin(a * Math.PI / 18), 30 - 30 * Math.cos(a * Math.PI / 18)]);
for (let x = 2000; x >= 1000; x -= 20) ROAD.push([x, 60]);
function drive(cut, mps) {
  const pts = cut ? ROAD.filter(([x, z]) => !(x > 1960 && z > 0 && z < 60)) : ROAD;
  const rows = [];
  let clock = 100, left = 0;
  for (let i = 1; i < pts.length; i++) {
    const [ax, az] = pts[i - 1], [bx, bz] = pts[i], len = Math.hypot(bx - ax, bz - az);
    let s = left;
    while (s < len) {
      const u = s / len, slow = Math.min(1, Math.abs(ax - 1990) / 200 + 0.35);
      rows.push([clock, Math.round((ax + (bx - ax) * u) * 100), 500, Math.round((az + (bz - az) * u) * 100), 0, 0, 0,
        Math.round(mps * slow * 36), slow < 0.6 ? 3 : 5, Math.round(4000 + 3000 * slow), slow < 0.6 ? 0 : 900, slow < 0.6 ? 700 : 0, 0, 0]);
      clock += 100;
      s += (mps * slow) / 10;
    }
    left = s - len;
  }
  return rows;
}
f.db.prepare("INSERT INTO routes (track, points, length, updated) VALUES ('Test Road', ?, 3100, 0)").run(JSON.stringify(ROAD));
f.db.prepare('INSERT INTO players (steam_id, name, created) VALUES (?, ?, 0), (?, ?, 0)').run(sid(1), 'Ann Clean', sid(2), 'Ben Cutter');
const add = (code, who, rows, verdict, notes, road) => {
  const fin = rows[rows.length - 1][0];
  const doc = { format: 'acr-replay', v: 1, head: { driver: { steamId: who, name: '' }, track: 'Test Road', car: 'Skoda Fabia RS Rally2',
    kind: 'practice', status: 'finished', finMs: fin }, rows };
  const data = gzipSync(JSON.stringify(doc));
  f.db.prepare(`INSERT INTO replay_files (code, steam_id, kind, track, car, status, fin_ms, penalty_ms, verdict, report, digest, why, public,
      data, size, created, expires) VALUES (?, ?, 'practice', 'Test Road', 'Skoda Fabia RS Rally2', 'finished', ?, 0, ?, ?, 'x', 'share', 1, ?, ?, ?, ?)`)
    .run(code, who, fin, verdict, JSON.stringify({ signed: true, live: true, notes, road }), data, data.length, Date.now(), Date.now() + 1e10);
};
add('clean23456', sid(1), drive(false, 28), 'clean', [], { start: true, finishNear: true, checkpoints: 1, offMs: 0, maxOffM: 3, cuts: [], jumps: 0, topKmh: 101, fast: 0, km: 3.09 });
const cut = drive(true, 27);
add('cutcut2345', sid(2), cut, 'review', ['a cut at km 2: 64 m of road skipped'], { start: true, finishNear: true, checkpoints: 1, offMs: 2200, maxOffM: 26,
  cuts: [{ km: 2, m: 64, ms: cut[Math.floor(cut.length * 0.66)][0] }], jumps: 0, topKmh: 97, fast: 0, km: 3.02 });
const worker = (await import('../src/index.js')).default;
http.createServer(async (req, res) => {
  const body = req.method === 'POST' ? await new Promise((ok) => { const b = []; req.on('data', (c) => b.push(c)); req.on('end', () => ok(Buffer.concat(b))); }) : undefined;
  const r = await worker.fetch(new Request('http://127.0.0.1:8798' + req.url, { method: req.method, headers: req.headers, body }), f.env, { waitUntil() {} });
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
}).listen(8798, () => console.log('ready: http://127.0.0.1:8798/r/clean23456'));
