// Official leagues: ACR Daily's own championships, made by the site's admin (POST /api/admin/league; tools/admin.py
// league), never by a driver, as official cups are (src/cups.js). Owned by "acr-daily", which is no driver: the league's
// settings, banner and rounds change through the admin, and the drivers it names in `admins` run it on the website as
// its admins (events, seasons, stewarding, the invite code, the members). Public or private like any league (private:
// only with its invite link). Its page and the leagues list say "official"; public ones are listed first.
//
// Its rounds come from a plan (b.rounds): one event every `everyDays` (a week by default) from its start, each in the next rally of the plan's list, all in one season (its championship). Each round's stages are
// drawn from its rally's own (cups.js drawStages: never two on the same road, or where the rally hasn't the roads, a
// road again only the other way), the ones earlier rounds raced last; each stage's weather is drawn from the rally's
// odds (conditions.js RALLY_WEATHER) unless the plan sets it. Everything is hidden by default until the round ends
// (src/hidden.js). Sending the plan again makes only the rounds not made yet (a longer plan: the weeks after).

import { drawStages } from './cups.js';
import { RALLY_WEATHER } from './conditions.js';
import { catalog, checkBanner, checkEvent, checkLeague, checkSeason, LIMITS, newCode, newLeagueId, OFFICIAL_OWNER, RALLIES,
  showCode, text } from './leagues.js';
import { routesRows, storeBanner } from './leaguesapi.js';

export const OFFICIAL_LEAGUE = { maxWeeks: 52, startWithinDays: 60, admins: 10, maxEveryDays: 28 };
const DAY = 86400000;
const STEAM_ID = /^\d{17}$/;

/** A stage's weather, drawn from its rally's odds (a rally not listed: Alsace's, no snow). rand() -> [0, 1). */
export function drawWeather(rally, rand = Math.random) {
  const odds = RALLY_WEATHER[rally] || RALLY_WEATHER.Alsace;
  const list = Object.entries(odds);
  let r = rand() * list.reduce((a, [, x]) => a + x, 0);
  for (const [w, x] of list) { r -= x; if (r < 0) return w; }
  return list[list.length - 1][0];
}

/** A round's name from the plan's: "{n}" its number, "{rally}" its rally. */
const roundName = (tpl, n, rally) => text(String(tpl || 'Round {n} · {rally}').replace(/\{n\}/g, n).replace(/\{rally\}/g, rally), LIMITS.name);

/** The rounds a plan makes (no database). plan = {starts (ms), weeks, everyDays (7), rallies: [names, in turn], name
 *  ("Round {n} · {rally}"), car | carClass | carClasses, rules, hide, stages: [{day, service, time, weather?}] (the
 *  slots every round fills), maxKm}; routes: [{track, stage_id, length}]; made: Set of the opens (ms) of the rounds
 *  made already (skipped); used: Set of the tracks raced so far (drawn last; the new rounds' added). -> {value: [{n,
 *  ...checkEvent's value}]} or {error}. */
