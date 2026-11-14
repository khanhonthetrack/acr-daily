// The weekly time trial (TIME_TRIAL_FROM in wrangler.toml, the first week; empty = off): a hotlap mode. Every week,
// Monday 00:00 UTC to the next Monday, has two stages (TT1 and TT2), each from the dailies' pool with its own car,
// conditions and board. Each is a one-stage Rally Weekend in the game, set up by the app's DRIVE with the dailies' rules
// (src/weekend.js), and timed by the game: its stage time + penalty. Drive them as often as you like all week: each
// driver's best time is the one on the board.
//
// TT1 (TT.freeSlot) is free, as the free daily is: no entry fee and no prizes, every signed-in driver's runs count.
// Entry to TT2 (credits on for the week, src/credits.js): TT.fee, paid before the first run on it (DRIVE asks; the
// website's Enter button too). Runs from a driver who hasn't entered, or that started before the entry, are refused.
// Once the week is over (TT.settleAfter later, so the last runs are in), the pot (every entry fee) is paid out: the
// top half of the drivers with a time (rounded up) get their fee back plus a share of everyone else's fees, the shares
// rising by place in equal steps (the last place paid 1 share, the one above 2... P1 as many as there are places
// paid: ttPayouts). Entrants without a time get their fee back. No credits are made: the fees only move between the
// drivers. Credits off: both free, no prizes. (Fees paid on TT1 before it went free come back when its week settles.)
//
// Only finished runs are sent (the app keeps DNFs and restarts to itself). Each driver's best run keeps its trace
// (the app's live gap and ghosts against the leader); once the week is settled only the TT.keepTraces fastest do.
// A live map as the dailies': while on a stage the app sends where it is every liveSendS (tt_live), and the /tt page
// draws everyone on each stage (src/stagemap.js), the app's stage strip the others on mine. On a stage with an entry
// fee only entrants show. Not rated (src/rating.js: easy to farm with as many runs as one likes).
//
// API:  GET  /api/tt?week=&lite=1        the week's two stages (each with its fee; its route unless lite), the pots,
//                                        my entries
//       GET  /api/tt/board?week=&slot=   a stage's board: each driver's best run, with the prize it pays now
//       GET  /api/tt/runs/:id/trace      a driver's best run's trace (the app's ghost of the leader)
//       POST /api/tt/enter {slot}        enter this week's TT<slot> (the fee is taken; a free stage: nothing to pay)
//       POST /api/tt/runs                a finished run (the app's result with the game's official one)
//       GET  /api/tt/live?week=&slot=    who is on a stage right now (slot=all: both); POST: the app's position
// Page: /tt (src/timetrialpage.js). The cron: ttTick (the week's stages fixed as it starts, finished weeks settled).

import { CARS, carByName } from './cars.js';
import { describe, pickConditions, stageParts } from './conditions.js';
import { menuName } from './stages.js';
import { WEEKEND_RULES } from './weekend.js';
import { routeInfo, validateRun } from './validate.js';
import { timesAt } from './realism.js';
import { cached, dropCached } from './cache.js';
import { getTrace, packTrace } from './traces.js';
import { LOOK_COLS, lookJoin, lookOfRow, unlooked } from './shop.js';
import { balanceOf, clash, creditsOn, giveManyWhenStmts, takeWhenStmts } from './credits.js';
import { noticesStmt } from './social.js';
import { APP_FLAG, INVESTIGATING, reinstatedTime } from './apptime.js';

export const TT = {
  stages: 2,                    // TT1 and TT2
  fee: 200,                     // credits, the entry of a stage that has one (credits on)
  freeSlot: 1,                  // TT1 is free: no entry fee, no prizes (as SS1, the free daily)
  maxRuns: 1000,                // finished runs a driver sends a stage a week (a cap for the database, not a rule)
  lateMs: 30 * 60000,           // a run finished just before the close may arrive a bit after (its official result)
  settleAfterMs: 60 * 60000,    // the week settles an hour after it closes
  keepTraces: 3,                // a settled week's stage keeps the traces of its fastest drivers only
};
const DAY = 86400000, WEEK = 7 * DAY;
const MAX_BODY = 2_000_000;
const ENTRY_SLACK_MS = 2 * 60000;   // the PC's clock against the server's, for a start just after entering
const SETTLE_WEEKS_BACK = 4;        // the weeks the cron looks at (a cron that was down)
const LIVE_STALE_MS = 15000;        // as the dailies' (index.js): a driver leaves the map 15 s after their last update,
const LIVE_KEEP_DONE_MS = 60000;    // a finish or a DNF stays on it for a minute

