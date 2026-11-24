// The public API (/api/v1): what ACR Daily's results, timing and tables are, for anyone to read and put on their own page
// (a championship's organizers above all: its results and standings on its own site). Read-only, no key, no sign-in:
// it shows exactly what the website shows anyone (21 Nov 2026, the user's call: a private championship is readable by
// whoever has its link, as on the website; a private rally's results need its invite code, ?code=, as a driver does;
// a hidden event keeps what it hides until it closes, whoever asks).
//
// Its answers are its own, kept stable (v1), whatever the website's and the app's endpoints become: each one is made by
// asking those endpoints in-process as an anonymous visitor (`call`), then reshaped here. So what is hidden, locked or
// private is decided in one place, theirs. JSON, every origin (Access-Control-Allow-Origin: *); the tables also as CSV
// (?format=csv). Each answer is kept at Cloudflare's edge for a few seconds (live) to a few minutes (results, tables),
// so other sites' visitors don't each cost the database (the free plan's limits).
//
//   GET /api/v1                                         what there is (this list)
//   GET /api/v1/championships                           every championship
//   GET /api/v1/championships/<id>                      one: its members, events, seasons
//   GET /api/v1/championships/<id>/standings[?season=]  its season tables: drivers, each class and division, teams   (csv)
//   GET /api/v1/events/<id>[?code=]                     an event: its itinerary and full results                    (csv)
//   GET /api/v1/events/<id>/live[?code=]                who is on its stages now: stage, progress, time, position
//   GET /api/v1/events/<id>/map[?code=]                 its stages' routes (the live map's lines, the game's x/z)
//   GET /api/v1/cups/<id>                               a cup: entrants, bracket, results
//   GET /api/v1/dailies[?date=]                         a day's dailies
//   GET /api/v1/dailies/<date>/<slot>                   a daily's results                                           (csv)
//   GET /api/v1/timetrials[?week=]                      a week's time trial stages
//   GET /api/v1/timetrials/<week>/<slot>                a time trial stage's results                                (csv)
//   GET /api/v1/ranking[?country=&page=]                the world ranking, 100 a page                               (csv)
//   GET /api/v1/drivers/<steamId>                       a driver: rating, rank, team, recent results
//
// Documented for people at /developers (src/developerspage.js); embeds that draw these on another site: src/embeds.js.

export const API_VERSION = 1;
// how long an answer is kept at the edge, seconds: live timing, an event or a table still changing, one over, lists
export const TTL = { live: 5, open: 30, closed: 600, list: 120, map: 3600 };

const PAGE = { championship: '/l/', event: '/e/', cup: '/cup/', driver: '/d/', rally: '/e/' };

/** ms -> "1:02.417" (a time as the timing sheets show it), '' for none. */
export const fmtMs = (ms) => {
  if (ms == null || !Number.isFinite(+ms)) return '';
  const t = Math.round(+ms), m = Math.floor(t / 60000), s = (t % 60000) / 1000;
  const h = Math.floor(m / 60);
  return h ? `${h}:${String(m % 60).padStart(2, '0')}:${s.toFixed(3).padStart(6, '0')}` : `${m}:${s.toFixed(3).padStart(6, '0')}`;
};

/** rows (arrays) -> CSV text: RFC 4180 quoting, CRLF lines, a byte-order mark so Excel reads the letters right. A text
 *  starting = + - @ (a driver's name is theirs to type: a spreadsheet would run it as a formula) gets a ' first; a time
 *  or a number (+0:03.500, -5) stays as it is. */
export function csv(rows) {
  const formula = (s) => /^[=+\-@]/.test(s) && !/^[+-]\d[\d:.]*$/.test(s);
  const cell = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\r\n]/.test(s) || formula(s) ? `"${(formula(s) ? "'" : '') + s.replace(/"/g, '""')}"` : s;
  };
  return '﻿' + rows.map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
}

