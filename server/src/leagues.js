// Leagues: groups of drivers running their own multi-stage events, as in the clubs of DiRT Rally / EA WRC. This file
// holds the rules and the standings (no database); the API is src/leaguesapi.js, the Discord posts src/leaguediscord.js.
//
// A league: a name, a description, a banner, public (listed on /leagues, anyone can join) or private (only with its
// invite code: /join/<code>; a new code makes the old links stop working). Members sign in with Steam. Roles: the
// owner (who made it: its settings, banner, Discord posts, who the admins are, deleting it), admins (events, seasons,
// the invite code, removing and banning members, stewarding) and members.
// A season: a championship over some of the league's events: its points (a table from P1, then points for every other
// finisher), an optional Power Stage bonus (points for the fastest on each event's last stage) and each driver's worst
// rounds dropped. An event outside any season is a one-off.
// An event: a Rally Weekend in the game, so it follows the game's rules: one location; days, each opening with a
// service park; more service parks between stages if wanted; a start time and weather per stage; one car for everyone
// or a class; the damage, wear, failure, respawn and penalty settings. The damage is carried from stage to stage and
// repaired in the service parks by the game itself. The app sets it up in the game's save (client rallyweekend.py).
// (Hardcore Mode and driving-assist rules were worked out and shelved: docs/hardcore-and-assists.md.)
// An entry: one per driver and event, the first start counts. The stages are driven in order, in one go or over
// several sessions (the game keeps the rally between them) until the event closes; each stage's time is the game's own
// (its stage time + its penalties), read from its save by the app. A retire, a restart, a stage started a second
// time, a stage driven without the app watching or not finishing before the event closes is a DNF.
// Stewards (the owner and admins) can add time penalties (on a stage or to the total; negative gives time back) and
// disqualify an entry, each with a reason everyone sees.

import { CARS, carByName } from './cars.js';
import { stageParts, SURFACE, WEATHER } from './conditions.js';
import { menuName } from './stages.js';

export const RALLIES = ['Alsace', 'Greece', 'Monte Carlo', 'Wales'];
export const LIMITS = {
  leaguesPerOwner: 5, members: 1000, eventsPerLeague: 300, seasonsPerLeague: 50,
  days: 4, stages: 16, stagesPerDay: 8,           // the game's own presets go up to 3 days and 9 stages
  name: 60, about: 600, reason: 200, windowDays: 62,   // an event is open at most this long
  graceMs: 30 * 60000,                            // a stage finished just before the close may arrive a bit after
  penaltyMs: 3600000,                             // a steward's time penalty: at most an hour either way
};
export const LEVELS = ['off', 'light', 'severe', 'realistic'];
export const PENALTIES = ['light', 'realistic'];
export const DEFAULT_RULES = { penalty: 'light', respawn: true, damage: true, damageIntensity: 'light', wear: 'light',
  failures: 'off' };
// Points tables a season can start from (the website offers them; any other list can be typed in)
export const POINTS_PRESETS = {
  wrc: { label: 'WRC: 25-18-15-12-10-8-6-4-2-1, then 1 for every finisher', table: [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], finisher: 1 },
  top10: { label: 'Top ten only: 25-18-15-12-10-8-6-4-2-1', table: [25, 18, 15, 12, 10, 8, 6, 4, 2, 1], finisher: 0 },
};
export const POWER_PRESET = [5, 4, 3, 2, 1];      // the WRC's Power Stage bonus
export const DEFAULT_SEASON = { points: { table: POINTS_PRESETS.wrc.table, finisher: 1 }, power: [], drop: 0 };
const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';   // no 0/O, 1/I: codes are read out and typed
const ID_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789';

function random(chars, n) {
  const a = crypto.getRandomValues(new Uint8Array(n));
  return [...a].map((x) => chars[x % chars.length]).join('');
}
export const newCode = () => random(CODE_CHARS, 8);
export const newLeagueId = () => random(ID_CHARS, 8);
/** 'k7q2-m9xp ' -> 'K7Q2M9XP', or null if it can't be a code. */
export function normCode(s) {
  const c = String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  return c.length === 8 && [...c].every((x) => CODE_CHARS.includes(x)) ? c : null;
}
export const showCode = (c) => `${c.slice(0, 4)}-${c.slice(4)}`;

export const text = (v, max) => String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max);

