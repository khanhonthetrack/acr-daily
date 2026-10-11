// Cups: a knockout of 1v1s any driver can run. Its maker sets the size (4 to 32 drivers), the entry fee (credits; 0 =
// free), how the pot is shared (CUP.splits), what every match races (stages, car, rules: as a league event), when it
// starts and how long each round is open. Drivers join before the start (the fee is taken then; leaving before the
// start gives it back). At the start the entrants are seeded at random; a cup not full runs with byes for the top
// seeds; fewer than two: it is called off, fees back. Each round's matches open together, each for its two drivers
// only, driven from the app's LEAGUES view (src/leaguesapi.js holders): the lower total goes through; one finisher goes
// through; nobody finishing, or a dead heat: the higher seed. The cron (socialTick in index.js) opens the next round
// once a round is over, and shares the pot when the final is: places 1, 2, then the losing semi-finalists (3).
//
//   GET  /api/cups                       {open, running, finished, mine}
//   GET  /api/cups/<id>                  a cup: its settings, entrants, bracket
//   POST /api/cups {name, about, size, fee, split, event, starts, roundHours}
//   POST /api/cups/<id>/join | leave | cancel (its maker, before the start)

import { stageParts } from './conditions.js';
import { clash, giveWhenStmts, potPayouts, takeWhenStmts } from './credits.js';
import { LIMITS, newLeagueId, text } from './leagues.js';
import { checkMatchSpec, makeHolder, makeMatchEvent, matchRows } from './leaguesapi.js';
import { noticeStmt } from './social.js';

export const CUP = {
  sizes: [4, 8, 16, 32], maxFee: 1000, roundHours: [12, 24, 48, 72], perOwner: 3, startWithinDays: 30,
  splits: { all: { label: 'Winner takes all', shares: [100] }, two: { label: '70 / 30', shares: [70, 30] },
    four: { label: '60 / 30, 5 each to the losing semi-finalists', shares: [60, 30, 5, 5] } },
};

// ------------------------------------------------------------------ the bracket

/** The bracket's size for n entrants: the smallest power of two from 2 that holds them. */
export const bracketSize = (n) => { let b = 2; while (b < n) b *= 2; return b; };

/** The seeds' places in a bracket of size b, slot pairs in order: 2 -> [1, 2], 4 -> [1, 4, 2, 3], 8 -> [1, 8, 4, 5, 2,
 *  7, 3, 6]. The top seeds meet as late as can be. */
export function seedOrder(b) {
  let o = [1, 2];
  while (o.length < b) o = o.flatMap((s) => [s, 2 * o.length + 1 - s]);
  return o;
}

/** Round 1: seeded (steam ids, [0] = the top seed) -> [{slot, a, b}] (a: the higher seed; b null: a bye). */
export function firstRound(seeded) {
  const order = seedOrder(bracketSize(seeded.length));
  const out = [];
  for (let k = 0; k < order.length / 2; k++) {
    const [x, y] = [order[2 * k], order[2 * k + 1]];
    out.push({ slot: k, a: seeded[x - 1] || null, b: seeded[y - 1] || null });
  }
  return out;
}

/** What a round is called, the last being the final. */
export function roundName(round, rounds) {
  return ['Final', 'Semi-final', 'Quarter-final'][rounds - round] || `Round ${round}`;
}

/** A match's winner from its standings rows (eventStandings). seedOf(steamId) -> seed (1 = top). -> {winner, note}. */
export function decideMatch(rows, a, b, seedOf) {
  if (!a || !b) return { winner: a || b, note: 'a bye' };
  const fin = rows.filter((r) => r.status === 'finished' && (r.steamId === a || r.steamId === b));
  const higher = seedOf(a) <= seedOf(b) ? a : b;
  if (!fin.length) return { winner: higher, note: 'nobody finished: the higher seed goes through' };
  if (fin.length === 2 && fin[0].totalMs === fin[1].totalMs) return { winner: higher, note: 'a dead heat: the higher seed goes through' };
  return { winner: fin[0].steamId, note: fin.length === 2 ? `by ${((fin[1].totalMs - fin[0].totalMs) / 1000).toFixed(3)} s` : 'the only finisher' };
}

