// REPLAYS: a run on the app's own replay (client acr_daily/replays.py) as a proof of what was driven. The app keeps
// every run on its PC; a counted one (a daily, an online rally's stage) is followed by this server while it is driven:
// at the start the app gets a run id and a nonce, then every 10 s and at the finish line it sends the hash of its rows
// so far, chained from the nonce. Each commit is kept here with THIS server's clock. An uploaded replay must hash to
// the same chain: its rows existed at those moments (driven as the stage ran: not made afterwards, not sped up), they
// are the driver's (their app's Ed25519 key signs the file; the key was told to us with the begin, signed in), and
// they are checked against the stage's road (left it, cut it, faster than a car can be).
//
// What it is for (the user, 26 Nov 2026): a DNF whose result the game lost (the loading hang, the game closed) taken
// back on its own: a daily's (as the admin's reinstate, src/apptime.js) or an online rally's stage (as a steward's
// "time": the entry goes on to its next stage). Clean replays only, five a week a driver; anything else goes to the
// admin / the stewards with the replay to watch. And: stewards ask a driver for a stage's replay (the app sends it by
// itself), drivers share theirs (/r/<code>, on the stage's map; a replay of a stage still open can't be public until
// it closes: no line to copy while it counts).
//
//   POST /api/replays/begin   {kind, ref, track, car, clockMs, key}       (signed in) -> {rid, nonce}
//   POST /api/replays/commit  {rid, n, count, hash, clockMs, fin}         -> {ok}
//   POST /api/replays/upload?public=1   the .acrreplay file's bytes      -> {code, verdict, report, action, stamp}
//   GET  /api/replays/wanted                                              -> {wanted: [{rid, ref, why, requestId}]}
//   POST /api/replays/requests/<id>/none                                  the driver has no replay of it
//   GET  /api/replays/mine                                                -> {replays: [...]} (what I uploaded)
//   GET  /api/replays/<code>            what it is and its checks (the owner, the admin, the event's stewards; anyone
//                                       when public)
//   GET  /api/replays/<code>/file       the file itself (same)
//   POST /api/replays/<code>/share      {public: true|false} (its driver)
//   GET  /api/admin/replays             the ones sent to review, newest first (admin key)
import { routeInfo, teleported } from './validate.js';
import { noticeStmt } from './social.js';

export const REPLAY = {
  maxBytes: 1500000,          // a gzip'd file (about 2 h 30 min of stage)
  maxRows: 100000,
  maxCommits: 2000,
  slackMs: 5000,              // a commit's stage clock at most this far past the server's clock since the begin
  lateBeginMs: 60000,         // followed from at most this far into the stage (the connection down at the start) for a DNF
                              // to be taken back without a human
  lateFinMs: 180000,          // ... and the finish on the server at most this late (pauses, a connection lost a while)
  missingAfterMs: 30 * 60000, // a finish with no result from the app this long after the begin: the replay stands in
  endM: 15,                   // the road's end this near: the finish line reached (the game frozen at the line)
  runHours: 4,                // commits taken this long after the begin
  followM: 30,                // off the road past this (as the routes' own check, src/index.js followsRoute)
  cutM: 30,                   // the road covered faster than the car moved, by this much in CUT_WINDOW
  cutWindow: 50,              // rows (5 s)
  checkpointM: 40,
  startM: 60,
  finishM: 120,
  topKmh: 330,
  autoPerWeek: 5,             // DNFs taken back by a replay, a driver, in 7 days (more: the admin decides)
  wantedDays: 3,
  keepShareDays: 90,
  keepProofDays: 365,
  perDriver: 40,              // files kept a driver (the oldest shared ones go first)
};
const DAY = 86400000;
// The DNFs a replay may take back: a finish the game or the app lost, nothing the driver did. (A DNF for a restart after
// the finish, settings changed, disqualified by the game, missed, retired by the stewards: never.)
//   LOST   the finish line crossed, the result lost after it: the game closed, hung on its loading, left its results
//          unsaved; dailies and events alike (as src/index.js reinstateRun takes them back)
//   FROZE  the game froze or crashed at the line, before the app saw its finish: the road tells it (verifyReplay)
const LOST = /^(the game closed|no official result|restarted from the game's results screen|left from the results screen)/;
const FROZE = /^(lost the game|stopped \(clock frozen away from the finish\))/;
export const takesBack = (reason) => LOST.test(reason || '') || FROZE.test(reason || '');
const KINDS = ['daily', 'event'];
const utf8 = new TextEncoder();

// ------------------------------------------------------------------ the format (as the app's replays.py)

/** JSON as Python's json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True) writes it. */
export function canon(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v));
  if (typeof v === 'string') return JSON.stringify(v).replace(/[\u0080-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
  return '{' + Object.keys(v).sort().map((k) => canon(k) + ':' + canon(v[k])).join(',') + '}';
}
const hexOf = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
const bytesOf = (hex) => {
  if (typeof hex !== 'string' || !/^([0-9a-f]{2})*$/i.test(hex)) return null;
  return Uint8Array.from(hex.match(/../g) || [], (h) => parseInt(h, 16));
};
const sha = async (text) => hexOf(await crypto.subtle.digest('SHA-256', utf8.encode(text)));
export const rowText = (r) => JSON.stringify(r);
export const chainStart = (rid, nonce) => sha(`acr-replay-chain|${rid}|${nonce}`);
export const chainNext = (h, rows) => sha(h + '\n' + rows.map(rowText).join('\n'));
export async function digestHex(head, rows, rid) {
  const rh = await sha(rows.map(rowText).join('\n'));
  return sha(`acr-replay/1\n${canon(head)}\n${rh}\n${rid || ''}`);
}

/** The file's bytes (gzip'd JSON, or JSON) -> the replay, or {error}. */
export async function readFile(bytes) {
  let text;
  try {
    const u = new Uint8Array(bytes);
    if (u[0] === 0x1f && u[1] === 0x8b) {
      const ds = new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream('gzip')));
      const out = new Uint8Array(await ds.arrayBuffer());
      if (out.length > 40 * 1000 * 1000) return { error: 'too big' };
      text = new TextDecoder().decode(out);
    } else text = new TextDecoder().decode(u);
  } catch { return { error: 'not a replay file' }; }
  let doc;
  try { doc = JSON.parse(text); } catch { return { error: 'not a replay file' }; }
  if (!doc || doc.format !== 'acr-replay' || !Array.isArray(doc.rows) || !doc.head || typeof doc.head !== 'object') return { error: 'not a replay file' };
  if (Number(doc.v) > 1) return { error: 'a replay from a newer app' };
  if (doc.rows.length < 2 || doc.rows.length > REPLAY.maxRows) return { error: 'too short or too long' };
  for (const r of doc.rows) {
    if (!Array.isArray(r) || r.length !== 14 || !r.every(Number.isInteger)) return { error: 'its rows are not the app\'s' };
  }
  for (let i = 1; i < doc.rows.length; i++) if (doc.rows[i][0] <= doc.rows[i - 1][0]) return { error: 'its clock goes back' };
  return { doc };
}

