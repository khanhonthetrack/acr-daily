// Cups: a knockout of 1V1s any driver can run. Its maker sets the size (4 to 128 drivers), the entry fee (credits; 0 =
// free), how the pot is shared (CUP.splits), what every match races (stages, car, rules: as a league event), when it
// starts and how long each round is open. Drivers join before the start (the fee is taken then; leaving before the
// start gives it back). At the start the entrants are seeded by their driver rating (src/rating.js; equal ratings in a
// random order) and the bracket is the smallest that holds them; a cup not full runs with byes for the top
// seeds; fewer than two: it is called off, fees back. Each round's matches open together, each for its two drivers
// only, driven from the app's LEAGUES view (src/leaguesapi.js holders): the lower total goes through; one finisher goes
// through; nobody finishing, or a dead heat: the higher seed. The cron (socialTick in index.js) opens the next round
// once a round is over, and shares the pot when the final is: places 1, 2, then the losing semi-finalists (3).
// Whatever the size, a round is opened, decided and paid with the same few bulk statements (json_each): the free plan
// allows 50 database queries a cron run, and a 128-driver cup's first round is 64 matches.
// Official cups are ACR Daily's own, made by the site's admin (adminCup: POST /api/admin/cup): run by "ACR Daily", listed
// first, rounds of up to two weeks, a banner, and a prize of ACR Daily's credits added to the pot.
//
//   GET  /api/cups                       {open, running, finished, mine}
//   GET  /api/cups/official              the official cups open or under way (the home page's strip)
//   GET  /api/cups/<id>                  a cup: its settings, entrants, bracket
//   POST /api/cups {name, about, size, fee, split, event, starts, roundHours}
//   POST /api/cups/<id>/join | leave | cancel (its maker, before the start)

import { stageParts } from './conditions.js';
import { clash, giveManyWhenStmts, giveWhenStmts, potPayouts, takeWhenStmts } from './credits.js';
import { bannerUrl, checkBanner, LIMITS, newLeagueId, text } from './leagues.js';
import { checkMatchSpec, holderRows, makeHolder, matchEventsStmt, storeBanner } from './leaguesapi.js';
import { cupMatchStmts, RATING, ratingOn } from './rating.js';
import { noticesStmt } from './social.js';

export const CUP = {
  sizes: [4, 8, 16, 32, 64, 128], maxFee: 1000, roundHours: [12, 24, 48, 72], perOwner: 3, startWithinDays: 30,
  splits: { all: { label: 'Winner takes all', shares: [100] }, two: { label: '70 / 30', shares: [70, 30] },
    four: { label: '60 / 30, 5 each to the losing semi-finalists', shares: [60, 30, 5, 5] } },
};
// ACR Daily's own cups: who runs them, and what only they may have
export const OFFICIAL = { owner: 'acr-daily', name: 'ACR Daily', maxRoundHours: 14 * 24, maxPrize: 100000, startWithinDays: 60 };
const HOUSE = '';                                         // ACR Daily's share of a pot (its prize): never paid to anyone

/** How long a round is open, said: "7 days", "36 hours". */
export const roundLength = (h) => (h % 24 === 0 && h >= 48 ? `${h / 24} days` : `${h} hours`);

/** A cup's pot by who put in what: the entry fees, and ACR Daily's prize (HOUSE). -> Map for potPayouts. */
export const potOf = (entries, prize) => new Map([...entries.filter((e) => e.fee).map((e) => [e.steam_id, e.fee]),
  ...(prize ? [[HOUSE, prize]] : [])]);

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

