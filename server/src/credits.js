// Credits (on from CREDITS_FROM in wrangler.toml): points each driver earns and spends inside
// ACR Daily. They are only ever earned (never bought), can't be cashed out or given to another driver: a game's score,
// not money. Keep it that way: credits that could be bought or exchanged would make the wager daily gambling.
//
// Earned: a welcome bonus (with the first daily bonus); a daily bonus for coming back (claimed by the app when it
//   starts, or by the first page of the website opened that day, which says so in a popup: src/bonus.js); finishing
//   the free daily (paid as soon as that run is in: payFinish).
// Spent: the wager daily (one of the two dailies, WAGER.slot) is only driven with a stake: no stake, no run on it (the
//   server refuses its live position and its run: wagerGate). A driver stakes WAGER.stake before their first run on it
//   (a day's stake is the one its first driver staked, so a new WAGER.stake starts with a new day). The house stakes
//   too, as one more entrant who never finishes, so a driver on their own can win. Once the day is over, the top half
//   of the entrants (the house counted: the top half of the drivers, rounded up) get double their stake back, the rest
//   lose it; what is left over goes to the fastest. Nobody finishing: everyone gets their stake back. A stake counts
//   only when the server then saw the driver start the stage (attempts): one never driven goes back.
//   The house's stake is the only credits a wager makes; the drivers' stakes only move between them.
//   The shop's looks (src/shop.js). Leagues are free: no credits in them.
// Settled by the cron (index.js) once the day is over, once: the marker and the payouts are one batch.
// A run under review holds its day for REVIEW_HOLD_MS (an admin rejects or clears it); after that the day is settled
// as its board stands. Every change is a line in the ledger.
// Every signed-in driver gets the welcome bonus with their first daily bonus (the user's choice, 2026-10-12: no
// finished run needed first, existing drivers too).

export const CREDITS = { welcome: 50, daily: 50, finish: 50 };
export const WAGER = { slot: 2, stake: 100 };
export const POT_SHARES = [50, 30, 20];         // potPayouts' default split
export const SETTLE_AFTER_MS = 25 * 3600000;    // a day's dailies settle at 01:00 UTC the next day (late runs, abandoned starts)
export const REVIEW_HOLD_MS = 3 * 86400000;     // ...or up to this much later while a run that counts is under review
const SETTLE_DAYS_BACK = 5;                     // the days the cron looks at (the hold, and a cron that was down)
const STAKE_SLACK_MS = 2 * 60000;               // the PC's clock against the server's, for a start just after staking
const day = (ms) => new Date(ms).toISOString().slice(0, 10);
const prevDay = (date) => day(Date.parse(date + 'T00:00:00Z') - 86400000);

/** Credits are on for this day's dailies (CREDITS_FROM in wrangler.toml; empty = off). */
export const creditsOn = (env, date) => !!env.CREDITS_FROM && date >= env.CREDITS_FROM;

/** Days in a row the daily bonus was claimed, after claiming today: one more when the last claim was yesterday, else 1
 *  (shown on /credits; the bonus is the same every day). */
export const nextStreak = (lastDay, today, streak) => (lastDay === prevDay(today) ? (streak || 0) + 1 : 1);

/** The wager of a daily, settled. entrants: [{steamId, finished, totalMs, stake?}] (everyone whose stake counts;
 *  finished = their counted run finished; stake: what they staked, else `stake`). The house is one more entrant with
 *  the day's stake who never finishes. -> Map steamId -> credits paid back (0: lost); the house's share is not in it.
 *  Ties go to who staked first (the entrants' order). */
export function wagerPayouts(entrants, stake) {
  const own = (e) => (e.stake != null ? e.stake : stake);
  const out = new Map(entrants.map((e) => [e.steamId, 0]));
  const fin = entrants.filter((e) => e.finished).sort((a, b) => a.totalMs - b.totalMs);
  if (!fin.length) {
    for (const e of entrants) out.set(e.steamId, own(e));          // nobody finished: refunds (the house pays nothing)
    return out;
  }
  const house = own(entrants[0]);
  const winners = fin.slice(0, Math.floor((entrants.length + 1) / 2));   // the top half, the house counted
  for (const w of winners) out.set(w.steamId, 2 * own(w));
  const left = entrants.reduce((a, e) => a + own(e), house) - winners.reduce((a, w) => a + 2 * own(w), 0);
  out.set(winners[0].steamId, out.get(winners[0].steamId) + left);
  return out;
}