// ------------------------------------------------------------------ what an event can be made of

/** The stages a league event can use (the routes with the game's stage id), the cars and classes, the weathers.
 *  routes: [{track, stage_id, length}]. */
export function catalog(routes) {
  const byRally = new Map(RALLIES.map((r) => [r, []]));
  for (const r of routes) {
    const { rally } = stageParts(r.track);
    if (!r.stage_id || !byRally.has(rally)) continue;
    byRally.get(rally).push({ track: r.track, stageId: r.stage_id, name: menuName(r.stage_id) || stageParts(r.track).stageName,
      lengthM: Math.round(r.length || 0) });
  }
  const classes = [];
  for (const c of CARS) if (!classes.some((k) => k.cls === c.cls)) classes.push({ cls: c.cls, group: c.group });
  return {
    rallies: RALLIES.map((name) => ({ name, surface: SURFACE[name] || null,
      stages: byRally.get(name).sort((a, b) => a.name.localeCompare(b.name)) })),
    cars: CARS.map((c) => ({ name: c.name, id: c.id, cls: c.cls, group: c.group })),
    classes,
    weathers: Object.entries(WEATHER).map(([id, w]) => ({ id, label: w.label, game: w.game })),
    rules: { penalty: PENALTIES, levels: LEVELS, defaults: DEFAULT_RULES },
    points: { presets: POINTS_PRESETS, power: POWER_PRESET, defaults: DEFAULT_SEASON },
    limits: LIMITS,
  };
}

/** A league's settings from a form: -> {value: {name, about, public}} or {error}. */
export function checkLeague(b) {
  const name = text(b && b.name, LIMITS.name);
  if (name.length < 3) return { error: 'give the league a name (3 to 60 characters)' };
  // the description keeps its line breaks (at most one empty line in a row)
  const about = String(b.about == null ? '' : b.about).replace(/\r\n?/g, '\n').replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g, ' ')
    .replace(/[ \t]+/g, ' ').replace(/ ?\n ?/g, '\n').replace(/\n{3,}/g, '\n\n').trim().slice(0, LIMITS.about);
  return { value: { name, about, public: b.public === false || b.public === 0 ? 0 : 1 } };
}

const toMin = (t) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(t || ''));
  return m && +m[1] < 24 && +m[2] < 60 ? +m[1] * 60 + +m[2] : null;
};

/** An event from the builder: b = {name, rally, car | carClass, rules, stages: [{track, day (1..), service, weather,
 *  time 'HH:MM'}], opens, closes (ms)}. cat: catalog(). -> {value: row fields} or {error}. The stages must make a
 *  calendar the game takes: one location, days in order from day 1, each day opening with a service park (set here),
 *  a later start time for each stage of a day. */
