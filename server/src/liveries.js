// Liveries (the /liveries page, src/liverypage.js; the app's COMMUNITY > LIVERIES, client acr_daily/liveries.py): the
// drivers' liveries for the game's cars. The file stays where its author put it (Overtake.gg, Google Drive, Dropbox,
// a GitHub release...): the site keeps a card with a preview, the link, the drivers' stars and the downloads. A driver
// sends one (signed in with Steam); it shows once the admin has published it (the /admin page, tools/admin.py liveries).
//
// In the game a livery is a folder, Documents\My Games\acr\Liveries\<car>\<name>\ (what ACR Livery Tool exports), 25
// a car at most, seen when the game starts. The app installs one from its zip in one click when the link gives the zip
// itself (directUrl: a GitHub release, Dropbox, Google Drive, a .zip address); other links (a download page) open in
// the browser.
//
//   GET  /api/liveries?car=                 the published ones (+ my stars when signed in), the cars with their counts
//   GET  /api/liveries/:id/shot?v=          its preview (published; any for the admin)
//   GET  /api/liveries/:id/go[?direct=1]    -> its link (direct: the zip itself), a download counted
//   POST /api/liveries                      {car, title, author, link, description, shot: data URL} -> {id} (pending)
//   GET  /api/liveries/mine                 my own, all of them, and where each stands
//   POST /api/liveries/:id/vote             {stars: 1..5} -> {votes, stars, mine}
//   POST /api/liveries/:id/flag             "link not working?" (once a driver, until the admin has looked)
//   POST /api/liveries/:id/delete           my own one, gone
// Admin (Bearer ADMIN_KEY):
//   GET  /api/admin/liveries?status=pending|published|rejected|hidden|flagged|all
//   POST /api/admin/liveries                {car, title, author, link, description, shot, status?}: one found on the
//                                           web (tools/admin.py livery-import), published (or pending) at once; its
//                                           link is the author's own page, the file stays there. Sent by IMPORTED
//                                           (its author has no account here: never told, no "sent by"). A link
//                                           already on the page: nothing added -> {id, status, existing}
//   POST /api/admin/liveries/:id            {action: publish|reject|hide|delete|clear, note, link}: the sender is told
//
// What a driver writes is shown as text (never as markup), and a link is an https address only.

import { CARS } from './cars.js';
import { text } from './leagues.js';
import { para, sniff } from './reports.js';
import { noticeStmt } from './social.js';
import { bytesOf } from './drivers.js';

export const LIVERY = {
  perDay: 5,                 // liveries a driver can send in 24 hours
  allPerDay: 100,            // everyone's together
  waiting: 5,                // a driver's liveries waiting for the admin at once
  maxShotBytes: 1000000,     // the preview as stored (the page squeezes it to a JPEG at most 1600 px wide first)
  title: [2, 80], author: [2, 60], description: 1500, link: 500,
  perCar: 25,                // the game's own limit: user liveries a car (said on the page and by the app)
};
// pending: waiting for the admin; published: on the page and in the app; rejected: turned down (the note says why);
// hidden: taken off after it was published (a dead link, a complaint), its votes and downloads kept
export const STATUSES = ['pending', 'published', 'rejected', 'hidden'];
/** The sender of a livery the admin brought in from the web (its author has no account here): no inbox, no "sent by". */
export const IMPORTED = 'imported';
export const HOSTS = { 'overtake.gg': 'Overtake.gg', 'drive.google.com': 'Google Drive', 'dropbox.com': 'Dropbox',
  'mega.nz': 'MEGA', 'mediafire.com': 'MediaFire', 'github.com': 'GitHub' };
const SAID = { published: 'is published: it is on the liveries page and in the app', rejected: 'was not published',
  hidden: 'was taken off the liveries page' };

const carOf = (id) => CARS.find((c) => c.id === id) || null;