export function planRounds(plan, routes, { made = new Set(), used = new Set(), now = Date.now(), rand = Math.random } = {}) {
  if (!plan || typeof plan !== 'object') return { error: 'rounds: {starts, weeks, rallies, stages, carClass | car}' };
  const starts = Math.round(+plan.starts), weeks = Number(plan.weeks), every = plan.everyDays == null ? 7 : Number(plan.everyDays);
  if (!Number.isFinite(starts)) return { error: 'rounds.starts: when the first round opens' };
  if (starts > now + OFFICIAL_LEAGUE.startWithinDays * DAY) return { error: `the first round opens within ${OFFICIAL_LEAGUE.startWithinDays} days` };
  if (!Number.isInteger(weeks) || weeks < 1 || weeks > OFFICIAL_LEAGUE.maxWeeks) return { error: `rounds.weeks: 1 to ${OFFICIAL_LEAGUE.maxWeeks}` };
  if (!Number.isInteger(every) || every < 1 || every > OFFICIAL_LEAGUE.maxEveryDays) return { error: `rounds.everyDays: 1 to ${OFFICIAL_LEAGUE.maxEveryDays}` };
  const rallies = Array.isArray(plan.rallies) ? plan.rallies.map(String) : [];
  if (!rallies.length || !rallies.every((r) => RALLIES.includes(r))) return { error: `rounds.rallies: some of ${RALLIES.join(', ')}` };
  const slots = Array.isArray(plan.stages) ? plan.stages : [];
  if (!slots.length) return { error: 'rounds.stages: the stages every round has ({day, time})' };
  const maxKm = Number(plan.maxKm) > 0 ? Number(plan.maxKm) : null;
  const cat = catalog(routes);
  const pools = new Map(cat.rallies.map((r) => [r.name, r.stages.map((s) => ({ track: s.track, stageId: s.stageId, lengthM: s.lengthM }))]));
  const taken = new Set(used);
  const out = [];
  for (let w = 0; w < weeks; w++) {
    const opens = starts + w * every * DAY, closes = opens + every * DAY, n = w + 1;
    if (made.has(opens) || closes < now + 3600000) continue;        // made already, or over
    const rally = rallies[w % rallies.length];
    const template = slots.map((s) => ({ day: s && s.day, service: !!(s && s.service), time: s && s.time,
      weather: (s && s.weather) || drawWeather(rally, rand) }));
    const stages = drawStages(pools.get(rally) || [], template, taken, maxKm, rand, { twice: true });
    if (!stages) return { error: `round ${n}: ${rally} hasn't the stages for ${slots.length} a round` };
    const c = checkEvent({ name: roundName(plan.name, n, rally), rally, car: plan.car, carClass: plan.carClass,
      carClasses: plan.carClasses, rules: plan.rules, hide: plan.hide, stages, opens, closes }, cat, now);
    if (c.error) return { error: `round ${n}: ${c.error}` };
    for (const s of c.value.stages) taken.add(s.track);
    out.push({ n, ...c.value });
  }
  return { value: out };
}

/** ACR Daily's own leagues, from the site's admin: b = {name, about, public, banner (base64 PNG/JPEG/WebP, about 3:1),
 *  admins: [steam ids], season: {name, points, power, drop}, rounds: a plan (planRounds)} makes one; with {id} it
 *  changes one (what is given; the season found by its name, made if new; the plan's rounds not made yet added, in
 *  that season: the plan without a season makes one-offs).
 *  rand: the draws (tests). -> {id, invite, public, seasonId, rounds: [{id, name, rally, opens, closes}]} or {error, status} */
