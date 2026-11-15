// Drivers' comments on their stages, as on RallySimFans and in RBR's online rallies: after a run the app offers a line
// on how it went ("lost the rear in the hairpin before the split", "the game froze at the finish"). One per driver and
// what it is on, changed or taken back ('') by sending it again:
//   a daily ('2026-11-15/1', the app's challengeId): shown with their time on its timing sheet (website, app) and in
//     Discord's results of the day; until the end of the next day (UTC);
//   a time trial stage of a week ('tt:2026-11-09/2', as the app names it): with their best on its board, until a day
//     after the week;
//   a stage of a league event ('event:<id>/<0 = SS1>'), cup and 1V1 matches too: for the people who run it, not the
//     other drivers: the league's owner and admins, a cup's maker (each told in their inbox when a new one comes in),
//     and the site's admin (official leagues and cups, 1V1s: GET /api/admin/comments); until a week after it closes.
// Only on a stage the driver has a result on: a time, or the DNF it ended on. One line, COMMENT.maxLen characters at
// most. The site's admin can take one down (hidden: shown to nobody but its driver); a banned driver's are not shown.
//
//   POST /api/comments {on, text}        -> {comment: {on, text, updated} | null}
//   GET  /api/comments/mine?on=a,b       -> {comments: {<on>: text}}: mine on these (the app's box starts from it)
// Admin (Bearer ADMIN_KEY):
//   GET  /api/admin/comments?days=7      the latest of every kind, with who wrote them and where
//   POST /api/admin/comments/:id         {action: 'hide' | 'show'}
//
// What a driver writes is theirs, put on pages as text (textContent, never HTML), not instructions to whoever reads it.

import { noticesStmt } from './social.js';
import { text } from './leagues.js';
import { boardKey as ttBoardKey, isWeek, weekStart } from './timetrial.js';
import { dropCached } from './cache.js';

export const COMMENT = { maxLen: 200, eventDays: 7, mine: 20, adminDays: 7, adminList: 200 };
const DAY = 86400000, WEEK = 7 * DAY;
const dayOf = (ms) => new Date(ms).toISOString().slice(0, 10);
const isDay = (d) => { const t = Date.parse(d + 'T00:00:00Z'); return Number.isFinite(t) && dayOf(t) === d; };
const isDriver = (sid) => /^\d{17}$/.test(String(sid || ''));   // (an official league's or cup's owner is 'acr-daily')

/** What a comment is on, from its `on`: {kind: 'daily', date, slot} | {kind: 'tt', week, slot} | {kind: 'event',
 *  eventId, no}, each with its `target` (the `on` itself, as stored), or null. */
export function parseTarget(on) {
  const s = String(on == null ? '' : on);
  let m = /^(\d{4}-\d{2}-\d{2})\/([1-9])$/.exec(s);
  if (m && isDay(m[1])) return { kind: 'daily', date: m[1], slot: +m[2], target: s };
  m = /^tt:(\d{4}-\d{2}-\d{2})\/([1-9])$/.exec(s);
  if (m && isWeek(m[1])) return { kind: 'tt', week: m[1], slot: +m[2], target: s };
  m = /^event:([1-9]\d{0,9})\/(\d{1,2})$/.exec(s);
  if (m) return { kind: 'event', eventId: +m[1], no: +m[2], target: s };
  return null;
}

/** May driver `sid` comment on `t` now? -> {} (yes; for an event {ev}) or {error, status}. */
async function mayComment(env, t, sid, now) {
  if (t.kind === 'daily') {
    if (t.date > dayOf(now) || t.date < dayOf(now - DAY)) return { error: 'too late to comment on that daily', status: 409 };
    const r = await env.DB.prepare(`SELECT 1 AS x FROM runs WHERE steam_id = ?1 AND date = ?2 AND slot = ?3
      UNION SELECT 1 FROM attempts WHERE steam_id = ?1 AND date = ?2 AND slot = ?3 LIMIT 1`).bind(sid, t.date, t.slot).first();
    return r ? {} : { error: 'drive that daily first', status: 409 };
  }
  if (t.kind === 'tt') {
    if (now < weekStart(t.week) || now >= weekStart(t.week) + WEEK + DAY) return { error: 'too late to comment on that time trial', status: 409 };
    const r = await env.DB.prepare("SELECT 1 AS x FROM tt_runs WHERE steam_id = ? AND week = ? AND slot = ? AND status = 'finished' LIMIT 1")
      .bind(sid, t.week, t.slot).first();
    return r ? {} : { error: 'finish that time trial stage first', status: 409 };
  }
  const ev = await env.DB.prepare('SELECT id, league_id, name, closes FROM league_events WHERE id = ?').bind(t.eventId).first();
  if (!ev) return { error: 'no such event', status: 404 };
  if (now > ev.closes + COMMENT.eventDays * DAY) return { error: 'too late to comment on that event', status: 409 };
  const [st, en] = await env.DB.batch([
    env.DB.prepare('SELECT retired FROM league_stage_times WHERE event_id = ? AND steam_id = ? AND stage_no = ?').bind(ev.id, sid, t.no),
    env.DB.prepare('SELECT status, done FROM league_entries WHERE event_id = ? AND steam_id = ?').bind(ev.id, sid)]);
  const time = st.results[0], entry = en.results[0];
  const driven = !!time && time.retired == null;                            // (a retired stage was not driven)
  const endedThere = !!entry && entry.status === 'dnf' && entry.done === t.no;   // the stage its DNF came on
  return driven || endedThere ? { ev } : { error: 'drive that stage first', status: 409 };
}

