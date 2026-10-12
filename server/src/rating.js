// The driver rating and the world ranking (like iRacing's iRating), and each daily's results kept for the driver
// pages (src/drivers.js).
//
// What counts (the user's choices, 2026-10-11): both dailies and cup matches; not 1V1s, not league events (friends or
// a second account could farm them). Everyone starts at RATING.start on the day it is switched on (RATING_FROM in
// wrangler.toml: a fresh start, nothing before it is rated). A daily is a race of everyone on its board: the finishers
// by their place, every DNF (retired, invalid, a start that never finished) last, together. Each pair of drivers in it
// is an Elo game: the expected score from the rating gap; a driver's change is K times (score - expected), spread over
// the field by its square root, so a big field moves a rating more than a 1V1 but not field-size times more. A driver's
// first RATING.newRaces races move it faster (kNew). A cup match is a race of two; one that nobody finished, or a dead
// heat, is not rated. The world ranking lists everyone with a rating (banned drivers left out).
//
// Each daily is taken once its day is over and settled (the cron, resultsTick): its results go to daily_results (the
// driver pages; every day since FIRST_DAY, also before RATING_FROM) and, from RATING_FROM, into the ratings. A daily
// or a cup match is taken once (daily_done, rating_done: a second go clashes on their keys and changes nothing). The
// free plan allows 50 D1 queries a cron run: a few dailies a run, each a handful of bulk statements.

export const RATING = { start: 1500, k: 32, kNew: 48, newRaces: 10, scale: 400 };

/** Is the rating on for a day (YYYY-MM-DD)? */
export const ratingOn = (env, date) => !!env.RATING_FROM && date >= env.RATING_FROM;

/** A race's places from a board's entries ({steamId, status, totalMs}): finishers by their time (equal times share a
 *  place), every DNF last together. -> [{steamId, pos}] */
export function racePlaces(entries) {
  const fin = entries.filter((e) => e.status === 'finished' && e.totalMs != null).sort((a, b) => a.totalMs - b.totalMs);
  const out = [];
  fin.forEach((e, i) => out.push({ steamId: e.steamId, pos: i && e.totalMs === fin[i - 1].totalMs ? out[i - 1].pos : i + 1 }));
  const last = fin.length + 1;
  for (const e of entries) if (!(e.status === 'finished' && e.totalMs != null)) out.push({ steamId: e.steamId, pos: last });
  return out;
}

/** The rating changes of one race. field: [{steamId, pos, rating, races}] (rating / races: what they have, undefined
 *  for someone new). -> Map steamId -> change (rounded to 0.1) */
export function raceDeltas(field) {
  const out = new Map();
  const n = field.length;
  if (n < 2) return out;
  const r = field.map((d) => (d.rating == null ? RATING.start : d.rating));
  field.forEach((d, i) => {
    let score = 0, expected = 0;
    field.forEach((o, j) => {
      if (i === j) return;
      score += d.pos < o.pos ? 1 : d.pos === o.pos ? 0.5 : 0;
      expected += 1 / (1 + 10 ** ((r[j] - r[i]) / RATING.scale));
    });
    const k = (d.races || 0) < RATING.newRaces ? RATING.kNew : RATING.k;
    out.set(d.steamId, Math.round(10 * k * (score - expected) / Math.sqrt(n - 1)) / 10);
  });
  return out;
}

/** What drivers have now: Map steamId -> {rating, races} (one query). */
export async function ratingsOf(env, ids) {
  if (!ids.length) return new Map();
  const { results } = await env.DB.prepare('SELECT steam_id, rating, races FROM ratings WHERE steam_id IN (SELECT value FROM json_each(?))')
    .bind(JSON.stringify(ids)).all();
  return new Map(results.map((x) => [x.steam_id, { rating: x.rating, races: x.races }]));
}

/** The statements applying a race's changes (in the batch with what makes it happen once): ratings, their history.
 *  changes: [{steamId, delta, before}] (before: undefined for someone new). */
