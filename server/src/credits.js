// Credits (a prototype, off unless CREDITS_FROM is set in wrangler.toml): points each driver earns and spends inside
// ACR Daily. They are only ever earned (never bought), can't be cashed out or given to another driver: a game's score,
// not money. Keep it that way: credits that could be bought or exchanged would make the wager daily gambling.
//
// Earned: a welcome bonus; a daily bonus for coming back (claimed by the app, or on the website's /credits page), more
//   on a streak of days; finishing the free daily.
// Spent: the wager daily (one of the two dailies, WAGER.slot): a driver may stake WAGER.stake before their first run
//   on it. Once the day is over, the drivers in the top half of everyone who staked (by their counted run) get double
//   their stake back, the rest lose it; what is left over (an odd number of entrants, or fewer finishers than winners)
//   goes to the fastest of them. Fewer than two entrants, or nobody of them finishing: everyone gets their stake back.
//   The stakes only move between drivers: no credits are made or lost.
//   League events with an entry fee (set by the league's staff): paid before the start, the fees make a pot that goes
//   to the event's top three (50 / 30 / 20 %; the rest to the winner when fewer finish; nobody finishing: refunds).
// Settled by the cron (index.js) once the day or the event is over; every change is a line in the ledger.

export const CREDITS = { welcome: 100, daily: 10, streakStep: 2, streakMax: 10, finish: 5, feeMax: 1000 };
export const WAGER = { slot: 2, stake: 10 };
export const POT_SHARES = [50, 30, 20];
export const SETTLE_AFTER_MS = 25 * 3600000;    // a day's dailies settle at 01:00 UTC the next day (late runs, abandoned starts)
const day = (ms) => new Date(ms).toISOString().slice(0, 10);
const prevDay = (date) => day(Date.parse(date + 'T00:00:00Z') - 86400000);

/** Credits are on for this day's dailies (CREDITS_FROM in wrangler.toml; empty = off). */
export const creditsOn = (env, date) => !!env.CREDITS_FROM && date >= env.CREDITS_FROM;

/** The daily bonus on the n-th day in a row (1 = no streak): 10, 12, 14 ... 20. */
export const dailyBonus = (streak) => CREDITS.daily + Math.min(CREDITS.streakStep * Math.max(0, streak - 1), CREDITS.streakMax);

/** The streak after claiming today: one more when the last claim was yesterday, else 1. */
export const nextStreak = (lastDay, today, streak) => (lastDay === prevDay(today) ? (streak || 0) + 1 : 1);

/** The wager of a daily, settled. entrants: [{steamId, finished, totalMs}] (everyone who staked; finished = their
 *  counted run finished). -> Map steamId -> credits paid back (0: lost). */
export function wagerPayouts(entrants, stake) {
  const out = new Map(entrants.map((e) => [e.steamId, 0]));
  const fin = entrants.filter((e) => e.finished).sort((a, b) => a.totalMs - b.totalMs);
  if (entrants.length < 2 || !fin.length) {
    for (const e of entrants) out.set(e.steamId, stake);           // no contest: refunds
    return out;
  }
  const winners = fin.slice(0, Math.max(1, Math.floor(entrants.length / 2)));
  for (const w of winners) out.set(w.steamId, 2 * stake);
  const left = entrants.length * stake - winners.length * 2 * stake;
  out.set(winners[0].steamId, out.get(winners[0].steamId) + left);
  return out;
}

/** An event's pot, settled. fees: Map steamId -> fee paid; finishers: steamIds in finishing order (DSQ left out).
 *  -> Map steamId -> credits won (refunds when nobody finished). */
export function potPayouts(fees, finishers, shares = POT_SHARES) {
  const out = new Map();
  const pot = [...fees.values()].reduce((a, x) => a + x, 0);
  if (!pot) return out;
  if (!finishers.length) {
    for (const [sid, fee] of fees) out.set(sid, fee);
    return out;
  }
  let given = 0;
  finishers.slice(0, shares.length).forEach((sid, i) => {
    const amt = Math.floor((pot * shares[i]) / 100);
    out.set(sid, amt);
    given += amt;
  });
  out.set(finishers[0], out.get(finishers[0]) + pot - given);      // rounding, and the shares of missing places
  return out;
}

// ------------------------------------------------------------------ the ledger

/** A driver's credits: {balance, streak, lastDay} (all 0 / null for someone new). */
export async function balanceOf(env, steamId) {
  const r = await env.DB.prepare('SELECT balance, streak, last_day FROM credits WHERE steam_id = ?').bind(steamId).first();
  return r ? { balance: r.balance, streak: r.streak, lastDay: r.last_day } : { balance: 0, streak: 0, lastDay: null };
}

/** Statements that add `amount` (negative: take) to a driver's credits, with its ledger line. */
export function giveStmts(env, steamId, amount, kind, ref, note, now) {
  return [
    env.DB.prepare(`INSERT INTO credits (steam_id, balance, streak, last_day) VALUES (?1, ?2, 0, NULL)
      ON CONFLICT(steam_id) DO UPDATE SET balance = balance + ?2`).bind(steamId, amount),
    env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(steamId, amount, kind, ref || null, note || null, now),
  ];
}