/** What a round is called, the last being the final: ... Round of 16, Quarter-final, Semi-final, Final. */
export function roundName(round, rounds) {
  return ['Final', 'Semi-final', 'Quarter-final'][rounds - round] || `Round of ${2 ** (rounds - round + 1)}`;
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
  const n = entrants != null ? entrants : c.entrants || 0;
  return { id: c.id, name: c.name, about: c.about, official: !!c.official,
    owner: c.official ? { steamId: null, name: OFFICIAL.name } : { steamId: c.owner, name: c.owner_name || 'a driver' }, size: c.size,
    fee: c.fee, prize: c.prize || 0, split: JSON.parse(c.split), starts: c.starts, roundHours: c.round_hours, status: c.status,
    round: c.round, entrants: n, pot: c.fee * n + (c.prize || 0), banner: bannerUrl(c.id, c.banner),
    rally: spec.rally, car: spec.car, carClass: spec.car_class, rules: spec.rules,
    stages: spec.stages.map((s) => ({ name: stageParts(s.track).stageName, day: s.day, weather: s.weather, time: s.time })) };
};
const LIST = `SELECT c.*, p.name AS owner_name, h.banner, (SELECT COUNT(*) FROM cup_entries e WHERE e.cup_id = c.id) AS entrants
  FROM cups c LEFT JOIN players p ON p.steam_id = c.owner LEFT JOIN leagues h ON h.id = c.id`;