/** The wager daily's result decides nothing: none of the entrants finished (their stakes go back). */
export const wagerRefunds = (entrants) => !entrants.some((e) => e.finished);

/** A pot of entry fees, settled (cups). fees: Map steamId -> fee paid; finishers: steamIds in finishing order; shares:
 *  the % of each place. -> Map steamId -> credits won (refunds when nobody finished). */
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

/** giveStmts, only when `cond` (SQL with plain ? binds) holds as the batch gets to them. */
export function giveWhenStmts(env, steamId, amount, kind, ref, note, now, cond, binds) {
  return [
    env.DB.prepare(`INSERT INTO credits (steam_id, balance, streak, last_day) SELECT ?, ?, 0, NULL WHERE ${cond}
      ON CONFLICT(steam_id) DO UPDATE SET balance = balance + excluded.balance`).bind(steamId, amount, ...binds),
    env.DB.prepare(`INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) SELECT ?, ?, ?, ?, ?, ? WHERE ${cond}`)
      .bind(steamId, amount, kind, ref || null, note || null, now, ...binds),
  ];
}

/** giveWhenStmts for many drivers at once (a cup's refunds or prizes), two statements however many: pays [{to, amount}],
 *  each driver once. */
export function giveManyWhenStmts(env, pays, kind, ref, note, now, cond, binds) {
  const j = JSON.stringify(pays.map((p) => ({ to: p.to, n: p.amount })));
  return [
    env.DB.prepare(`INSERT INTO credits (steam_id, balance, streak, last_day)
      SELECT json_extract(j.value, '$.to'), json_extract(j.value, '$.n'), 0, NULL FROM json_each(?) j WHERE ${cond}
      ON CONFLICT(steam_id) DO UPDATE SET balance = balance + excluded.balance`).bind(j, ...binds),
    env.DB.prepare(`INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created)
      SELECT json_extract(j.value, '$.to'), json_extract(j.value, '$.n'), ?, ?, ?, ? FROM json_each(?) j WHERE ${cond}`)
      .bind(kind, ref || null, note || null, now, j, ...binds),
  ];
}

/** Statements that take `amount` from a driver, with its ledger line, when `cond` (SQL with plain ? binds) holds once
 *  the statements before them in the same batch have run. A batch is all or nothing: a payment goes in the batch
 *  with what it pays for (a row that is only written when the driver has the credits). */
export function takeWhenStmts(env, steamId, amount, kind, ref, note, now, cond, binds) {
  return [
    env.DB.prepare(`UPDATE credits SET balance = balance - ? WHERE steam_id = ? AND ${cond}`).bind(amount, steamId, ...binds),
    env.DB.prepare(`INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) SELECT ?, ?, ?, ?, ?, ? WHERE ${cond}`)
      .bind(steamId, -amount, kind, ref || null, note || null, now, ...binds),
  ];
}

/** A unique-key clash: someone else wrote that row first (a batch with it was undone). */
export const clash = (e) => /UNIQUE|constraint/i.test(String((e && e.message) || e));

/** Has the driver finished a run (any daily, practice too)? Credits start then. */
export async function hasFinished(env, steamId) {
  return !!await env.DB.prepare("SELECT 1 AS x FROM runs WHERE steam_id = ? AND status = 'finished' LIMIT 1").bind(steamId).first();
}