async function verifySig(doc) {
  const sig = doc.sig || {};
  const key = bytesOf(sig.key), s = bytesOf(sig.sig);
  if (!key || key.length !== 32 || !s || s.length !== 64) return { ok: false, digest: await digestHex(doc.head, doc.rows, (doc.live || {}).rid) };
  const digest = await digestHex(doc.head, doc.rows, (doc.live || {}).rid);
  try {
    const k = await crypto.subtle.importKey('raw', key, { name: 'Ed25519' }, false, ['verify']);
    return { ok: await crypto.subtle.verify({ name: 'Ed25519' }, k, s, bytesOf(digest)), digest, key: sig.key.toLowerCase() };
  } catch {
    return { ok: false, digest };
  }
}

// ------------------------------------------------------------------ the checks

/** The replay's rows against the server's commits: the same chain, and never ahead of the server's clock.
 *  run: the replay_runs row. -> {chain, timing, committed (rows), note} */
export async function checkChain(rows, run) {
  let commits;
  try { commits = JSON.parse(run.commits || '[]'); } catch { commits = []; }
  if (!commits.length) return { chain: false, timing: false, committed: 0, note: 'no commits from the stage', lateAt: () => null };
  let h = await chainStart(run.rid, run.nonce), at = 0;
  // (the stage clock when the server began following the run: a begin made late, the connection down at the start,
  // follows from there; what came before it is the app's word alone)
  const base = Math.max(0, run.begin_clock || 0);
  let timing = true, note = null;
  const got = [];                                  // [rows committed, how late the server got them (ms)]
  for (const [count, hash, sms] of commits) {
    if (!(count >= at && count <= rows.length)) return { chain: false, timing: false, committed: at, note: 'it has fewer rows than were sent while driving', lateAt: () => null };
    h = await chainNext(h, rows.slice(at, count));
    at = count;
    if (h !== hash) return { chain: false, timing: false, committed: at, note: 'its rows are not the ones sent while driving', lateAt: () => null };
    if (count > 0) {
      const late = (sms - run.begin_ms) + base - rows[count - 1][0];
      if (late < -REPLAY.slackMs) {
        timing = false;
        note = `its clock ran ahead of the server's (${Math.round(-late / 1000)} s)`;
      }
      got.push([count, late]);
    }
  }
  // how late the server got row i (the first commit with it): pauses in the game, a connection lost meanwhile
  const lateAt = (i) => { const c = got.find(([n]) => n > i); return c ? c[1] : null; };
  return { chain: true, timing, committed: at, note, lateAt };
}

/** The rows against the stage's road (points [[x, z]] m). -> {start, finishNear, checkpoints, offMs, maxOffM, cuts:
 *  [{km, m}], jumps, topKmh, fast, km} */