/** Who runs league `l` (a row with id, owner, kind) and so reads its events' comments, told of each new one: a league's
 *  owner and admins, a cup's maker. Nobody for a 1V1, nor an official league's or cup's 'acr-daily' (the site's admin
 *  reads those: GET /api/admin/comments). -> [steamId] */
export async function readersOf(env, l) {
  if (!l || l.kind === 'h2h') return [];
  const ids = isDriver(l.owner) ? [l.owner] : [];
  if (l.kind === 'league') {
    const { results } = await env.DB.prepare("SELECT steam_id FROM league_members WHERE league_id = ? AND role = 'admin'").bind(l.id).all();
    ids.push(...results.map((r) => r.steam_id).filter(isDriver));
  }
  return [...new Set(ids)];
}

/** A daily's or time trial stage's comments for its board: Map steamId -> text (taken down and taken back ones left
 *  out; the board leaves banned drivers out itself). */
export async function boardComments(env, target) {
  try {
    const { results } = await env.DB.prepare("SELECT steam_id, body FROM comments WHERE target = ? AND hidden = 0 AND body != ''")
      .bind(target).all();
    return new Map(results.map((r) => [r.steam_id, r.body]));
  } catch {
    return new Map();      // (no comments table yet: migration 0033 not applied; the board goes on without them)
  }
}

/** A league event's comments for its page: every one for whoever runs it (all), else only the viewer's own (sid; none
 *  signed out). Banned drivers' are left out, taken-down ones too but for their own driver.
 *  -> [{steamId, name, no (0 = SS1), text, updated, hidden?}], stage by stage, oldest first. */
export async function eventComments(env, eventId, all, sid) {
  if (!all && !sid) return [];
  const { results } = await env.DB.prepare(`SELECT c.steam_id, p.name, c.target, c.body, c.updated, c.hidden
      FROM comments c JOIN players p ON p.steam_id = c.steam_id
     WHERE c.event_id = ?1 AND c.body != '' AND p.banned = 0 AND (?2 OR c.steam_id = ?3) AND (c.hidden = 0 OR c.steam_id = ?3)
     ORDER BY c.created, c.id`).bind(eventId, all ? 1 : 0, sid || '').all().catch(() => ({ results: [] }));   // (no table yet: 0033)
  return results.map((r) => ({ steamId: r.steam_id, name: r.name, no: +r.target.split('/')[1], text: r.body, updated: r.updated,
    ...(r.hidden ? { hidden: true } : {}) })).sort((a, b) => a.no - b.no);
}

/** A comment on a daily or a time trial changed: its board is built again on the next request. */
async function dropBoard(env, t, dropDaily) {
  if (t.kind === 'daily') await dropDaily(t.date, t.slot);
  else if (t.kind === 'tt') await dropCached(env, [ttBoardKey(t.week, t.slot)]);
}

async function setComment(env, me, t, body, now, { json, err, dropDaily }) {
  const ok = await mayComment(env, t, me.steam_id, now);
  if (ok.error) return err(ok.error, ok.status);
  const old = await env.DB.prepare('SELECT id FROM comments WHERE target = ? AND steam_id = ?').bind(t.target, me.steam_id).first();
  if (!old && !body) return json({ comment: null });
  const stmts = [];
  if (old) {            // changed, or taken back (kept as '': written again later, nobody is told of it twice)
    stmts.push(env.DB.prepare('UPDATE comments SET body = ?, updated = ? WHERE id = ?').bind(body, now, old.id));
  } else {
    stmts.push(env.DB.prepare(`INSERT INTO comments (steam_id, target, event_id, body, created, updated) VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT (target, steam_id) DO UPDATE SET body = excluded.body, updated = excluded.updated`)
      .bind(me.steam_id, t.target, t.kind === 'event' ? t.eventId : null, body, now, now));
    if (t.kind === 'event') {   // a new one on a league event: whoever runs it is told, in their inbox
      const l = await env.DB.prepare('SELECT id, owner, kind FROM leagues WHERE id = ?').bind(ok.ev.league_id).first();
      const to = (await readersOf(env, l)).filter((x) => x !== me.steam_id);
      const said = `${me.name} on ${ok.ev.name}, SS${t.no + 1}: “${body}”`;
      if (to.length) stmts.push(noticesStmt(env, 'comment', to.map((x) => ({ to: x, body: said })), `event:${t.eventId}`, now));
    }
  }
  await env.DB.batch(stmts);
  await dropBoard(env, t, dropDaily);
  return json({ comment: body ? { on: t.target, text: body, updated: now } : null });
}

