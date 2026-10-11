// The inbox: notices from ACR Daily (a challenge came in, a cup match is ready, a result) and short 1:1 messages
// between drivers, on the website (/inbox) and counted in the app. A driver can block another (no messages, no
// challenges from them) and report a message to the site's admins. Plus finding a driver by name (a message, a
// challenge).
//
//   GET  /api/inbox                    {unread, notices: [...], threads: [{with, last, unread}]}
//   GET  /api/inbox/unread             {unread} (the app and the website's header ask this)
//   GET  /api/inbox/with/<steamId>     the conversation with one driver (their messages to me are read now)
//   POST /api/inbox/send {to, body}    a message
//   POST /api/inbox/read {ids?}        notices read (all without ids)
//   POST /api/inbox/block {steamId, block: true|false}
//   POST /api/inbox/report {id, reason}
//   GET  /api/players?q=               drivers whose name has q (signed-in drivers of ACR Daily)

import { text } from './leagues.js';

export const MSG = { maxLen: 500, perHour: 30, keepDays: 180, list: 50 };

/** The statement for a notice to a driver (batched with what it tells of); with `cond` (SQL with plain ? binds) only
 *  when that holds as the batch gets to it (the same condition as the change it tells of: told once). */
export const noticeStmt = (env, to, kind, body, ref, now, cond = null, binds = []) => env.DB.prepare(
  `INSERT INTO messages (to_id, from_id, kind, body, ref, created) SELECT ?, NULL, ?, ?, ?, ?${cond ? ` WHERE ${cond}` : ''}`)
  .bind(to, kind, text(body, 300), ref || null, now, ...binds);

/** Does `who` block `whom`? */
export async function blocks(env, who, whom) {
  return !!await env.DB.prepare('SELECT 1 AS x FROM blocks WHERE steam_id = ? AND blocked = ?').bind(who, whom).first();
}

const playerOut = (p) => (p ? { steamId: p.steam_id, name: p.name, avatar: p.avatar || null, country: p.country || null } : null);