export function checkEvent(b, cat, now = Date.now()) {
  if (!b || typeof b !== 'object') return { error: 'nothing sent' };
  const name = text(b.name, LIMITS.name);
  if (name.length < 3) return { error: 'give the event a name (3 to 60 characters)' };
  const rally = cat.rallies.find((r) => r.name === b.rally);
  if (!rally) return { error: 'pick a location' };
  let car = null, carClass = null;
  if (b.car) {
    const c = carByName(b.car);
    if (!c) return { error: 'unknown car' };
    car = c.name;
  } else if (b.carClass) {
    if (!cat.classes.some((k) => k.cls === b.carClass)) return { error: 'unknown car class' };
    carClass = b.carClass;
  } else return { error: 'pick a car or a car class' };
  const r = b.rules || {};
  const rules = {
    penalty: PENALTIES.includes(r.penalty) ? r.penalty : DEFAULT_RULES.penalty,
    respawn: r.respawn === undefined ? DEFAULT_RULES.respawn : !!r.respawn,
    damage: r.damage === undefined ? DEFAULT_RULES.damage : !!r.damage,
    damageIntensity: LEVELS.includes(r.damageIntensity) ? r.damageIntensity : DEFAULT_RULES.damageIntensity,
    wear: LEVELS.includes(r.wear) ? r.wear : DEFAULT_RULES.wear,
    failures: LEVELS.includes(r.failures) ? r.failures : DEFAULT_RULES.failures,
  };
  if (rules.damage && rules.damageIntensity === 'off') rules.damageIntensity = 'light';
  const list = Array.isArray(b.stages) ? b.stages : [];
  if (!list.length) return { error: 'add at least one stage' };
  if (list.length > LIMITS.stages) return { error: `at most ${LIMITS.stages} stages` };
  const stages = [];
  for (const [k, s] of list.entries()) {
    const st = rally.stages.find((x) => x.track === (s && s.track));
    if (!st) return { error: `SS${k + 1}: pick a stage of ${rally.name}` };
    const day = Number.isInteger(s.day) ? s.day : NaN;
    const prev = stages[k - 1];
    if (k === 0 ? day !== 1 : !(day === prev.day || day === prev.day + 1)) return { error: 'the days come in order, from day 1' };
    if (!WEATHER[s.weather]) return { error: `SS${k + 1}: pick the weather` };
    const min = toMin(s.time);
    if (min === null) return { error: `SS${k + 1}: the start time is HH:MM` };
    if (prev && prev.day === day && min <= toMin(prev.time)) return { error: `SS${k + 1} starts after SS${k} on the same day` };
    stages.push({ track: st.track, day, service: !prev || prev.day !== day ? true : !!s.service, weather: s.weather,
      time: `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}` });
  }
  const days = stages[stages.length - 1].day;
  if (days > LIMITS.days) return { error: `at most ${LIMITS.days} days` };
  for (let d = 1; d <= days; d++) {
    if (stages.filter((s) => s.day === d).length > LIMITS.stagesPerDay) return { error: `at most ${LIMITS.stagesPerDay} stages a day` };
  }
  const opens = Math.round(+b.opens), closes = Math.round(+b.closes);
  if (!Number.isFinite(opens) || !Number.isFinite(closes)) return { error: 'set when the event opens and closes' };
  if (closes <= opens) return { error: 'the event closes after it opens' };
  if (closes - opens > LIMITS.windowDays * 86400000) return { error: `an event is open for at most ${LIMITS.windowDays} days` };
  if (closes < now + 3600000) return { error: 'the event must stay open for at least another hour' };
  return { value: { name, rally: rally.name, car, car_class: carClass, rules, stages, opens, closes } };
}

// ------------------------------------------------------------------ seasons

/** A list of whole points typed in ("25, 18, 15" or [25, 18, 15]) -> numbers, or null. */
function pointsList(v, max, maxLen) {
  const a = Array.isArray(v) ? v : String(v == null ? '' : v).split(/[\s,;]+/).filter(Boolean);
  if (a.length > maxLen) return null;
  const out = a.map(Number);
  return out.every((x) => Number.isInteger(x) && x >= 0 && x <= max) ? out : null;
}

/** A season from its form: b = {name, points: {table, finisher}, power, drop}. -> {value} or {error}. */
export function checkSeason(b) {
  if (!b || typeof b !== 'object') return { error: 'nothing sent' };
  const name = text(b.name, LIMITS.name);
  if (name.length < 3) return { error: 'give the season a name (3 to 60 characters)' };
  const p = b.points || {};
  const table = pointsList(p.table, 1000, 50);
  if (!table || !table.length) return { error: 'the points: whole numbers from P1 down, e.g. 25, 18, 15, 12 (50 at most)' };
  const finisher = p.finisher == null || p.finisher === '' ? 0 : Number(p.finisher);
  if (!Number.isInteger(finisher) || finisher < 0 || finisher > 100) return { error: 'the points for every other finisher: 0 to 100' };
  const power = pointsList(b.power == null ? [] : b.power, 100, 10);
  if (!power) return { error: 'the Power Stage bonus: up to 10 whole numbers from P1 down, e.g. 5, 4, 3, 2, 1' };
  while (power.length && !power[power.length - 1]) power.pop();
  const drop = b.drop == null || b.drop === '' ? 0 : Number(b.drop);
  if (!Number.isInteger(drop) || drop < 0 || drop > 10) return { error: 'worst rounds dropped: 0 to 10' };
  return { value: { name, points: { table, finisher }, power, drop } };
}

/** How a season scores, in words (the website and the Discord posts). */
export function describeSeason(s) {
  const t = s.points.table;
  let out = `${t.join('-')} points for P1–P${t.length}` + (s.points.finisher ? `, then ${s.points.finisher} for every finisher` : '');
  if (s.power && s.power.length) out += `; Power Stage (each event's last stage): ${s.power.join('-')} bonus points`;
  if (s.drop) out += `; each driver's ${s.drop === 1 ? 'worst round is' : `${s.drop} worst rounds are`} dropped`;
  return out + '. A DNF or DSQ scores nothing.';
}