export function checkRoad(rows, points, finMs = null) {
  const info = routeInfo(points);
  const cum = [0];
  for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  const near = (x, z, from) => {          // -> [progress m, distance m, segment]
    let best = Infinity, bi = 1, bt = 0;
    const scan = (lo, hi) => {
      for (let i = Math.max(1, lo); i < Math.min(points.length, hi); i++) {
        const a = points[i - 1], b = points[i], dx = b[0] - a[0], dz = b[1] - a[1], l2 = dx * dx + dz * dz;
        const t = l2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / l2)) : 0;
        const d = Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz);
        if (d < best) { best = d; bi = i; bt = t; }
      }
    };
    scan(from - 8, from + 60);
    if (best > REPLAY.followM) scan(1, points.length);
    return [cum[bi - 1] + bt * (cum[bi] - cum[bi - 1]), best, bi];
  };
  const xz = rows.map((r) => [r[1] / 100, r[3] / 100]);
  const prog = [], lat = [], jump = [false];
  let seg = 1, offMs = 0, maxOff = 0, jumps = 0, top = 0, fast = 0, km = 0;
  for (let i = 0; i < rows.length; i++) {
    const [s, d, si] = near(xz[i][0], xz[i][1], seg);
    seg = si;
    prog.push(s);
    lat.push(d);
    top = Math.max(top, rows[i][7] / 10);
    if (i === 0) continue;
    const dt = (rows[i][0] - rows[i - 1][0]) / 1000, step = Math.hypot(xz[i][0] - xz[i - 1][0], xz[i][1] - xz[i - 1][1]);
    const j = teleported(step, dt, Math.max(rows[i][7], rows[i - 1][7]) / 10);
    jump.push(j);
    if (j) { jumps++; continue; }
    km += step / 1000;
    // (over 50 ms at least: two rows closer than that, the finish's own, make any wobble of the car look like speed)
    if (dt >= 0.05 && step / dt * 3.6 > REPLAY.topKmh) fast++;
    if (d > REPLAY.followM) { offMs += rows[i][0] - rows[i - 1][0]; maxOff = Math.max(maxOff, d); }
  }
  // cuts: the road's distance covered in a few seconds more than the car moved (corners taken across the fields)
  const cuts = [];
  for (let i = REPLAY.cutWindow; i < rows.length; i++) {
    const a = i - REPLAY.cutWindow;
    let moved = 0, ok = true, wide = 0;
    for (let k = a + 1; k <= i; k++) {
      if (jump[k]) { ok = false; break; }
      moved += Math.hypot(xz[k][0] - xz[k - 1][0], xz[k][1] - xz[k - 1][1]);
      wide = Math.max(wide, lat[k]);
    }
    const gain = prog[i] - prog[a];
    if (ok && gain - moved > REPLAY.cutM && wide > 12) {
      cuts.push({ km: Math.round(prog[a] / 100) / 10, m: Math.round(gain - moved), ms: rows[a][0] });
      i += REPLAY.cutWindow;              // (one corner counted once)
    }
  }
  let passed = 0;
  for (const c of info.checkpoints) {
    if (xz.some(([x, z]) => Math.hypot(x - c[0], z - c[1]) <= REPLAY.checkpointM)) passed++;
  }
  const end = points[points.length - 1];
  let fi = rows.length - 1;
  if (finMs != null) {
    fi = rows.findIndex((r) => r[0] >= finMs - 250);
    if (fi < 0) fi = rows.length - 1;
  }
  // the finish line reached, as the road says it (the game frozen at the line, before the app saw its finish): the
  // first row at the road's end, its clock the stage's (the clock stops there: the app keeps that row, replays.py)
  const atEnd = prog.findIndex((p, i) => info.length - p <= REPLAY.endM && Math.hypot(xz[i][0] - end[0], xz[i][1] - end[1]) <= REPLAY.finishM);
  return {
    start: Math.hypot(xz[0][0] - points[0][0], xz[0][1] - points[0][1]) <= REPLAY.startM,
    finishNear: Math.hypot(xz[fi][0] - end[0], xz[fi][1] - end[1]) <= REPLAY.finishM || info.length - prog[fi] <= REPLAY.finishM,
    endRow: atEnd < 0 ? null : atEnd,
    checkpoints: info.checkpoints.length ? passed / info.checkpoints.length : 1,
    offMs, maxOffM: Math.round(maxOff), cuts, jumps, topKmh: Math.round(top), fast, km: Math.round(km * 100) / 100,
    lengthKm: Math.round(info.length / 10) / 100,
  };
}

/** Everything told about one replay. ctx: {run (replay_runs row or null), points (the road or null), keys (the
 *  uploader's known keys), uploader (steam id), lost (the DNF's reason, when it is one: a finish the game froze on is
 *  then told by the road)}. -> {verdict: clean | review | refused, auto (a DNF may be taken back without a human),
 *  report, digest, finMs, byRoad}
 *
 *  clean: the drive itself (followed, the whole road, no cut, nothing a car can't do). auto, on top: the finish reached
 *  the server in time (LATE_FIN_MS: a pause, a connection lost for a while; later, its rows could have been made up
 *  meanwhile) and the server followed it from the start (LATE_BEGIN_MS: the connection down at the start). */
export async function verifyReplay(doc, { run = null, points = null, keys = [], uploader = null, lost = '' } = {}) {
  const h = doc.head;
  const report = { notes: [] };
  const no = (why) => { report.notes.push(why); return { verdict: 'refused', auto: false, report, digest: null, finMs: null }; };
  const sig = await verifySig(doc);
  report.signed = sig.ok;
  if (!sig.ok) return no('its signature does not match: changed after it was made, or not made by ACR DAILY');
  report.knownKey = keys.includes(sig.key);
  const driver = String((h.driver || {}).steamId || '');
  if (uploader && driver && driver !== uploader) return no('someone else\'s replay: only its driver sends it');
  report.live = !!run;
  let finMs = Number.isInteger(h.finMs) ? h.finMs : null;
  let c = null;
  if (run) {
    if (run.steam_id !== uploader) return no('not your run');
    if (sig.key !== run.key) return no('signed with another key than the one the run began with');
    if (run.track !== h.track || run.car !== h.car || run.kind !== h.kind || run.ref !== h.ref) return no('it is not the run the server followed');
    c = await checkChain(doc.rows, run);
    report.chain = c.chain;
    report.timing = c.timing;
    report.committed = c.committed;
    if (c.note) report.notes.push(c.note);
    if (!c.chain) return no(c.note || 'its rows are not the ones sent while driving');
    if (!c.timing) return no(c.note);
    report.beganAt = run.begin_clock || 0;
    if (report.beganAt > REPLAY.lateBeginMs) report.notes.push(`followed by the server only from ${Math.round(report.beganAt / 1000)} s into the stage`);
    // the finish: as the final commit said, inside the rows committed
    if (finMs != null && run.fin_ms !== finMs) { report.notes.push('its finish is not the one sent at the line'); finMs = null; }
    if (finMs != null && !(c.committed > 0 && doc.rows[c.committed - 1][0] >= finMs - 250)) {
      report.notes.push('its finish came after the last commit'); finMs = null;
    }
  } else {
    report.notes.push('not followed by the server while driven (practice, offline, or not signed in)');
  }
  report.finished = h.status === 'finished' && finMs != null;
  let byRoad = false;
  if (points && points.length > 2) {
    const r = checkRoad(c ? doc.rows.slice(0, c.committed) : doc.rows, points, finMs);
    report.road = r;
    // the game frozen at the finish line, before the app saw its finish (its DNF: the game lost): the line reached,
    // the whole road driven, as the rows the server got say
    if (!report.finished && run && FROZE.test(lost || '') && r.endRow != null && r.checkpoints >= 0.98) {
      finMs = doc.rows[r.endRow][0];
      report.finished = byRoad = true;
      report.notes.push('the finish line reached as the road says (the game froze before the app saw its finish)');
    }
    if (!r.start) report.notes.push('it does not start at the stage\'s start');
    if (report.finished && !r.finishNear && !byRoad) { report.notes.push('its finish is not at the stage\'s end'); report.finished = false; }
    if (r.checkpoints < 0.98) report.notes.push(`${Math.round((1 - r.checkpoints) * 100)} % of the road's checkpoints missed`);
    if (r.offMs > 3000) report.notes.push(`off the road ${Math.round(r.offMs / 1000)} s (up to ${r.maxOffM} m)`);
    for (const x of r.cuts) report.notes.push(`a cut at km ${x.km}: ${x.m} m of road skipped`);
    if (r.fast) report.notes.push(`moved faster than ${REPLAY.topKmh} km/h (${r.fast} times)`);
    if (r.topKmh > REPLAY.topKmh) report.notes.push(`top speed ${r.topKmh} km/h`);
    if (Number.isInteger(h.resets) && r.jumps > h.resets + 1) report.notes.push(`${r.jumps} jumps of the car, ${h.resets} resets counted`);
  } else {
    report.notes.push('no road known for this stage: not checked against it');
  }
  if (report.finished && c) {                  // how late the server got the finish
    const i = doc.rows.findIndex((x) => x[0] >= finMs - 250);
    report.finLateMs = i < 0 ? null : c.lateAt(i);
    if (report.finLateMs == null || report.finLateMs > REPLAY.lateFinMs) {
      report.notes.push(report.finLateMs == null ? 'its finish never reached the server'
        : `its finish reached the server ${Math.round(report.finLateMs / 60000)} min late (the connection down, or the app closed)`);
    }
  }
  const clean = !!(run && report.chain && report.timing && report.finished && points && report.road
    && report.road.start && report.road.checkpoints >= 0.98 && report.road.offMs <= 3000 && !report.road.cuts.length
    && !report.road.fast && report.road.topKmh <= REPLAY.topKmh
    && !(Number.isInteger(h.resets) && report.road.jumps > h.resets + 1));
  const auto = clean && report.finLateMs != null && report.finLateMs <= REPLAY.lateFinMs && report.beganAt <= REPLAY.lateBeginMs;
  return { verdict: clean ? 'clean' : 'review', auto, report, digest: sig.digest, finMs, byRoad };
}