const dayStr = (ms) => new Date(ms).toISOString().slice(0, 10);
export const weekStart = (week) => Date.parse(week + 'T00:00:00Z');
/** The week (its Monday, YYYY-MM-DD) of a moment (ms). 1970-01-01 was a Thursday: day 4 was a Monday. */
export function weekOf(ms) {
  const d = Math.floor(ms / DAY);
  return dayStr((d - (((d - 4) % 7) + 7) % 7) * DAY);
}
/** A week's id: a Monday as YYYY-MM-DD. */
export const isWeek = (w) => /^\d{4}-\d{2}-\d{2}$/.test(String(w)) && Number.isFinite(weekStart(w)) && weekOf(weekStart(w)) === w;
export const shiftWeek = (week, n) => dayStr(weekStart(week) + n * WEEK);
/** The ISO week number of a week ({year, no}: 2026-11-09 is week 46 of 2026), for its name. */
export function isoWeek(week) {
  const th = new Date(weekStart(week) + 3 * DAY);   // the week's Thursday is in its ISO year
  return { year: th.getUTCFullYear(), no: Math.floor((th.getTime() - Date.UTC(th.getUTCFullYear(), 0, 1)) / WEEK) + 1 };
}
/** The first week with a time trial (the week TIME_TRIAL_FROM is in), or null when off. */
export function firstWeek(env) {
  const t = Date.parse(String((env && env.TIME_TRIAL_FROM) || '') + 'T00:00:00Z');
  return Number.isFinite(t) ? weekOf(t) : null;
}
/** That week has a time trial. */
export const ttOn = (env, week) => { const f = firstWeek(env); return !!f && week >= f; };
/** The entry fee of a week's stage: TT.fee with credits on, else free; TT.freeSlot is always free. */
export const feeOf = (env, week, slot) => (creditsOn(env, week) && slot !== TT.freeSlot ? TT.fee : 0);
/** "tt:2026-11-09/2" (a stage's id, the app's challengeId) -> {week, slot}, or null. */
export function parseTtId(id) {
  const m = String(id || '').match(/^tt:(\d{4}-\d{2}-\d{2})\/([12])$/);
  return m && isWeek(m[1]) ? { week: m[1], slot: +m[2] } : null;
}

/** A stage's prizes. field: the steamIds of the drivers with a time, fastest first; fees: Map steamId -> the fee they
 *  paid (every entrant). The top half of the field (rounded up) get their fee back plus a share of the other fees, in
 *  equal steps by place: with k places paid, P1 k shares, P2 k - 1 ... the last 1 (the rounding to P1). An entrant
 *  without a time gets the fee back; one with a time outside the top half loses it.
 *  -> Map steamId -> credits paid back (0: lost), every entrant. */
export function ttPayouts(field, fees) {
  const out = new Map([...fees.keys()].map((s) => [s, 0]));
  const timed = field.filter((s) => fees.has(s));
  const inField = new Set(timed);
  for (const [s, fee] of fees) if (!inField.has(s)) out.set(s, fee);   // no time: the fee back
  if (!timed.length) return out;
  const k = Math.ceil(timed.length / 2), paid = timed.slice(0, k);
  const rest = timed.slice(k).reduce((a, s) => a + fees.get(s), 0);     // the fees of those outside the top half
  const units = (k * (k + 1)) / 2;
  let given = 0;
  paid.forEach((s, i) => {
    const share = Math.floor((rest * (k - i)) / units);
    out.set(s, fees.get(s) + share);
    given += share;
  });
  out.set(paid[0], out.get(paid[0]) + rest - given);
  return out;
}

// ------------------------------------------------------------------ the week's stages

/** The week's two stages, picked from the dailies' pool (index.js dailyPool: {byTrack: track -> its fixed cars,
 *  tracks: in rotation order}): the rotation moves two stages on each week, preferring stages none of that week's
 *  dailies is on (dailies: [{track, car}]) and, for TT2, another rally than TT1's; never the same stage twice, nor a
 *  car a daily of that week drives on the same stage (the app would take one run for both). fixed: the week's rows
 *  already stored (kept). hash: index.js hashStr. -> [{slot, track, car, weather, time}] */
export function pickWeek({ byTrack, tracks }, week, dailies, fixed, hash) {
  const n = tracks.length, w = Math.floor(weekStart(week) / WEEK), picks = [];
  const dailyTracks = new Set(dailies.map((d) => d.track));
  const dailyPairs = new Set(dailies.map((d) => d.track + '|' + d.car));
  for (let slot = 1; slot <= TT.stages; slot++) {
    const done = fixed.find((r) => r.slot === slot);
    if (done) { picks.push(done); continue; }
    const others = fixed.concat(picks);
    const taken = new Set(others.map((p) => p.track));
    const rallies = new Set(others.map((p) => stageParts(p.track).rally));
    const order = Array.from({ length: n }, (_, k) => tracks[(w * TT.stages + slot - 1 + k) % n]);
    const prefs = [(t) => !taken.has(t) && !dailyTracks.has(t) && !rallies.has(stageParts(t).rally),
      (t) => !taken.has(t) && !dailyTracks.has(t), (t) => !taken.has(t)];
    let track = null;
    for (const ok of prefs) if (!track) track = order.find(ok) || null;
    if (!track) break;                                   // fewer stages in the pool than time trial stages
    const fixedCars = byTrack.get(track) || [];
    let car;
    if (fixedCars.length) car = fixedCars[hash(week + '|tt|' + slot) % fixedCars.length];
    else {
      // from a hashed start: a car neither TT stage nor a daily on this stage has, else one no daily has here
      const cars = new Set(others.map((p) => p.car)), k0 = hash(week + '|tt|' + slot + '|' + track) % CARS.length;
      const round = Array.from({ length: CARS.length }, (_, i) => CARS[(k0 + i) % CARS.length].name);
      const free = (c) => !dailyPairs.has(track + '|' + c);
      car = round.find((c) => free(c) && !cars.has(c)) || round.find(free) || round[0];
    }
    const cond = pickConditions(track, hash(week + '|ttw|' + slot), hash(week + '|ttt|' + slot));
    picks.push({ slot, track, car, weather: cond.weather, time: cond.time });
  }
  return picks;
}