/** Take `amount` if the driver has it. -> true when taken. */
export async function spend(env, steamId, amount, kind, ref, note, now) {
  const r = await env.DB.prepare('UPDATE credits SET balance = balance - ?1 WHERE steam_id = ?2 AND balance >= ?1')
    .bind(amount, steamId).run();
  if (!r.meta.changes) return false;
  await env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(steamId, -amount, kind, ref || null, note || null, now).run();
  return true;
}

/** Today's bonus, once a day (the welcome bonus with the first). -> {claimed, amount, balance, streak} */
export async function claimDaily(env, steamId, now) {
  const today = day(now);
  const cur = await env.DB.prepare('SELECT balance, streak, last_day FROM credits WHERE steam_id = ?').bind(steamId).first();
  if (cur && cur.last_day === today) return { claimed: false, amount: 0, balance: cur.balance, streak: cur.streak };
  const streak = nextStreak(cur && cur.last_day, today, cur && cur.streak);
  const welcome = !cur || cur.last_day == null ? CREDITS.welcome : 0;
  const amount = dailyBonus(streak) + welcome;
  // only one claim a day, even with two requests at once: the update is on the day not being claimed yet
  const r = await env.DB.prepare(`INSERT INTO credits (steam_id, balance, streak, last_day) VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT(steam_id) DO UPDATE SET balance = balance + ?2, streak = ?3, last_day = ?4
    WHERE credits.last_day IS NULL OR credits.last_day <> ?4`).bind(steamId, amount, streak, today).run();
  if (!r.meta.changes) return { claimed: false, amount: 0, ...(await balanceOf(env, steamId)) };
  const lines = [env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(steamId, dailyBonus(streak), 'daily', today, streak > 1 ? `${streak} days in a row` : null, now)];
  if (welcome) {
    lines.push(env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(steamId, welcome, 'welcome', null, null, now));
  }
  await env.DB.batch(lines);
  const b = await balanceOf(env, steamId);
  return { claimed: true, amount, welcome, balance: b.balance, streak: b.streak };
}

const LABELS = { welcome: 'Welcome bonus', daily: 'Daily bonus', finish: 'Free daily finished', wager: 'Wager staked',
  'wager-win': 'Wager won', 'wager-refund': 'Wager refunded', fee: 'League entry fee', prize: 'League prize', 'fee-refund': 'League fee refunded' };

// ------------------------------------------------------------------ the API

/** GET /api/credits, POST /api/credits/claim, POST /api/credits/wager, GET /api/credits/wager?date=&slot=.
 *  -> a Response, or null when the path is not one of them. countedStart(date, slot, steamId): has the driver started
 *  that daily already (index.js: attempts and runs). */
export async function creditsApi(req, env, path, url, me, sameOrigin, now, { json, err, countedStart }) {
  if (!path.startsWith('/api/credits')) return null;
  const post = req.method === 'POST';
  const today = day(now);
  if (!env.CREDITS_FROM) return path === '/api/credits' && !post ? json({ enabled: false }) : err('credits are off on this server', 404);
  const need = () => (!me ? err('sign in with Steam first', 401) : me.banned ? err('this account is banned', 403)
    : post && !sameOrigin ? err('refused: not from this site', 403) : null);
  const wagerOf = async (date, slot) => {
    const w = await env.DB.prepare('SELECT COUNT(*) AS n, COALESCE(SUM(stake), 0) AS pot, MAX(settled) AS settled FROM wagers WHERE date = ? AND slot = ?')
      .bind(date, slot).first();
    return { date, slot, stake: WAGER.stake, entrants: w.n, pot: w.pot, settled: w.settled || null };
  };

  if (path === '/api/credits' && !post) {
    if (!me) return json({ enabled: creditsOn(env, today), signedIn: false, wager: creditsOn(env, today) ? await wagerOf(today, WAGER.slot) : null });
    const b = await balanceOf(env, me.steam_id);
    const { results } = await env.DB.prepare('SELECT delta, kind, ref, note, created FROM credit_ledger WHERE steam_id = ? ORDER BY id DESC LIMIT 30')
      .bind(me.steam_id).all();
    const mine = await env.DB.prepare('SELECT stake FROM wagers WHERE date = ? AND slot = ? AND steam_id = ?').bind(today, WAGER.slot, me.steam_id).first();
    return json({
      enabled: creditsOn(env, today), signedIn: true, balance: b.balance, streak: b.streak,
      claimable: b.lastDay !== today, nextBonus: dailyBonus(nextStreak(b.lastDay, today, b.streak)) + (b.lastDay == null ? CREDITS.welcome : 0),
      wager: creditsOn(env, today) ? { ...(await wagerOf(today, WAGER.slot)), entered: !!mine } : null,
      ledger: results.map((x) => ({ ...x, label: LABELS[x.kind] || x.kind })),
    });
  }
  if (path === '/api/credits/wager' && !post) {
    const date = url.searchParams.get('date') || today, slot = +(url.searchParams.get('slot') || WAGER.slot);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || slot !== WAGER.slot || !creditsOn(env, date)) return json(null);
    return json(await wagerOf(date, slot));
  }
  if (!post) return err('not found', 404);
  const no = need(); if (no) return no;
  if (path === '/api/credits/claim') {
    if (!creditsOn(env, today)) return err('credits start on ' + env.CREDITS_FROM, 409);
    return json(await claimDaily(env, me.steam_id, now));
  }
  if (path === '/api/credits/wager') {                    // stake on today's wager daily, before the first run on it
    const b = await req.json().catch(() => ({})) || {};
    const date = b.date || today, slot = +(b.slot || WAGER.slot);
    if (date !== today || slot !== WAGER.slot) return err('only today\'s wager daily (SS' + WAGER.slot + ') takes stakes', 409);
    if (!creditsOn(env, date)) return err('credits are not on for this daily', 409);
    if (await env.DB.prepare('SELECT 1 AS x FROM wagers WHERE date = ? AND slot = ? AND steam_id = ?').bind(date, slot, me.steam_id).first()) {
      return json({ entered: true, already: true, ...(await wagerOf(date, slot)), balance: (await balanceOf(env, me.steam_id)).balance });
    }
    if (await countedStart(date, slot, me.steam_id)) return err('you have started this daily already: stakes are taken before the first run', 409);
    const ref = `${date}/${slot}`;
    if (!await spend(env, me.steam_id, WAGER.stake, 'wager', ref, null, now)) {
      return err(`the stake is ${WAGER.stake} credits: you have ${(await balanceOf(env, me.steam_id)).balance}`, 402);
    }
    const r = await env.DB.prepare('INSERT OR IGNORE INTO wagers (date, slot, steam_id, stake, created) VALUES (?, ?, ?, ?, ?)')
      .bind(date, slot, me.steam_id, WAGER.stake, now).run();
    if (!r.meta.changes) await env.DB.batch(giveStmts(env, me.steam_id, WAGER.stake, 'wager-refund', ref, 'staked twice', now));
    return json({ entered: true, ...(await wagerOf(date, slot)), balance: (await balanceOf(env, me.steam_id)).balance });
  }
  return err('not found', 404);
}