// ------------------------------------------------------------------ the API

const rand = (n) => {
  const a = crypto.getRandomValues(new Uint8Array(n));
  return [...a].map((b) => 'abcdefghijkmnpqrstuvwxyz23456789'[b % 32]).join('');
};
const parseDaily = (ref) => {
  const m = String(ref || '').match(/^(\d{4}-\d{2}-\d{2})(?:\/([12]))?$/);
  return m ? { date: m[1], slot: m[2] ? +m[2] : 1 } : null;
};
const parseEvent = (ref) => {
  const m = String(ref || '').match(/^event:(\d+):(\d+)$/);
  return m ? { id: +m[1], no: +m[2] } : null;
};
const fmt = (ms) => {
  if (ms == null) return '-';
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
};

/** The stamp the server puts on a checked replay: HMAC(sha256('replay-stamp|' + ADMIN_KEY), code|digest|verdict). */
async function stampOf(env, code, digest, verdict) {
  const raw = await crypto.subtle.digest('SHA-256', utf8.encode(`replay-stamp|${(env.ADMIN_KEY || 'dev').trim()}`));
  const key = await crypto.subtle.importKey('raw', raw, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hexOf(await crypto.subtle.sign('HMAC', key, utf8.encode(`${code}|${digest}|${verdict}`)));
}

/** May `me` see this replay (its row)? Its driver, the admin, the stewards of its event; anyone once public. */
async function canView(env, row, me, admin) {
  if (row.public || admin || (me && me.steam_id === row.steam_id)) return true;
  const ev = parseEvent(row.ref);
  if (!me || !ev) return false;
  const l = await env.DB.prepare(`SELECT l.owner, m.role FROM league_events e JOIN leagues l ON l.id = e.league_id
      LEFT JOIN league_members m ON m.league_id = l.id AND m.steam_id = ? WHERE e.id = ?`).bind(me.steam_id, ev.id).first();
  return !!l && (l.owner === me.steam_id || l.role === 'admin');
}

/** When a replay of this run may be public: a daily's once its day is over, an event's stage once the event closes. */
async function publicFrom(env, kind, ref) {
  if (kind === 'daily') {
    const d = parseDaily(ref);
    return d ? Date.parse(d.date + 'T00:00:00Z') + DAY : 0;
  }
  if (kind === 'event') {
    const e = parseEvent(ref);
    const ev = e && await env.DB.prepare('SELECT closes FROM league_events WHERE id = ?').bind(e.id).first();
    return ev ? ev.closes || 0 : 0;
  }
  return 0;
}

function rowOut(r, extra = {}) {
  let report = {};
  try { report = JSON.parse(r.report || '{}'); } catch { report = {}; }
  return { code: r.code, steamId: r.steam_id, name: r.name || null, kind: r.kind, ref: r.ref, track: r.track, car: r.car,
    status: r.status, finMs: r.fin_ms, penaltyMs: r.penalty_ms, verdict: r.verdict, report, digest: r.digest, why: r.why,
    public: !!r.public, action: r.action || null, size: r.size, views: r.views || 0, created: r.created, ...extra };
}

/**
 * deps: {json, err, admin (bool), reinstate(runId, penaltyMs) -> Response (src/index.js reinstateRun),
 *        stageTime(eventId, steamId, no, timeMs, penaltyMs, reason, now) -> {ok} | {error} (src/leaguesapi.js),
 *        route(track) -> points or null, site}
 */
export async function replaysApi(req, env, path, url, me, now, deps) {
  const { json, err } = deps;
  if (!path.startsWith('/api/replays')) return null;
  const post = req.method === 'POST';
  const need = () => (me ? null : err('sign in with Steam first', 401));

  if (path === '/api/replays/begin' && post) {
    const no = need(); if (no) return no;
    if (me.banned) return err('this account is banned', 403);
    const b = await req.json().catch(() => ({}));
    const kind = String(b.kind || ''), ref = String(b.ref || '').slice(0, 60);
    if (!KINDS.includes(kind) || !(kind === 'daily' ? parseDaily(ref) : parseEvent(ref))) return err('what run is it?');
    const key = String(b.key || '').toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(key)) return err('no replay key');
    const track = String(b.track || '').slice(0, 120), car = String(b.car || '').slice(0, 120);
    if (!track || !car) return err('which stage and car?');
    // (a begin made late, the connection down at the start: followed from there; verifyReplay says how late)
    const clock = Math.max(0, Math.round(+b.clockMs || 0));
    if (clock > REPLAY.runHours * 3600000) return err('too late into the stage', 409);
    const keys = await env.DB.prepare('SELECT COUNT(*) AS n FROM replay_keys WHERE steam_id = ?').bind(me.steam_id).first();
    const rid = rand(16), nonce = rand(24);
    await env.DB.batch([
      // (a driver's keys: one a PC; at most 10 kept, an 11th PC's refused until the admin clears them)
      ...((keys && keys.n >= 10) ? [] : [env.DB.prepare('INSERT OR IGNORE INTO replay_keys (steam_id, key, created) VALUES (?, ?, ?)').bind(me.steam_id, key, now)]),
      env.DB.prepare(`INSERT INTO replay_runs (rid, nonce, steam_id, kind, ref, track, car, key, begin_ms, begin_clock)
        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM replay_keys WHERE steam_id = ? AND key = ?)`)
        .bind(rid, nonce, me.steam_id, kind, ref, track, car, key, now, clock, me.steam_id, key),
      env.DB.prepare('DELETE FROM replay_runs WHERE steam_id = ? AND begin_ms < ? AND uploaded IS NULL').bind(me.steam_id, now - 30 * DAY),
    ]);
    const ok = await env.DB.prepare('SELECT rid FROM replay_runs WHERE rid = ?').bind(rid).first();
    if (!ok) return err('too many PCs with replay keys on this account: ask the admin', 409);
    return json({ rid, nonce });
  }

  if (path === '/api/replays/commit' && post) {
    const no = need(); if (no) return no;
    const b = await req.json().catch(() => ({}));
    const rid = String(b.rid || ''), hash = String(b.hash || '');
    const n = Math.round(+b.n), count = Math.round(+b.count), clock = Math.round(+b.clockMs || 0);
    if (!/^[a-z0-9]{16}$/.test(rid) || !/^[0-9a-f]{64}$/.test(hash) || !(n >= 1 && n <= REPLAY.maxCommits) || !(count >= 0 && count <= REPLAY.maxRows)) return err('bad commit');
    const fin = Number.isInteger(b.fin) && b.fin > 0 ? b.fin : null;
    // (in order, each once: the n-th only after n - 1 of them; a finish once)
    const r = await env.DB.prepare(`UPDATE replay_runs SET commits = json_insert(commits, '$[#]', json(?)), fin_ms = COALESCE(fin_ms, ?)
        WHERE rid = ? AND steam_id = ? AND json_array_length(commits) = ? AND begin_ms > ? AND uploaded IS NULL`)
      .bind(JSON.stringify([count, hash, now, clock]), fin, rid, me.steam_id, n - 1, now - REPLAY.runHours * 3600000).run();
    if (r.meta.changes) return json({ ok: true, n });
    // (not the next one: where the server is with the run, so the app sends on from there: a commit that got through
    // while its answer was lost, or a run the server no longer takes)
    const at = await env.DB.prepare('SELECT json_array_length(commits) AS n, uploaded, begin_ms FROM replay_runs WHERE rid = ? AND steam_id = ?')
      .bind(rid, me.steam_id).first();
    return json({ error: 'not this run\'s next commit', have: at ? at.n : null,
      closed: !at || !!at.uploaded || at.begin_ms <= now - REPLAY.runHours * 3600000 }, 409);
  }

  const mr = path.match(/^\/api\/replays\/run\/([a-z0-9]{16})$/);
  if (mr && !post) {                                    // where the server is with a run: the app sends the commits it missed
    const no = need(); if (no) return no;
    const at = await env.DB.prepare('SELECT json_array_length(commits) AS n, fin_ms, uploaded, begin_ms FROM replay_runs WHERE rid = ? AND steam_id = ?')
      .bind(mr[1], me.steam_id).first();
    if (!at) return err('no such run', 404);
    return json({ have: at.n, fin: at.fin_ms, uploaded: at.uploaded || null, open: !at.uploaded && at.begin_ms > now - REPLAY.runHours * 3600000 });
  }

  if (path === '/api/replays/wanted' && !post) {
    const no = need(); if (no) return no;
    return json({ wanted: await wanted(env, me.steam_id, now) });
  }

  let m = path.match(/^\/api\/replays\/requests\/(\d+)\/none$/);
  if (m && post) {
    const no = need(); if (no) return no;
    const q = await env.DB.prepare(`UPDATE replay_requests SET state = 'none', answered = ? WHERE id = ? AND steam_id = ? AND state = 'open'
        RETURNING event_id, stage_no, by`).bind(now, +m[1], me.steam_id).first();
    if (!q) return err('no such request', 404);
    await noticeStmt(env, q.by, 'replay', `${me.name || 'The driver'} has no replay of SS${q.stage_no + 1} to send (its app kept none).`,
      `event:${q.event_id}`, now).run();
    return json({ ok: true });
  }

  if (path === '/api/replays/upload' && post) {
    const no = need(); if (no) return no;
    if (me.banned) return err('this account is banned', 403);
    const bytes = new Uint8Array(await req.arrayBuffer());
    if (bytes.length > REPLAY.maxBytes) return err('this replay is too big to send (over 1.5 MB)', 413);
    const got = await readFile(bytes);
    if (got.error) return err(got.error);
    return upload(env, me, got.doc, bytes, url.searchParams.get('public') === '1', now, deps);
  }

  m = path.match(/^\/api\/replays\/event\/(\d+)$/);
  if (m && !post) {                                     // an event's replays sent, for its stewards
    const no = need(); if (no) return no;
    if (!deps.admin && !(await canView(env, { ref: `event:${m[1]}:0`, steam_id: '', public: 0 }, me, false))) return err('only its stewards', 403);
    const { results } = await env.DB.prepare(`SELECT f.code, f.steam_id, p.name, f.ref, f.verdict, f.action, f.created FROM replay_files f
        LEFT JOIN players p ON p.steam_id = f.steam_id WHERE f.ref LIKE ? ORDER BY f.created DESC LIMIT 100`).bind(`event:${m[1]}:%`).all();
    return json({ replays: results.map((r) => ({ code: r.code, steamId: r.steam_id, name: r.name || 'Driver',
      stage: Number(String(r.ref).split(':')[2]) + 1, verdict: r.verdict, action: r.action, created: r.created })) });
  }

  if (path === '/api/replays/mine' && !post) {
    const no = need(); if (no) return no;
    const { results } = await env.DB.prepare(`SELECT code, rid, steam_id, kind, ref, track, car, status, fin_ms, penalty_ms, verdict,
        report, digest, why, public, action, size, views, created FROM replay_files WHERE steam_id = ? ORDER BY created DESC LIMIT 50`).bind(me.steam_id).all();
    return json({ replays: results.map((r) => rowOut(r)) });
  }

  m = path.match(/^\/api\/replays\/([a-z0-9]{10})(\/file|\/share)?$/);
  if (m) {
    const row = await env.DB.prepare(`SELECT f.*, p.name FROM replay_files f LEFT JOIN players p ON p.steam_id = f.steam_id WHERE f.code = ?`)
      .bind(m[1]).first();
    if (!row || !(await canView(env, row, me, deps.admin))) return err('no such replay', 404);
    if (m[2] === '/share') {
      if (!post) return err('POST it', 405);
      if (!me || me.steam_id !== row.steam_id) return err('only its driver shares it', 403);
      const b = await req.json().catch(() => ({}));
      const from = await publicFrom(env, row.kind, row.ref);
      if (b.public && from > now) return err(`it can be public once the stage no longer counts (${new Date(from).toISOString().slice(0, 16).replace('T', ' ')} UTC)`, 409);
      await env.DB.prepare('UPDATE replay_files SET public = ?, expires = MAX(expires, ?) WHERE code = ?')
        .bind(b.public ? 1 : 0, now + REPLAY.keepShareDays * DAY, row.code).run();
      return json({ ok: true, public: !!b.public });
    }
    if (m[2] === '/file') {
      return new Response(row.data, { headers: { 'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="acr-daily-${row.code}.acrreplay"`, 'Cache-Control': 'private, max-age=300',
        'Access-Control-Allow-Origin': '*' } });
    }
    if (!(me && me.steam_id === row.steam_id)) await env.DB.prepare('UPDATE replay_files SET views = views + 1 WHERE code = ?').bind(row.code).run();
    const ev = parseEvent(row.ref);
    const evRow = ev && await env.DB.prepare('SELECT name, stages FROM league_events WHERE id = ?').bind(ev.id).first();
    return json(rowOut(row, { mine: !!(me && me.steam_id === row.steam_id),
      ...(evRow ? { event: { id: ev.id, name: evRow.name, stage: ev.no + 1 } } : {}),
      publicFrom: await publicFrom(env, row.kind, row.ref) }));
  }
  return null;
}