/** The week's stages as stored ([{slot, track, car, weather, time}]); this week's are picked and stored the first
 *  time they are asked for (the cron does it as the week starts). Past weeks keep what they had; a week ahead is
 *  never picked. deps: {pool, hash} (index.js). */
export async function ttPicks(env, week, deps, now = Date.now()) {
  const read = async () => (await env.DB.prepare('SELECT slot, track, car, weather, time FROM tt_schedule WHERE week = ? ORDER BY slot')
    .bind(week).all()).results;
  const rows = await read();
  if (rows.length >= TT.stages || week !== weekOf(now) || !ttOn(env, week)) return rows;
  const { results: dailies } = await env.DB.prepare('SELECT track, car FROM schedule WHERE date BETWEEN ? AND ?')
    .bind(week, dayStr(weekStart(week) + 6 * DAY)).all();
  const picks = pickWeek(await deps.pool(), week, dailies, rows, deps.hash).filter((p) => !rows.some((r) => r.slot === p.slot));
  if (!picks.length) return rows;
  await env.DB.prepare(`INSERT OR IGNORE INTO tt_schedule (week, slot, track, car, weather, time)
    SELECT ?, json_extract(value, '$.slot'), json_extract(value, '$.track'), json_extract(value, '$.car'),
      json_extract(value, '$.weather'), json_extract(value, '$.time') FROM json_each(?)`).bind(week, JSON.stringify(picks)).run();
  return read();
}

/** A stage as the app and the website take it: what a daily's challenge has (index.js challengeFor), for the time
 *  trial. route: its routes row ({points?, length, stage_id}). */
export function stageOut(env, week, p, route, deps) {
  const car = carByName(p.car), parts = stageParts(p.track), start = weekStart(week);
  return {
    id: `tt:${week}/${p.slot}`, kind: 'tt', week, slot: p.slot,
    track: p.track, ...parts,
    menuName: (route && menuName(route.stage_id)) || parts.stageName,
    stageId: route ? route.stage_id || null : null,
    car: p.car, carId: car ? car.id : null, carClass: car ? car.cls : null,
    carAliases: car ? [car.telemetry, ...(car.aliases || [])].filter(Boolean) : [],
    ...describe(p.weather, p.time),
    mode: 'weekend', weekend: WEEKEND_RULES, penaltyMs: 0,
    splits: deps.splits, timing: deps.timing,
    startsAt: start, endsAt: start + WEEK,
    lengthM: route ? Math.round(route.length) : null,
    fee: feeOf(env, week, p.slot),
    ...(route && route.points ? { route: JSON.parse(route.points) } : {}),
  };
}

/** One stage of a week (with its route), or null. */
export async function ttStage(env, week, slot, deps, now = Date.now()) {
  const p = (await ttPicks(env, week, deps, now)).find((r) => r.slot === slot);
  if (!p) return null;
  const route = await env.DB.prepare('SELECT points, length, stage_id FROM routes WHERE track = ?').bind(p.track).first();
  return stageOut(env, week, p, route, deps);
}

// ------------------------------------------------------------------ the boards

export const boardKey = (week, slot) => `ttboard:${week}/${slot}`;

/** A stage's board, built: each driver's best finished run (ties: who set it first), banned drivers left out, with
 *  how many runs they finished and, on a stage with an entry fee (prizes), the credits their place pays: now (as the
 *  pot stands) or, once the week is settled, what it paid (a free stage: prize null). -> {week, slot, entries: [{rank,
 *  runId, steamId, name, avatar, country, totalMs, clockMs, gapMs, resets, splits, runs, created, prize, look?}],
 *  stats: {drivers, runs, entrants, pot, paidPlaces}, fee, credits, prizes, settled} */