/** The places once the final is decided. matches: [{round, a, b, winner}]; rounds: how many. -> [[steamId, place]]
 *  best first: the winner 1, the runner-up 2, the losing semi-finalists 3, the quarter-final losers 5 ... (the
 *  higher seed first among equals). */
export function places(matches, rounds, seedOf) {
  const out = [];
  for (let r = rounds; r >= 1; r--) {
    const lost = matches.filter((m) => m.round === r && m.a && m.b).map((m) => (m.winner === m.a ? m.b : m.a))
      .sort((x, y) => seedOf(x) - seedOf(y));
    if (r === rounds) {
      const f = matches.find((m) => m.round === r);
      if (f && f.winner) out.push([f.winner, 1]);
    }
    for (const sid of lost) out.push([sid, r === rounds ? 2 : 2 ** (rounds - r) + 1]);
  }
  return out;
}

// ------------------------------------------------------------------ the API

const cupOut = (c, entrants) => {
  const spec = JSON.parse(c.spec);
  return { id: c.id, name: c.name, about: c.about, owner: { steamId: c.owner, name: c.owner_name || 'a driver' }, size: c.size,
    fee: c.fee, split: JSON.parse(c.split), starts: c.starts, roundHours: c.round_hours, status: c.status, round: c.round,
    entrants: entrants != null ? entrants : c.entrants, pot: c.fee * (entrants != null ? entrants : c.entrants || 0),
    rally: spec.rally, car: spec.car, carClass: spec.car_class, rules: spec.rules,
    stages: spec.stages.map((s) => ({ name: stageParts(s.track).stageName, weather: s.weather, time: s.time })) };
};
const LIST = `SELECT c.*, p.name AS owner_name, (SELECT COUNT(*) FROM cup_entries e WHERE e.cup_id = c.id) AS entrants
  FROM cups c LEFT JOIN players p ON p.steam_id = c.owner`;

