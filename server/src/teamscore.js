// Team results: how a team's drivers' results in one event (a team 1V1's or a team cup's match, a league event) make the
// team's, and how a league season's team championship adds them up. Pure functions, no database: the leagues
// (src/leagues.js, leaguesapi.js), team 1V1s (src/teamh2h.js) and team cups (src/teamcups.js) use them.
//
// A match's scoring (checkScoring):
//   lineup  open: any of the team's drivers drives it / named: the team's captain or a manager names `size` drivers,
//           and only they drive it
//   count   all: every driver of the team who drove it (at least `min`) / best: the best `best` of them
//   by      time: their times added up / avg: their average time / places: their positions among the match's drivers
//           added up, lowest wins (cross-country) / points: points by position (`points`), added up
//   short   a team with fewer finishers than it counts: fewer (ranked after the teams with more, then on what it has) /
//           slowest (each one missing counts as the slowest finisher's time + plusPct % + plusS seconds; for places:
//           one place behind the last finisher; for points: none)
//   min     at least this many drivers count (count all): those who didn't drive are missing
// Ties: the counted drivers' times compared one by one (the best first); still equal: a dead heat (a cup's higher seed
// goes through). A team without a finisher is out (behind every team with one).
//
// A league season's team championship (checkTeamChamp), on the teams the league has (src/leaguesapi.js):
//   method  drivers: the counted drivers' own championship points added up / reranked: the counted drivers ranked
//           among themselves (every team's), the team table by that position (as the WRC's manufacturers) / result:
//           the teams ranked on each event as a match is (by, short, min), the team table by the team's place /
//           season: each team's best drivers' season points added up (no points per event)
//   best    how many of a team's drivers count each event (0: all)
//   nominate  0: every driver of the team can count / M: each team names up to M drivers before the event opens (its
//           manager, or the league's admins), only they count; a team that named nobody: fallback all / none
//   table   the team points table (reranked, result), power: the Power Stage bonus counts (drivers), drop: each team's
//           worst rounds not counted

import { N_ } from './i18n.js';

export const TEAMSCORE = { size: [1, 8], best: [1, 20], min: [1, 8], plusS: 3600, plusPct: 100, table: 30, maxPts: 1000,
  nominate: 20, drop: 20 };
export const BY = ['time', 'avg', 'places', 'points'];
export const SHORT = ['fewer', 'slowest'];
export const DEFAULT_TABLE = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];

// What a team match can be scored by (the website's choices; custom: any of the settings)
export const MATCH_PRESETS = {
  top: { label: N_('Top X: the best X times added up'), value: { lineup: 'open', count: 'best', best: 3, by: 'time', short: 'fewer', min: 1 } },
  average: { label: N_('Average: the average time of everyone who drove (at least X)'),
    value: { lineup: 'open', count: 'all', by: 'avg', short: 'slowest', plusS: 60, plusPct: 0, min: 2 } },
  named: { label: N_('Named: the team names X drivers, their times added up'),
    value: { lineup: 'named', size: 3, count: 'all', by: 'time', short: 'slowest', plusS: 60, plusPct: 0, min: 1 } },
  places: { label: N_('Cross-country: the best X places added up, lowest wins'), value: { lineup: 'open', count: 'best', best: 3, by: 'places', short: 'slowest', min: 1 } },
};
export const CHAMP_METHODS = {
  drivers: N_("Drivers' points: the counted drivers' championship points added up"),
  reranked: N_('Re-ranked: the counted drivers ranked among themselves, the team table by position'),
  result: N_("Team result: the teams ranked on each event, the team table by the team's place"),
  season: N_("Season: each team's best drivers' season points added up"),
};
export const DEFAULT_CHAMP = { method: 'drivers', best: 2, nominate: 0, fallback: 'all', by: 'time', short: 'fewer', plusS: 0, plusPct: 0,
  min: 1, table: DEFAULT_TABLE, power: true, drop: 0 };