/** Today's bonus, once a day (the welcome bonus with the first). -> {claimed, amount, welcome, balance, streak} */
export async function claimDaily(env, steamId, now) {
  const today = day(now);
  const cur = await env.DB.prepare('SELECT balance, streak, last_day FROM credits WHERE steam_id = ?').bind(steamId).first();
  if (cur && cur.last_day === today) return { claimed: false, amount: 0, balance: cur.balance, streak: cur.streak };
  const streak = nextStreak(cur && cur.last_day, today, cur && cur.streak);
  const welcome = !cur || cur.last_day == null ? CREDITS.welcome : 0;
  const amount = CREDITS.daily + welcome;
  // only one claim a day, even with two requests at once: the update is on the day not being claimed yet
  const r = await env.DB.prepare(`INSERT INTO credits (steam_id, balance, streak, last_day) VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT(steam_id) DO UPDATE SET balance = balance + ?2, streak = ?3, last_day = ?4
    WHERE credits.last_day IS NULL OR credits.last_day <> ?4`).bind(steamId, amount, streak, today).run();
  if (!r.meta.changes) return { claimed: false, amount: 0, ...(await balanceOf(env, steamId)) };
  const lines = [env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
    .bind(steamId, CREDITS.daily, 'daily', today, streak > 1 ? `${streak} days in a row` : null, now)];
  if (welcome) {
    lines.push(env.DB.prepare('INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) VALUES (?, ?, ?, ?, ?, ?)')
      .bind(steamId, welcome, 'welcome', null, null, now));
  }
  await env.DB.batch(lines);
  const b = await balanceOf(env, steamId);
  return { claimed: true, amount, welcome, balance: b.balance, streak: b.streak };
}

/** What each kind of ledger line says in a driver's history (every kind the code writes: test/social.test.mjs). */
export const LABELS = { welcome: 'Welcome bonus', daily: 'Daily bonus', finish: 'Free daily finished', 'finish-back': 'Free daily bonus taken back',
  wager: 'Wager staked', 'wager-win': 'Wager won', 'wager-refund': 'Wager refunded', shop: 'Shop',
  'h2h-stake': '1V1 stake', 'h2h-win': '1V1 won', 'h2h-refund': '1V1 stake back',
  'cup-fee': 'Cup entry', 'cup-refund': 'Cup entry back', 'cup-prize': 'Cup prize', 'daily-set': 'A daily of your own' };

/** The free daily finished: its counted run is in (not under review), CREDITS.finish once per driver and daily.
 *  -> what was paid (0: paid before). */
export async function payFinish(env, steamId, date, slot, now) {
  const ref = `${date}/${slot}`;
  const cond = "NOT EXISTS (SELECT 1 FROM credit_ledger WHERE steam_id = ? AND kind = 'finish' AND ref = ?)";
  try {
    const r = await env.DB.batch(giveWhenStmts(env, steamId, CREDITS.finish, 'finish', ref, null, now, cond, [steamId, ref]));
    return r[1].meta.changes ? CREDITS.finish : 0;
  } catch (e) {
    if (clash(e)) return 0;                              // paid meanwhile (the unique index on the finish lines)
    throw e;
  }
}

/** The free daily's counted run rejected by an admin: its finish bonus goes back, once (the balance may go below 0). */
export async function takeBackFinish(env, steamId, date, slot, now) {
  const ref = `${date}/${slot}`;
  const cond = "EXISTS (SELECT 1 FROM credit_ledger WHERE steam_id = ? AND kind = 'finish' AND ref = ?) " +
    "AND NOT EXISTS (SELECT 1 FROM credit_ledger WHERE steam_id = ? AND kind = 'finish-back' AND ref = ?)";
  const r = await env.DB.batch(giveWhenStmts(env, steamId, -CREDITS.finish, 'finish-back', ref, 'run rejected', now, cond,
    [steamId, ref, steamId, ref]));
  return r[1].meta.changes ? CREDITS.finish : 0;
}

/** The wager daily is driven with a stake: a live position or a run on it from a driver who hasn't staked (or one
 *  that started before the stake) is refused. startedAt: the run's start (ms), null: only whether they staked.
 *  -> null when it may go on, else {status, error} ("invalid run": the app drops it from its send queue). */