export async function cupsApi(req, env, path, me, sameOrigin, now, { json, err }) {
  if (!path.startsWith('/api/cups')) return null;
  const post = req.method === 'POST';
  if (path === '/api/cups' && !post) {
    const [op, ru, fi] = await env.DB.batch([
      env.DB.prepare(`${LIST} WHERE c.status = 'open' ORDER BY c.starts LIMIT 100`),
      env.DB.prepare(`${LIST} WHERE c.status = 'running' ORDER BY c.starts LIMIT 100`),
      env.DB.prepare(`${LIST} WHERE c.status = 'finished' ORDER BY c.settled DESC LIMIT 20`),
    ]);
    const mine = me ? (await env.DB.prepare(`SELECT cup_id FROM cup_entries WHERE steam_id = ?`).bind(me.steam_id).all()).results.map((r) => r.cup_id) : [];
    return json({ open: op.results.map((c) => cupOut(c)), running: ru.results.map((c) => cupOut(c)),
      finished: fi.results.map((c) => cupOut(c)), mine, credits: !!env.CREDITS_FROM,
      limits: { sizes: CUP.sizes, maxFee: CUP.maxFee, roundHours: CUP.roundHours, splits: CUP.splits } });
  }
  let m = path.match(/^\/api\/cups\/([a-z0-9]{8})$/);
  if (m && !post) {
    const c = await env.DB.prepare(`${LIST} WHERE c.id = ?`).bind(m[1]).first();
    if (!c) return err('no such cup', 404);
    const [en, ma] = await env.DB.batch([
      env.DB.prepare(`SELECT e.*, p.name, p.avatar, p.country FROM cup_entries e JOIN players p ON p.steam_id = e.steam_id
        WHERE e.cup_id = ? ORDER BY COALESCE(e.seed, 999), e.joined`).bind(c.id),
      env.DB.prepare('SELECT * FROM cup_matches WHERE cup_id = ? ORDER BY round, slot').bind(c.id),
    ]);
    const who = new Map(en.results.map((e) => [e.steam_id, { steamId: e.steam_id, name: e.name, avatar: e.avatar || null,
      country: e.country || null, seed: e.seed, place: e.place }]));
    const rounds = ma.results.length ? Math.log2(2 * ma.results.filter((x) => x.round === 1).length) : 0;
    // each match's totals as they stand (the standings of its event)
    const totals = new Map();
    for (const x of ma.results) {
      if (x.event_id && x.a && x.b) totals.set(x.id, await matchRows(env, x.event_id, now));
    }
    const side = (sid, rows) => {
      if (!sid) return null;
      const r = (rows || []).find((y) => y.steamId === sid);
      return { ...who.get(sid), status: r ? r.status : null, totalMs: r && r.status === 'finished' ? r.totalMs : null, done: r ? r.done : 0 };
    };
    return json({ ...cupOut(c), entrants: [...who.values()], rounds,
      matches: ma.results.map((x) => ({ id: x.id, round: x.round, slot: x.slot, name: roundName(x.round, rounds), eventId: x.event_id,
        a: side(x.a, totals.get(x.id)), b: side(x.b, totals.get(x.id)), winner: x.winner, note: x.note })),
      me: me ? { signedIn: true, entered: who.has(me.steam_id), owner: c.owner === me.steam_id } : { signedIn: false } });
  }
  if (!post) return err('not found', 404);
  if (!me) return err('sign in with Steam first', 401);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (me.banned) return err('this account is banned', 403);
  const b = await req.json().catch(() => ({})) || {};

  if (path === '/api/cups') {                             // a new cup
    const name = text(b.name, LIMITS.name);
    if (name.length < 3) return err('give the cup a name (3 to 60 characters)');
    const size = Number(b.size), fee = b.fee == null || b.fee === '' ? 0 : Number(b.fee), hours = Number(b.roundHours);
    if (!CUP.sizes.includes(size)) return err(`the size: ${CUP.sizes.join(', ')} drivers`);
    if (!Number.isInteger(fee) || fee < 0 || fee > CUP.maxFee) return err(`the entry fee: 0 to ${CUP.maxFee} credits`);
    if (fee && !env.CREDITS_FROM) return err('entry fees need credits, which are not on yet: make it free (0)', 409);
    if (!CUP.roundHours.includes(hours)) return err(`each round is open ${CUP.roundHours.join(', ')} hours`);
    const split = CUP.splits[b.split];
    if (!split) return err('pick how the pot is shared');
    const starts = Math.round(+b.starts);
    if (!(starts >= now + 3600000 && starts <= now + CUP.startWithinDays * 86400000)) {
      return err(`the cup starts from an hour to ${CUP.startWithinDays} days from now`);
    }
    const c = await checkMatchSpec(env, { ...(b.event || {}), name, opens: now, closes: now + 2 * 3600000 }, now);
    if (c.error) return err(c.error);
    const { opens, closes, ...spec } = c.value;
    const mine = await env.DB.prepare("SELECT COUNT(*) AS n FROM cups WHERE owner = ? AND status IN ('open', 'running')").bind(me.steam_id).first();
    if (mine.n >= CUP.perOwner) return err(`you run ${CUP.perOwner} cups already`, 409);
    for (let tries = 0; tries < 5; tries++) {
      const id = newLeagueId();
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO cups (id, name, about, owner, size, fee, split, spec, starts, round_hours,
        status, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)`).bind(id, name, text(b.about, LIMITS.about), me.steam_id,
        size, fee, JSON.stringify(split.shares), JSON.stringify(spec), starts, hours, now).run();
      if (r.meta.changes) {
        await makeHolder(env, { id, kind: 'cup', name, owner: me.steam_id }, now);
        return json({ id });
      }
    }
    return err('try again', 503);
  }

  m = path.match(/^\/api\/cups\/([a-z0-9]{8})\/(join|leave|cancel)$/);
  if (!m) return err('not found', 404);
  const c = await env.DB.prepare('SELECT * FROM cups WHERE id = ?').bind(m[1]).first();
  if (!c) return err('no such cup', 404);
  if (c.status !== 'open' || now >= c.starts) return err('the cup has started: no more changes to who is in it', 409);
  const ref = `cup:${c.id}`;
  if (m[2] === 'join') {
    if (await env.DB.prepare('SELECT 1 AS x FROM cup_entries WHERE cup_id = ? AND steam_id = ?').bind(c.id, me.steam_id).first()) {
      return json({ entered: true, already: true });
    }
    // the entry, its fee and the place among the holder's members together: only while there is room and the driver
    // has the credits
    const joined = 'EXISTS (SELECT 1 FROM cup_entries WHERE cup_id = ? AND steam_id = ? AND joined = ?)';
    await env.DB.batch([
      env.DB.prepare(`INSERT OR IGNORE INTO cup_entries (cup_id, steam_id, fee, joined) SELECT ?1, ?2, ?3, ?4
        WHERE (SELECT COUNT(*) FROM cup_entries WHERE cup_id = ?1) < ?5
          AND (?3 = 0 OR (SELECT balance FROM credits WHERE steam_id = ?2) >= ?3)`).bind(c.id, me.steam_id, c.fee, now, c.size),
      ...(c.fee ? takeWhenStmts(env, me.steam_id, c.fee, 'cup-fee', ref, c.name, now, joined, [c.id, me.steam_id, now]) : []),
      env.DB.prepare(`INSERT OR IGNORE INTO league_members (league_id, steam_id, joined, role) SELECT ?, ?, ?, 'member' WHERE ${joined}`)
        .bind(c.id, me.steam_id, now, c.id, me.steam_id, now),
    ]);
    const e = await env.DB.prepare('SELECT 1 AS x FROM cup_entries WHERE cup_id = ? AND steam_id = ?').bind(c.id, me.steam_id).first();
    if (!e) {
      const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM cup_entries WHERE cup_id = ?').bind(c.id).first();
      return n.n >= c.size ? err('the cup is full', 409) : err(`the entry fee is ${c.fee} credits: you have ${((await env.DB.prepare('SELECT balance FROM credits WHERE steam_id = ?').bind(me.steam_id).first()) || { balance: 0 }).balance}`, 402);
    }
    return json({ entered: true });
  }
  if (m[2] === 'leave') {
    const e = await env.DB.prepare('SELECT fee FROM cup_entries WHERE cup_id = ? AND steam_id = ?').bind(c.id, me.steam_id).first();
    if (!e) return err('you are not in this cup', 409);
    await env.DB.batch([
      ...(e.fee ? giveWhenStmts(env, me.steam_id, e.fee, 'cup-refund', ref, 'left before the start', now,
        'EXISTS (SELECT 1 FROM cup_entries WHERE cup_id = ? AND steam_id = ?)', [c.id, me.steam_id]) : []),
      env.DB.prepare('DELETE FROM cup_entries WHERE cup_id = ? AND steam_id = ?').bind(c.id, me.steam_id),
      env.DB.prepare('DELETE FROM league_members WHERE league_id = ? AND steam_id = ?').bind(c.id, me.steam_id),
    ]);
    return json({ entered: false });
  }
  if (c.owner !== me.steam_id) return err('only the cup\'s maker calls it off', 403);
  return json(await callOff(env, c, now, `${c.name} was called off by its maker`));
}

/** A cup that won't run: every fee back, a notice to each entrant. */
async function callOff(env, c, now, why) {
  const { results: en } = await env.DB.prepare('SELECT steam_id, fee FROM cup_entries WHERE cup_id = ?').bind(c.id).all();
  const ref = `cup:${c.id}`;
  const off = ["EXISTS (SELECT 1 FROM cups WHERE id = ? AND status = 'cancelled' AND settled = ?)", [c.id, now]];
  await env.DB.batch([
    env.DB.prepare("UPDATE cups SET status = 'cancelled', settled = ? WHERE id = ? AND status = 'open'").bind(now, c.id),
    ...en.filter((e) => e.fee).flatMap((e) => giveWhenStmts(env, e.steam_id, e.fee, 'cup-refund', ref, 'called off', now, ...off)),
    ...en.map((e) => noticeStmt(env, e.steam_id, 'cup', why + (e.fee ? ': your entry fee is back.' : '.'), ref, now, ...off)),
  ]);
  return { cancelled: true, refunded: en.filter((e) => e.fee).length };
}

// ------------------------------------------------------------------ the cron

const shuffle = (a) => {
  const r = crypto.getRandomValues(new Uint32Array(a.length));
  for (let i = a.length - 1; i > 0; i--) { const j = r[i] % (i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
};

/** Open a round's matches (each an event for its two drivers, open from `opensAt`), byes decided at once. pairs:
 *  [{slot, a, b}]. */
async function openRound(env, c, round, rounds, pairs, now, opensAt = now) {
  const spec = JSON.parse(c.spec);
  const names = new Map((await env.DB.prepare('SELECT steam_id, name FROM players WHERE steam_id IN (SELECT steam_id FROM cup_entries WHERE cup_id = ?)')
    .bind(c.id).all()).results.map((p) => [p.steam_id, p.name]));
  const closes = now + c.round_hours * 3600000;
  const rn = roundName(round, rounds);
  const ref = `cup:${c.id}`;
  for (const p of pairs) {
    if (!p.a || !p.b) {
      await env.DB.prepare(`INSERT OR IGNORE INTO cup_matches (cup_id, round, slot, a, b, winner, note) VALUES (?, ?, ?, ?, ?, ?, 'a bye')`)
        .bind(c.id, round, p.slot, p.a, p.b, p.a || p.b).run();
      if (p.a || p.b) await noticeStmt(env, p.a || p.b, 'cup', `${c.name}: a bye in ${rn.toLowerCase()}, you go through.`, ref, now).run();
      continue;
    }
    const ins = await env.DB.prepare('INSERT OR IGNORE INTO cup_matches (cup_id, round, slot, a, b) VALUES (?, ?, ?, ?, ?)')
      .bind(c.id, round, p.slot, p.a, p.b).run();
    if (!ins.meta.changes) continue;                      // (opened already)
    const ev = await makeMatchEvent(env, c.id, spec, `${rn}: ${names.get(p.a)} vs ${names.get(p.b)}`, [p.a, p.b], opensAt, closes, now);
    await env.DB.batch([
      env.DB.prepare('UPDATE cup_matches SET event_id = ? WHERE cup_id = ? AND round = ? AND slot = ?').bind(ev, c.id, round, p.slot),
      ...[[p.a, p.b], [p.b, p.a]].map(([x, y]) => noticeStmt(env, x, 'cup',
        `${c.name}, ${rn.toLowerCase()}: you against ${names.get(y)}. Drive it from ACR Daily's LEAGUES view within ${c.round_hours} hours.`, ref, now)),
    ]);
  }
  await env.DB.prepare('UPDATE cups SET round = ? WHERE id = ?').bind(round, c.id).run();
}