export async function buildBoard(env, week, slot) {
  const [best, ents, done] = await env.DB.batch([
    env.DB.prepare(`SELECT b.id AS runId, b.steam_id AS steamId, p.name, p.avatar, p.country, b.total_ms AS totalMs,
        b.clock_ms AS clockMs, b.resets, b.created, b.splits, b.runs, b.reason, ${LOOK_COLS}
      FROM (SELECT id, steam_id, total_ms, clock_ms, resets, created, splits, reason,
                   ROW_NUMBER() OVER (PARTITION BY steam_id ORDER BY total_ms, created, id) AS n,
                   COUNT(*) OVER (PARTITION BY steam_id) AS runs
              FROM tt_runs WHERE week = ? AND slot = ? AND status = 'finished') b
      JOIN players p ON p.steam_id = b.steam_id ${lookJoin('b.steam_id')}
      WHERE b.n = 1 AND p.banned = 0 ORDER BY b.total_ms, b.created, b.id`).bind(week, slot),
    env.DB.prepare('SELECT steam_id, fee, paid FROM tt_entries WHERE week = ? AND slot = ? ORDER BY created').bind(week, slot),
    env.DB.prepare('SELECT settled FROM tt_weeks WHERE week = ? AND slot = ?').bind(week, slot),
  ]);
  const settled = done.results[0] ? done.results[0].settled : null;
  const fees = new Map(ents.results.map((e) => [e.steam_id, e.fee]));
  const fee = feeOf(env, week, slot), prizes = fee > 0;
  const pay = !prizes ? null : settled ? new Map(ents.results.map((e) => [e.steam_id, e.paid || 0]))
    : ttPayouts(best.results.map((r) => r.steamId), fees);
  const lead = best.results.length ? best.results[0].totalMs : null;
  const entries = best.results.map((r, i) => {
    const look = lookOfRow(r), { splits, reason, ...e } = unlooked(r);
    return { ...e, rank: i + 1, gapMs: r.totalMs - lead, splits: splits ? JSON.parse(splits) : null,
      prize: pay ? pay.get(r.steamId) || 0 : null, ...(look ? { look } : {}) };
  });
  return {
    week, slot, entries, fee, credits: creditsOn(env, week), prizes, settled,
    stats: { drivers: entries.length, runs: entries.reduce((a, e) => a + e.runs, 0), entrants: fees.size,
      pot: [...fees.values()].reduce((a, x) => a + x, 0), paidPlaces: Math.ceil(entries.length / 2) },
  };
}

/** A stage's board from its kept copy (src/cache.js): a new run or entry drops it; kept 5 minutes until the week is
 *  settled, a month after. */
export function ttBoard(env, week, slot, now = Date.now()) {
  const open = now < weekStart(week) + WEEK + TT.settleAfterMs + DAY;
  return cached(env, boardKey(week, slot), open ? 5 * 60000 : 30 * DAY, () => buildBoard(env, week, slot));
}

// ------------------------------------------------------------------ settling a week (cron)

/** A finished week's stage settled, once (tt_weeks, in the same batch as the payouts): the prizes and the refunds
 *  paid, each driver told in the inbox, the traces trimmed to the fastest few. A free stage pays no prizes: a fee paid
 *  on it (before it went free) comes back. -> {week, slot, drivers, paid} or null (settled already). */
export async function settleStage(env, week, slot, now) {
  if (await env.DB.prepare('SELECT 1 AS x FROM tt_weeks WHERE week = ? AND slot = ?').bind(week, slot).first()) return null;
  const b = await buildBoard(env, week, slot);
  const { results: ents } = await env.DB.prepare('SELECT steam_id, fee FROM tt_entries WHERE week = ? AND slot = ? ORDER BY created')
    .bind(week, slot).all();
  const st = await env.DB.prepare(`SELECT t.track, r.stage_id FROM tt_schedule t LEFT JOIN routes r ON r.track = t.track
    WHERE t.week = ? AND t.slot = ?`).bind(week, slot).first();
  const stage = st ? menuName(st.stage_id) || stageParts(st.track).stageName : '';
  const fees = new Map(ents.map((e) => [e.steam_id, e.fee]));
  const free = !b.prizes;                                // every fee back, no prizes
  const pay = free ? new Map(fees) : ttPayouts(b.entries.map((e) => e.steamId), fees);
  const ref = `tt:${week}`, label = `Time trial TT${slot}${stage ? ` (${stage})` : ''}, week ${isoWeek(week).no}`;
  const placed = new Map(b.entries.map((e) => [e.steamId, e]));
  const prizes = [], refunds = [], notes = [];
  for (const [to, amount] of pay) if (amount) (placed.has(to) && !free ? prizes : refunds).push({ to, amount });
  const time = (ms) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
  const back = (n) => `TT${slot} is free now: your entry fee of ${n} credits is back.`;
  for (const e of b.entries) {
    const won = pay.get(e.steamId);
    notes.push({ to: e.steamId, body: `${label} is over: you placed P${e.rank} of ${b.entries.length} (${time(e.totalMs)}, ` +
      `${e.runs} run${e.runs === 1 ? '' : 's'})` + (!fees.has(e.steamId) ? '.' : free ? `. ${back(won)}`
        : won ? `. Prize: ${won} credits.` : '. Outside the top half: no prize this time.') });
  }
  for (const r of refunds) {
    if (!placed.has(r.to)) notes.push({ to: r.to, body: `${label} is over. ` + (free ? back(r.amount) : `You set no time: your entry fee of ${r.amount} credits is back.`) });
  }
  const top = b.entries.slice(0, TT.keepTraces).map((e) => e.runId);
  const stmts = [
    env.DB.prepare('INSERT INTO tt_weeks (week, slot, settled) VALUES (?, ?, ?)').bind(week, slot, now),
    ...(prizes.length ? giveManyWhenStmts(env, prizes, 'tt-prize', `tt:${week}/${slot}`, null, now, '1', []) : []),
    ...(refunds.length ? giveManyWhenStmts(env, refunds, 'tt-refund', `tt:${week}/${slot}`, free ? 'the stage went free' : 'no time set', now, '1', []) : []),
    env.DB.prepare(`UPDATE tt_entries SET settled = ?1, paid = COALESCE((SELECT json_extract(j.value, '$.n') FROM json_each(?2) j
        WHERE json_extract(j.value, '$.to') = tt_entries.steam_id), 0) WHERE week = ?3 AND slot = ?4`)
      .bind(now, JSON.stringify([...pay].map(([to, n]) => ({ to, n }))), week, slot),
    env.DB.prepare(`UPDATE tt_runs SET trace = NULL WHERE week = ? AND slot = ? AND trace IS NOT NULL
        AND id NOT IN (SELECT value FROM json_each(?))`).bind(week, slot, JSON.stringify(top)),
    ...(notes.length ? [noticesStmt(env, 'tt', notes, ref, now)] : []),
  ];
  try {
    await env.DB.batch(stmts);
  } catch (e) {
    if (clash(e)) return null;                           // settled meanwhile
    throw e;
  }
  await dropCached(env, [boardKey(week, slot)]);
  return { week, slot, drivers: b.entries.length, paid: Object.fromEntries([...pay].filter(([, n]) => n)) };
}