export function ratingStmts(env, changes, ref, now) {
  if (!changes.length) return [];
  const rows = changes.map((c) => ({ id: c.steamId, d: c.delta, after: Math.round(10 * ((c.before == null ? RATING.start : c.before) + c.delta)) / 10 }));
  const j = JSON.stringify(rows);
  return [
    env.DB.prepare(`INSERT INTO ratings (steam_id, rating, races, peak, updated)
        SELECT json_extract(j.value, '$.id'), ?2 + json_extract(j.value, '$.d'), 1, MAX(?2, ?2 + json_extract(j.value, '$.d')), ?3
          FROM json_each(?1) j WHERE true
      ON CONFLICT(steam_id) DO UPDATE SET rating = ratings.rating + (excluded.rating - ?2), races = ratings.races + 1,
        peak = MAX(ratings.peak, ratings.rating + (excluded.rating - ?2)), updated = excluded.updated`).bind(j, RATING.start, now),
    env.DB.prepare(`INSERT INTO rating_history (steam_id, ref, delta, after, created)
        SELECT json_extract(j.value, '$.id'), ?2, json_extract(j.value, '$.d'), json_extract(j.value, '$.after'), ?3 FROM json_each(?1) j`)
      .bind(j, ref, now),
  ];
}

/** A cup's decided matches, rated (with RATING_FROM on): the statements for the batch deciding them. decided:
 *  [{id, a, b, winner, note}] (a bye, nobody finishing or a dead heat: not rated). */
export async function cupMatchStmts(env, decided, now) {
  const rated = decided.filter((d) => d.a && d.b && d.winner && !/^(nobody finished|a dead heat)/.test(d.note || ''));
  if (!rated.length) return [];
  const have = await ratingsOf(env, rated.flatMap((d) => [d.a, d.b]));
  const stmts = [env.DB.prepare('INSERT INTO rating_done (ref, created) SELECT value, ? FROM json_each(?)')
    .bind(now, JSON.stringify(rated.map((d) => `cup:${d.id}`)))];
  for (const d of rated) {
    const field = [d.a, d.b].map((sid) => ({ steamId: sid, pos: sid === d.winner ? 1 : 2, ...(have.get(sid) || {}) }));
    const deltas = raceDeltas(field);
    stmts.push(...ratingStmts(env, field.map((f) => ({ steamId: f.steamId, delta: deltas.get(f.steamId), before: f.rating })), `cup:${d.id}`, now));
  }
  return stmts;
}

// ------------------------------------------------------------------ the dailies: results and ratings, once a day

const SETTLED_MS = 24 * 3600000 + 65 * 60000;   // a day's dailies are taken at 01:05 UTC the next day (late runs, DNFs)
const PER_RUN = 2;                               // dailies taken a cron run (the first runs catch up on the past days)
const day = (t) => new Date(t).toISOString().slice(0, 10);

/** The cron's part: the next dailies not taken yet, oldest first (from `first`, the first day ACR Daily had): their
 *  results kept and, from RATING_FROM, rated. board(date, slot): the daily's board (index.js leaderboard).
 *  -> [{date, slot, drivers, rated}] */
export async function resultsTick(env, now, board, { first, slots = 2, perRun = PER_RUN } = {}) {
  const { results } = await env.DB.prepare('SELECT date, slot FROM daily_done WHERE date >= ?').bind(first).all();
  const done = new Set(results.map((r) => `${r.date}/${r.slot}`));
  const out = [];
  for (let t = Date.parse(first + 'T00:00:00Z'); t + SETTLED_MS <= now && out.length < perRun; t += 86400000) {
    for (let slot = 1; slot <= slots && out.length < perRun; slot++) {
      const date = day(t);
      if (done.has(`${date}/${slot}`)) continue;
      out.push(await takeDaily(env, date, slot, now, await board(date, slot)));
    }
  }
  return out;
}