const headers = (type, ttl) => ({ 'Content-Type': type, 'Access-Control-Allow-Origin': '*',
  'Cache-Control': ttl > 0 ? `public, max-age=${ttl}, s-maxage=${ttl}` : 'no-store', 'X-ACR-API': `v${API_VERSION}` });
const out = (data, ttl = 0, status = 200) => new Response(JSON.stringify(data), { status, headers: headers('application/json; charset=utf-8', ttl) });
const outCsv = (rows, name, ttl) => new Response(csv(rows), { headers: { ...headers('text/csv; charset=utf-8', ttl),
  'Content-Disposition': `inline; filename="${name}.csv"` } });
const fail = (error, status) => out({ error, status }, 0, status);

/** The website's and the app's endpoint at `path`, asked as an anonymous visitor: -> {ok, status, data}. */
async function ask(call, path) {
  const res = await call(path);
  let data = null;
  try { data = await res.json(); } catch { data = null; }
  return { ok: res.ok, status: res.status, data };
}
const passFail = (r) => fail((r.data && r.data.error) || 'not found', r.status === 200 ? 500 : r.status || 500);

const team = (t) => (t && (t.tag || t.name) ? { id: t.id || null, tag: t.tag || null, name: t.name || null } : null);
const look = (x) => (x && x.team ? team(x.team) : x && x.look && x.look.tag ? { id: null, tag: x.look.tag.text, name: null } : null);

// ------------------------------------------------------------------ championships

const champListItem = (l, site) => ({ id: l.id, name: l.name, about: l.about || '', official: !!l.official, private: !l.public,
  owner: l.owner ? (typeof l.owner === 'string' ? l.owner : l.owner.name) : null, members: l.members || 0, events: l.events || 0,
  openEvents: l.openEvents || 0, banner: l.banner ? site + l.banner : null, url: site + PAGE.championship + l.id });

const eventSummary = (e, site) => ({ id: e.id, name: e.name, seasonId: e.seasonId || null, rally: e.rally, car: e.car || null,
  carClass: e.carClass || null, carClasses: e.carClasses || null, stages: e.stages, days: e.days, lengthM: e.lengthM ?? null,
  opens: e.opens, closes: e.closes, status: e.status, hidden: e.hidden || null, entries: e.entries, finished: e.finished,
  winner: e.winner || null, url: site + PAGE.event + e.id });

function championship(l, site) {
  return {
    id: l.id, name: l.name, about: l.about || '', official: !!l.official, private: !l.public, created: l.created,
    owner: l.owner ? l.owner.name : null, banner: l.banner ? site + l.banner : null, url: site + PAGE.championship + l.id,
    divisions: l.divisions || [],
    teams: l.teams ? (l.teams.list || []).map((t) => ({ id: t.id, name: t.name, tag: t.tag || null, color: t.color || null })) : [],
    members: (l.members || []).map((m) => ({ steamId: m.steamId, name: m.name, country: m.country || null, role: m.role,
      division: m.division || null, team: look(m), joined: m.joined })),
    events: (l.events || []).map((e) => eventSummary(e, site)),
    seasons: (l.seasons || []).map((s) => ({ id: s.id, name: s.name, about: s.about || '', events: s.events || [],
      points: s.points, powerStage: s.power, dropWorst: s.drop || 0 })),
  };
}

const standingRow = (r, eventIds) => ({ rank: r.rank, steamId: r.steamId, name: r.name, country: r.country || null, team: look(r),
  points: r.points, wins: r.wins, finished: r.finished,
  events: Object.fromEntries(eventIds.map((id) => {
    const c = (r.cells || {})[id];
    return [id, c ? { pos: c.pos ?? null, points: c.pts || 0, powerStage: c.power || 0, dnf: !!c.dnf, dsq: !!c.dsq, dropped: !!c.dropped,
      running: !!c.running } : null];
  })) });