/** A link's host without www. ('overtake.gg'), or ''. */
export function hostOf(link) {
  try {
    return new URL(link).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return '';
  }
}

/** The address of the zip itself, for the app to download without a web page in the way, or null (a page: the
 *  browser). A GitHub release asset, a Dropbox share (dl=1), a Google Drive file, any https address of a .zip. */
export function directUrl(link) {
  let u;
  try {
    u = new URL(link);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:') return null;
  const host = u.hostname.toLowerCase().replace(/^www\./, '');
  if (host === 'github.com' && /^\/[\w.-]+\/[\w.-]+\/releases\/download\/[^/]+\/[^/]+$/.test(u.pathname)) return u.href;
  if (host === 'dropbox.com' || host === 'dl.dropboxusercontent.com') {
    if (host === 'dropbox.com' && !/^\/(s|scl\/fi)\//.test(u.pathname)) return null;      // (a folder, a page)
    u.searchParams.set('dl', '1');
    return u.href;
  }
  if (host === 'drive.google.com') {
    const id = (u.pathname.match(/^\/file\/d\/([\w-]{10,})/) || [])[1] || (/^\/(open|uc)$/.test(u.pathname) && u.searchParams.get('id'));
    return id && /^[\w-]{10,}$/.test(id) ? `https://drive.usercontent.google.com/download?id=${id}&export=download&confirm=t` : null;
  }
  return /\.zip$/i.test(u.pathname) ? u.href : null;
}

/** A livery's fields from the form -> {value} or {error}. */
export function checkLivery(b) {
  b = b || {};
  const car = carOf(String(b.car || ''));
  if (!car) return { error: 'pick the car' };
  const title = text(b.title, LIVERY.title[1] + 1), author = text(b.author, LIVERY.author[1] + 1);
  if (title.length < LIVERY.title[0] || title.length > LIVERY.title[1]) return { error: `a name of ${LIVERY.title[0]} to ${LIVERY.title[1]} characters` };
  if (author.length < LIVERY.author[0] || author.length > LIVERY.author[1]) return { error: `the author: ${LIVERY.author[0]} to ${LIVERY.author[1]} characters` };
  const description = para(b.description, LIVERY.description + 1);
  if (description.length > LIVERY.description) return { error: `the description: ${LIVERY.description} characters at most` };
  const link = String(b.link == null ? '' : b.link).trim();
  if (link) {
    if (link.length > LIVERY.link) return { error: `the link: ${LIVERY.link} characters at most` };
    let u;
    try {
      u = new URL(link);
    } catch {
      return { error: 'the link is not a web address' };
    }
    if (u.protocol !== 'https:' || u.username || u.password || !u.hostname.includes('.')) return { error: 'the link: an https:// address' };
  }
  return { value: { car: car.id, title, author, description: description || null, link: link || null } };
}

/** A data URL (data:image/jpeg;base64,...) -> its bytes, or null. */
export function dataUrlBytes(s) {
  const m = /^data:image\/(?:jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)$/.exec(String(s || ''));
  if (!m) return null;
  try {
    return Uint8Array.from(atob(m[1].replace(/\s+/g, '')), (c) => c.charCodeAt(0));
  } catch {
    return null;
  }
}

const shotVersion = (bytes) => {      // a short tag of the preview, so its address can be kept by browsers for good
  let h = 2166136261;
  for (let i = 0; i < bytes.length; i += 7) h = Math.imul(h ^ bytes[i], 16777619) >>> 0;
  return ((h ^ bytes.length) >>> 0).toString(36);
};

const avg = (r) => (r.votes ? Math.round((r.stars_sum / r.votes) * 10) / 10 : 0);

/** A row as the page and the app see it. origin: the site's address (the app needs whole addresses). */
export function liveryOut(r, origin = '', mine = 0) {
  const car = carOf(r.car), host = r.link ? hostOf(r.link) : '';
  return { id: r.id, car: r.car, carName: car ? car.name : r.car, title: r.title, author: r.author,
    by: { steamId: r.steam_id, name: r.sender || null }, description: r.description || '', link: r.link || '',
    host, hostName: HOSTS[host] || host, direct: !!(r.link && directUrl(r.link)),
    shot: r.shot_v ? `${origin}/api/liveries/${r.id}/shot?v=${r.shot_v}` : null,
    go: r.link ? `${origin}/api/liveries/${r.id}/go` : null,
    clicks: r.clicks, votes: r.votes, stars: avg(r), mine: mine || 0, published: r.published, created: r.created };
}

const COLS = `l.id, l.steam_id, l.car, l.title, l.author, l.description, l.link, l.status, l.note, l.clicks, l.votes, l.stars_sum,
  l.flags, l.shot_v, l.created, l.updated, l.published, p.name AS sender`;

export async function liveriesApi(req, env, path, url, me, sameOrigin, now, { json, err, admin }) {
  if (path.startsWith('/api/admin/liveries')) {
    if (!admin) return err('not allowed', 403);
    return adminLiveries(req, env, path, url, now, { json, err });
  }
  if (path !== '/api/liveries' && !path.startsWith('/api/liveries/')) return null;
  const post = req.method === 'POST';
  const origin = url.origin;
  const need = () => (!me ? err('sign in with Steam first', 401) : me.banned ? err('this account is banned', 403)
    : !sameOrigin ? err('not allowed', 403) : null);

  if (path === '/api/liveries' && !post) {
    const car = url.searchParams.get('car');
    const [list, counts, votes] = await env.DB.batch([
      env.DB.prepare(`SELECT ${COLS} FROM liveries l LEFT JOIN players p ON p.steam_id = l.steam_id
        WHERE l.status = 'published' AND (?1 IS NULL OR l.car = ?1) ORDER BY l.published DESC LIMIT 500`).bind(carOf(car) ? car : null),
      env.DB.prepare(`SELECT car, COUNT(*) AS n FROM liveries WHERE status = 'published' GROUP BY car`),
      env.DB.prepare(`SELECT v.livery_id, v.stars FROM livery_votes v JOIN liveries l ON l.id = v.livery_id
        WHERE v.steam_id = ? AND l.status = 'published'`).bind(me ? me.steam_id : ''),
    ]);
    const mine = new Map(votes.results.map((v) => [v.livery_id, v.stars]));
    const n = new Map(counts.results.map((c) => [c.car, c.n]));
    return json({ liveries: list.results.map((r) => liveryOut(r, origin, mine.get(r.id))),
      cars: CARS.map((c) => ({ id: c.id, name: c.name, count: n.get(c.id) || 0 })), signedIn: !!me,
      limits: { perCar: LIVERY.perCar, maxShotBytes: LIVERY.maxShotBytes, title: LIVERY.title, author: LIVERY.author,
        description: LIVERY.description, link: LIVERY.link }, hosts: HOSTS });
  }

  const sm = path.match(/^\/api\/liveries\/(\d+)\/shot$/);
  if (sm && !post) return shotResponse(env, +sm[1], { err, any: false });

  const gm = path.match(/^\/api\/liveries\/(\d+)\/go$/);
  if (gm && !post) {
    const r = await env.DB.prepare("SELECT id, link FROM liveries WHERE id = ? AND status = 'published'").bind(+gm[1]).first();
    if (!r || !r.link) return err('no such livery', 404);
    const to = url.searchParams.get('direct') === '1' ? directUrl(r.link) : r.link;
    if (!to) return err('its link is a page, not the file: open it in the browser', 409);
    await env.DB.prepare('UPDATE liveries SET clicks = clicks + 1 WHERE id = ?').bind(r.id).run();
    return new Response(null, { status: 302, headers: { Location: to, 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' } });
  }

  if (path === '/api/liveries/mine' && !post) {
    if (!me) return err('sign in with Steam first', 401);
    const { results } = await env.DB.prepare(`SELECT ${COLS} FROM liveries l LEFT JOIN players p ON p.steam_id = l.steam_id
      WHERE l.steam_id = ? ORDER BY l.id DESC LIMIT 100`).bind(me.steam_id).all();
    return json({ liveries: results.map((r) => ({ ...liveryOut(r, origin), status: r.status, note: r.note || '' })) });
  }

  if (path === '/api/liveries' && post) {
    const no = need();
    if (no) return no;
    if (+(req.headers.get('Content-Length') || 0) > LIVERY.maxShotBytes * 1.4 + 20000) return err('the preview is too big', 413);
    const b = await req.json().catch(() => null);
    const c = checkLivery(b);
    if (c.error) return err(c.error);
    const shot = dataUrlBytes(b.shot);
    if (!shot || !shot.length) return err('add the preview picture (a screenshot of the car wearing it)');
    if (shot.length > LIVERY.maxShotBytes) return err(`the preview: ${(LIVERY.maxShotBytes / 1e6).toFixed(1)} MB at most`, 413);
    const type = sniff(shot);
    if (!type || !type.startsWith('image/')) return err('the preview: a JPEG, PNG or WebP picture', 415);
    const v = c.value, day = now - 86400000;
    // the limits in the insert itself: two sent at once can't both slip under them
    const r = await env.DB.prepare(`INSERT INTO liveries (steam_id, car, title, author, description, link, status, shot_v, created, updated)
      SELECT ?1, ?2, ?3, ?4, ?5, ?6, 'pending', ?7, ?8, ?8
      WHERE (SELECT COUNT(*) FROM liveries WHERE steam_id = ?1 AND created > ?9) < ?10
        AND (SELECT COUNT(*) FROM liveries WHERE steam_id = ?1 AND status = 'pending') < ?11
        AND (SELECT COUNT(*) FROM liveries WHERE created > ?9) < ?12`)
      .bind(me.steam_id, v.car, v.title, v.author, v.description, v.link, shotVersion(shot), now, day,
        LIVERY.perDay, LIVERY.waiting, LIVERY.allPerDay).run();
    if (!r.meta.changes) return err(`${LIVERY.perDay} liveries a day and ${LIVERY.waiting} waiting at most: come back once the admin has looked`, 429);
    const id = r.meta.last_row_id;
    try {
      await env.DB.prepare('INSERT INTO livery_shots (livery_id, type, data, created) VALUES (?, ?, ?, ?)').bind(id, type, shot.buffer, now).run();
    } catch (e) {
      await env.DB.prepare('DELETE FROM liveries WHERE id = ?').bind(id).run();
      throw e;
    }
    return json({ id, status: 'pending' });
  }

  const am = path.match(/^\/api\/liveries\/(\d+)\/(vote|flag|delete)$/);
  if (am && post) {
    const no = need();
    if (no) return no;
    const id = +am[1];
    const row = await env.DB.prepare('SELECT id, steam_id, status FROM liveries WHERE id = ?').bind(id).first();
    if (am[2] === 'delete') {
      if (!row || row.steam_id !== me.steam_id) return err('no such livery of yours', 404);
      await env.DB.batch(['liveries WHERE id', 'livery_shots WHERE livery_id', 'livery_votes WHERE livery_id', 'livery_flags WHERE livery_id']
        .map((t) => env.DB.prepare(`DELETE FROM ${t} = ?`).bind(id)));
      return json({ deleted: true });
    }
    if (!row || row.status !== 'published') return err('no such livery', 404);
    if (am[2] === 'flag') {
      const f = await env.DB.prepare('INSERT OR IGNORE INTO livery_flags (livery_id, steam_id, created) VALUES (?, ?, ?)').bind(id, me.steam_id, now).run();
      if (f.meta.changes) await env.DB.prepare('UPDATE liveries SET flags = flags + 1 WHERE id = ?').bind(id).run();
      return json({ flagged: true });
    }
    const b = await req.json().catch(() => ({})) || {};
    const stars = Number(b.stars);
    if (!Number.isInteger(stars) || stars < 1 || stars > 5) return err('stars: 1 to 5');
    if (row.steam_id === me.steam_id) return err('not on your own livery', 403);
    const [, , got] = await env.DB.batch([
      env.DB.prepare(`INSERT INTO livery_votes (livery_id, steam_id, stars, created) VALUES (?, ?, ?, ?)
        ON CONFLICT (livery_id, steam_id) DO UPDATE SET stars = excluded.stars, created = excluded.created`).bind(id, me.steam_id, stars, now),
      env.DB.prepare(`UPDATE liveries SET votes = (SELECT COUNT(*) FROM livery_votes WHERE livery_id = ?1),
        stars_sum = (SELECT COALESCE(SUM(stars), 0) FROM livery_votes WHERE livery_id = ?1) WHERE id = ?1`).bind(id),
      env.DB.prepare('SELECT votes, stars_sum FROM liveries WHERE id = ?').bind(id),
    ]);
    const t = got.results[0];
    return json({ votes: t.votes, stars: avg(t), mine: stars });
  }
  return err('not found', 404);
}

/** A livery's preview: published ones for everyone (kept by browsers: its address has its version), any for the admin. */
async function shotResponse(env, id, { err, any }) {
  const r = await env.DB.prepare(`SELECT s.type, s.data, l.status FROM livery_shots s JOIN liveries l ON l.id = s.livery_id
    WHERE s.livery_id = ?`).bind(id).first();
  if (!r || (!any && r.status !== 'published')) return err('no such livery', 404);
  return new Response(bytesOf(r.data), { headers: { 'Content-Type': r.type, 'X-Content-Type-Options': 'nosniff',
    'Cache-Control': any ? 'no-store' : 'public, max-age=31536000, immutable', 'Access-Control-Allow-Origin': '*' } });
}

async function adminLiveries(req, env, path, url, now, { json, err }) {
  const post = req.method === 'POST';
  if (path === '/api/admin/liveries' && !post) {
    const which = url.searchParams.get('status') || 'pending';
    const where = which === 'all' ? '1' : which === 'flagged' ? "l.flags > 0 AND l.status = 'published'"
      : STATUSES.includes(which) ? 'l.status = ?1' : null;
    if (!where) return err('status: pending, published, rejected, hidden, flagged or all');
    const { results } = await env.DB.prepare(`SELECT ${COLS} FROM liveries l LEFT JOIN players p ON p.steam_id = l.steam_id
      WHERE ${where} ORDER BY l.id ${which === 'pending' ? 'ASC' : 'DESC'} LIMIT 200`).bind(...(STATUSES.includes(which) ? [which] : [])).all();
    return json({ liveries: results.map((r) => ({ ...liveryOut(r, url.origin), status: r.status, note: r.note || '', flags: r.flags,
      updated: r.updated, shot: `/api/admin/liveries/${r.id}/shot` })) });
  }
  if (path === '/api/admin/liveries' && post) return importLivery(req, env, now, { json, err });
  const sm = path.match(/^\/api\/admin\/liveries\/(\d+)\/shot$/);
  if (sm && !post) return shotResponse(env, +sm[1], { err, any: true });
  const um = path.match(/^\/api\/admin\/liveries\/(\d+)$/);
  if (um && post) {
    const id = +um[1];
    const b = await req.json().catch(() => ({})) || {};
    const row = await env.DB.prepare('SELECT id, steam_id, title, status, published FROM liveries WHERE id = ?').bind(id).first();
    if (!row) return err('no such livery', 404);
    const action = b.action;
    if (action === 'delete') {
      await env.DB.batch(['liveries WHERE id', 'livery_shots WHERE livery_id', 'livery_votes WHERE livery_id', 'livery_flags WHERE livery_id']
        .map((t) => env.DB.prepare(`DELETE FROM ${t} = ?`).bind(id)));
      return json({ id, deleted: true });
    }
    const to = { publish: 'published', reject: 'rejected', hide: 'hidden', clear: row.status }[action];
    if (!to) return err('action: publish, reject, hide, clear or delete');
    const note = b.note === undefined ? null : para(b.note, 500) || null;
    let link;
    if (b.link !== undefined) {               // the admin mends a link (one reported as not working)
      const c = checkLivery({ car: CARS[0].id, title: 'xx', author: 'xx', link: b.link });
      if (c.error) return err(c.error);
      link = c.value.link;
    }
    const stmts = [env.DB.prepare(`UPDATE liveries SET status = ?, note = CASE WHEN ? THEN ? ELSE note END, updated = ?,
        published = COALESCE(published, CASE WHEN ? = 'published' THEN ? END), link = CASE WHEN ? THEN ? ELSE link END,
        flags = CASE WHEN ? THEN 0 ELSE flags END WHERE id = ?`)
      .bind(to, b.note !== undefined ? 1 : 0, note, now, to, now, link !== undefined ? 1 : 0, link === undefined ? null : link,
        action === 'clear' || action === 'publish' || link !== undefined ? 1 : 0, id)];
    if (action === 'clear' || action === 'publish' || link !== undefined) stmts.push(env.DB.prepare('DELETE FROM livery_flags WHERE livery_id = ?').bind(id));
    const tell = to !== row.status && !!SAID[to] && row.steam_id !== IMPORTED;
    if (tell) {                                 // the sender is told, once a change
      stmts.push(noticeStmt(env, row.steam_id, 'livery', `Your livery ${row.title} ${SAID[to]}` + (note ? `: ${note}` : '.'),
        `livery:${id}`, now));
    }
    await env.DB.batch(stmts);
    return json({ id, status: to, told: tell });
  }
  return err('not found', 404);
}

/** One found on the web, put on the page by the admin: its link the author's own page (the file stays there), its
 *  preview, published at once (status 'pending': to look at it on /admin first). No limits; a link already there:
 *  nothing added. */
async function importLivery(req, env, now, { json, err }) {
  const b = await req.json().catch(() => ({})) || {};
  const c = checkLivery(b);
  if (c.error) return err(c.error);
  const v = c.value;
  if (!v.link) return err('the link: the page it came from');
  const same = await env.DB.prepare('SELECT id, status FROM liveries WHERE link = ?').bind(v.link).first();
  if (same) return json({ id: same.id, status: same.status, existing: true });
  const shot = dataUrlBytes(b.shot);
  if (!shot) return err('the preview: a JPEG, PNG or WebP picture', 415);
  if (shot.length > LIVERY.maxShotBytes) return err(`the preview: ${(LIVERY.maxShotBytes / 1e6).toFixed(1)} MB at most`, 413);
  const type = sniff(shot);
  if (!type || !type.startsWith('image/')) return err('the preview: a JPEG, PNG or WebP picture', 415);
  const status = b.status === 'pending' ? 'pending' : 'published';
  const r = await env.DB.prepare(`INSERT INTO liveries (steam_id, car, title, author, description, link, status, shot_v, created, updated,
      published) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(IMPORTED, v.car, v.title, v.author, v.description, v.link, status, shotVersion(shot), now, now,
      status === 'published' ? now : null).run();
  const id = r.meta.last_row_id;
  try {
    await env.DB.prepare('INSERT INTO livery_shots (livery_id, type, data, created) VALUES (?, ?, ?, ?)').bind(id, type, shot.buffer, now).run();
  } catch (e) {
    await env.DB.prepare('DELETE FROM liveries WHERE id = ?').bind(id).run();
    throw e;
  }
  return json({ id, status });
}