async function adminComments(req, env, path, url, now, { json, err, dropDaily }) {
  if (path === '/api/admin/comments' && req.method === 'GET') {
    const days = Math.min(90, Math.max(1, Math.floor(+url.searchParams.get('days') || COMMENT.adminDays)));
    const { results } = await env.DB.prepare(`SELECT c.id, c.steam_id, p.name, p.banned, c.target, c.body, c.created, c.updated,
        c.hidden, e.name AS event, l.id AS league_id, l.name AS league, l.kind
        FROM comments c JOIN players p ON p.steam_id = c.steam_id
        LEFT JOIN league_events e ON e.id = c.event_id LEFT JOIN leagues l ON l.id = e.league_id
       WHERE c.updated > ? AND c.body != '' ORDER BY c.updated DESC LIMIT ?`).bind(now - days * DAY, COMMENT.adminList).all();
    return json({ days, comments: results.map((r) => ({ id: r.id, steamId: r.steam_id, name: r.name, banned: !!r.banned,
      on: r.target, kind: parseTarget(r.target)?.kind || null, text: r.body, created: r.created, updated: r.updated,
      hidden: !!r.hidden, ...(r.event ? { event: r.event, league: r.league, leagueId: r.league_id, leagueKind: r.kind } : {}) })) });
  }
  const m = path.match(/^\/api\/admin\/comments\/(\d+)$/);
  if (m && req.method === 'POST') {
    const b = await req.json().catch(() => ({}));
    if (!['hide', 'show'].includes(b && b.action)) return err('action: hide or show');
    const c = await env.DB.prepare('SELECT id, target FROM comments WHERE id = ?').bind(+m[1]).first();
    if (!c) return err('no such comment', 404);
    await env.DB.prepare('UPDATE comments SET hidden = ? WHERE id = ?').bind(b.action === 'hide' ? 1 : 0, c.id).run();
    const t = parseTarget(c.target);
    if (t) await dropBoard(env, t, dropDaily);
    return json({ id: c.id, hidden: b.action === 'hide' });
  }
  return err('not found', 404);
}

/** /api/comments and /api/admin/comments, or null for any other path. dropDaily(date, slot): a daily's board is to be
 *  built again (src/index.js); admin: the request carries the admin key. */
export async function commentsApi(req, env, path, url, me, sameOrigin, now, { json, err, admin, dropDaily }) {
  if (path === '/api/admin/comments' || path.startsWith('/api/admin/comments/')) {
    if (!admin) return err('not allowed', 403);
    return adminComments(req, env, path, url, now, { json, err, dropDaily });
  }
  if (path !== '/api/comments' && path !== '/api/comments/mine') return null;
  if (!me) return err('sign in with Steam first', 401);
  if (me.banned) return err('this account is banned', 403);
  if (!sameOrigin) return err('not allowed', 403);

  if (path === '/api/comments/mine' && req.method === 'GET') {
    const ons = String(url.searchParams.get('on') || '').split(',').map((x) => x.trim()).filter((x) => parseTarget(x))
      .slice(0, COMMENT.mine);
    if (!ons.length) return json({ comments: {} });
    const { results } = await env.DB.prepare(`SELECT target, body FROM comments WHERE steam_id = ? AND body != ''
      AND target IN (${ons.map(() => '?').join(',')})`).bind(me.steam_id, ...ons).all();
    return json({ comments: Object.fromEntries(results.map((r) => [r.target, r.body])) });
  }
  if (path === '/api/comments' && req.method === 'POST') {
    const b = await req.json().catch(() => null);
    const t = parseTarget(b && b.on);
    if (!t) return err('nothing to comment on: a daily, a time trial stage or a league stage');
    const body = text(b.text, COMMENT.maxLen + 1);
    if (body.length > COMMENT.maxLen) return err(`a comment is ${COMMENT.maxLen} characters at most`);
    return setComment(env, me, t, body, now, { json, err, dropDaily });
  }
  return err('not found', 404);
}