function seasonTables(l, s) {
  const ids = s.events || [];
  const events = (l.events || []).filter((e) => ids.includes(e.id)).map((e) => ({ id: e.id, name: e.name, rally: e.rally, status: e.status }));
  return { id: s.id, name: s.name, about: s.about || '', events,
    drivers: (s.standings || []).map((r) => standingRow(r, ids)),
    groups: (s.groups || []).map((g) => ({ kind: g.kind, name: g.name, drivers: (g.standings || []).map((r) => standingRow(r, ids)) })),
    teams: (s.teamStandings || []).map((t) => ({ rank: t.rank ?? null, id: t.id ?? t.teamId ?? null, name: t.name || null, tag: t.tag || null,
      points: t.points ?? null })),
    teamChampionship: s.teamAbout || null };
}

// ------------------------------------------------------------------ events

const stageOut = (s) => ({ no: s.no, day: s.day ?? null, name: s.name ?? null, track: s.track ?? null, lengthM: s.lengthM ?? null,
  rally: s.rally ?? null, weather: s.weatherLabel ?? s.weather ?? null, time: s.time ?? null, serviceBefore: !!s.service });

const timeRow = (r) => ({ rank: r.rank ?? null, steamId: r.steamId, name: r.name, country: r.country || null, team: look(r),
  car: r.car || null, carClass: r.cls || null, division: r.division || null, status: r.status, reason: r.reason || null,
  stagesDone: r.done ?? null, totalMs: r.totalMs ?? null, gapMs: r.gapMs ?? null, gamePenaltyMs: r.penaltyMs ?? null,
  stewardMs: r.stewardMs ?? null, classified: r.classified ?? null,
  stages: (r.stages || []).map((s) => (s ? { timeMs: s.timeMs ?? null, penaltyMs: s.penaltyMs ?? null, stewardMs: s.stewardMs ?? null,
    totalMs: s.totalMs ?? null, pos: s.pos ?? null, overallPos: s.cumPos ?? null, retired: s.retired || null } : null)) });

function eventOut(o, site) {
  const lg = o.league || {};
  const holder = lg.kind === 'league' ? { kind: 'championship', id: lg.id, name: lg.name, url: site + PAGE.championship + lg.id }
    : lg.kind === 'event' ? { kind: 'rally', id: lg.id, name: lg.name, owner: lg.owner || null }
      : { kind: lg.kind || null, id: lg.id, name: lg.name };
  return {
    id: o.id, name: o.name, url: site + PAGE.event + o.id, holder, season: o.season ? { id: o.season.id, name: o.season.name } : null,
    rally: o.rally, surface: o.surface || null, car: o.car || null, carClass: o.carClass || null, carClasses: o.carClasses || null,
    days: o.days ?? null, lengthM: o.lengthM ?? null, opens: o.opens, closes: o.closes, status: o.status,
    hidden: o.hidden || null, revealsAt: o.revealsAt ?? null, locked: !!o.locked,
    rules: o.rules || null, stages: (o.stages || []).map(stageOut),
    results: (o.standings || []).map(timeRow),
    groups: (o.groups || []).map((g) => ({ kind: g.kind, name: g.name, results: (g.standings || []).map(timeRow) })),
    penalties: (o.decisions || []).map((d) => ({ ...d })),
  };
}

function eventCsv(e) {
  const n = e.stages.length;
  const head = ['Pos', 'Driver', 'Country', 'Team', 'Car', 'Class', 'Division', 'Status', 'Total', 'Gap', 'Total (ms)'];
  for (let k = 1; k <= n; k++) head.push(`SS${k}`);
  head.push('Game penalties (ms)', 'Steward (ms)');
  const rows = e.results.map((r) => [r.rank ?? '', r.name, (r.country || '').toUpperCase(), r.team ? r.team.tag || r.team.name : '',
    r.car || '', r.carClass || '', r.division || '', r.status, fmtMs(r.totalMs), r.rank > 1 ? '+' + fmtMs(r.gapMs) : '', r.totalMs ?? '',
    ...Array.from({ length: n }, (_x, k) => { const s = r.stages[k]; return s ? (s.retired ? 'retired' : fmtMs(s.totalMs ?? s.timeMs)) : ''; }),
    r.gamePenaltyMs ?? '', r.stewardMs ?? '']);
  return [head, ...rows];
}

