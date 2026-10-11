// 1V1s (head-to-heads, h2h in the code, the API and the database; /1v1 on the website): a driver challenges another to
// an event of their own making (the stages, the car, the window), with
// a stake each (0: a friendly; stakes need credits on). The challenged driver accepts (their stake is taken then) or
// declines; not accepted within a day (H2H.answerMs), it expires. Accepted, it is a match both drive from the app's
// LEAGUES view (src/leaguesapi.js holders), each whenever they like inside the window: the lower total wins both
// stakes. Nobody finishing, or a dead heat: the stakes go back. Settled by the cron (socialTick in index.js) once the
// window and its grace are over. Each step is a notice in both drivers' inboxes (src/social.js).
//
//   GET  /api/h2h                                   my head-to-heads: {incoming, outgoing, active, past}
//   POST /api/h2h {opponent, stake, event}          a challenge (event: {name?, rally, car | carClass, rules, stages,
//                                                   opens, closes}, as a league event)
//   POST /api/h2h/<id>/accept | decline | cancel    (cancel: the challenger, before it is answered)

import { stageParts } from './conditions.js';
import { clash, giveWhenStmts, takeWhenStmts } from './credits.js';
import { LIMITS, text } from './leagues.js';
import { checkMatchSpec, makeHolder, makeMatchEvent, matchRows } from './leaguesapi.js';
import { blocks, noticeStmt } from './social.js';

export const H2H = { maxStake: 1000, answerMs: 86400000, pending: 5, windowDays: 14 };

/** The result of a head-to-head from its match's standings rows (eventStandings): -> {winner: steamId | null,
 *  note}. The lower total of the finishers wins; one finisher wins; nobody finishing, or a dead heat: no contest. */
export function h2hOutcome(rows, a, b) {
  const fin = rows.filter((r) => r.status === 'finished' && (r.steamId === a || r.steamId === b));
  if (!fin.length) return { winner: null, note: 'nobody finished' };
  if (fin.length === 2 && fin[0].totalMs === fin[1].totalMs) return { winner: null, note: 'a dead heat' };
  const w = fin[0];
  return { winner: w.steamId, note: fin.length === 2 ? `by ${((fin[1].totalMs - w.totalMs) / 1000).toFixed(3)} s` : 'the only finisher' };
}

const nameOf = async (env, sid) => ((await env.DB.prepare('SELECT name FROM players WHERE steam_id = ?').bind(sid).first()) || {}).name || 'a driver';

/** A challenge as the website shows it. */
function h2hOut(r, me) {
  const spec = JSON.parse(r.spec);
  return {
    id: r.id, status: r.status, stake: r.stake, mine: r.challenger === me ? 'challenger' : 'opponent',
    challenger: { steamId: r.challenger, name: r.c_name, avatar: r.c_avatar || null },
    opponent: { steamId: r.opponent, name: r.o_name, avatar: r.o_avatar || null },
    name: spec.name, rally: spec.rally, car: spec.car, carClass: spec.car_class, opens: spec.opens, closes: spec.closes,
    stages: spec.stages.map((s) => ({ name: stageParts(s.track).stageName, weather: s.weather, time: s.time })),
    rules: spec.rules, answerBy: r.answer_by, eventId: r.event_id, winner: r.winner, note: r.note, created: r.created,
  };
}

const H2H_SQL = `SELECT h.*, c.name AS c_name, c.avatar AS c_avatar, o.name AS o_name, o.avatar AS o_avatar FROM h2h h
  JOIN players c ON c.steam_id = h.challenger JOIN players o ON o.steam_id = h.opponent`;