// ------------------------------------------------------------------ penalties

/** A steward's time penalty: b = {steamId, seconds (negative gives time back), stage (1.., or empty for the total),
 *  reason}. -> {value: {ms, stage (0-based or null), reason}} or {error}. */
export function checkPenalty(b, nStages) {
  const ms = Math.round(Number(b && b.seconds) * 1000);
  if (!Number.isFinite(ms) || ms === 0 || Math.abs(ms) > LIMITS.penaltyMs) {
    return { error: 'a time penalty in seconds (negative gives time back), an hour at most' };
  }
  let stage = null;
  if (b.stage != null && b.stage !== '') {
    const s = Number(b.stage);
    if (!Number.isInteger(s) || s < 1 || s > nStages) return { error: 'pick a stage, or the total' };
    stage = s - 1;
  }
  const reason = text(b.reason, LIMITS.reason);
  if (reason.length < 3) return { error: 'give a reason: everyone sees it' };
  return { value: { ms, stage, reason } };
}

// ------------------------------------------------------------------ standings

export const eventStatus = (ev, now) => (now < ev.opens ? 'upcoming' : now < ev.closes ? 'open' : 'closed');

/** An entry as the boards show it: disqualified by the stewards = DSQ; running past the close (and its grace) = DNF. */
export function entryState(e, ev, now) {
  if (e.dsq) return { status: 'dsq', reason: e.dsq };
  if (e.status === 'running' && now > ev.closes + LIMITS.graceMs) return { status: 'dnf', reason: 'not finished in time' };
  return { status: e.status, reason: e.reason || '' };
}

const rankBy = (list, key, out) => list.forEach((x, i) => {
  x[out] = i && x[key] === list[i - 1][key] ? list[i - 1][out] : i + 1;
});

/** An event's standings. ev: {stages, opens, closes}; entries: rows (+ name, country, avatar; dsq = the stewards'
 *  reason); times: rows of league_stage_times; penalties: rows of league_penalties (stage_no null = on the total).
 *  -> {rows: [{steamId, name, country, avatar, car, status, reason, done, totalMs, penaltyMs (the game's), stewardMs,
 *  rank, gapMs, stages: [{timeMs, penaltyMs, stewardMs, totalMs, pos, cumPos}]}], stages: per stage [{steamId, totalMs,
 *  pos}]}. A stage's total = the game's time + its penalties + the stewards' on that stage. Order: finished by total,
 *  then still running (most stages first), then DNFs (most stages first), then DSQs. A DSQ takes no position. */