// ------------------------------------------------------------------ the router

/** -> a Response for /api/v1..., or null for any other path. call(path): the site's own endpoint at path, asked as an
 *  anonymous visitor (src/index.js route). ctx: the request's (the edge cache is filled after the answer). */
export async function publicApi(req, env, ctx, url, path, call) {
  if (path !== '/api/v1' && !path.startsWith('/api/v1/')) return null;
  if (req.method !== 'GET' && req.method !== 'HEAD') return fail('read-only: GET only', 405);
  const cache = typeof caches !== 'undefined' && caches.default ? caches.default : null;
  const key = new Request(url.toString(), { method: 'GET' });
  if (cache) {
    const hit = await cache.match(key);
    if (hit) return hit;
  }
  const res = await v1(env, url, path.slice('/api/v1'.length) || '/', call, env.SITE_URL || url.origin);
  if (cache && res.status === 200 && /max-age=[1-9]/.test(res.headers.get('Cache-Control') || '')) {
    const put = cache.put(key, res.clone());
    if (ctx && ctx.waitUntil) ctx.waitUntil(put); else await put;
  }
  return res;
}

async function v1(env, url, p, call, site) {
  const q = url.searchParams, asCsv = q.get('format') === 'csv';
  const code = q.get('code') ? `?code=${encodeURIComponent(q.get('code'))}` : '';
  let m;

  if (p === '/') return out(INDEX(site), TTL.list);

  if (p === '/championships') {
    const r = await ask(call, '/api/leagues');
    if (!r.ok) return passFail(r);
    const list = [...(r.data.public || []), ...(r.data.private || [])];
    return out({ championships: list.map((l) => champListItem(l, site)) }, TTL.list);
  }

  if ((m = p.match(/^\/championships\/([a-z0-9]{8})(\/standings)?$/))) {
    const r = await ask(call, `/api/leagues/${m[1]}`);
    if (!r.ok) return passFail(r);
    const l = r.data, open = (l.events || []).some((e) => e.status !== 'closed');
    if (!m[2]) return out(championship(l, site), open ? TTL.open : TTL.closed);
    const want = q.get('season');
    const seasons = (l.seasons || []).filter((s) => !want || String(s.id) === want);
    if (want && !seasons.length) return fail('no such season in this championship', 404);
    const tables = seasons.map((s) => seasonTables(l, s));
    if (!asCsv) return out({ championship: { id: l.id, name: l.name, url: site + PAGE.championship + l.id }, seasons: tables },
      open ? TTL.open : TTL.closed);
    // CSV: one season's drivers' table (the one asked, else the latest), a column of points per event
    const s = tables[tables.length - 1];
    if (!s) return outCsv([['Pos', 'Driver', 'Country', 'Team', 'Points', 'Wins', 'Finished']], `${l.id}-standings`, TTL.open);
    const head = ['Pos', 'Driver', 'Country', 'Team', 'Points', 'Wins', 'Finished', ...s.events.map((e) => e.name)];
    const rows = s.drivers.map((d) => [d.rank, d.name, (d.country || '').toUpperCase(), d.team ? d.team.tag || d.team.name : '', d.points,
      d.wins, d.finished, ...s.events.map((e) => {
        const c = d.events[e.id];
        return !c ? '' : c.dsq ? 'DSQ' : c.dnf ? 'DNF' : c.running ? '…' : `${c.points}${c.dropped ? ' (dropped)' : ''}`;
      })]);
    return outCsv([head, ...rows], `${l.id}-season-${s.id}`, open ? TTL.open : TTL.closed);
  }

  if ((m = p.match(/^\/events\/(\d+)(\/live|\/map)?$/))) {
    const id = +m[1];
    if (m[2] === '/live') {
      const r = await ask(call, `/api/events/${id}/live${code}`);
      if (!r.ok) return passFail(r);
      const d = r.data;
      return out({ eventId: id, now: d.now, pollSeconds: Math.max(TTL.live, (d.timing && d.timing.livePollS) || TTL.live),
        hidden: d.hidden || null, stageCount: d.count,
        stages: d.stages ? d.stages.map((s) => ({ no: s.no, name: s.name || null, track: s.track || null })) : null,
        drivers: (d.drivers || []).map((x) => ({ steamId: x.steamId, name: x.name, country: x.country || null, team: look(x),
          // (stageNo from 1, as the stages' no: the site keeps them from 0)
          stageNo: x.stageNo != null ? x.stageNo + 1 : null, progress: x.progress ?? null, totalMs: x.totalMs ?? null, state: x.state || null,
          x: x.x ?? null, z: x.z ?? null, updated: x.updated ?? null })) }, TTL.live);
    }
    if (m[2] === '/map') {
      const r = await ask(call, `/api/events/${id}/live${code}`);
      if (!r.ok) return passFail(r);
      if (!r.data.stages) return out({ eventId: id, hidden: true, stages: null }, TTL.open);
      const stages = [];
      for (const s of r.data.stages) {
        const rt = await ask(call, `/api/route?track=${encodeURIComponent(s.track)}`);
        const pts = rt.ok && Array.isArray(rt.data.route) ? rt.data.route : null;
        const len = pts ? pts.reduce((a, q, i) => (i ? a + Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) : 0), 0) : null;
        stages.push({ no: s.no, name: s.name || null, track: s.track, lengthM: len == null ? null : Math.round(len), points: pts });
      }
      return out({ eventId: id, hidden: false, units: 'the game\'s x and z (as live positions), metres', stages }, TTL.map);
    }
    const r = await ask(call, `/api/events/${id}${code}`);
    if (!r.ok) return passFail(r);
    const e = eventOut(r.data, site), ttl = e.status === 'closed' && !e.hidden ? TTL.closed : TTL.open;
    return asCsv ? outCsv(eventCsv(e), `event-${id}`, ttl) : out(e, ttl);
  }

  if ((m = p.match(/^\/cups\/([a-z0-9]{8})$/))) {
    const r = await ask(call, `/api/cups/${m[1]}`);
    if (!r.ok) return passFail(r);
    const c = r.data;
    return out({ id: c.id, name: c.name, about: c.about || '', url: site + PAGE.cup + c.id, official: !!c.official,
      status: c.status, round: c.round, size: c.size, starts: c.starts, roundHours: c.roundHours, seeding: c.seeding || 'rating',
      rally: c.rally, rallies: c.rallies || null, car: c.car || null, carClass: c.carClass || null, fee: c.fee, prize: c.prize, pot: c.pot,
      prizes: c.prizes || null, rounds: c.rounds ?? null, roundStages: c.roundStages || null,
      entrants: (c.entrants || []).map((e) => ({ steamId: e.steamId, name: e.name, country: e.country || null, seed: e.seed ?? null,
        place: e.place ?? null, rating: e.rating ?? null })),
      matches: (c.matches || []).map((x) => ({ round: x.round, slot: x.slot, name: x.name || null, eventId: x.eventId || null,
        closes: x.closes || null, a: x.a || null, b: x.b || null, winner: x.winner || null, note: x.note || null })) },
    c.status === 'finished' || c.status === 'cancelled' ? TTL.closed : TTL.open);
  }

  if (p === '/dailies') {
    const r = await ask(call, `/api/challenges${q.get('date') ? `?date=${encodeURIComponent(q.get('date'))}` : ''}`);
    if (!r.ok) return passFail(r);
    return out({ date: r.data.date, dailies: (r.data.challenges || []).map((c, i) => ({ slot: c.slot || i + 1, rally: c.rally, stage: c.stageName,
      track: c.track, lengthM: c.lengthM ?? null, car: c.car, carClass: c.carClass || null, weather: c.weather, time: c.time,
      startsAt: c.startsAt, endsAt: c.endsAt, results: `${site}/api/v1/dailies/${r.data.date}/${c.slot || i + 1}` })) }, TTL.list);
  }
  // who is on a daily's / a time trial stage now (the broadcast overlay, src/broadcast.js; anyone's stream graphics)
  if ((m = p.match(/^\/(dailies|timetrials)\/(\d{4}-\d{2}-\d{2})\/([12])\/live$/))) {
    const r = await ask(call, m[1] === 'dailies' ? `/api/live?date=${m[2]}&slot=${m[3]}` : `/api/tt/live?week=${m[2]}&slot=${m[3]}`);
    if (!r.ok) return passFail(r);
    return out({ [m[1] === 'dailies' ? 'date' : 'week']: m[2], slot: +m[3], now: r.data.now, pollSeconds: TTL.live,
      drivers: (r.data.drivers || []).map((x) => ({ steamId: x.steamId, name: x.name, country: x.country || null, team: look(x),
        progress: x.progress ?? null, totalMs: x.totalMs ?? null, state: x.state || null, x: x.x ?? null, z: x.z ?? null,
        updated: x.updated ?? null })) }, TTL.live);
  }
  if ((m = p.match(/^\/dailies\/(\d{4}-\d{2}-\d{2})\/([12])$/))) {
    const r = await ask(call, `/api/leaderboard?date=${m[1]}&slot=${m[2]}`);
    if (!r.ok) return passFail(r);
    const rows = (r.data.entries || []).map((e) => ({ rank: e.rank ?? null, steamId: e.steamId, name: e.name, country: e.country || null,
      team: look(e), status: e.status, reason: e.reason || null, totalMs: e.totalMs ?? null, gapMs: e.gapMs ?? null, resets: e.resets ?? null,
      splits: e.splits || null }));
    const today = new Date().toISOString().slice(0, 10), ttl = m[1] < today ? TTL.closed : TTL.open;
    if (asCsv) return outCsv([['Pos', 'Driver', 'Country', 'Status', 'Time', 'Gap', 'Time (ms)'],
      ...rows.map((e) => [e.rank ?? '', e.name, (e.country || '').toUpperCase(), e.status, fmtMs(e.totalMs), e.rank > 1 ? '+' + fmtMs(e.gapMs) : '', e.totalMs ?? ''])],
    `daily-${m[1]}-${m[2]}`, ttl);
    return out({ date: m[1], slot: +m[2], drivers: r.data.stats ? r.data.stats.drivers : rows.length, results: rows }, ttl);
  }

  if (p === '/timetrials') {
    const r = await ask(call, `/api/tt?lite=1${q.get('week') ? `&week=${encodeURIComponent(q.get('week'))}` : ''}`);
    if (!r.ok) return passFail(r);
    const d = r.data;
    if (!d.on) return out({ week: d.week, on: false, stages: [] }, TTL.list);
    return out({ week: d.week, on: true, startsAt: d.startsAt, endsAt: d.endsAt, stages: (d.stages || []).map((s) => ({ slot: s.slot,
      rally: s.rally || null, stage: s.menuName || s.stageName || null, track: s.track || null, car: s.car || null, carClass: s.carClass || null,
      weather: s.weather || null, time: s.time || null, entrants: s.entrants || 0, results: `${site}/api/v1/timetrials/${d.week}/${s.slot}` })) }, TTL.list);
  }
  if ((m = p.match(/^\/timetrials\/(\d{4}-\d{2}-\d{2})\/([12])$/))) {
    const r = await ask(call, `/api/tt/board?week=${m[1]}&slot=${m[2]}`);
    if (!r.ok) return passFail(r);
    const rows = (r.data.entries || []).map((e) => ({ rank: e.rank, steamId: e.steamId, name: e.name, country: e.country || null, team: look(e),
      totalMs: e.totalMs, gapMs: e.gapMs, runs: e.runs ?? null, splits: e.splits || null, prize: e.prize ?? null }));
    if (asCsv) return outCsv([['Pos', 'Driver', 'Country', 'Time', 'Gap', 'Runs', 'Time (ms)'],
      ...rows.map((e) => [e.rank, e.name, (e.country || '').toUpperCase(), fmtMs(e.totalMs), e.rank > 1 ? '+' + fmtMs(e.gapMs) : '', e.runs ?? '', e.totalMs])],
    `timetrial-${m[1]}-${m[2]}`, TTL.open);
    return out({ week: m[1], slot: +m[2], drivers: rows.length, results: rows }, TTL.open);
  }

  if (p === '/ranking') {
    const ps = new URLSearchParams();
    if (q.get('country')) ps.set('country', q.get('country'));
    if (q.get('page')) ps.set('page', q.get('page'));
    const r = await ask(call, `/api/ranking${ps.toString() ? '?' + ps : ''}`);
    if (!r.ok) return passFail(r);
    const d = r.data, rows = (d.rows || []).map((x) => ({ rank: x.rank, steamId: x.steamId, name: x.name, country: x.country || null,
      team: team(x.team), rating: x.rating, races: x.races, peak: x.peak }));
    if (asCsv) return outCsv([['Rank', 'Driver', 'Country', 'Team', 'Rating', 'Races', 'Peak'],
      ...rows.map((x) => [x.rank, x.name, (x.country || '').toUpperCase(), x.team ? x.team.tag : '', x.rating, x.races, x.peak])], 'ranking', TTL.list);
    return out({ total: d.total, page: d.page, size: d.size, rows }, TTL.list);
  }

  if ((m = p.match(/^\/drivers\/(\d{17})$/))) {
    const r = await ask(call, `/api/drivers/${m[1]}?lite=1`);
    if (!r.ok) return passFail(r);
    const d = r.data;
    return out({ steamId: m[1], name: d.name, country: d.country || null, url: site + PAGE.driver + m[1], team: team(d.team),
      rating: d.rating ? { rating: d.rating.rating ?? null, rank: d.rating.rank ?? null, races: d.rating.races ?? null, peak: d.rating.peak ?? null } : null },
    TTL.list);
  }

  return fail('no such endpoint: see /api/v1', 404);
}