export async function h2hApi(req, env, path, me, sameOrigin, now, { json, err }) {
  if (!path.startsWith('/api/h2h')) return null;
  if (!me) return err('sign in with Steam first', 401);
  const post = req.method === 'POST';
  if (path === '/api/h2h' && !post) {
    const { results } = await env.DB.prepare(`${H2H_SQL} WHERE h.challenger = ?1 OR h.opponent = ?1 ORDER BY h.id DESC LIMIT 60`)
      .bind(me.steam_id).all();
    const all = results.map((r) => h2hOut(r, me.steam_id));
    return json({
      incoming: all.filter((h) => h.status === 'sent' && h.mine === 'opponent'),
      outgoing: all.filter((h) => h.status === 'sent' && h.mine === 'challenger'),
      active: all.filter((h) => h.status === 'accepted'),
      past: all.filter((h) => !['sent', 'accepted'].includes(h.status)),
      credits: !!env.CREDITS_FROM, maxStake: H2H.maxStake,
    });
  }
  if (!post) return err('not found', 404);
  if (!sameOrigin) return err('refused: not from this site', 403);
  if (me.banned) return err('this account is banned', 403);
  const b = await req.json().catch(() => ({})) || {};

  if (path === '/api/h2h') {                              // a challenge
    const opp = await env.DB.prepare('SELECT steam_id, name, banned FROM players WHERE steam_id = ?').bind(String(b.opponent || '')).first();
    if (!opp || opp.banned) return err('no such driver', 404);
    if (opp.steam_id === me.steam_id) return err('challenge someone else');
    if (await blocks(env, opp.steam_id, me.steam_id)) return err('this driver takes no challenges from you', 403);
    const stake = b.stake == null || b.stake === '' ? 0 : Number(b.stake);
    if (!Number.isInteger(stake) || stake < 0 || stake > H2H.maxStake) return err(`the stake: 0 to ${H2H.maxStake} credits`);
    if (stake && !env.CREDITS_FROM) return err('stakes need credits, which are not on yet: make it a friendly (0)', 409);
    const open = await env.DB.prepare("SELECT COUNT(*) AS n FROM h2h WHERE challenger = ? AND status = 'sent'").bind(me.steam_id).first();
    if (open.n >= H2H.pending) return err(`${H2H.pending} challenges waiting for an answer at most`, 409);
    const ev = b.event || {};
    const c = await checkMatchSpec(env, { ...ev, name: text(ev.name, LIMITS.name) || `${me.name} vs ${opp.name}` }, now);
    if (c.error) return err(c.error);
    const spec = c.value;
    if (spec.closes - spec.opens > H2H.windowDays * 86400000 || spec.opens > now + H2H.windowDays * 86400000) {
      return err(`a 1V1 is open for ${H2H.windowDays} days at most, from within the next ${H2H.windowDays} days`);
    }
    const answerBy = Math.min(now + H2H.answerMs, spec.closes - 3600000);
    const me2 = [me.steam_id, now];
    // the challenge and the challenger's stake together: the row only when they have the credits, the stake only with it
    await env.DB.batch([
      env.DB.prepare(`INSERT INTO h2h (challenger, opponent, stake, spec, status, created, answer_by)
        SELECT ?1, ?2, ?3, ?4, 'sent', ?5, ?6 WHERE ?3 = 0 OR (SELECT balance FROM credits WHERE steam_id = ?1) >= ?3`)
        .bind(me.steam_id, opp.steam_id, stake, JSON.stringify(spec), now, answerBy),
      env.DB.prepare('UPDATE credits SET balance = balance - ?1 WHERE steam_id = ?2 AND ?1 > 0 AND EXISTS (SELECT 1 FROM h2h WHERE challenger = ?2 AND created = ?3)')
        .bind(stake, ...me2),
      env.DB.prepare(`INSERT INTO credit_ledger (steam_id, delta, kind, ref, note, created) SELECT ?1, -?2, 'h2h-stake', 'h2h:' || id, ?3, ?4
        FROM h2h WHERE challenger = ?1 AND created = ?4 AND ?2 > 0`).bind(me.steam_id, stake, `vs ${opp.name}`, now),
      env.DB.prepare(`INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT ?1, NULL, 'h2h', ?2, 'h2h:' || id, ?3
        FROM h2h WHERE challenger = ?4 AND created = ?3`).bind(opp.steam_id,
        `${me.name} challenges you: ${spec.name}, ${spec.rally}, ${spec.stages.length} stage${spec.stages.length > 1 ? 's' : ''}` +
        (stake ? `, ${stake} credits each` : ', a friendly') + '. Answer within a day.', now, me.steam_id),
    ]);
    const row = await env.DB.prepare('SELECT id FROM h2h WHERE challenger = ? AND created = ?').bind(...me2).first();
    if (!row) return err(`the stake is ${stake} credits: you have ${((await env.DB.prepare('SELECT balance FROM credits WHERE steam_id = ?').bind(me.steam_id).first()) || { balance: 0 }).balance}`, 402);
    return json({ id: row.id, status: 'sent' });
  }

  const m = path.match(/^\/api\/h2h\/(\d+)\/(accept|decline|cancel)$/);
  if (!m) return err('not found', 404);
  const h = await env.DB.prepare('SELECT * FROM h2h WHERE id = ?').bind(+m[1]).first();
  if (!h || (h.challenger !== me.steam_id && h.opponent !== me.steam_id)) return err('no such challenge', 404);
  const spec = JSON.parse(h.spec);
  if (h.status !== 'sent') return err(`this challenge is ${h.status}`, 409);
  const other = h.challenger === me.steam_id ? h.opponent : h.challenger;
  if (m[2] === 'decline' || m[2] === 'cancel') {
    if ((m[2] === 'decline') !== (h.opponent === me.steam_id)) return err(m[2] === 'decline' ? 'only the challenged driver declines' : 'only the challenger cancels', 403);
    const status = m[2] === 'decline' ? 'declined' : 'cancelled';
    const done = ['EXISTS (SELECT 1 FROM h2h WHERE id = ? AND status = ? AND answered = ?)', [h.id, status, now]];
    await env.DB.batch([
      env.DB.prepare("UPDATE h2h SET status = ?, answered = ? WHERE id = ? AND status = 'sent'").bind(status, now, h.id),
      ...(h.stake ? giveWhenStmts(env, h.challenger, h.stake, 'h2h-refund', `h2h:${h.id}`, status, now, ...done) : []),
      noticeStmt(env, other, 'h2h', `${me.name} ${status} the 1V1 ${spec.name}` + (h.stake && status === 'declined' ? ': your stake is back.' : '.'),
        `h2h:${h.id}`, now, ...done),
    ]);
    const after = await env.DB.prepare('SELECT status FROM h2h WHERE id = ?').bind(h.id).first();
    return after.status === status ? json({ status }) : err(`this challenge is ${after.status}`, 409);
  }
  // accept: the opponent's stake, then the match
  if (h.opponent !== me.steam_id) return err('only the challenged driver accepts', 403);
  if (now >= h.answer_by) return err('too late: it has expired', 409);
  await env.DB.batch([
    env.DB.prepare(`UPDATE h2h SET status = 'accepted', answered = ?1 WHERE id = ?2 AND status = 'sent'
      AND (stake = 0 OR (SELECT balance FROM credits WHERE steam_id = ?3) >= stake)`).bind(now, h.id, me.steam_id),
    ...(h.stake ? takeWhenStmts(env, me.steam_id, h.stake, 'h2h-stake', `h2h:${h.id}`, `vs ${await nameOf(env, other)}`, now,
      "EXISTS (SELECT 1 FROM h2h WHERE id = ? AND status = 'accepted' AND answered = ?)", [h.id, now]) : []),
  ]);
  const now2 = await env.DB.prepare('SELECT status, answered FROM h2h WHERE id = ?').bind(h.id).first();
  if (now2.status !== 'accepted' || now2.answered !== now) {
    return now2.status === 'sent' ? err(`the stake is ${h.stake} credits: you have ${((await env.DB.prepare('SELECT balance FROM credits WHERE steam_id = ?').bind(me.steam_id).first()) || { balance: 0 }).balance}`, 402)
      : err(`this challenge is ${now2.status}`, 409);
  }
  const eventId = await openMatch(env, h, spec, now);
  await noticeStmt(env, other, 'h2h', `${me.name} accepted ${spec.name}: drive it from ACR Daily's LEAGUES view.`, `h2h:${h.id}`, now).run();
  return json({ status: 'accepted', eventId });
}