/** The cron (every 5 minutes): this week's stages fixed (stored) as it starts; the weeks before settled once they are
 *  over (TT.settleAfterMs after the close). deps: {pool, hash}. -> {settled: [...]} */
export async function ttTick(env, now, deps) {
  if (!firstWeek(env)) return { settled: [] };
  const cur = weekOf(now);
  if (ttOn(env, cur)) await ttPicks(env, cur, deps, now);
  const weeks = [];
  for (let k = SETTLE_WEEKS_BACK; k >= 1; k--) {
    const w = shiftWeek(cur, -k);
    if (ttOn(env, w) && now >= weekStart(w) + WEEK + TT.settleAfterMs) weeks.push(w);
  }
  if (!weeks.length) return { settled: [] };
  const { results } = await env.DB.prepare('SELECT week, slot FROM tt_weeks WHERE week >= ?').bind(weeks[0]).all();
  const done = new Set(results.map((r) => `${r.week}/${r.slot}`));
  const settled = [];
  for (const w of weeks) {
    for (let slot = 1; slot <= TT.stages; slot++) {
      if (done.has(`${w}/${slot}`)) continue;
      const r = await settleStage(env, w, slot, now);
      if (r) settled.push(r);
    }
  }
  return { settled };
}

// ------------------------------------------------------------------ entering, runs

/** Enter this week's TT<slot>: the fee taken, in the same batch as the entry row (only when the driver has the
 *  credits). A free stage (TT.freeSlot, or credits off) needs no entry: {entered, free}. */
async function enter(env, me, b, now, deps) {
  const { json, err } = deps;
  const week = weekOf(now), slot = +b.slot;
  if (b.week && b.week !== week) return err('only this week\'s time trial takes entries', 409);
  if (![1, 2].includes(slot)) return err('slot: 1 or 2');
  if (!ttOn(env, week)) return err('no time trial this week', 409);
  if (!(await ttPicks(env, week, deps, now)).some((p) => p.slot === slot)) return err('no stage TT' + slot + ' this week', 409);
  const fee = feeOf(env, week, slot);
  if (!fee) return json({ entered: true, free: true, fee: 0, week, slot });
  const pot = async () => env.DB.prepare('SELECT COUNT(*) AS entrants, COALESCE(SUM(fee), 0) AS pot FROM tt_entries WHERE week = ? AND slot = ?')
    .bind(week, slot).first();
  const had = await env.DB.prepare('SELECT created FROM tt_entries WHERE week = ? AND slot = ? AND steam_id = ?').bind(week, slot, me.steam_id).first();
  if (had) return json({ entered: true, already: true, fee, week, slot, ...(await pot()), balance: (await balanceOf(env, me.steam_id)).balance });
  await env.DB.batch([
    env.DB.prepare(`INSERT OR IGNORE INTO tt_entries (week, slot, steam_id, fee, created) SELECT ?1, ?2, ?3, ?4, ?5
      WHERE (SELECT balance FROM credits WHERE steam_id = ?3) >= ?4`).bind(week, slot, me.steam_id, fee, now),
    ...takeWhenStmts(env, me.steam_id, fee, 'tt-fee', `tt:${week}/${slot}`, null, now,
      'EXISTS (SELECT 1 FROM tt_entries WHERE week = ? AND slot = ? AND steam_id = ? AND created = ?)', [week, slot, me.steam_id, now]),
  ]);
  const mine = await env.DB.prepare('SELECT created FROM tt_entries WHERE week = ? AND slot = ? AND steam_id = ?').bind(week, slot, me.steam_id).first();
  const balance = (await balanceOf(env, me.steam_id)).balance;
  if (!mine) return err(`the entry fee is ${fee} credits: you have ${balance}`, 402);
  await dropCached(env, [boardKey(week, slot)]);
  return json({ entered: true, ...(mine.created !== now ? { already: true } : {}), fee, week, slot, ...(await pot()), balance });
}