/** GET /api/v1: what there is, with a link to the page for people. */
const INDEX = (site) => ({
  name: 'ACR Daily public API', version: API_VERSION, docs: `${site}/developers`,
  notes: ['Read-only, no key. Every origin may read it (CORS).', 'Times are in milliseconds; ?format=csv on the tables.',
    'A private rally\'s results need its invite code: ?code=XXXX-XXXX.', 'A hidden event keeps what it hides until it closes.'],
  endpoints: ['/api/v1/championships', '/api/v1/championships/{id}', '/api/v1/championships/{id}/standings?season={id}',
    '/api/v1/events/{id}', '/api/v1/events/{id}/live', '/api/v1/events/{id}/map', '/api/v1/cups/{id}', '/api/v1/dailies?date={YYYY-MM-DD}',
    '/api/v1/dailies/{date}/{slot}', '/api/v1/dailies/{date}/{slot}/live', '/api/v1/timetrials?week={Monday}',
    '/api/v1/timetrials/{week}/{slot}', '/api/v1/timetrials/{week}/{slot}/live', '/api/v1/ranking?country={cc}&page={n}',
    '/api/v1/drivers/{steamId}'].map((e) => site + e),
  broadcast: ['/broadcast/daily/{slot}', '/broadcast/tt/{slot}', '/broadcast/event/{id}'].map((e) => site + e),
});