/** What a followed run's replay can do now (run: its replay_runs row): -> {why: 'dnf' | 'missing', lost, target} or
 *  null.
 *    dnf      the run ended as a DNF the game or the app lost (takesBack: never one the driver earned); a daily's: that
 *             run (its clock the replay's finish, the game frozen at the line: the DNF's), an event's: the entry's DNF
 *             on that very stage
 *    missing  the replay shows a finish and no result ever came from the app (a crash past the line, the result lost
 *             on its way): MISSING_AFTER_MS after the start, the replay stands in for it
 *  Only the driver's first start of that stage / daily (the one that counts): a later attempt's replay never stands
 *  in for it. */
async function situation(env, run, sid, now) {
  const first = await env.DB.prepare('SELECT rid FROM replay_runs WHERE ref = ? AND steam_id = ? ORDER BY begin_ms LIMIT 1').bind(run.ref, sid).first();
  if (!first || first.rid !== run.rid) return null;
  const late = now - run.begin_ms >= REPLAY.missingAfterMs;
  if (run.kind === 'daily') {
    const d = parseDaily(run.ref);
    if (!d) return null;
    const { results: rows } = await env.DB.prepare(`SELECT id, status, reason, clock_ms, flags FROM runs WHERE steam_id = ? AND date = ? AND slot = ?
        AND created >= ? ORDER BY created LIMIT 10`).bind(sid, d.date, d.slot, run.begin_ms).all();
    const dnf = rows.find((r) => r.status === 'dnf' && takesBack(r.reason) && !String(r.flags || '').includes('reviewed: kept as a DNF')
      && (run.fin_ms != null ? Math.abs((r.clock_ms || 0) - run.fin_ms) <= 1500 : FROZE.test(r.reason || '')));
    if (dnf) return { why: 'dnf', lost: dnf.reason, target: dnf };
    if (!rows.length && run.fin_ms != null && late) return { why: 'missing', lost: '', target: d };
    return null;
  }
  if (run.kind === 'event') {
    const e = parseEvent(run.ref);
    const en = e && await env.DB.prepare(`SELECT e.status, e.reason, e.done, e.on_stage, e.dsq, v.closes FROM league_entries e
        JOIN league_events v ON v.id = e.event_id WHERE e.event_id = ? AND e.steam_id = ?`).bind(e.id, sid).first();
    if (!en || en.dsq || en.done !== e.no || run.begin_ms > en.closes) return null;
    if (en.status === 'dnf' && takesBack(en.reason) && (run.fin_ms != null || FROZE.test(en.reason || ''))) {
      return { why: 'dnf', lost: en.reason, target: e };
    }
    if (en.status === 'running' && (en.on_stage === e.no || en.on_stage == null) && run.fin_ms != null && late) {
      return { why: 'missing', lost: '', target: e };
    }
  }
  return null;
}