export async function wagerGate(env, steamId, date, slot, startedAt) {
  if (slot !== WAGER.slot || !creditsOn(env, date)) return null;
  const w = await env.DB.prepare('SELECT created FROM wagers WHERE date = ? AND slot = ? AND steam_id = ?').bind(date, slot, steamId).first();
  if (!w) {
    return { status: 402, error: `invalid run: SS${slot} is the wager daily, driven with a stake of ${WAGER.stake} credits. ` +
      'Stake first: DRIVE in ACR Daily asks' };
  }
  if (startedAt != null && startedAt < w.created - STAKE_SLACK_MS) {
    return { status: 409, error: 'invalid run: it started before your stake (the runs after it count)' };
  }
  return null;
}

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
    const w = await env.DB.prepare(`SELECT COUNT(*) AS n, COALESCE(SUM(stake), 0) AS pot, MAX(settled) AS settled,
      (SELECT stake FROM wagers WHERE date = ?1 AND slot = ?2 ORDER BY created LIMIT 1) AS stake FROM wagers WHERE date = ?1 AND slot = ?2`)
      .bind(date, slot).first();
    return { date, slot, stake: w.stake || WAGER.stake, entrants: w.n, pot: w.pot, settled: w.settled || null };
  };

  if (path === '/api/credits' && !post) {
    if (!me) return json({ enabled: creditsOn(env, today), signedIn: false, wager: creditsOn(env, today) ? await wagerOf(today, WAGER.slot) : null });
    const b = await balanceOf(env, me.steam_id);
    const { results } = await env.DB.prepare('SELECT delta, kind, ref, note, created FROM credit_ledger WHERE steam_id = ? ORDER BY id DESC LIMIT 30')
      .bind(me.steam_id).all();
    const mine = await env.DB.prepare('SELECT stake FROM wagers WHERE date = ? AND slot = ? AND steam_id = ?').bind(today, WAGER.slot, me.steam_id).first();
    const earning = true;   // (apps before 0.0.13 read it: credits used to start with the first finished run)
    return json({
      enabled: creditsOn(env, today), signedIn: true, name: me.name, balance: b.balance, streak: b.streak, earning,   // (name: as shown, src/drivers.js)
      claimable: earning && b.lastDay !== today, nextBonus: CREDITS.daily + (b.lastDay == null ? CREDITS.welcome : 0),
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
    const { stake } = await wagerOf(date, slot);
    // the stake row and the payment together: the row only when the driver has the credits, the payment only with it
    await env.DB.batch([
      env.DB.prepare(`INSERT OR IGNORE INTO wagers (date, slot, steam_id, stake, created) SELECT ?1, ?2, ?3, ?4, ?5
        WHERE (SELECT balance FROM credits WHERE steam_id = ?3) >= ?4`).bind(date, slot, me.steam_id, stake, now),
      ...takeWhenStmts(env, me.steam_id, stake, 'wager', ref, null, now,
        'EXISTS (SELECT 1 FROM wagers WHERE date = ? AND slot = ? AND steam_id = ? AND created = ?)', [date, slot, me.steam_id, now]),
    ]);
    const mine = await env.DB.prepare('SELECT created FROM wagers WHERE date = ? AND slot = ? AND steam_id = ?').bind(date, slot, me.steam_id).first();
    const balance = (await balanceOf(env, me.steam_id)).balance;
    if (!mine) return err(`the stake is ${stake} credits: you have ${balance}`, 402);
    return json({ entered: true, ...(mine.created !== now ? { already: true } : {}), ...(await wagerOf(date, slot)), balance });
  }
  return err('not found', 404);
}

// ------------------------------------------------------------------ settling a day (cron)

/** Once a day is over (SETTLE_AFTER_MS after its start): the wager daily's stakes are paid out (the free daily's
 *  finishers are paid as their runs come in: payFinish). board(date, slot): the daily's board as built fresh (index.js
 *  buildLeaderboard). Each day is settled once (credit_days). -> [{date, slot, paid}] */
export async function settleDays(env, now, board) {
  if (!env.CREDITS_FROM) return [];
  const { results } = await env.DB.prepare('SELECT date, slot FROM credit_days WHERE date >= ?')
    .bind(day(now - SETTLE_DAYS_BACK * 86400000)).all();
  const done = new Set(results.map((r) => `${r.date}/${r.slot}`));
  const out = [];
  // the last days not settled yet (one held by a run under review, a cron that was down)
  for (let k = SETTLE_DAYS_BACK; k >= 1; k--) {
    const date = day(now - k * 86400000);
    if (!creditsOn(env, date) || now < Date.parse(date + 'T00:00:00Z') + SETTLE_AFTER_MS) continue;
    if (done.has(`${date}/${WAGER.slot}`)) continue;
    const r = await settleDay(env, date, WAGER.slot, now, board);
    if (r) out.push(r);
  }
  return out;
}

/** Settle a day's wager daily now (once: credit_days, written in the same batch as the payouts). The cron calls it once
 *  the day is over; a local test server's admin can call it any time (POST /api/admin/credits-settle). -> {date, slot,
 *  payouts: {steamId: credits}}, {date, slot, held: true} while a run that counts is under review (REVIEW_HOLD_MS),
 *  or null if it was settled already (or the daily is not the wager daily: nothing to settle). */
export async function settleDay(env, date, slot, now, board) {
  if (slot !== WAGER.slot) return null;
  const settled = () => env.DB.prepare('SELECT 1 AS x FROM credit_days WHERE date = ? AND slot = ?').bind(date, slot).first();
  if (await settled()) return null;
  const b = await board(date, slot);
  const byId = new Map(b.entries.map((e) => [e.steamId, e]));
  const finished = (sid) => { const e = byId.get(sid); return !!(e && e.status === 'finished' && e.totalMs != null); };
  const ref = `${date}/${slot}`;
  const pays = [];                                       // [steamId, credits, kind, note]
  const { results: ws } = await env.DB.prepare(`SELECT w.steam_id, w.stake, w.created, a.started FROM wagers w
    LEFT JOIN attempts a ON a.steam_id = w.steam_id AND a.date = w.date AND a.slot = w.slot
    WHERE w.date = ? AND w.slot = ? ORDER BY w.created`).bind(date, slot).all();
  // a stake counts when the server saw the driver start after it; else it goes back (never driven, or a start sent later)
  const counts = (w) => w.started != null && w.started >= w.created - STAKE_SLACK_MS;
  const entrants = ws.filter(counts).map((w) => ({ steamId: w.steam_id, stake: w.stake, finished: finished(w.steam_id),
    totalMs: finished(w.steam_id) ? byId.get(w.steam_id).totalMs : null }));
  const pay = wagerPayouts(entrants);
  const refund = wagerRefunds(entrants);
  for (const w of ws) {
    if (!counts(w)) pays.push([w.steam_id, w.stake, 'wager-refund', w.started == null ? 'not started' : 'staked after the start']);
    else pays.push([w.steam_id, pay.get(w.steam_id), refund ? 'wager-refund' : 'wager-win', null]);
  }
  // a run under review that would win something holds the day, until an admin decides or the hold is over
  const review = pays.some(([sid, amt]) => amt > 0 && finished(sid) && byId.get(sid).review);
  if (review && now < Date.parse(date + 'T00:00:00Z') + SETTLE_AFTER_MS + REVIEW_HOLD_MS) return { date, slot, held: true };
  const stmts = [env.DB.prepare('INSERT INTO credit_days (date, slot, settled) VALUES (?, ?, ?)').bind(date, slot, now)];
  const payouts = {};
  for (const [sid, amt, kind, note] of pays) {
    payouts[sid] = amt;
    if (amt) stmts.push(...giveStmts(env, sid, amt, kind, ref, note, now));
  }
  for (const w of ws) {
    stmts.push(env.DB.prepare('UPDATE wagers SET settled = ?, paid = ? WHERE date = ? AND slot = ? AND steam_id = ?')
      .bind(now, payouts[w.steam_id], date, slot, w.steam_id));
  }
  try {
    await env.DB.batch(stmts);
  } catch (e) {
    if (clash(e)) return null;                           // settled meanwhile (the cron and an admin at once)
    throw e;
  }
  return { date, slot, payouts };
}