/** An accepted head-to-head's match: its holder and its event (also the cron's, if accepting stopped half-way). */
async function openMatch(env, h, spec, now) {
  const [cn, on] = [await nameOf(env, h.challenger), await nameOf(env, h.opponent)];
  let holder = h.holder;
  if (!holder) {                                         // (kept at once: a retry uses it, not a second one)
    holder = await makeHolder(env, { kind: 'h2h', name: `1V1: ${cn} vs ${on}`, owner: h.challenger,
      members: [h.challenger, h.opponent] }, now);
    await env.DB.prepare('UPDATE h2h SET holder = ? WHERE id = ?').bind(holder, h.id).run();
  }
  const eventId = await makeMatchEvent(env, holder, spec, spec.name, [h.challenger, h.opponent], spec.opens,
    Math.max(spec.closes, now + 3600000), now);
  await env.DB.prepare('UPDATE h2h SET event_id = ? WHERE id = ?').bind(eventId, h.id).run();
  return eventId;
}

/** The cron's part: challenges not answered in time expire (the stake back), an accepted one without its match gets
 *  it, and those whose window (and grace) is over are settled. -> [{id, status, winner}] */
export async function h2hTick(env, now) {
  const out = [];
  // only what is due: answers too late, accepted ones without their match, matches closed (and their grace over); a
  // few a run (each a few queries, and the free plan allows 50 a cron run): the rest 5 minutes later
  const { results: due } = await env.DB.prepare(`SELECT h.* FROM h2h h LEFT JOIN league_events e ON e.id = h.event_id
    WHERE (h.status = 'sent' AND h.answer_by <= ?1)
       OR (h.status = 'accepted' AND (h.event_id IS NULL OR e.id IS NULL OR e.closes + ?2 <= ?1))
    ORDER BY h.id LIMIT 4`).bind(now, LIMITS.graceMs).all();
  for (const h of due) {
    const spec = JSON.parse(h.spec);
    if (h.status === 'sent') {
      const done = ["EXISTS (SELECT 1 FROM h2h WHERE id = ? AND status = 'expired' AND answered = ?)", [h.id, now]];
      await env.DB.batch([
        env.DB.prepare("UPDATE h2h SET status = 'expired', answered = ? WHERE id = ? AND status = 'sent'").bind(now, h.id),
        ...(h.stake ? giveWhenStmts(env, h.challenger, h.stake, 'h2h-refund', `h2h:${h.id}`, 'not answered', now, ...done) : []),
        noticeStmt(env, h.challenger, 'h2h', `${spec.name} was not answered in time` + (h.stake ? ': your stake is back.' : '.'), `h2h:${h.id}`, now, ...done),
      ]);
      out.push({ id: h.id, status: 'expired' });
      continue;
    }
    if (!h.event_id) { await openMatch(env, h, spec, now); continue; }
    const res = h2hOutcome(await matchRows(env, h.event_id, now), h.challenger, h.opponent);
    const pays = !h.stake ? [] : res.winner ? [[res.winner, 2 * h.stake, 'h2h-win']]
      : [[h.challenger, h.stake, 'h2h-refund'], [h.opponent, h.stake, 'h2h-refund']];
    const cond = "EXISTS (SELECT 1 FROM h2h WHERE id = ? AND status = 'settled' AND settled = ?)";
    const wn = res.winner ? await nameOf(env, res.winner) : null;
    const said = res.winner ? `${wn} won ${spec.name} (${res.note})` : `${spec.name}: no contest (${res.note})`;
    try {
      await env.DB.batch([
        env.DB.prepare("UPDATE h2h SET status = 'settled', winner = ?, note = ?, settled = ? WHERE id = ? AND status = 'accepted'")
          .bind(res.winner, res.note, now, h.id),
        ...pays.flatMap(([sid, amt, kind]) => giveWhenStmts(env, sid, amt, kind, `h2h:${h.id}`, spec.name, now, cond, [h.id, now])),
        ...[h.challenger, h.opponent].map((sid) => noticeStmt(env, sid, 'h2h', said + (h.stake ? (res.winner ? `: ${2 * h.stake} credits to ${wn}.` : ': stakes back.') : '.'),
          `h2h:${h.id}`, now, cond, [h.id, now])),
      ]);
    } catch (e) {
      if (!clash(e)) throw e;
    }
    out.push({ id: h.id, status: 'settled', winner: res.winner });
  }
  return out;
}