// ------------------------------------------------------------------ settling a day (cron)

/** Once a day is over (SETTLE_AFTER_MS after its start): the free daily's finishers get their bonus, the wager daily's
 *  stakes are paid out. board(date, slot): the daily's board as built fresh (index.js buildLeaderboard). Each daily is
 *  settled once (credit_days). -> [{date, slot, paid}] */
export async function settleDays(env, now, board) {
  if (!env.CREDITS_FROM) return [];
  const out = [];
  // the last three days not settled yet (a missed cron catches up)
  for (let k = 3; k >= 1; k--) {
    const date = day(now - k * 86400000);
    if (!creditsOn(env, date) || now < Date.parse(date + 'T00:00:00Z') + SETTLE_AFTER_MS) continue;
    for (const slot of [1, 2]) {
      const r = await settleDay(env, date, slot, now, board);
      if (r) out.push(r);
    }
  }
  return out;
}

/** Settle one daily now (once: credit_days). The cron calls it once the day is over; a local test server's admin can
 *  call it any time (POST /api/admin/credits-settle). -> {date, slot, payouts: {steamId: credits}} or null if done. */
export async function settleDay(env, date, slot, now, board) {
  const claim = await env.DB.prepare('INSERT OR IGNORE INTO credit_days (date, slot, settled) VALUES (?, ?, ?)').bind(date, slot, now).run();
  if (!claim.meta.changes) return null;                  // settled already
  const b = await board(date, slot);
  const ref = `${date}/${slot}`;
  const stmts = [];
  const payouts = {};
  if (slot === WAGER.slot) {
    const { results: ws } = await env.DB.prepare('SELECT steam_id, stake FROM wagers WHERE date = ? AND slot = ?').bind(date, slot).all();
    const byId = new Map(b.entries.map((e) => [e.steamId, e]));
    const pay = wagerPayouts(ws.map((w) => {
      const e = byId.get(w.steam_id);
      return { steamId: w.steam_id, finished: !!(e && e.status === 'finished' && e.totalMs != null), totalMs: e ? e.totalMs : null };
    }), WAGER.stake);
    const refund = ws.length < 2 || ![...pay.values()].some((x) => x !== WAGER.stake);
    for (const [sid, amt] of pay) {
      payouts[sid] = amt;
      if (amt) stmts.push(...giveStmts(env, sid, amt, refund ? 'wager-refund' : 'wager-win', ref, null, now));
      stmts.push(env.DB.prepare('UPDATE wagers SET settled = ?, paid = ? WHERE date = ? AND slot = ? AND steam_id = ?').bind(now, amt, date, slot, sid));
    }
  } else {
    for (const e of b.entries) {
      if (e.status !== 'finished') continue;
      payouts[e.steamId] = CREDITS.finish;
      stmts.push(...giveStmts(env, e.steamId, CREDITS.finish, 'finish', ref, null, now));
    }
  }
  if (stmts.length) await env.DB.batch(stmts);
  return { date, slot, payouts };
}