const int = (v, lo, hi, dflt) => {
  if (v == null || v === '') return dflt;
  const n = Number(v);
  return Number.isInteger(n) && n >= lo && n <= hi ? n : NaN;
};

/** A points table from a form: a list or "25, 18, 15": -> [numbers] or null. */
function tableOf(v) {
  const a = Array.isArray(v) ? v : String(v == null ? '' : v).split(/[\s,;-]+/).filter(Boolean);
  const out = a.map(Number);
  if (!out.length || out.length > TEAMSCORE.table || out.some((x) => !Number.isInteger(x) || x < 0 || x > TEAMSCORE.maxPts)) return null;
  return out;
}

/** A match's scoring from a form ({preset} fills in the rest; given values win). maxSize: a team's most drivers in a
 *  match. -> {value} or {error}. */
export function checkScoring(b, { maxSize = TEAMSCORE.size[1] } = {}) {
  b = b || {};
  const base = (MATCH_PRESETS[b.preset] || {}).value || {};
  const g = (k) => (b[k] == null || b[k] === '' ? base[k] : b[k]);
  const lineup = g('lineup') || 'open';
  if (!['open', 'named'].includes(lineup)) return { error: 'the lineup: open or named' };
  const by = g('by') || 'time';
  if (!BY.includes(by)) return { error: 'add up by: time, average, places or points' };
  const count = g('count') || 'all';
  if (!['all', 'best'].includes(count)) return { error: 'who counts: everyone or the best few' };
  const v = { lineup, count, by };
  if (lineup === 'named') {
    v.size = int(g('size'), 1, maxSize, 3);
    if (Number.isNaN(v.size)) return { error: `each team names 1 to ${maxSize} drivers` };
  }
  if (count === 'best') {
    v.best = int(g('best'), 1, lineup === 'named' ? v.size : TEAMSCORE.best[1], Math.min(3, v.size || 3));
    if (Number.isNaN(v.best)) return { error: lineup === 'named' ? 'the best X: 1 to the drivers each team names' : `the best X: 1 to ${TEAMSCORE.best[1]}` };
  }
  v.min = int(g('min'), 1, TEAMSCORE.min[1], 1);
  if (Number.isNaN(v.min)) return { error: `at least 1 to ${TEAMSCORE.min[1]} drivers count` };
  if (lineup === 'named' && v.min > v.size) v.min = v.size;
  v.short = g('short') || 'fewer';
  if (!SHORT.includes(v.short)) return { error: 'a team short of finishers: fewer finishers lose, or the slowest time' };
  if (v.short === 'slowest') {
    v.plusS = int(g('plusS'), 0, TEAMSCORE.plusS, 0);
    v.plusPct = int(g('plusPct'), 0, TEAMSCORE.plusPct, 0);
    if (Number.isNaN(v.plusS) || Number.isNaN(v.plusPct)) return { error: `a missing finisher: the slowest time + 0 to ${TEAMSCORE.plusPct} % + 0 to ${TEAMSCORE.plusS} s` };
  }
  if (by === 'points') {
    v.points = tableOf(g('points') || DEFAULT_TABLE);
    if (!v.points) return { error: `the points: up to ${TEAMSCORE.table} whole numbers, 0 to ${TEAMSCORE.maxPts}` };
  }
  return { value: v };
}

/** The most drivers a team can have count in a match (its lineup's size, the best X, or its min). */
export const matchDrivers = (s) => (s.lineup === 'named' ? s.size : s.count === 'best' ? s.best : s.min);

const fmtS = (ms) => (ms / 1000).toFixed(3);

/** A match's scoring in plain words (English: notices; the pages say it in their language from the fields). */
export function describeScoring(s) {
  const who = s.lineup === 'named' ? `${s.size} named driver${s.size > 1 ? 's' : ''} a team` : 'any driver of the team';
  const counts = s.count === 'best' ? `the best ${s.best}` : s.min > 1 ? `everyone who drove (at least ${s.min})` : 'everyone who drove';
  const by = { time: 'times added up', avg: 'average time', places: 'places added up, lowest wins', points: 'points by position added up' }[s.by];
  return `${who}; ${counts} count; ${by}`;
}