export function eventStandings(ev, entries, times, now = Date.now(), penalties = []) {
  const n = ev.stages.length;
  const byDriver = new Map(entries.map((e) => [e.steam_id, { e, t: new Array(n).fill(null), pen: new Array(n).fill(0), over: 0 }]));
  for (const t of times) {
    const d = byDriver.get(t.steam_id);
    if (d && t.stage_no >= 0 && t.stage_no < n) d.t[t.stage_no] = t;
  }
  for (const p of penalties) {
    const d = byDriver.get(p.steam_id);
    if (!d) continue;
    if (p.stage_no != null && p.stage_no >= 0 && p.stage_no < n) d.pen[p.stage_no] += p.ms;
    else d.over += p.ms;
  }
  const stageTotal = (d, k) => d.t[k].time_ms + d.t[k].penalty_ms + d.pen[k];
  // stage positions (each stage on its own) and positions after each stage (the total so far); no DSQ among them
  const stages = [];
  const cum = new Map();
  for (let k = 0; k < n; k++) {
    const on = [...byDriver.values()].filter((d) => d.t[k] && !d.e.dsq).map((d) => {
      const total = stageTotal(d, k);
      cum.set(d.e.steam_id, (cum.get(d.e.steam_id) || 0) + total);
      return { steamId: d.e.steam_id, name: d.e.name, totalMs: total, cumMs: cum.get(d.e.steam_id) };
    });
    const byStage = [...on].sort((a, b) => a.totalMs - b.totalMs);
    rankBy(byStage, 'totalMs', 'pos');
    rankBy([...on].sort((a, b) => a.cumMs - b.cumMs), 'cumMs', 'cumPos');
    stages.push(byStage);
  }
  const rows = [...byDriver.values()].map((d) => {
    const { e, t } = d;
    const st = entryState(e, ev, now);
    const done = t.filter(Boolean).length;
    // the stewards' penalties on stages not driven (yet) count on the total
    const stewardMs = d.over + d.pen.reduce((a, x) => a + x, 0);
    const totalMs = t.reduce((a, x, k) => a + (x ? stageTotal(d, k) : d.pen[k]), 0) + d.over;
    return {
      steamId: e.steam_id, name: e.name || 'Driver', country: e.country || null, avatar: e.avatar || null, car: e.car,
      status: st.status, reason: st.reason, done, totalMs, stewardMs,
      penaltyMs: t.reduce((a, x) => a + (x ? x.penalty_ms : 0), 0),
      stages: t.map((x, k) => {
        if (!x) return null;
        const s = stages[k].find((y) => y.steamId === e.steam_id) || {};
        return { timeMs: x.time_ms, penaltyMs: x.penalty_ms, stewardMs: d.pen[k], totalMs: stageTotal(d, k),
          pos: s.pos || null, cumPos: s.cumPos || null, splits: x.splits ? JSON.parse(x.splits) : null };
      }),
    };
  });
  const order = { finished: 0, running: 1, dnf: 2, dsq: 3 };
  rows.sort((a, b) => order[a.status] - order[b.status] || (a.status === 'finished' ? a.totalMs - b.totalMs
    : b.done - a.done || a.totalMs - b.totalMs) || a.name.localeCompare(b.name));
  const fin = rows.filter((r) => r.status === 'finished');
  rankBy(fin, 'totalMs', 'rank');
  fin.forEach((r) => { r.gapMs = r.totalMs - fin[0].totalMs; });
  return { rows, stages };
}

/** A season's championship. season: {points: {table, finisher}, power, drop}; events: the season's events in order,
 *  [{id, status, rows, stages}] (eventStandings() of each). Events not open yet count for nothing; those still open
 *  count as they stand. Points: the table from P1, then `finisher` for every other finisher; the Power Stage bonus for
 *  the fastest on each event's last stage (finishers only); a DNF or DSQ scores nothing. With `drop`, each driver's
 *  worst rounds (one not entered = 0) don't count once more rounds than that have been run. Ties: more wins, then more
 *  events finished. -> [{steamId, name, country, rank, points, wins, finished, cells: {eventId: {pos, pts, power,
 *  dropped, dnf, dsq, running}}}] */
export function seasonStandings(season, events) {
  const table = season.points.table, power = season.power || [];
  const run = events.filter((e) => e.status !== 'upcoming');
  const t = new Map();
  for (const ev of run) {
    const last = ev.stages[ev.stages.length - 1] || [];
    for (const r of ev.rows) {
      if (!t.has(r.steamId)) t.set(r.steamId, { steamId: r.steamId, name: r.name, country: r.country, points: 0, wins: 0, finished: 0, cells: {} });
      const p = t.get(r.steamId);
      if (r.status === 'finished') {
        const base = r.rank <= table.length ? table[r.rank - 1] : season.points.finisher;
        const ps = last.find((x) => x.steamId === r.steamId);
        const bonus = ps && ps.pos <= power.length ? power[ps.pos - 1] : 0;
        p.finished++;
        if (r.rank === 1) p.wins++;
        p.cells[ev.id] = { pos: r.rank, pts: base + bonus, power: bonus };
      } else {
        p.cells[ev.id] = { pos: null, pts: 0, dnf: r.status === 'dnf', dsq: r.status === 'dsq', running: r.status === 'running' };
      }
    }
  }
  const k = season.drop || 0;
  for (const p of t.values()) {
    const scores = run.map((ev) => ({ id: ev.id, pts: (p.cells[ev.id] || {}).pts || 0 }));
    const dropped = k > 0 && run.length > k ? [...scores].sort((a, b) => a.pts - b.pts).slice(0, k).map((s) => s.id) : [];
    for (const id of dropped) p.cells[id] = { ...(p.cells[id] || { pos: null, pts: 0, absent: true }), dropped: true };
    p.points = scores.filter((s) => !dropped.includes(s.id)).reduce((a, s) => a + s.pts, 0);
  }
  const out = [...t.values()].sort((a, b) => b.points - a.points || b.wins - a.wins || b.finished - a.finished || a.name.localeCompare(b.name));
  out.forEach((p, i) => {
    const q = out[i - 1];
    p.rank = q && q.points === p.points && q.wins === p.wins && q.finished === p.finished ? q.rank : i + 1;
  });
  return out;
}