export async function adminLeague(env, b, now, rand = Math.random) {
  if (!b || typeof b !== 'object') return { error: 'nothing sent' };
  const old = b.id ? await env.DB.prepare("SELECT * FROM leagues WHERE id = ? AND official = 1 AND kind = 'league'").bind(String(b.id)).first() : null;
  if (b.id && !old) return { error: 'no official league with that id', status: 404 };
  const has = (k) => b[k] !== undefined && b[k] !== null;
  const c = checkLeague({ name: has('name') ? b.name : old ? old.name : '', about: has('about') ? b.about : old ? old.about : '',
    public: has('public') ? b.public : old ? !!old.public : true });
  if (c.error) return { error: c.error };
  const admins = has('admins') ? (Array.isArray(b.admins) ? b.admins.map(String) : null) : [];
  if (!admins || admins.length > OFFICIAL_LEAGUE.admins || !admins.every((s) => STEAM_ID.test(s))) {
    return { error: `admins: up to ${OFFICIAL_LEAGUE.admins} Steam ids (17 digits)` };
  }
  const season = has('season') ? checkSeason(b.season) : null;
  if (season && season.error) return { error: `the season: ${season.error}` };
  let banner = null;
  if (has('banner')) {
    let bytes;
    try { bytes = Uint8Array.from(atob(String(b.banner)), (ch) => ch.charCodeAt(0)); } catch { return { error: 'the banner: base64, please' }; }
    const k = checkBanner(bytes);
    if (k.error) return { error: `the banner: ${k.error}`, status: k.status };
    banner = { bytes, type: k.value.type };
  }
  let rounds = [];
  if (has('rounds')) {
    const evs = old ? (await env.DB.prepare('SELECT opens, stages FROM league_events WHERE league_id = ?').bind(old.id).all()).results : [];
    const p = planRounds(b.rounds, await routesRows(env), { made: new Set(evs.map((e) => e.opens)),
      used: new Set(evs.flatMap((e) => JSON.parse(e.stages).map((s) => s.track))), now, rand });
    if (p.error) return { error: p.error };
    if (evs.length + p.value.length > LIMITS.eventsPerLeague) return { error: `at most ${LIMITS.eventsPerLeague} events in a league` };
    rounds = p.value;
  }

  // everything checked: the writes
  let id = old && old.id;
  if (old) {
    await env.DB.prepare('UPDATE leagues SET name = ?, about = ?, public = ? WHERE id = ?')
      .bind(c.value.name, c.value.about, c.value.public, id).run();
  } else {
    for (let tries = 0; tries < 5 && !id; tries++) {
      const nid = newLeagueId();
      const r = await env.DB.prepare(`INSERT OR IGNORE INTO leagues (id, name, about, owner, public, code, created, official)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)`).bind(nid, c.value.name, c.value.about, OFFICIAL_OWNER.id, c.value.public, newCode(), now).run();
      if (r.meta.changes) id = nid;
    }
    if (!id) return { error: 'try again', status: 503 };
  }
  if (admins.length) {
    await env.DB.batch(admins.map((sid) => env.DB.prepare(`INSERT INTO league_members (league_id, steam_id, joined, role)
      VALUES (?, ?, ?, 'admin') ON CONFLICT (league_id, steam_id) DO UPDATE SET role = 'admin'`).bind(id, sid, now)));
  }
  let seasonId = null;
  if (season) {
    const v = season.value;
    const s = await env.DB.prepare('SELECT id FROM league_seasons WHERE league_id = ? AND name = ?').bind(id, v.name).first();
    if (s) {
      seasonId = s.id;
      await env.DB.prepare('UPDATE league_seasons SET points = ?, power = ?, drop_worst = ? WHERE id = ?')
        .bind(JSON.stringify(v.points), JSON.stringify(v.power), v.drop, s.id).run();
    } else {
      seasonId = (await env.DB.prepare(`INSERT INTO league_seasons (league_id, name, points, power, drop_worst, created)
        VALUES (?, ?, ?, ?, ?, ?)`).bind(id, v.name, JSON.stringify(v.points), JSON.stringify(v.power), v.drop, now).run()).meta.last_row_id;
    }
  }
  if (banner) await storeBanner(env, id, banner.bytes, banner.type, now);
  const made = rounds.length ? await env.DB.batch(rounds.map((v) => env.DB.prepare(`INSERT INTO league_events (league_id, season_id,
    name, rally, car, car_class, car_classes, rules, stages, opens, closes, created, hide) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(id, seasonId, v.name, v.rally, v.car, v.car_class, v.car_classes ? JSON.stringify(v.car_classes) : null, JSON.stringify(v.rules),
      JSON.stringify(v.stages), v.opens, v.closes, now, v.hide ? JSON.stringify(v.hide) : null))) : [];
  const l = await env.DB.prepare('SELECT code, public FROM leagues WHERE id = ?').bind(id).first();
  return { id, invite: showCode(l.code), public: !!l.public, seasonId,
    // (not the stages: whoever runs this may drive the league too)
    rounds: rounds.map((v, k) => ({ id: made[k].meta.last_row_id, name: v.name, rally: v.rally, stages: v.stages.length,
      opens: v.opens, closes: v.closes })) };
}