/** Positions among drivers' rows (finished, by total; ties share one): Map steamId -> pos. */
function positions(rows) {
  const fin = rows.filter((r) => r.status === 'finished').sort((a, b) => a.totalMs - b.totalMs);
  const pos = new Map();
  fin.forEach((r, i) => pos.set(r.steamId, i && r.totalMs === fin[i - 1].totalMs ? pos.get(fin[i - 1].steamId) : i + 1));
  return pos;
}

/** One event's team results. rows: its standings rows (leagues.js eventStandings: {steamId, name, status, totalMs,
 *  done}); teams: [{id, drivers: [steamId]}] (who can count for it: its drivers, or its named lineup); s: a scoring
 *  (checkScoring). -> [{id, rank, score, finishers, counted, need, missing, pending, out, drivers: [{steamId, name,
 *  status, totalMs, pos, pts, counted}]}] best first; score: ms (time, avg), places or points; null when out. */
export function teamResult(rows, teams, s) {
  const teamOf = new Map();
  for (const t of teams) for (const sid of t.drivers) if (!teamOf.has(sid)) teamOf.set(sid, t.id);
  const mine = rows.filter((r) => teamOf.has(r.steamId));
  const pos = positions(mine);
  const nFin = pos.size;
  const slowest = Math.max(0, ...mine.filter((r) => r.status === 'finished').map((r) => r.totalMs));
  const missingMs = Math.round(slowest * (1 + (s.plusPct || 0) / 100)) + (s.plusS || 0) * 1000;
  const ptsAt = (p) => (s.points && p ? s.points[p - 1] || 0 : 0);
  const out = teams.map((t) => {
    const ds = mine.filter((r) => teamOf.get(r.steamId) === t.id).map((r) => ({ steamId: r.steamId, name: r.name, status: r.status,
      totalMs: r.status === 'finished' ? r.totalMs : null, done: r.done, pos: pos.get(r.steamId) || null, pts: s.by === 'points' ? ptsAt(pos.get(r.steamId)) : null, counted: false }));
    const fin = ds.filter((d) => d.status === 'finished').sort((a, b) => a.totalMs - b.totalMs);
    const need = s.lineup === 'named' ? (s.count === 'best' ? s.best : s.size)
      : s.count === 'best' ? s.best : Math.max(s.min || 1, ds.length);
    const counted = fin.slice(0, need);
    counted.forEach((d) => { d.counted = true; });
    const missing = need - counted.length;
    const pending = ds.filter((d) => d.status === 'running').length;
    let score = null;
    if (counted.length) {
      const sumMs = counted.reduce((a, d) => a + d.totalMs, 0);
      if (s.by === 'time') score = sumMs + (s.short === 'slowest' ? missing * missingMs : 0);
      else if (s.by === 'avg') score = Math.round((sumMs + (s.short === 'slowest' ? missing * missingMs : 0)) / (s.short === 'slowest' ? need : counted.length));
      else if (s.by === 'places') score = counted.reduce((a, d) => a + d.pos, 0) + (s.short === 'slowest' ? missing * (nFin + 1) : 0);
      else score = counted.reduce((a, d) => a + d.pts, 0);
    }
    ds.sort((a, b) => (a.pos || 1e9) - (b.pos || 1e9) || b.done - a.done || String(a.name).localeCompare(String(b.name)));
    return { id: t.id, rank: null, score, finishers: fin.length, counted: counted.length, need, missing: score == null ? need : missing,
      pending, out: score == null, drivers: ds, _times: counted.map((d) => d.totalMs) };
  });
  const cmp = (a, b) => {
    if (a.out !== b.out) return a.out ? 1 : -1;
    if (a.out) return b.finishers - a.finishers;
    if (s.short === 'fewer' && a.missing !== b.missing) return a.missing - b.missing;
    if (a.score !== b.score) return s.by === 'points' ? b.score - a.score : a.score - b.score;
    for (let i = 0; i < Math.max(a._times.length, b._times.length); i++) {
      const x = a._times[i], y = b._times[i];
      if (x == null || y == null) return x == null ? 1 : -1;
      if (x !== y) return x - y;
    }
    return 0;
  };
  out.sort(cmp);
  out.forEach((t, i) => { t.rank = i && cmp(out[i - 1], t) === 0 ? out[i - 1].rank : i + 1; });
  for (const t of out) delete t._times;
  return out;
}