// ------------------------------------------------------------------ banners

// The owner's picture across the top of the league's page: the website cuts it to 3:1 and makes it a 1200 x 400 JPEG
// before sending it. The server keeps what it is sent if it is a PNG, JPEG or WebP of that shape (never SVG or anything
// a browser could run) and serves it with its type from its bytes.
export const BANNER = { maxBytes: 250_000, minW: 600, maxW: 2400, maxH: 1200, minRatio: 2, maxRatio: 4.5 };

const u16be = (b, i) => (b[i] << 8) | b[i + 1];
const u16le = (b, i) => b[i] | (b[i + 1] << 8);
const u24le = (b, i) => b[i] | (b[i + 1] << 8) | (b[i + 2] << 16);
const ascii = (b, i, n) => String.fromCharCode(...b.subarray(i, i + n));

/** An image's type and size from its bytes: {type, w, h} for a PNG, JPEG or WebP, else null. */
export function sniffImage(b) {
  if (!(b instanceof Uint8Array) || b.length < 32) return null;
  if (b[0] === 0x89 && ascii(b, 1, 3) === 'PNG' && ascii(b, 12, 4) === 'IHDR') {
    const w = (b[16] << 24 >>> 0) + (b[17] << 16) + (b[18] << 8) + b[19];
    const h = (b[20] << 24 >>> 0) + (b[21] << 16) + (b[22] << 8) + b[23];
    return { type: 'image/png', w, h };
  }
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) {        // JPEG: its size is in the frame header (SOFn)
    let i = 2;
    while (i + 9 < b.length) {
      if (b[i] !== 0xff) return null;
      const m = b[i + 1];
      if (m === 0xff) { i++; continue; }
      if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return { type: 'image/jpeg', w: u16be(b, i + 7), h: u16be(b, i + 5) };
      }
      if (m === 0xd9 || m === 0xda) return null;               // the end, or the picture data, with no frame header
      i += 2 + u16be(b, i + 2);
    }
    return null;
  }
  if (ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WEBP') {
    const chunk = ascii(b, 12, 4);
    if (chunk === 'VP8X') return { type: 'image/webp', w: u24le(b, 24) + 1, h: u24le(b, 27) + 1 };
    if (chunk === 'VP8L' && b[20] === 0x2f) {
      const bits = (b[21] | (b[22] << 8) | (b[23] << 16) | (b[24] << 24)) >>> 0;
      return { type: 'image/webp', w: (bits & 0x3fff) + 1, h: ((bits >>> 14) & 0x3fff) + 1 };
    }
    if (chunk === 'VP8 ' && b[23] === 0x9d && b[24] === 0x01 && b[25] === 0x2a) {
      return { type: 'image/webp', w: u16le(b, 26) & 0x3fff, h: u16le(b, 28) & 0x3fff };
    }
  }
  return null;
}

/** A banner as sent: -> {value: {type, w, h}} or {error, status}. */
export function checkBanner(bytes) {
  if (bytes.length > BANNER.maxBytes) {
    return { status: 413, error: `the picture is ${Math.round(bytes.length / 1000)} KB: ${BANNER.maxBytes / 1000} KB at most` };
  }
  const img = sniffImage(bytes);
  if (!img) return { status: 415, error: 'a PNG, JPEG or WebP picture, please' };
  const r = img.w / img.h;
  if (img.w < BANNER.minW || img.w > BANNER.maxW || img.h > BANNER.maxH || !(r >= BANNER.minRatio && r <= BANNER.maxRatio)) {
    return { status: 422, error: `a wide picture, about 3:1 (it is ${img.w} x ${img.h})` };
  }
  return { value: img };
}

/** Where a league's banner is (its address changes with each new one, so browsers keep it for good), or null. */
export const bannerUrl = (id, version) => (version ? `/l/${id}/banner?v=${version}` : null);