export async function cupsApi(req, env, path, me, sameOrigin, now, { json, err }) {
  if (!path.startsWith('/api/cups')) return null;
  const post = req.method === 'POST';
  if (path === '/api/cups/official' && !post) {           // the home page's strip: one look, official cups first
    const { results } = await env.DB.prepare(`${LIST} WHERE c.official = 1 AND c.status IN ('open', 'running')
      ORDER BY c.starts LIMIT 3`).all();
    return json({ cups: results.map((c) => cupOut(c)) });
  }
  if (path === '/api/cups' && !post) {                    // (ACR Daily's own first)
    const [op, ru, fi] = await env.DB.batch([
      env.DB.prepare(`${LIST} WHERE c.status = 'open' ORDER BY c.official DESC, c.starts LIMIT 100`),
      env.DB.prepare(`${LIST} WHERE c.status = 'running' ORDER BY c.official DESC, c.starts LIMIT 100`),
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
      env.DB.prepare(`SELECT e.*, p.name, p.avatar, p.country, r.rating FROM cup_entries e JOIN players p ON p.steam_id = e.steam_id
        LEFT JOIN ratings r ON r.steam_id = e.steam_id WHERE e.cup_id = ? ORDER BY COALESCE(e.seed, 999), r.rating DESC, e.joined`).bind(c.id),
      env.DB.prepare('SELECT * FROM cup_matches WHERE cup_id = ? ORDER BY round, slot').bind(c.id),
    ]);
    const who = new Map(en.results.map((e) => [e.steam_id, { steamId: e.steam_id, name: e.name, avatar: e.avatar || null,
      country: e.country || null, seed: e.seed, place: e.place, rating: e.rating == null ? null : Math.round(e.rating) }]));
    const rounds = ma.results.length ? Math.log2(2 * ma.results.filter((x) => x.round === 1).length) : 0;
    // each match's totals as they stand (the standings of its event), the whole cup in one look
    const rows = ma.results.length ? await holderRows(env, c.id, now) : new Map();
    const totals = new Map(ma.results.filter((x) => x.event_id).map((x) => [x.id, rows.get(x.event_id)]));
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

/** ACR Daily's own cups, from the site's admin (POST /api/admin/cup; tools/admin.py cup): b = {name, about, size, fee,
 *  split, prize, event, starts, roundHours, banner (base64 PNG/JPEG/WebP, about 3:1)} makes one; with {id} it changes
 *  one not started yet (what is given: its fee only while nobody has joined); {id, cancel: true} calls it off.
 *  -> {id} / {cancelled} or {error, status} */
export async function adminCup(env, b, now) {
  const old = b.id ? await env.DB.prepare('SELECT * FROM cups WHERE id = ? AND official = 1').bind(String(b.id)).first() : null;
  if (b.id && !old) return { error: 'no official cup with that id', status: 404 };
  if (old && old.status !== 'open') return { error: `the cup is ${old.status}: it can't change now`, status: 409 };
  if (old && b.cancel) return callOff(env, old, now, `${old.name} was called off by ACR Daily`);
  const has = (k) => b[k] !== undefined && b[k] !== null;
  const was = (col, dflt) => (old ? old[col] : dflt);      // what isn't given: as it was (a new cup: the default)
  const name = has('name') ? text(b.name, LIMITS.name) : was('name', '');
  if (name.length < 3) return { error: 'the name: 3 to 60 characters' };
  const size = has('size') ? Number(b.size) : was('size'), fee = has('fee') ? Number(b.fee) : was('fee', 0);
  const prize = has('prize') ? Number(b.prize) : was('prize', 0), hours = has('roundHours') ? Number(b.roundHours) : was('round_hours');
  const starts = has('starts') ? Math.round(+b.starts) : was('starts');
  if (!CUP.sizes.includes(size)) return { error: `the size: ${CUP.sizes.join(', ')} drivers` };
  if (!Number.isInteger(fee) || fee < 0 || fee > CUP.maxFee) return { error: `the entry fee: 0 to ${CUP.maxFee} credits` };
  if ((fee || prize) && !env.CREDITS_FROM) return { error: 'fees and prizes need credits on', status: 409 };
  if (!Number.isInteger(prize) || prize < 0 || prize > OFFICIAL.maxPrize) return { error: `the prize: 0 to ${OFFICIAL.maxPrize} credits` };
  if (!Number.isInteger(hours) || hours < 1 || hours > OFFICIAL.maxRoundHours) return { error: `each round: 1 to ${OFFICIAL.maxRoundHours} hours` };
  if (!(starts > now && starts <= now + OFFICIAL.startWithinDays * 86400000)) return { error: `it starts within ${OFFICIAL.startWithinDays} days` };
  const split = has('split') ? CUP.splits[b.split] && CUP.splits[b.split].shares : old ? JSON.parse(old.split) : CUP.splits.all.shares;
  if (!split) return { error: `the split: ${Object.keys(CUP.splits).join(', ')}` };
  let spec = old ? JSON.parse(old.spec) : null;
  if (has('event')) {
    const c = await checkMatchSpec(env, { ...b.event, name, opens: now, closes: now + 2 * 3600000 }, now);
    if (c.error) return { error: c.error };
    const { opens, closes, ...rest } = c.value;
    spec = rest;
  }
  if (!spec) return { error: 'what every match races: event {rally, car | carClass, rules, stages}' };
  let banner = null;
  if (has('banner')) {
    const bytes = Uint8Array.from(atob(String(b.banner)), (ch) => ch.charCodeAt(0));
    const c = checkBanner(bytes);
    if (c.error) return { error: `the banner: ${c.error}`, status: c.status };
    banner = { bytes, type: c.value.type };
  }
  let id = old && old.id;
  if (old) {
    if (fee !== old.fee && (await env.DB.prepare('SELECT COUNT(*) AS n FROM cup_entries WHERE cup_id = ?').bind(id).first()).n) {
      return { error: 'drivers have joined: the entry fee can\'t change', status: 409 };
    }
    await env.DB.batch([
      env.DB.prepare(`UPDATE cups SET name = ?, about = ?, size = ?, fee = ?, prize = ?, split = ?, spec = ?, starts = ?, round_hours = ?
        WHERE id = ? AND status = 'open'`).bind(name, has('about') ? text(b.about, LIMITS.about) : old.about, size, fee, prize,
        JSON.stringify(split), JSON.stringify(spec), starts, hours, id),
      env.DB.prepare('UPDATE leagues SET name = ? WHERE id = ?').bind(name, id),
    ]);
  } else {
    for (let tries = 0; tries < 5 && !id; tries++) {
      const nid = newLeagueId();
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO cups (id, name, about, owner, size, fee, split, spec, starts, round_hours,
        status, created, official, prize) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, 1, ?)`).bind(nid, name, text(b.about, LIMITS.about),
        OFFICIAL.owner, size, fee, JSON.stringify(split), JSON.stringify(spec), starts, hours, now, prize).run();
      if (r.meta.changes) id = nid;
    }
    if (!id) return { error: 'try again', status: 503 };
    await makeHolder(env, { id, kind: 'cup', name, owner: OFFICIAL.owner }, now);
  }
  if (banner) await storeBanner(env, id, banner.bytes, banner.type, now);
  return { id };
}

/** A cup that won't run: every fee back, a notice to each entrant. en: its entries ({steam_id, fee}), when read already. */
async function callOff(env, c, now, why, en = null) {
  if (!en) en = (await env.DB.prepare('SELECT steam_id, fee FROM cup_entries WHERE cup_id = ?').bind(c.id).all()).results;
  const ref = `cup:${c.id}`;
  const off = ["EXISTS (SELECT 1 FROM cups WHERE id = ? AND status = 'cancelled' AND settled = ?)", [c.id, now]];
  await env.DB.batch([
    env.DB.prepare("UPDATE cups SET status = 'cancelled', settled = ? WHERE id = ? AND status = 'open'").bind(now, c.id),
    ...giveManyWhenStmts(env, en.filter((e) => e.fee).map((e) => ({ to: e.steam_id, amount: e.fee })), 'cup-refund', ref, 'called off', now, ...off),
    noticesStmt(env, 'cup', en.map((e) => ({ to: e.steam_id, body: why + (e.fee ? ': your entry fee is back.' : '.') })), ref, now, ...off),
  ]);
  return { cancelled: true, refunded: en.filter((e) => e.fee).length };
}

// ------------------------------------------------------------------ the cron

const shuffle = (a) => {
  const r = crypto.getRandomValues(new Uint32Array(a.length));
  for (let i = a.length - 1; i > 0; i--) { const j = r[i] % (i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
};

/** The seeds: by the driver rating (src/rating.js; someone not rated yet counts as RATING.start), equal ratings in a
 *  random order. entries: [{steam_id, rating}] -> steam ids, the top seed first. */
export const seedOrderOf = (entries) => shuffle(entries.slice())
  .sort((a, b) => (b.rating == null ? RATING.start : b.rating) - (a.rating == null ? RATING.start : a.rating)).map((e) => e.steam_id);

// how many cups a cron run starts, and how many under way it moves on (each a few queries: the rest wait 5 minutes)
const PER_RUN = { start: 2, running: 2 };

/** The statements opening a round, for the batch with the cup's change to that round (`cond` with `binds`: it went in):
 *  its matches (byes decided at once), each other match an event for its two drivers open from `opensAt`, a notice to
 *  each driver. pairs: [{slot, a, b}]; names: Map steamId -> name. The same four statements for 2 drivers or 128. */
function roundStmts(env, c, round, rounds, pairs, names, now, opensAt, cond, binds) {
  const rn = roundName(round, rounds), ref = `cup:${c.id}`, name = (sid) => names.get(sid) || 'a driver';
  const games = pairs.filter((p) => p.a && p.b), byes = pairs.filter((p) => !(p.a && p.b) && (p.a || p.b));
  const bye = (p) => !(p.a && p.b);
  return [
    env.DB.prepare(`INSERT OR IGNORE INTO cup_matches (cup_id, round, slot, a, b, winner, note)
      SELECT ?, ?, json_extract(j.value, '$.slot'), json_extract(j.value, '$.a'), json_extract(j.value, '$.b'),
        json_extract(j.value, '$.w'), json_extract(j.value, '$.note') FROM json_each(?) j WHERE ${cond}`)
      .bind(c.id, round, JSON.stringify(pairs.map((p) => ({ slot: p.slot, a: p.a, b: p.b, w: bye(p) ? p.a || p.b : null,
        note: bye(p) ? 'a bye' : null }))), ...binds),
    matchEventsStmt(env, c.id, JSON.parse(c.spec), games.map((p) => ({ name: `${rn}: ${name(p.a)} vs ${name(p.b)}`, only: [p.a, p.b] })),
      opensAt, now + c.round_hours * 3600000, now, cond, binds),
    // each match its event: two drivers meet once at most in a knockout, so the cup's event naming them is the one
    env.DB.prepare(`UPDATE cup_matches SET event_id = (SELECT e.id FROM league_events e WHERE e.league_id = cup_matches.cup_id
        AND e.only_ids = json_array(cup_matches.a, cup_matches.b))
      WHERE cup_id = ? AND round = ? AND event_id IS NULL AND a IS NOT NULL AND b IS NOT NULL`).bind(c.id, round),
    noticesStmt(env, 'cup', [
      ...byes.map((p) => ({ to: p.a || p.b, body: `${c.name}: a bye in ${rn.toLowerCase()}, you go through.` })),
      ...games.flatMap((p) => [[p.a, p.b], [p.b, p.a]].map(([x, y]) => ({ to: x,
        body: `${c.name}, ${rn.toLowerCase()}: you against ${name(y)}. Drive it from ACR Daily's LEAGUES view within ${roundLength(c.round_hours)}.` }))),
    ], ref, now, cond, binds),
  ];
}