/** A match of two teams decided from teamResult(): -> {winner: a | b | null, note, margin}. Nobody with a finisher, or a
 *  dead heat: no winner (a cup decides by seed). */
export function decideTeams(res, a, b, s) {
  const A = res.find((t) => t.id === a), B = res.find((t) => t.id === b);
  if (!A || !B) return { winner: (A || B || {}).id || null, note: 'the only team' };
  if (A.out && B.out) return { winner: null, note: 'nobody finished' };
  if (A.out || B.out) return { winner: A.out ? b : a, note: 'the only team with a finisher' };
  if (A.rank === B.rank) return { winner: null, note: 'a dead heat' };
  const [w, l] = A.rank < B.rank ? [A, B] : [B, A];
  if (s.short === 'fewer' && w.missing !== l.missing) return { winner: w.id, note: 'more finishers' };
  if (w.score === l.score) return { winner: w.id, note: 'on the tie-break: the best driver' };
  const d = Math.abs(w.score - l.score);
  const note = s.by === 'time' || s.by === 'avg' ? `by ${fmtS(d)} s` : s.by === 'places' ? `by ${d} place${d === 1 ? '' : 's'}` : `by ${d} point${d === 1 ? '' : 's'}`;
  return { winner: w.id, note };
}

// ------------------------------------------------------------------ a league season's team championship

/** A season's team championship from a form: -> {value} or {error}. {off: true} (or nothing): {value: null}. */
export function checkTeamChamp(b) {
  if (!b || b.off) return { value: null };
  const g = (k) => (b[k] == null || b[k] === '' ? DEFAULT_CHAMP[k] : b[k]);
  const method = g('method');
  if (!CHAMP_METHODS[method]) return { error: 'the team championship: drivers\' points, re-ranked, team result or season' };
  const v = { method };
  v.best = int(g('best'), 0, TEAMSCORE.best[1], 2);
  if (Number.isNaN(v.best)) return { error: `the drivers who count for a team: 0 (all) to ${TEAMSCORE.best[1]}` };
  v.nominate = int(g('nominate'), 0, TEAMSCORE.nominate, 0);
  if (Number.isNaN(v.nominate)) return { error: `nominated drivers: 0 (none) to ${TEAMSCORE.nominate}` };
  if (v.nominate && v.best > v.nominate) return { error: 'more drivers count than a team can nominate' };
  if (v.nominate) {
    v.fallback = g('fallback');
    if (!['all', 'none'].includes(v.fallback)) return { error: 'a team that nominated nobody: all its drivers, or none' };
  }
  if (method === 'result') {
    const m = checkScoring({ lineup: 'open', count: v.best ? 'best' : 'all', best: v.best || undefined, by: g('by'), short: g('short'),
      plusS: g('plusS'), plusPct: g('plusPct'), min: g('min') });
    if (m.error) return m;
    if (m.value.by === 'points') return { error: 'the team result: by time, average or places' };
    Object.assign(v, { by: m.value.by, short: m.value.short, min: m.value.min, ...(m.value.short === 'slowest' ? { plusS: m.value.plusS, plusPct: m.value.plusPct } : {}) });
  }
  if (method === 'reranked' || method === 'result') {
    v.table = tableOf(g('table'));
    if (!v.table) return { error: `the team points: up to ${TEAMSCORE.table} whole numbers, 0 to ${TEAMSCORE.maxPts}` };
  }
  if (method === 'drivers') v.power = !!g('power');
  if (method !== 'season') {
    v.drop = int(g('drop'), 0, TEAMSCORE.drop, 0);
    if (Number.isNaN(v.drop)) return { error: `dropped rounds: 0 to ${TEAMSCORE.drop}` };
  }
  return { value: v };
}