/** One daily taken: its results kept, rated from RATING_FROM, marked done, all in one batch (a second go: nothing). */
export async function takeDaily(env, date, slot, now, b) {
  const entries = (b && b.entries) || [];
  const rated = ratingOn(env, date) && entries.length >= 2;
  const places = racePlaces(entries);
  const posOf = new Map(places.map((p) => [p.steamId, p.pos]));
  const have = rated ? await ratingsOf(env, entries.map((e) => e.steamId)) : new Map();
  const deltas = rated ? raceDeltas(places.map((p) => ({ ...p, ...(have.get(p.steamId) || {}) }))) : new Map();
  const st = entries.length ? await env.DB.prepare('SELECT track, car FROM runs WHERE date = ? AND slot = ? LIMIT 1').bind(date, slot).first() : null;
  const ref = `daily:${date}/${slot}`;
  const rows = entries.map((e) => {
    const fin = e.status === 'finished' && e.totalMs != null;
    return { id: e.steamId, place: fin ? posOf.get(e.steamId) : null, status: fin ? 'finished' : 'dnf', t: fin ? e.totalMs : null,
      gap: fin ? e.gapMs : null, run: e.runId || null, d: rated ? deltas.get(e.steamId) : null };
  });
  try {
    await env.DB.batch([
      env.DB.prepare('INSERT INTO daily_done (date, slot, rated, created) VALUES (?, ?, ?, ?)').bind(date, slot, rated ? 1 : 0, now),
      ...(rows.length ? [env.DB.prepare(`INSERT OR REPLACE INTO daily_results (date, slot, steam_id, place, field, status, total_ms, gap_ms,
          run_id, track, car, delta)
        SELECT ?1, ?2, json_extract(j.value, '$.id'), json_extract(j.value, '$.place'), ?3, json_extract(j.value, '$.status'),
          json_extract(j.value, '$.t'), json_extract(j.value, '$.gap'), json_extract(j.value, '$.run'), ?4, ?5, json_extract(j.value, '$.d')
        FROM json_each(?6) j`).bind(date, slot, entries.length, st ? st.track : null, st ? st.car : null, JSON.stringify(rows))] : []),
      ...(rated ? [env.DB.prepare('INSERT INTO rating_done (ref, created) VALUES (?, ?)').bind(ref, now),
        ...ratingStmts(env, entries.map((e) => ({ steamId: e.steamId, delta: deltas.get(e.steamId),
          before: (have.get(e.steamId) || {}).rating })), ref, now)] : []),
    ]);
  } catch (e) {
    if (!/UNIQUE|constraint/i.test(String((e && e.message) || e))) throw e;   // (taken already)
    return { date, slot, drivers: entries.length, rated: false, already: true };
  }
  return { date, slot, drivers: entries.length, rated };
}

// ------------------------------------------------------------------ the world ranking

/** A page of the world ranking (everyone rated, banned drivers left out), by country if asked: -> {total, rows}. */
export async function rankingPage(env, { country = null, page = 1, size = 100 } = {}) {
  const where = `p.banned = 0${country ? ' AND p.country = ?' : ''}`;
  const binds = country ? [country] : [];
  const [rows, total] = await env.DB.batch([
    env.DB.prepare(`SELECT r.steam_id, r.rating, r.races, r.peak, p.name, p.avatar, p.country, t.tag, t.color AS tag_color, t.id AS team_id, t.tag_fmt
        FROM ratings r JOIN players p ON p.steam_id = r.steam_id LEFT JOIN team_members m ON m.steam_id = r.steam_id
        LEFT JOIN teams t ON t.id = m.team_id
       WHERE ${where} ORDER BY r.rating DESC, r.races DESC, r.steam_id LIMIT ? OFFSET ?`).bind(...binds, size, (page - 1) * size),
    env.DB.prepare(`SELECT COUNT(*) AS n FROM ratings r JOIN players p ON p.steam_id = r.steam_id WHERE ${where}`).bind(...binds),
  ]);
  return { total: total.results[0].n, page, size, rows: rows.results.map((x, i) => ({ rank: (page - 1) * size + i + 1,
    steamId: x.steam_id, name: x.name, avatar: x.avatar || null, country: x.country || null, rating: Math.round(x.rating),
    races: x.races, peak: Math.round(x.peak), team: x.tag ? { id: x.team_id, tag: x.tag, color: x.tag_color, tagFmt: x.tag_fmt || null } : null })) };
}

/** A driver's place in the world ranking: {rating, races, peak, rank, of} or null (not rated yet). */
export const RANK_SQL = `SELECT x.rating, x.races, x.peak,
    (SELECT COUNT(*) FROM ratings r JOIN players p ON p.steam_id = r.steam_id WHERE p.banned = 0 AND r.rating > x.rating) + 1 AS rank,
    (SELECT COUNT(*) FROM ratings r JOIN players p ON p.steam_id = r.steam_id WHERE p.banned = 0) AS total
  FROM ratings x WHERE x.steam_id = ?`;
export const rankOut = (r) => (r ? { rating: Math.round(r.rating), races: r.races, peak: Math.round(r.peak), rank: r.rank, of: r.total } : null);