/** What the server wants from this driver's app: the replays that take a DNF back or stand in for a result that never
 *  came (situation), and the stewards' requests. */
export async function wanted(env, sid, now) {
  const since = now - REPLAY.wantedDays * DAY;
  const [runs, reqs] = await env.DB.batch([
    env.DB.prepare(`SELECT * FROM replay_runs WHERE steam_id = ? AND begin_ms > ? AND uploaded IS NULL ORDER BY begin_ms LIMIT 20`).bind(sid, since),
    env.DB.prepare(`SELECT id, event_id, stage_no FROM replay_requests WHERE steam_id = ? AND state = 'open' ORDER BY id`).bind(sid),
  ]);
  const out = [];
  for (const r of runs.results) {
    const s = await situation(env, r, sid, now);
    if (s) out.push({ rid: r.rid, ref: r.ref, why: s.why });
  }
  for (const q of reqs.results) out.push({ rid: null, ref: `event:${q.event_id}:${q.stage_no}`, why: 'steward', requestId: q.id });
  return out;
}

async function upload(env, me, doc, bytes, wantPublic, now, deps) {
  const { json, err } = deps;
  const h = doc.head;
  const rid = (doc.live || {}).rid ? String(doc.live.rid) : null;
  const run = rid ? await env.DB.prepare('SELECT * FROM replay_runs WHERE rid = ?').bind(rid).first() : null;
  if (rid && !run) return err('the server no longer has this run (over 30 days old?)', 404);
  if (run && run.uploaded) {
    const had = await env.DB.prepare('SELECT code, verdict, action FROM replay_files WHERE code = ?').bind(run.uploaded).first();
    if (had) return json({ code: had.code, verdict: had.verdict, action: had.action, again: true });
  }
  const { results: keyRows } = await env.DB.prepare('SELECT key FROM replay_keys WHERE steam_id = ?').bind(me.steam_id).all();
  const points = await deps.route(String(h.track || ''));
  const s = run ? await situation(env, run, me.steam_id, now) : null;
  const v = await verifyReplay(doc, { run, points, keys: keyRows.map((k) => k.key), uploader: me.steam_id, lost: s ? s.lost : '' });
  if (v.verdict === 'refused') return json({ verdict: 'refused', report: v.report }, 422);
  const code = rand(10);
  let action = null, why = 'share';
  const notes = [];
  // the game's penalty at the finish (the mod read it there, on the results screen too); unknown: a daily counts 10 s
  // a respawn (src/apptime.js), an event's stewards set it if there were respawns
  const pen = Number.isInteger(h.penaltyMs) ? h.penaltyMs : null;
  // the car as it crossed the line (life points per part, x damageScale in the file: ints only in what is signed)
  const damage = h.damage && typeof h.damage === 'object' && !Array.isArray(h.damage)
    ? Object.fromEntries(Object.entries(h.damage).map(([k, x]) => [k, Number(x) / (Number(h.damageScale) || 1)])) : null;
  if (s && run.kind === 'daily') {
    why = s.why;
    action = await takeBack(env, me, v, now, async () => {
      let id = s.target.id;
      if (s.why === 'missing') {                        // (no result from the app: a DNF row of its own, taken back at once)
        const att = await env.DB.prepare('SELECT started FROM attempts WHERE steam_id = ? AND date = ? AND slot = ?')
          .bind(me.steam_id, s.target.date, s.target.slot).first();
        const sch = await env.DB.prepare('SELECT car FROM schedule WHERE date = ? AND slot = ?').bind(s.target.date, s.target.slot).first();
        const ins = await env.DB.prepare(`INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, total_ms, flags,
            app_version, created, started_at) VALUES (?, ?, ?, ?, ?, 'dnf', ?, ?, ?, NULL, '[]', ?, ?, ?)`)
          .bind(s.target.date, s.target.slot, me.steam_id, run.track, sch ? sch.car : run.car,
            'no official result from the game (no result came from the app: its replay stands in)', v.finMs, h.resets | 0,
            String(h.appVersion || '').slice(0, 20), now, att ? att.started : run.begin_ms - (run.begin_clock || 0)).run();
        id = ins.meta.last_row_id;
      } else if (Math.abs((s.target.clock_ms || 0) - v.finMs) > 1500) {
        return { error: 'its finish is not the DNF\'s clock' };
      }
      const res = await deps.reinstate(id, pen == null ? undefined : pen);
      const out = await res.json().catch(() => ({}));
      if (!res.ok) return { error: out.error || 'not taken back' };
      await env.DB.prepare(`UPDATE runs SET flags = json_insert(COALESCE(flags, '[]'), '$[#]', ?) WHERE id = ?`)
        .bind(`reinstated by replay ${code}`, id).run();
      return { ok: true, text: `${s.why === 'missing' ? 'Result put in from the replay' : 'DNF taken back'}: ${fmt(out.totalMs)}${out.rank ? `, P${out.rank}` : ''}` };
    });
  } else if (s && run.kind === 'event') {
    why = s.why;
    const p = pen != null ? pen : ((h.resets || 0) > 0 ? null : 0);
    if (p == null) notes.push('the game\'s penalty at the finish is not known (respawns): the stewards set the time');
    action = p == null ? 'sent to the stewards' : await takeBack(env, me, v, now, () => deps.stageTime(s.target.id, me.steam_id, s.target.no,
      v.finMs, p, `finish shown by the driver's replay /r/${code}`, now, damage).then((r) => (r.error ? r
      : { ok: true, text: `SS${s.target.no + 1}: ${fmt(v.finMs + p)}, the rally goes on` })));
  }
  // a steward asked for it
  const reqs = h.ref ? (await env.DB.prepare(`SELECT id, by, stage_no, event_id FROM replay_requests WHERE steam_id = ? AND state = 'open'
      AND 'event:' || event_id || ':' || stage_no = ?`).bind(me.steam_id, String(h.ref)).all()).results : [];
  if (reqs.length && why === 'share') why = 'steward';
  const took = /^(DNF taken back|Result put in|SS\d)/.test(action || '');
  const from = await publicFrom(env, String(h.kind || ''), h.ref);
  const pub = wantPublic && from <= now ? 1 : 0;
  if (wantPublic && !pub) notes.push('public once the stage no longer counts');
  const keepDays = why === 'share' ? REPLAY.keepShareDays : REPLAY.keepProofDays;
  const report = { ...v.report, notes: [...v.report.notes, ...notes] };
  const stmts = [
    env.DB.prepare(`INSERT INTO replay_files (code, rid, steam_id, kind, ref, track, car, status, fin_ms, penalty_ms, verdict, report, digest,
        why, public, action, data, size, created, expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(code, rid, me.steam_id, String(h.kind || 'practice').slice(0, 20), h.ref ? String(h.ref).slice(0, 60) : null,
        String(h.track || '').slice(0, 120), String(h.car || '').slice(0, 120), String(h.status || 'ended').slice(0, 20),
        v.finMs, pen, v.verdict, JSON.stringify(report), v.digest, why === 'missing' ? 'dnf' : why, pub, action,
        bytes, bytes.length, now, now + keepDays * DAY),
    env.DB.prepare('DELETE FROM replay_files WHERE expires < ?').bind(now),
    // (a driver's oldest shared ones past perDriver)
    env.DB.prepare(`DELETE FROM replay_files WHERE steam_id = ? AND why = 'share' AND code NOT IN
        (SELECT code FROM replay_files WHERE steam_id = ? ORDER BY created DESC LIMIT ?)`).bind(me.steam_id, me.steam_id, REPLAY.perDriver),
  ];
  // (the run's replay in: a proof uploaded once; one only shared leaves the run open for a DNF still to come)
  if (run && (s || reqs.length)) stmts.push(env.DB.prepare('UPDATE replay_runs SET uploaded = ? WHERE rid = ?').bind(code, run.rid));
  for (const q of reqs) {
    stmts.push(env.DB.prepare(`UPDATE replay_requests SET state = 'sent', code = ?, answered = ? WHERE id = ?`).bind(code, now, q.id));
    stmts.push(noticeStmt(env, q.by, 'replay', `${me.name || 'The driver'} sent the replay of SS${q.stage_no + 1} you asked for (${v.verdict === 'clean' ? 'its checks are clean' : 'its checks want a look'}): /r/${code}`,
      `event:${q.event_id}`, now));
  }
  if (took) {                                          // (the driver's own note of it, in their inbox)
    stmts.push(noticeStmt(env, me.steam_id, 'replay', `Your replay proved the finish the game lost. ${action}. /r/${code}`, h.ref ? String(h.ref) : null, now));
  }
  if (s && run.kind === 'event' && !took) {
    // (not taken back on its own: the stewards told, with the replay to watch)
    const staff = await env.DB.prepare(`SELECT l.owner FROM league_events ev JOIN leagues l ON l.id = ev.league_id WHERE ev.id = ?`).bind(s.target.id).first();
    if (staff) stmts.push(noticeStmt(env, staff.owner, 'replay', `${me.name || 'A driver'} sent a replay of their ${s.why === 'missing' ? 'stage with no result' : 'DNF'} on SS${s.target.no + 1} for you to look at: /r/${code}`,
      `event:${s.target.id}`, now));
  }
  await env.DB.batch(stmts);
  const stamp = { code, verdict: v.verdict, at: now, mac: await stampOf(env, code, v.digest, v.verdict) };
  return json({ code, verdict: v.verdict, auto: v.auto, report, action, why, public: !!pub, stamp, url: `${deps.site || ''}/r/${code}` });
}

/** A DNF taken back by a replay (fn does it): its checks clean and its finish on the server in time (verifyReplay's
 *  auto), AUTO_PER_WEEK a driver; otherwise left to the admin / the stewards, with the replay to watch. */
async function takeBack(env, me, v, now, fn) {
  if (!v.auto) return 'sent to review';
  const n = await env.DB.prepare(`SELECT COUNT(*) AS n FROM replay_files WHERE steam_id = ? AND created > ?
      AND (action LIKE 'DNF taken back%' OR action LIKE 'Result put in%' OR action LIKE 'SS%')`).bind(me.steam_id, now - 7 * DAY).first();
  if (n && n.n >= REPLAY.autoPerWeek) return `sent to review (more than ${REPLAY.autoPerWeek} this week)`;
  const r = await fn();
  return r && r.ok ? r.text : `sent to review (${(r && r.error) || 'not taken back'})`;
}

/** The admin's list: replays whose checks want a look, newest first. */
export async function adminReplays(env, now) {
  const { results } = await env.DB.prepare(`SELECT f.code, f.rid, f.steam_id, p.name, f.kind, f.ref, f.track, f.car, f.status, f.fin_ms,
      f.penalty_ms, f.verdict, f.report, f.digest, f.why, f.public, f.action, f.size, f.views, f.created
      FROM replay_files f LEFT JOIN players p ON p.steam_id = f.steam_id WHERE f.created > ? AND (f.verdict != 'clean' OR f.why = 'dnf')
      ORDER BY f.created DESC LIMIT 100`).bind(now - 30 * DAY).all();
  return results.map((r) => rowOut(r));
}