/** The cron's part: cups due to start start (or are called off), finished rounds are decided and the next opened,
 *  a decided final shares the pot. opensAt: when the matches it opens open (the cron: now; a test running it as if
 *  later: the real time, so its drivers can start them). -> [{cup, did}] */
export async function cupsTick(env, now, opensAt = now) {
  const out = [];
  const { results: starting } = await env.DB.prepare("SELECT * FROM cups WHERE status = 'open' AND starts <= ? LIMIT 10").bind(now).all();
  for (const c of starting) {
    const { results: en } = await env.DB.prepare('SELECT steam_id FROM cup_entries WHERE cup_id = ?').bind(c.id).all();
    if (en.length < 2) {
      await callOff(env, c, now, `${c.name} did not start: fewer than two drivers joined`);
      out.push({ cup: c.id, did: 'called off' });
      continue;
    }
    const seeded = shuffle(en.map((e) => e.steam_id));
    const go = await env.DB.prepare("UPDATE cups SET status = 'running' WHERE id = ? AND status = 'open'").bind(c.id).run();
    if (!go.meta.changes) continue;
    await env.DB.batch(seeded.map((sid, i) => env.DB.prepare('UPDATE cup_entries SET seed = ? WHERE cup_id = ? AND steam_id = ?').bind(i + 1, c.id, sid)));
    await openRound(env, c, 1, Math.log2(bracketSize(seeded.length)), firstRound(seeded), now, opensAt);
    out.push({ cup: c.id, did: 'started' });
  }
  const { results: running } = await env.DB.prepare("SELECT * FROM cups WHERE status = 'running' LIMIT 20").all();
  for (const c of running) {
    const { results: ms } = await env.DB.prepare('SELECT m.*, e.closes FROM cup_matches m LEFT JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = ? ORDER BY m.round, m.slot')
      .bind(c.id).all();
    const rounds = Math.log2(2 * ms.filter((x) => x.round === 1).length);
    const seeds = new Map((await env.DB.prepare('SELECT steam_id, seed FROM cup_entries WHERE cup_id = ?').bind(c.id).all()).results.map((e) => [e.steam_id, e.seed]));
    const seedOf = (sid) => seeds.get(sid) || 999;
    const cur = ms.filter((x) => x.round === c.round);
    for (const x of cur.filter((y) => !y.winner && y.closes != null && now >= y.closes + LIMITS.graceMs)) {
      const d = decideMatch(await matchRows(env, x.event_id, now), x.a, x.b, seedOf);
      await env.DB.prepare('UPDATE cup_matches SET winner = ?, note = ? WHERE id = ? AND winner IS NULL').bind(d.winner, d.note, x.id).run();
      x.winner = d.winner;
      x.note = d.note;
    }
    if (!cur.length || cur.some((x) => !x.winner)) continue;
    if (c.round < rounds) {                               // the next round: the winners of slots 2k and 2k+1 meet
      const next = [];
      for (let k = 0; k < cur.length / 2; k++) {
        const [w1, w2] = [cur[2 * k].winner, cur[2 * k + 1].winner];
        next.push({ slot: k, a: seedOf(w1) <= seedOf(w2) ? w1 : w2, b: seedOf(w1) <= seedOf(w2) ? w2 : w1 });
      }
      await openRound(env, c, c.round + 1, rounds, next, now, opensAt);
      out.push({ cup: c.id, did: `round ${c.round + 1}` });
      continue;
    }
    // the final is decided: places, the pot by the split, notices
    const pl = places(ms, rounds, seedOf);
    const fees = new Map((await env.DB.prepare('SELECT steam_id, fee FROM cup_entries WHERE cup_id = ?').bind(c.id).all()).results
      .filter((e) => e.fee).map((e) => [e.steam_id, e.fee]));
    const pay = potPayouts(fees, pl.map(([sid]) => sid), JSON.parse(c.split));
    const names = new Map((await env.DB.prepare('SELECT steam_id, name FROM players WHERE steam_id IN (SELECT steam_id FROM cup_entries WHERE cup_id = ?)')
      .bind(c.id).all()).results.map((p) => [p.steam_id, p.name]));
    const ref = `cup:${c.id}`;
    const over = ["EXISTS (SELECT 1 FROM cups WHERE id = ? AND status = 'finished' AND settled = ?)", [c.id, now]];
    try {
      await env.DB.batch([
        env.DB.prepare("UPDATE cups SET status = 'finished', settled = ? WHERE id = ? AND status = 'running'").bind(now, c.id),
        ...pl.map(([sid, place]) => env.DB.prepare('UPDATE cup_entries SET place = ? WHERE cup_id = ? AND steam_id = ?').bind(place, c.id, sid)),
        ...[...pay].filter(([, amt]) => amt > 0).flatMap(([sid, amt]) => giveWhenStmts(env, sid, amt, 'cup-prize', ref, c.name, now, ...over)),
        ...pl.map(([sid, place]) => noticeStmt(env, sid, 'cup', `${c.name} is over: ${names.get(pl[0][0])} won it. You placed ${place}` +
          (pay.get(sid) ? `: ${pay.get(sid)} credits.` : '.'), ref, now, ...over)),
      ]);
    } catch (e) {
      if (!clash(e)) throw e;
    }
    out.push({ cup: c.id, did: 'finished', winner: pl[0] && pl[0][0] });
  }
  return out;
}