/** The team championship in plain words (English). */
export function describeTeamChamp(c) {
  if (!c) return '';
  const who = c.best ? `the best ${c.best} of each team` : 'every driver of a team';
  const nom = c.nominate ? `; each team nominates up to ${c.nominate} (${c.fallback === 'none' ? 'none nominated: no points' : 'none nominated: all count'})` : '';
  const how = c.method === 'drivers' ? `their championship points${c.power ? '' : ' (no Power Stage)'}`
    : c.method === 'reranked' ? `ranked among themselves: ${(c.table || []).join('-')}`
      : c.method === 'result' ? `the team's place on the event (${c.by === 'avg' ? 'average time' : c.by === 'places' ? 'places' : 'times added up'}): ${(c.table || []).join('-')}`
        : 'their season points';
  return `${who}${nom}; ${how}` + (c.drop ? `; worst ${c.drop} dropped` : '');
}

/** Who counts for each team on one event. teamOf: Map steamId -> teamId (the team each driver drove it for); named:
 *  Map teamId -> Set steamId (this event's nominations), or null. -> [{id, drivers: [steamId]}] */
export function eligible(c, teamIds, entries, teamOf, named) {
  return teamIds.map((id) => {
    let ds = entries.filter((sid) => teamOf.get(sid) === id);
    if (c.nominate) {
      const n = named && named.get(id);
      if (n && n.size) ds = ds.filter((sid) => n.has(sid));
      else if (c.fallback === 'none') ds = [];
    }
    return { id, drivers: ds };
  });
}

/** One event's team points. ev: {id, rows, stages} (eventStandings); teams: eligible()'s; cells: Map steamId -> the
 *  driver's championship cell for this event ({pts, power}: seasonStandings). -> Map teamId -> {pts, rank, score,
 *  counted: [steamId], out} (rank: its place among the teams that scored on the event). */
export function teamRound(c, ev, teams, cells) {
  const res = new Map();
  const best = c.best || Infinity;
  if (c.method === 'result') {
    const r = teamResult(ev.rows, teams, { lineup: 'open', count: c.best ? 'best' : 'all', best: c.best, by: c.by, short: c.short,
      plusS: c.plusS, plusPct: c.plusPct, min: c.min || 1 });
    for (const t of r) {
      res.set(t.id, { pts: t.out ? 0 : c.table[t.rank - 1] || 0, rank: t.out ? null : t.rank, score: t.score, out: t.out,
        counted: t.drivers.filter((d) => d.counted).map((d) => d.steamId) });
    }
    return res;
  }
  if (c.method === 'reranked') {
    const fin = new Map(ev.rows.filter((r) => r.status === 'finished').map((r) => [r.steamId, r.totalMs]));
    const all = [];
    for (const t of teams) {
      const ds = t.drivers.filter((sid) => fin.has(sid)).sort((a, b) => fin.get(a) - fin.get(b));
      ds.forEach((sid) => all.push({ team: t.id, sid, ms: fin.get(sid) }));
    }
    all.sort((a, b) => a.ms - b.ms);
    all.forEach((x, i) => { x.pos = i && x.ms === all[i - 1].ms ? all[i - 1].pos : i + 1; });
    for (const t of teams) {
      const mine = all.filter((x) => x.team === t.id).slice(0, best);
      res.set(t.id, { pts: mine.reduce((a, x) => a + (c.table[x.pos - 1] || 0), 0), counted: mine.map((x) => x.sid), out: !mine.length });
    }
  } else {                                               // drivers (and season: shown per event the same way)
    for (const t of teams) {
      const mine = t.drivers.map((sid) => {
        const cell = cells.get(sid) || {};
        return { sid, pts: (cell.pts || 0) - (c.method === 'drivers' && !c.power ? cell.power || 0 : 0), fin: cell.pos != null };
      }).filter((x) => x.fin).sort((a, b) => b.pts - a.pts).slice(0, best);
      res.set(t.id, { pts: mine.reduce((a, x) => a + x.pts, 0), counted: mine.map((x) => x.sid), out: !mine.length });
    }
  }
  const scored = [...res.entries()].filter(([, x]) => !x.out).sort((a, b) => b[1].pts - a[1].pts);
  scored.forEach(([, x], i) => { x.rank = i && x.pts === scored[i - 1][1].pts ? scored[i - 1][1].rank : i + 1; });
  return res;
}

