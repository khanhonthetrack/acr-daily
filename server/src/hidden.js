// Hidden events: what a league event, a 1V1 or a cup keeps from its drivers until it ends, so nobody hotlaps it
// beforehand (league_events.hide, JSON {weather, times, stages}; set in the event's form, all three by default since
// migration 0029; events made before it hide nothing):
//   weather  the stages' weather
//   times    the stages' time of day, and the drivers' results (stage times, totals, positions, gaps, splits)
//   stages   the stages' names, lengths and maps (the location stays)
// It ends when the event does: a league event or a 1V1 once it has closed (and its grace for late results is over), or a
// 1V1 when it is settled; a cup's matches when the cup is over (every round races the same stages: src/cups.js clears it).
//
// Who sees what before then: the league's owner and admins see everything (they set it up and steward it); a 1V1's
// challenger and a cup's maker see the set-up (not the others' results); a driver sees the set-up once their app has
// asked for it to set the rally up (DRIVE: POST /api/events/:id/reveal, kept in event_reveals) or once they have started
// it, and their own times. Everyone else sees "Hidden". The app needs the stages to set the game's save up, so a
// determined driver can still find them in the save after DRIVE; starting the stage commits them (a restart is a DNF).

import { LIMITS } from './leagues.js';

export const hideOf = (ev) => (ev && ev.hide ? JSON.parse(ev.hide) : null);

/** The event's hide flags while they still hold: null when nothing is hidden (any more). kind: its league's kind. */
export function activeHide(ev, kind, now) {
  const h = hideOf(ev);
  if (!h || !(h.weather || h.times || h.stages)) return null;
  if (kind !== 'cup' && now > ev.closes + LIMITS.graceMs) return null;
  return h;
}

/** What one viewer doesn't see of an event: h = activeHide(); knows: they see its set-up (staff, its maker, a driver who
 *  revealed or started it); staff: the league's owner or admins (they see the results too). -> {weather, time, stages,
 *  results} (true: kept from them), or null when they see everything. */
export function viewHide(h, { knows = false, staff = false } = {}) {
  if (!h || staff) return null;
  const v = { weather: !!h.weather && !knows, time: !!h.times && !knows, stages: !!h.stages && !knows, results: !!h.times };
  return v.weather || v.time || v.stages || v.results ? v : null;
}

/** An event as eventOut gives it, with what the viewer may not see taken out (null). Sets o.hidden (the event's own
 *  flags, or null) and o.revealed (whether the viewer sees its set-up). */
export function maskEvent(o, h, v) {
  o.hidden = h ? { weather: !!h.weather, times: !!h.times, stages: !!h.stages } : null;
  o.revealed = !v || !(v.weather || v.time || v.stages);
  if (!v) return o;
  o.stages = o.stages.map((s) => maskStage(s, v));
  if (v.stages) o.lengthM = null;
  return o;
}

/** One stage (eventOut's, or a cup's or a 1V1's as they list it) without what v keeps. */
export function maskStage(s, v) {
  if (!v) return s;
  const out = { ...s };
  if (v.stages) Object.assign(out, { track: null, name: null, stageId: null, lengthM: null });
  if (v.weather) Object.assign(out, { weather: null, weatherLabel: null, weatherGame: null });
  if (v.time) Object.assign(out, { time: null, startSeconds: null });
  return out;
}

const ORDER = { finished: 0, running: 1, dnf: 2, dsq: 3 };

/** Standings rows (eventStandings) without the results: everyone's status and how many stages they have driven, by
 *  name; only `me` keeps their own times (no position: that would tell the others' pace). */
export function maskRows(rows, me) {
  return rows.map((r) => {
    const mine = me && r.steamId === me;
    return { ...r, rank: null, gapMs: null, ...(mine ? {} : { totalMs: null, penaltyMs: null, stewardMs: null }),
      stages: r.stages.map((x) => (!x ? null : mine ? { ...x, pos: null, cumPos: null }
        : { timeMs: null, penaltyMs: null, stewardMs: null, totalMs: null, pos: null, cumPos: null, splits: null })) };
  }).sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.name || '').localeCompare(b.name || ''));
}

/** The events of `ids` whose set-up `sid` sees, and those whose results too: -> {knows: Set, staff: Set} (one query). */
export async function viewerOf(env, sid, ids) {
  const knows = new Set(), staff = new Set();
  if (!sid || !ids.length) return { knows, staff };
  const { results } = await env.DB.prepare(`SELECT e.id, (l.kind = 'league' AND (l.owner = ?2 OR EXISTS (SELECT 1 FROM league_members m
      WHERE m.league_id = l.id AND m.steam_id = ?2 AND m.role = 'admin'))) AS staff FROM league_events e JOIN leagues l ON l.id = e.league_id
    WHERE e.id IN (SELECT value FROM json_each(?1)) AND (l.owner = ?2
      OR (l.kind = 'league' AND EXISTS (SELECT 1 FROM league_members m WHERE m.league_id = l.id AND m.steam_id = ?2 AND m.role = 'admin'))
      OR EXISTS (SELECT 1 FROM league_entries x WHERE x.event_id = e.id AND x.steam_id = ?2)
      OR EXISTS (SELECT 1 FROM event_reveals r WHERE r.event_id = e.id AND r.steam_id = ?2))`).bind(JSON.stringify(ids), sid).all();
  for (const r of results) { knows.add(r.id); if (r.staff) staff.add(r.id); }
  return { knows, staff };
}