/** The cron's part: cups due to start start (or are called off), finished rounds are decided and the next opened,
 *  a decided final shares the pot. opensAt: when the matches it opens open (the cron: now; a test running it as if
 *  later: the real time, so its drivers can start them). -> [{cup, did}] */
export async function cupsTick(env, now, opensAt = now) {
  const out = [];
  const { results: starting } = await env.DB.prepare("SELECT * FROM cups WHERE status = 'open' AND starts <= ? ORDER BY starts LIMIT ?")
    .bind(now, PER_RUN.start).all();
  for (const c of starting) {
    const { results: en } = await env.DB.prepare(`SELECT e.steam_id, e.fee, p.name, r.rating FROM cup_entries e LEFT JOIN players p
      ON p.steam_id = e.steam_id LEFT JOIN ratings r ON r.steam_id = e.steam_id WHERE e.cup_id = ?`).bind(c.id).all();
    if (en.length < 2) {
      await callOff(env, c, now, `${c.name} did not start: fewer than two drivers joined`, en);
      out.push({ cup: c.id, did: 'called off' });
      continue;
    }
    // the start, the seeds and round 1 together (round_at: this run's mark, so only what it started goes in)
    const seeded = seedOrderOf(en);
    const went = ['EXISTS (SELECT 1 FROM cups WHERE id = ? AND round = 1 AND round_at = ?)', [c.id, now]];
    await env.DB.batch([
      env.DB.prepare("UPDATE cups SET status = 'running', round = 1, round_at = ? WHERE id = ? AND status = 'open'").bind(now, c.id),
      env.DB.prepare(`UPDATE cup_entries SET seed = (SELECT j.key + 1 FROM json_each(?) j WHERE j.value = cup_entries.steam_id)
        WHERE cup_id = ? AND ${went[0]}`).bind(JSON.stringify(seeded), c.id, ...went[1]),
      ...roundStmts(env, c, 1, Math.log2(bracketSize(seeded.length)), firstRound(seeded), new Map(en.map((e) => [e.steam_id, e.name])),
        now, opensAt, ...went),
    ]);
    out.push({ cup: c.id, did: 'started' });
  }
  // only the cups with something to do: a match of their round closed (and its grace over) undecided, or the round all
  // decided (the next to open, or the pot to share)
  const { results: running } = await env.DB.prepare(`SELECT c.* FROM cups c WHERE c.status = 'running'
      AND EXISTS (SELECT 1 FROM cup_matches m WHERE m.cup_id = c.id AND m.round = c.round)
      AND (EXISTS (SELECT 1 FROM cup_matches m JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = c.id AND m.round = c.round
             AND m.winner IS NULL AND e.closes + ? <= ?)
        OR NOT EXISTS (SELECT 1 FROM cup_matches m WHERE m.cup_id = c.id AND m.round = c.round AND m.winner IS NULL))
    ORDER BY c.starts LIMIT ?`).bind(LIMITS.graceMs, now, PER_RUN.running).all();
  for (const c of running) {
    const [{ results: ms }, { results: en }] = await env.DB.batch([
      env.DB.prepare('SELECT m.*, e.closes FROM cup_matches m LEFT JOIN league_events e ON e.id = m.event_id WHERE m.cup_id = ? ORDER BY m.round, m.slot')
        .bind(c.id),
      env.DB.prepare('SELECT e.steam_id, e.seed, e.fee, p.name FROM cup_entries e LEFT JOIN players p ON p.steam_id = e.steam_id WHERE e.cup_id = ?')
        .bind(c.id),
    ]);
    const rounds = Math.log2(2 * ms.filter((x) => x.round === 1).length);
    const seeds = new Map(en.map((e) => [e.steam_id, e.seed])), names = new Map(en.map((e) => [e.steam_id, e.name]));
    const seedOf = (sid) => seeds.get(sid) || 999;
    const cur = ms.filter((x) => x.round === c.round);
    const due = cur.filter((y) => !y.winner && y.closes != null && now >= y.closes + LIMITS.graceMs);
    if (due.length) {                                     // the round's closed matches, all decided in one go
      const rows = await holderRows(env, c.id, now, due.map((x) => x.event_id));
      const ds = due.map((x) => ({ id: x.id, a: x.a, b: x.b, ...decideMatch(rows.get(x.event_id) || [], x.a, x.b, seedOf) }));
      // the results, and (RATING_FROM) the drivers' ratings, together: a match is rated once (rating_done)
      try {
        await env.DB.batch([
          env.DB.prepare(`UPDATE cup_matches SET
              winner = (SELECT json_extract(j.value, '$.winner') FROM json_each(?1) j WHERE json_extract(j.value, '$.id') = cup_matches.id),
              note = (SELECT json_extract(j.value, '$.note') FROM json_each(?1) j WHERE json_extract(j.value, '$.id') = cup_matches.id)
            WHERE id IN (SELECT json_extract(value, '$.id') FROM json_each(?1)) AND winner IS NULL`).bind(JSON.stringify(ds)),
          ...(ratingOn(env, new Date(now).toISOString().slice(0, 10)) ? await cupMatchStmts(env, ds, now) : []),
        ]);
      } catch (e) {
        if (!clash(e)) throw e;
        continue;                                         // (another run decided them: the next one goes on)
      }
      for (const d of ds) Object.assign(due.find((x) => x.id === d.id), { winner: d.winner, note: d.note });
    }
    if (!cur.length || cur.some((x) => !x.winner)) continue;
    if (c.round < rounds) {                               // the next round: the winners of slots 2k and 2k+1 meet
      const next = [];
      for (let k = 0; k < cur.length / 2; k++) {
        const [w1, w2] = [cur[2 * k].winner, cur[2 * k + 1].winner];
        next.push({ slot: k, a: seedOf(w1) <= seedOf(w2) ? w1 : w2, b: seedOf(w1) <= seedOf(w2) ? w2 : w1 });
      }
      const went = ['EXISTS (SELECT 1 FROM cups WHERE id = ? AND round = ? AND round_at = ?)', [c.id, c.round + 1, now]];
      await env.DB.batch([
        env.DB.prepare('UPDATE cups SET round = ?, round_at = ? WHERE id = ? AND round = ?').bind(c.round + 1, now, c.id, c.round),
        ...roundStmts(env, c, c.round + 1, rounds, next, names, now, opensAt, ...went),
      ]);
      out.push({ cup: c.id, did: `round ${c.round + 1}` });
      continue;
    }
    // the final is decided: places, the pot (the fees and ACR Daily's prize) by the split, notices
    const pl = places(ms, rounds, seedOf);
    const pay = potPayouts(potOf(en, c.prize), pl.map(([sid]) => sid), JSON.parse(c.split));
    pay.delete(HOUSE);
    const ref = `cup:${c.id}`;
    const over = ["EXISTS (SELECT 1 FROM cups WHERE id = ? AND status = 'finished' AND settled = ?)", [c.id, now]];
    try {
      await env.DB.batch([
        env.DB.prepare("UPDATE cups SET status = 'finished', settled = ? WHERE id = ? AND status = 'running'").bind(now, c.id),
        env.DB.prepare(`UPDATE cup_entries SET place = (SELECT json_extract(j.value, '$[1]') FROM json_each(?1) j
            WHERE json_extract(j.value, '$[0]') = cup_entries.steam_id)
          WHERE cup_id = ?2 AND steam_id IN (SELECT json_extract(value, '$[0]') FROM json_each(?1))`).bind(JSON.stringify(pl), c.id),
        ...giveManyWhenStmts(env, [...pay].filter(([, amt]) => amt > 0).map(([to, amount]) => ({ to, amount })), 'cup-prize', ref, c.name, now, ...over),
        noticesStmt(env, 'cup', pl.map(([sid, place]) => ({ to: sid, body: `${c.name} is over: ${names.get(pl[0][0])} won it. You placed ${place}` +
          (pay.get(sid) ? `: ${pay.get(sid)} credits.` : '.') })), ref, now, ...over),
      ]);
    } catch (e) {
      if (!clash(e)) throw e;
    }
    out.push({ cup: c.id, did: 'finished', winner: pl[0] && pl[0][0] });
  }
  return out;
}