/** A season's team championship. c: checkTeamChamp's value; teams: [{id, name, tag, color}]; events: the season's
 *  events in order, [{id, status, rows, stages, teamOf: Map steamId -> teamId, named: Map teamId -> Set | null}]
 *  (status 'upcoming': not counted yet); drivers: seasonStandings' rows (each driver's cells); penalties: [{teamId,
 *  points}] (points taken off; negative: given back). -> [{id, name, tag, color, rank, points, wins, penalty, cells:
 *  {eventId: {pts, rank, counted, dropped}}, best: [{steamId, points}] (season)}] best first. */
export function teamSeasonStandings(c, teams, events, drivers, penalties = []) {
  const run = events.filter((e) => e.status !== 'upcoming');
  const cellsOf = new Map(drivers.map((d) => [d.steamId, d.cells]));
  const ids = teams.map((t) => t.id);
  const t = new Map(teams.map((x) => [x.id, { id: x.id, name: x.name, tag: x.tag || null, color: x.color || null, points: 0, wins: 0, penalty: 0, cells: {} }]));
  const bySeason = new Map(ids.map((id) => [id, new Map()]));   // season: teamId -> steamId -> points for it
  for (const ev of run) {
    const entries = ev.rows.map((r) => r.steamId);
    const teamsEv = eligible(c, ids, entries, ev.teamOf, ev.named);
    const cells = new Map(entries.map((sid) => [sid, (cellsOf.get(sid) || {})[ev.id] || {}]));
    const round = teamRound(c, ev, teamsEv, cells);
    for (const [id, x] of round) {
      const p = t.get(id);
      if (!p) continue;
      if (!x.out || teamsEv.find((y) => y.id === id).drivers.length) p.cells[ev.id] = { pts: x.pts, rank: x.rank || null, counted: x.counted };
      if (x.rank === 1) p.wins++;
      if (c.method === 'season') {
        for (const sid of teamsEv.find((y) => y.id === id).drivers) {
          const cell = cells.get(sid);
          if (cell && cell.pts) bySeason.get(id).set(sid, (bySeason.get(id).get(sid) || 0) + cell.pts);
        }
      }
    }
  }
  const k = c.drop || 0;
  for (const p of t.values()) {
    if (c.method === 'season') {
      const best = [...bySeason.get(p.id)].map(([steamId, points]) => ({ steamId, points })).sort((a, b) => b.points - a.points).slice(0, c.best || Infinity);
      p.best = best;
      p.points = best.reduce((a, x) => a + x.points, 0);
    } else {
      const scores = run.map((ev) => ({ id: ev.id, pts: (p.cells[ev.id] || {}).pts || 0 }));
      const dropped = k > 0 && run.length > k ? [...scores].sort((a, b) => a.pts - b.pts).slice(0, k).map((s) => s.id) : [];
      for (const id of dropped) p.cells[id] = { ...(p.cells[id] || { pts: 0, absent: true }), dropped: true };
      p.points = scores.filter((s) => !dropped.includes(s.id)).reduce((a, s) => a + s.pts, 0);
    }
    p.penalty = penalties.filter((x) => x.teamId === p.id).reduce((a, x) => a + x.points, 0);
    p.points -= p.penalty;
  }
  const out = [...t.values()].sort((a, b) => b.points - a.points || b.wins - a.wins || a.name.localeCompare(b.name));
  out.forEach((p, i) => {
    const q = out[i - 1];
    p.rank = q && q.points === p.points && q.wins === p.wins ? q.rank : i + 1;
  });
  return out;
}