export async function socialApi(req, env, path, url, me, sameOrigin, now, { json, err }) {
  if (path === '/api/players') {                          // find a driver by name
    const q = text(url.searchParams.get('q'), 40);
    if (q.length < 2) return json({ players: [] });
    const { results } = await env.DB.prepare(`SELECT steam_id, name, avatar, country FROM players
      WHERE banned = 0 AND name LIKE ? ESCAPE '\\' ORDER BY name LIMIT 10`).bind('%' + q.replace(/[\\%_]/g, '\\$&') + '%').all();
    return json({ players: results.map(playerOut) });
  }
  if (!path.startsWith('/api/inbox')) return null;
  if (!me) return err('sign in with Steam first', 401);
  const post = req.method === 'POST';
  if (post && !sameOrigin) return err('refused: not from this site', 403);
  if (post && me.banned) return err('this account is banned', 403);
  const b = post ? await req.json().catch(() => ({})) || {} : {};

  if (path === '/api/inbox/unread' && !post) {
    const r = await env.DB.prepare('SELECT COUNT(*) AS n FROM messages WHERE to_id = ? AND read_at IS NULL').bind(me.steam_id).first();
    return json({ unread: r.n });
  }
  if (path === '/api/inbox' && !post) {
    const [no, th, un] = await env.DB.batch([
      env.DB.prepare(`SELECT id, kind, body, ref, created, read_at FROM messages WHERE to_id = ? AND from_id IS NULL
        ORDER BY id DESC LIMIT ?`).bind(me.steam_id, MSG.list),
      // each conversation's latest message, either way
      env.DB.prepare(`SELECT m.*, p.name, p.avatar, p.country FROM messages m
        JOIN (SELECT CASE WHEN from_id = ?1 THEN to_id ELSE from_id END AS other, MAX(id) AS last FROM messages
              WHERE from_id IS NOT NULL AND (to_id = ?1 OR from_id = ?1) GROUP BY other) t ON t.last = m.id
        JOIN players p ON p.steam_id = t.other ORDER BY m.id DESC LIMIT ?2`).bind(me.steam_id, MSG.list),
      env.DB.prepare(`SELECT from_id, COUNT(*) AS n FROM messages WHERE to_id = ? AND from_id IS NOT NULL AND read_at IS NULL
        GROUP BY from_id`).bind(me.steam_id),
    ]);
    const unreadFrom = new Map(un.results.map((r) => [r.from_id, r.n]));
    const blocked = new Set((await env.DB.prepare('SELECT blocked FROM blocks WHERE steam_id = ?').bind(me.steam_id).all())
      .results.map((r) => r.blocked));
    return json({
      unread: no.results.filter((n) => !n.read_at).length + [...unreadFrom.values()].reduce((a, x) => a + x, 0),
      notices: no.results.map((n) => ({ id: n.id, kind: n.kind, body: n.body, ref: n.ref, created: n.created, read: !!n.read_at })),
      threads: th.results.map((m) => {
        const other = m.from_id === me.steam_id ? m.to_id : m.from_id;
        return { with: { steamId: other, name: m.name, avatar: m.avatar || null, country: m.country || null },
          last: { body: m.body, created: m.created, mine: m.from_id === me.steam_id }, unread: unreadFrom.get(other) || 0,
          blocked: blocked.has(other) };
      }),
    });
  }
  let m = path.match(/^\/api\/inbox\/with\/(\d{17})$/);
  if (m && !post) {
    const other = playerOut(await env.DB.prepare('SELECT steam_id, name, avatar, country FROM players WHERE steam_id = ?').bind(m[1]).first());
    if (!other) return err('no such driver', 404);
    const { results } = await env.DB.prepare(`SELECT id, from_id, body, created, read_at FROM messages
      WHERE (from_id = ?1 AND to_id = ?2) OR (from_id = ?2 AND to_id = ?1) ORDER BY id DESC LIMIT 100`).bind(me.steam_id, m[1]).all();
    await env.DB.prepare('UPDATE messages SET read_at = ? WHERE to_id = ? AND from_id = ? AND read_at IS NULL').bind(now, me.steam_id, m[1]).run();
    return json({ with: other, blocked: await blocks(env, me.steam_id, m[1]),
      messages: results.reverse().map((x) => ({ id: x.id, mine: x.from_id === me.steam_id, body: x.body, created: x.created })) });
  }
  if (!post) return err('not found', 404);
  if (path === '/api/inbox/send') {
    const to = String(b.to || '');
    const body = String(b.body == null ? '' : b.body).replace(/\r\n?/g, '\n').replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g, ' ')
      .replace(/\n{3,}/g, '\n\n').trim().slice(0, MSG.maxLen);
    if (!body) return err('write something');
    if (to === me.steam_id) return err('that is you');
    const p = await env.DB.prepare('SELECT steam_id, banned FROM players WHERE steam_id = ?').bind(to).first();
    if (!p || p.banned) return err('no such driver', 404);
    if (await blocks(env, to, me.steam_id)) return err('this driver takes no messages from you', 403);
    const sent = await env.DB.prepare('SELECT COUNT(*) AS n FROM messages WHERE from_id = ? AND created > ?')
      .bind(me.steam_id, now - 3600000).first();
    if (sent.n >= MSG.perHour) return err(`${MSG.perHour} messages an hour at most: try again later`, 429);
    const r = await env.DB.prepare('INSERT INTO messages (to_id, from_id, kind, body, created) VALUES (?, ?, \'msg\', ?, ?)')
      .bind(to, me.steam_id, body, now).run();
    return json({ id: r.meta.last_row_id });
  }
  if (path === '/api/inbox/read') {
    if (Array.isArray(b.ids) && b.ids.length) {
      const ids = b.ids.slice(0, 100).map((x) => Math.round(+x)).filter(Number.isFinite);
      await env.DB.prepare(`UPDATE messages SET read_at = ? WHERE to_id = ? AND from_id IS NULL AND read_at IS NULL
        AND id IN (${ids.map(() => '?').join(',')})`).bind(now, me.steam_id, ...ids).run();
    } else {
      await env.DB.prepare('UPDATE messages SET read_at = ? WHERE to_id = ? AND from_id IS NULL AND read_at IS NULL').bind(now, me.steam_id).run();
    }
    return json({ ok: true });
  }
  if (path === '/api/inbox/block') {
    const sid = String(b.steamId || '');
    if (!/^\d{17}$/.test(sid) || sid === me.steam_id) return err('no such driver', 404);
    if (b.block === false) await env.DB.prepare('DELETE FROM blocks WHERE steam_id = ? AND blocked = ?').bind(me.steam_id, sid).run();
    else await env.DB.prepare('INSERT OR IGNORE INTO blocks (steam_id, blocked, created) VALUES (?, ?, ?)').bind(me.steam_id, sid, now).run();
    return json({ blocked: b.block !== false });
  }
  if (path === '/api/inbox/report') {
    const id = Math.round(+b.id);
    const msg = await env.DB.prepare('SELECT id FROM messages WHERE id = ? AND to_id = ? AND from_id IS NOT NULL').bind(id, me.steam_id).first();
    if (!msg) return err('no such message', 404);
    await env.DB.prepare('INSERT OR IGNORE INTO message_reports (message_id, by, reason, created) VALUES (?, ?, ?, ?)')
      .bind(id, me.steam_id, text(b.reason, 200) || null, now).run();
    return json({ reported: true });
  }
  return err('not found', 404);
}

/** Old messages go (the cron, once a day). */
export async function trimMessages(env, now) {
  return env.DB.prepare('DELETE FROM messages WHERE created < ?').bind(now - MSG.keepDays * 86400000).run();
}