/** A finished run on a time trial stage: on the board if it is the driver's best. Refused ("invalid": the app drops
 *  it from its queue) when it isn't the stage or car, wasn't finished, has no official result, came from a driver
 *  who hasn't entered a stage with a fee or started before the entry, or started after the close. */
async function submit(req, env, me, now, deps) {
  const { json, err } = deps;
  if (+(req.headers.get('Content-Length') || 0) > MAX_BODY) return err('run too big', 413);
  let sub;
  try { sub = await req.json(); } catch { return err('bad json'); }
  const id = parseTtId(sub && sub.challengeId);
  if (!id) return err('invalid run: not a time trial stage');
  const { week, slot } = id, cur = weekOf(now);
  if (week !== cur && !(week === weekOf(now - TT.lateMs) && now - weekStart(cur) < TT.lateMs)) {
    return err('too late: that time trial is over', 409);
  }
  const old = deps.tooOld(req, sub);
  if (old) return old;
  if (!ttOn(env, week)) return err('invalid run: no time trial that week', 409);
  const started = deps.startedMs(sub.startedAt, now);
  if (started >= weekStart(week) + WEEK) return err('invalid run: it started after the time trial closed', 409);
  if (started < weekStart(week) - ENTRY_SLACK_MS) return err('invalid run: it started before the time trial opened', 409);
  const ch = await ttStage(env, week, slot, deps, now);
  if (!ch || !ch.route) return err('no time trial stage', 409);
  if (sub.track !== ch.track || sub.car !== ch.car) return err('invalid: not the time trial\'s stage/car', 422);
  if (ch.fee) {
    const e = await env.DB.prepare('SELECT created FROM tt_entries WHERE week = ? AND slot = ? AND steam_id = ?').bind(week, slot, me.steam_id).first();
    if (!e) return err(`invalid run: TT${slot} takes runs from drivers who entered (${ch.fee} credits). Enter first: DRIVE in ACR Daily asks`, 402);
    if (started < e.created - ENTRY_SLACK_MS) return err('invalid run: it started before your entry (the runs after it count)', 409);
  }
  if (sub.status !== 'finished') return err('invalid: only finished runs go on the time trial board', 422);
  const mine = await env.DB.prepare(`SELECT COUNT(*) AS n, MIN(total_ms) AS best FROM tt_runs
    WHERE week = ? AND slot = ? AND steam_id = ? AND status = 'finished'`).bind(week, slot, me.steam_id).first();
  if (mine.n >= TT.maxRuns) return err('too many runs on this stage this week', 429);
  const v = validateRun(sub, routeInfo(ch.route), 0, true);
  if (!v.ok) return err('invalid: ' + v.reason, 422);
  if (v.status !== 'finished') {   // a lost result with respawns (src/apptime.js): kept off the board for the admin
    await env.DB.prepare(`INSERT INTO tt_runs (week, slot, steam_id, track, car, status, reason, clock_ms, resets, total_ms,
        app_version, started_at, created) VALUES (?, ?, ?, ?, ?, 'rejected', ?, ?, ?, NULL, ?, ?, ?)`)
      .bind(week, slot, me.steam_id, ch.track, ch.car, v.reason, v.clockMs, v.resets,
        String(sub.appVersion || '').slice(0, 20), started, now).run();
    return err('invalid: ' + v.reason, 422);                             // ("invalid": the app drops it)
  }
  const best = mine.best == null || v.totalMs < mine.best;
  // the app's time for a result the game lost (src/apptime.js): taken as it is, marked
  const note = v.appTime ? APP_FLAG : null, appTime = v.appTime ? { counted: best } : null;
  const splits = v.trace.length ? timesAt(v.trace, { points: ch.route }, deps.splits, 0) : null;
  const trace = best && v.trace.length ? await packTrace(JSON.stringify(v.trace)) : null;
  const res = await env.DB.prepare(`INSERT INTO tt_runs (week, slot, steam_id, track, car, status, reason, clock_ms, resets,
      total_ms, splits, app_version, started_at, created, trace) VALUES (?, ?, ?, ?, ?, 'finished', ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(week, slot, me.steam_id, ch.track, ch.car, note, v.clockMs, v.resets, v.totalMs,
      splits ? JSON.stringify(splits) : null, String(sub.appVersion || '').slice(0, 20), started, now, trace).run();
  const rid = res.meta.last_row_id;
  // only the best run keeps its trace (the leader's is the app's ghost)
  if (best) {
    await env.DB.prepare('UPDATE tt_runs SET trace = NULL WHERE week = ? AND slot = ? AND steam_id = ? AND id != ? AND trace IS NOT NULL')
      .bind(week, slot, me.steam_id, rid).run();
  }
  await dropCached(env, [boardKey(week, slot)]);
  const board = await ttBoard(env, week, slot, now);
  const me2 = board.entries.find((e) => e.steamId === me.steam_id);
  return json({ ok: true, id: rid, status: 'finished', counted: true, totalMs: v.totalMs, best,
    improvedMs: best && mine.best != null ? mine.best - v.totalMs : null, bestMs: me2 ? me2.totalMs : null,
    rank: me2 ? me2.rank : null, drivers: board.entries.length, prize: me2 ? me2.prize : null, runs: mine.n + 1,
    ...(appTime ? { appTime } : {}) });
}

// ------------------------------------------------------------------ live positions

/** Who is on a week's stage right now (slot null: both, each driver with their slot), as /api/live has the dailies'
 *  (index.js getLive): {week, slot, now, drivers: [{steamId, slot, name, country, avatar, x, z, progress, totalMs,
 *  state, updated, look?}]}. */
export async function ttLive(env, week, slot = null, now = Date.now()) {
  const bySlot = slot == null ? [] : [slot];
  const { results } = await env.DB.prepare(
    `SELECT l.steam_id AS steamId, l.slot, p.name, p.country, p.avatar, l.x, l.z, l.progress, l.total_ms AS totalMs, l.state,
            l.updated, ${LOOK_COLS}
       FROM tt_live l JOIN players p ON p.steam_id = l.steam_id ${lookJoin('l.steam_id')}
      WHERE l.week = ?${bySlot.length ? ' AND l.slot = ?' : ''} AND p.banned = 0
        AND ((l.state = 'live' AND l.updated > ?) OR (l.state != 'live' AND l.updated > ?))
      ORDER BY l.progress DESC`).bind(week, ...bySlot, now - LIVE_STALE_MS, now - LIVE_KEEP_DONE_MS).all();
  return { week, slot, now, drivers: results.map((r) => { const look = lookOfRow(r), d = unlooked(r); return look ? { ...d, look } : d; }) };
}

/** The app's position on this week's stage (every liveSendS while on it, and at its start, finish or DNF): body
 *  {challengeId, x, z, progress, totalMs, state, others}. On a stage with an entry fee, only an entrant's (a 402
 *  "invalid run" otherwise). others: the answer brings who else is on the stage (the app's stage strip). */
async function postLive(req, env, me, now, deps) {
  const { json, err } = deps;
  const b = await req.json().catch(() => null);
  const id = parseTtId(b && b.challengeId);
  if (!id || id.week !== weekOf(now)) return err('bad time trial stage');
  const old = deps.tooOld(req, b);
  if (old) return old;
  if (!ttOn(env, id.week)) return err('no time trial this week', 409);
  if (feeOf(env, id.week, id.slot) && !await env.DB.prepare('SELECT 1 AS x FROM tt_entries WHERE week = ? AND slot = ? AND steam_id = ?')
    .bind(id.week, id.slot, me.steam_id).first()) {
    return err(`invalid run: enter TT${id.slot} first (DRIVE in ACR Daily)`, 402);
  }
  const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  const state = ['live', 'finished', 'dnf'].includes(b.state) ? b.state : 'live';
  await env.DB.prepare(
    `INSERT INTO tt_live (steam_id, week, slot, x, z, progress, total_ms, state, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (steam_id, week, slot) DO UPDATE SET x = excluded.x, z = excluded.z, progress = excluded.progress,
       total_ms = excluded.total_ms, state = excluded.state, updated = excluded.updated`)
    .bind(me.steam_id, id.week, id.slot, n(b.x), n(b.z), Math.max(0, Math.min(1, n(b.progress))), Math.round(n(b.totalMs)), state, now).run();
  return json(b.others ? { ok: true, drivers: (await ttLive(env, id.week, id.slot, now)).drivers } : { ok: true });
}

// ------------------------------------------------------------------ the API

/** /api/tt...: a Response, or null when the path isn't one. deps (index.js): {json, err, pool, hash, timing, splits,
 *  tooOld(req, body), startedMs(v, now)}. */
export async function ttApi(req, env, path, url, me, sameOrigin, now, deps) {
  if (path !== '/api/tt' && !path.startsWith('/api/tt/')) return null;
  const { json, err } = deps;
  const post = req.method === 'POST';
  if (!firstWeek(env)) return path === '/api/tt' && !post ? json({ on: false }) : err('the time trial is off on this server', 404);
  const cur = weekOf(now);

  if (path === '/api/tt' && !post) {
    const week = url.searchParams.get('week') || cur;
    if (!isWeek(week)) return err('bad week: its Monday, YYYY-MM-DD');
    if (week > cur) return err('no peeking', 403);
    const nav = { first: firstWeek(env), current: cur, prev: ttOn(env, shiftWeek(week, -1)) ? shiftWeek(week, -1) : null,
      next: week < cur ? shiftWeek(week, 1) : null };
    if (!ttOn(env, week)) return json({ on: false, week, ...nav, startsAt: weekStart(nav.first) });
    const rows = await ttPicks(env, week, deps, now);
    const lite = url.searchParams.get('lite') === '1';
    const tracks = rows.map((r) => r.track);
    const [routes, pots, mine] = await env.DB.batch([
      env.DB.prepare(`SELECT track, ${lite ? '' : 'points, '}length, stage_id FROM routes WHERE track IN (SELECT value FROM json_each(?))`)
        .bind(JSON.stringify(tracks)),
      env.DB.prepare('SELECT slot, COUNT(*) AS entrants, COALESCE(SUM(fee), 0) AS pot FROM tt_entries WHERE week = ? GROUP BY slot').bind(week),
      env.DB.prepare(`SELECT s.slot, (SELECT 1 FROM tt_entries e WHERE e.week = ?1 AND e.slot = s.slot AND e.steam_id = ?2) AS entered,
          (SELECT MIN(total_ms) FROM tt_runs r WHERE r.week = ?1 AND r.slot = s.slot AND r.steam_id = ?2 AND r.status = 'finished') AS best,
          (SELECT COUNT(*) FROM tt_runs r WHERE r.week = ?1 AND r.slot = s.slot AND r.steam_id = ?2 AND r.status = 'finished') AS runs
        FROM tt_schedule s WHERE s.week = ?1`).bind(week, me ? me.steam_id : ''),
    ]);
    const byTrack = new Map(routes.results.map((r) => [r.track, r]));
    const potOf = new Map(pots.results.map((p) => [p.slot, p]));
    const meOf = new Map(mine.results.map((m) => [m.slot, m]));
    const stages = rows.map((p) => {
      const s = stageOut(env, week, p, byTrack.get(p.track) || null, deps), pt = potOf.get(p.slot), m = meOf.get(p.slot);
      return { ...s, entrants: pt ? pt.entrants : 0, pot: pt ? pt.pot : 0,
        ...(me ? { me: { entered: !s.fee || !!(m && m.entered), bestMs: m ? m.best : null, runs: m ? m.runs : 0 } } : {}) };
    });
    return json({ on: true, week, isoWeek: isoWeek(week), startsAt: weekStart(week), endsAt: weekStart(week) + WEEK, ...nav,
      credits: creditsOn(env, week), signedIn: !!me, stages });
  }
  if (path === '/api/tt/board' && !post) {
    const week = url.searchParams.get('week') || cur, slot = +(url.searchParams.get('slot') || 1);
    if (!isWeek(week) || ![1, 2].includes(slot)) return err('bad week or slot');
    if (week > cur || !ttOn(env, week)) return json({ week, slot, entries: [], stats: { drivers: 0, runs: 0, entrants: 0, pot: 0, paidPlaces: 0 } });
    return json(await ttBoard(env, week, slot, now));
  }
  if (path === '/api/tt/live' && !post) {
    const week = url.searchParams.get('week') || cur, s = url.searchParams.get('slot') || 'all';
    if (!isWeek(week) || !['all', '1', '2'].includes(s)) return err('bad week or slot');
    return json(await ttLive(env, week, s === 'all' ? null : +s, now));
  }
  const tm = path.match(/^\/api\/tt\/runs\/(\d+)\/trace$/);
  if (tm && !post) {
    const r = await env.DB.prepare("SELECT id, track, car, total_ms, trace FROM tt_runs WHERE id = ? AND status = 'finished'").bind(+tm[1]).first();
    // (only the row's own copy: an R2 object of the same number is a daily's run, src/traces.js)
    const trace = r && r.trace ? await getTrace(env, r) : null;
    return trace ? json({ id: r.id, track: r.track, car: r.car, totalMs: r.total_ms, trace }) : err('not found', 404);
  }
  if (!post) return err('not found', 404);
  if (!me) return err('sign in with Steam first', 401);
  if (me.banned) return err('this account is banned', 403);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (path === '/api/tt/enter') return enter(env, me, (await req.json().catch(() => ({}))) || {}, now, deps);
  if (path === '/api/tt/runs') return submit(req, env, me, now, deps);
  if (path === '/api/tt/live') return postLive(req, env, me, now, deps);
  return err('not found', 404);
}

/** An admin takes a run off the board (POST /api/admin/tt/runs/:id/reject): the driver's next best run counts. A week
 *  already settled keeps its payouts. -> true if there was such a run. */
/** A time trial run under investigation (src/apptime.js) on its board after all: the app's stage clock + the game's
 *  penalty read off its pictures (penaltyMs), else the respawn estimate, marked. -> {week, slot, total_ms}, {error}
 *  or null (no such run). */
export async function reinstateTtRun(env, id, penaltyMs) {
  const lost = await env.DB.prepare(`SELECT clock_ms, resets FROM tt_runs WHERE id = ? AND status = 'rejected'
      AND reason LIKE ? AND clock_ms > 0`).bind(id, INVESTIGATING + '%').first();
  if (!lost) return null;
  const t = reinstatedTime(lost.clock_ms, lost.resets || 0, penaltyMs);
  if (t.error) return { error: t.error };
  const r = await env.DB.prepare(`UPDATE tt_runs SET status = 'finished', total_ms = ?, reason = ?
      WHERE id = ? AND status = 'rejected' RETURNING week, slot, total_ms`).bind(t.totalMs, t.note, id).first();
  if (r) await dropCached(env, [boardKey(r.week, r.slot)]);
  return r || null;
}

export async function rejectTtRun(env, id, reason) {
  const r = await env.DB.prepare("UPDATE tt_runs SET status = 'rejected', reason = ?, trace = NULL WHERE id = ? RETURNING week, slot")
    .bind(String(reason || 'rejected by admin').slice(0, 200), id).first();
  if (r) await dropCached(env, [boardKey(r.week, r.slot)]);
  return !!r;
}
