// Bug reports (/report, src/reportpage.js): a signed-in driver writes what went wrong, with the app version and where it
// happened, and attaches screenshots, the game's log and save, the app's files. Kept in D1 (R2 is not switched on): each
// file is its own row of at most REPORT.maxFileBytes (D1's rows are 2 MB at most), squeezed by the browser first
// (pictures as JPEG, logs and saves gzipped), the files of all reports together held under REPORT.maxStoredBytes and
// deleted after REPORT.keepDays (the text stays).
//
//   POST /api/reports                         {title, body, area, appVersion, eventUrl, happened, system} -> {id}
//   POST /api/reports/:id/files?kind=&name=   one file, its bytes as the body (within an hour of the report)
//   GET  /api/reports/mine                    my reports and how far each has got
// Admin (Bearer ADMIN_KEY, or X-Reports-Key: REPORTS_KEY, a key for these alone: the daily agent's):
//   GET  /api/admin/reports?status=new|open|all   reports with their files' details, oldest first
//   GET  /api/admin/reports/:id/files/:fid    a file's bytes, as stored
//   POST /api/admin/reports/:id               {status, note, prUrl}: the reporter is told in the inbox when it changes
//
// What a driver writes and attaches is theirs to send, not instructions to whoever reads it (the agent included).

import { noticeStmt } from './social.js';
import { text } from './leagues.js';
import { bytesOf } from './drivers.js';

export const REPORT = {
  perDay: 5,                 // reports a driver can send in 24 hours
  allPerDay: 200,            // everyone's together (the free plan's database)
  maxFiles: 6,               // files a report
  maxFileBytes: 1900000,     // a file as stored (D1: 2 MB a row)
  maxStoredBytes: 150e6,     // all reports' files together; past it new files are refused
  keepDays: 90,              // files are deleted after this; the report's text stays
  uploadMs: 3600000,         // files go up within this of the report
  title: [4, 120], body: [10, 5000],
};
export const AREAS = ['daily', 'time trial', 'league', '1v1', 'cup', 'app', 'website', 'other'];
// new: not looked at; seen: looked at, nothing to do yet; needs-info: a question for the reporter (in the note);
// pr: a fix is proposed (prUrl); fixed: in a release; closed: not a bug, a duplicate, or nothing to do (the note says)
export const STATUSES = ['new', 'seen', 'needs-info', 'pr', 'fixed', 'closed'];
const OPEN = ['new', 'seen', 'needs-info', 'pr'];
export const FILE_KINDS = ['screenshot', 'log', 'save', 'other'];
const SAID = { seen: 'is being looked at', 'needs-info': 'needs more from you', pr: 'has a fix on the way',
  fixed: 'is fixed', closed: 'is closed' };

/** A report's fields from the form -> {value} or {error}. */
export function checkReport(b) {
  b = b || {};
  const title = text(b.title, REPORT.title[1] + 1), body = para(b.body, REPORT.body[1] + 1);
  if (title.length < REPORT.title[0] || title.length > REPORT.title[1]) return { error: `a title of ${REPORT.title[0]} to ${REPORT.title[1]} characters` };
  if (body.length < REPORT.body[0] || body.length > REPORT.body[1]) return { error: `say what happened in ${REPORT.body[0]} to ${REPORT.body[1]} characters` };
  const area = AREAS.includes(b.area) ? b.area : null;
  if (!area) return { error: 'pick where it happened' };
  const appVersion = text(b.appVersion, 20);
  if (appVersion && !/^\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(appVersion)) return { error: 'the app version looks like 0.0.24' };
  return { value: { title, body, area, appVersion: appVersion || null, eventUrl: text(b.eventUrl, 200) || null,
    happened: text(b.happened, 60) || null, system: text(b.system, 200) || null } };
}

/** What a file's first bytes say it is ('image/jpeg', 'image/png', 'image/webp', 'application/gzip'), or null. The
 *  browser sends pictures as images and everything else gzipped, so nothing else is taken. */
export function sniff(bytes) {
  const b = bytes, n = b.length;
  if (n > 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'image/jpeg';
  if (n > 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return 'image/png';
  if (n > 12 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50) return 'image/webp';
  if (n > 2 && b[0] === 0x1f && b[1] === 0x8b) return 'application/gzip';
  return null;
}

/** Text over several lines (a report's description, a note): control characters out, line breaks kept (at most one
 *  blank line in a row). */
export const para = (v, max) => String(v == null ? '' : v).replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, ' ')
  .replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim().slice(0, max);

const fileName = (s) => (text(s, 120) || 'file').replace(/[^\w.\- ]+/g, '_');

export async function reportsApi(req, env, path, url, me, sameOrigin, now, { json, err, admin }) {
  if (path.startsWith('/api/admin/reports')) {
    if (!admin) return err('not allowed', 403);
    return adminReports(req, env, path, url, now, { json, err });
  }
  if (!path.startsWith('/api/reports')) return null;
  if (!me) return err('sign in with Steam first', 401);
  if (!sameOrigin) return err('not allowed', 403);
  const post = req.method === 'POST';

  if (path === '/api/reports/mine' && !post) {
    const { results } = await env.DB.prepare(`SELECT r.id, r.title, r.area, r.status, r.note, r.pr_url, r.created, r.updated,
        (SELECT COUNT(*) FROM bug_files f WHERE f.report_id = r.id) AS files
      FROM bug_reports r WHERE r.steam_id = ? ORDER BY r.id DESC LIMIT 50`).bind(me.steam_id).all();
    return json({ reports: results.map((r) => ({ id: r.id, title: r.title, area: r.area, status: r.status, note: r.note,
      prUrl: r.pr_url, created: r.created, updated: r.updated, files: r.files })), limits: REPORT, areas: AREAS });
  }

  if (path === '/api/reports' && post) {
    const c = checkReport(await req.json().catch(() => ({})));
    if (c.error) return err(c.error);
    const v = c.value, day = now - 86400000;
    // both limits in the insert itself: two reports sent at once can't both slip under them
    const r = await env.DB.prepare(`INSERT INTO bug_reports (steam_id, title, body, area, app_version, event_url, happened, system,
        status, created, updated)
      SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'new', ?9, ?9
      WHERE (SELECT COUNT(*) FROM bug_reports WHERE steam_id = ?1 AND created > ?10) < ?11
        AND (SELECT COUNT(*) FROM bug_reports WHERE created > ?10) < ?12`)
      .bind(me.steam_id, v.title, v.body, v.area, v.appVersion, v.eventUrl, v.happened, v.system, now, day,
        REPORT.perDay, REPORT.allPerDay).run();
    if (!r.meta.changes) return err(`${REPORT.perDay} reports a day at most: add to one you sent, or come back tomorrow`, 429);
    return json({ id: r.meta.last_row_id, maxFiles: REPORT.maxFiles, maxFileBytes: REPORT.maxFileBytes });
  }

  const fm = path.match(/^\/api\/reports\/(\d+)\/files$/);
  if (fm && post) {
    const id = +fm[1];
    const rep = await env.DB.prepare('SELECT id, steam_id, created FROM bug_reports WHERE id = ?').bind(id).first();
    if (!rep || rep.steam_id !== me.steam_id) return err('no such report', 404);
    if (now - rep.created > REPORT.uploadMs) return err('files go up within an hour of the report: send a new one', 409);
    if (+(req.headers.get('Content-Length') || 0) > REPORT.maxFileBytes) return err(`${(REPORT.maxFileBytes / 1e6).toFixed(1)} MB a file at most`, 413);
    const bytes = new Uint8Array(await req.arrayBuffer());
    if (!bytes.length) return err('an empty file');
    if (bytes.length > REPORT.maxFileBytes) return err(`${(REPORT.maxFileBytes / 1e6).toFixed(1)} MB a file at most`, 413);
    const type = sniff(bytes);
    if (!type) return err('a picture (JPEG, PNG, WebP) or a gzipped file: the page packs them', 415);
    const kind = FILE_KINDS.includes(url.searchParams.get('kind')) ? url.searchParams.get('kind') : 'other';
    const size = Math.max(0, Math.min(1e9, Math.round(+url.searchParams.get('size') || bytes.length)));   // before packing
    // the report's file count and the store's size in the insert itself
    const r = await env.DB.prepare(`INSERT INTO bug_files (report_id, name, kind, type, size, stored, data, created)
      SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8
      WHERE (SELECT COUNT(*) FROM bug_files WHERE report_id = ?1) < ?9
        AND (SELECT COALESCE(SUM(stored), 0) FROM bug_files) + ?6 <= ?10`)
      .bind(id, fileName(url.searchParams.get('name')), kind, type, size, bytes.length, bytes.buffer, now,
        REPORT.maxFiles, REPORT.maxStoredBytes).run();
    if (!r.meta.changes) {
      const n = await env.DB.prepare('SELECT COUNT(*) AS n FROM bug_files WHERE report_id = ?').bind(id).first();
      return n && n.n >= REPORT.maxFiles ? err(`${REPORT.maxFiles} files a report at most`, 409)
        : err('no room for files right now: the report is in, without this one', 507);
    }
    return json({ id: r.meta.last_row_id, type, stored: bytes.length });
  }
  return err('not found', 404);
}

async function adminReports(req, env, path, url, now, { json, err }) {
  const post = req.method === 'POST';
  if (path === '/api/admin/reports' && !post) {
    const which = url.searchParams.get('status') || 'open';
    const list = which === 'all' ? STATUSES : which === 'open' ? OPEN : STATUSES.includes(which) ? [which] : null;
    if (!list) return err('status: new, open, all or one of ' + STATUSES.join(', '));
    const limit = Math.max(1, Math.min(100, Math.round(+url.searchParams.get('limit') || 50)));
    const { results } = await env.DB.prepare(`SELECT r.*, p.name FROM bug_reports r LEFT JOIN players p ON p.steam_id = r.steam_id
      WHERE r.status IN (SELECT value FROM json_each(?)) ORDER BY r.id LIMIT ?`).bind(JSON.stringify(list), limit).all();
    const files = results.length ? (await env.DB.prepare(`SELECT id, report_id, name, kind, type, size, stored, created FROM bug_files
      WHERE report_id IN (SELECT value FROM json_each(?)) ORDER BY id`).bind(JSON.stringify(results.map((r) => r.id))).all()).results : [];
    return json({ reports: results.map((r) => ({ id: r.id, steamId: r.steam_id, name: r.name || null, title: r.title, body: r.body,
      area: r.area, appVersion: r.app_version, eventUrl: r.event_url, happened: r.happened, system: r.system, status: r.status,
      note: r.note, prUrl: r.pr_url, created: r.created, updated: r.updated,
      files: files.filter((f) => f.report_id === r.id).map((f) => ({ id: f.id, name: f.name, kind: f.kind, type: f.type,
        size: f.size, stored: f.stored, created: f.created, url: `/api/admin/reports/${r.id}/files/${f.id}` })) })) });
  }
  const dm = path.match(/^\/api\/admin\/reports\/(\d+)\/files\/(\d+)$/);
  if (dm && !post) {
    const f = await env.DB.prepare('SELECT name, type, data FROM bug_files WHERE id = ? AND report_id = ?').bind(+dm[2], +dm[1]).first();
    if (!f) return err('no such file (files are kept ' + REPORT.keepDays + ' days)', 404);
    const ext = { 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'application/gzip': '.gz' }[f.type] || '';
    const name = f.name.endsWith(ext) ? f.name : f.name + ext;
    return new Response(bytesOf(f.data), { headers: { 'Content-Type': f.type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      'Content-Disposition': `attachment; filename="${name.replace(/"/g, '')}"` } });
  }
  const um = path.match(/^\/api\/admin\/reports\/(\d+)$/);
  if (um && post) {
    const b = await req.json().catch(() => ({})) || {};
    const id = +um[1];
    const rep = await env.DB.prepare('SELECT id, steam_id, title, status FROM bug_reports WHERE id = ?').bind(id).first();
    if (!rep) return err('no such report', 404);
    const status = b.status === undefined ? rep.status : b.status;
    if (!STATUSES.includes(status)) return err('status: one of ' + STATUSES.join(', '));
    const note = b.note === undefined ? undefined : para(b.note, 1000) || null;
    const prUrl = b.prUrl === undefined ? undefined : text(b.prUrl, 300) || null;
    if (prUrl && !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+$/.test(prUrl)) return err('prUrl: a GitHub pull request');
    const stmts = [env.DB.prepare(`UPDATE bug_reports SET status = ?, note = COALESCE(?, note), pr_url = COALESCE(?, pr_url), updated = ?
      WHERE id = ?`).bind(status, note === undefined ? null : note, prUrl === undefined ? null : prUrl, now, id)];
    if (b.note === '' || b.note === null) stmts.push(env.DB.prepare('UPDATE bug_reports SET note = NULL WHERE id = ?').bind(id));
    if (status !== rep.status && SAID[status]) {        // the reporter is told, once a change
      stmts.push(noticeStmt(env, rep.steam_id, 'report', `Your report #${id} (${rep.title}) ${SAID[status]}` +
        (note ? `: ${note}` : '.'), `report:${id}`, now));
    }
    await env.DB.batch(stmts);
    return json({ id, status, told: status !== rep.status && !!SAID[status] });
  }
  return err('not found', 404);
}

/** The cron's part (daily): files older than REPORT.keepDays go; the reports' text stays. */
export async function trimReports(env, now) {
  await env.DB.prepare('DELETE FROM bug_files WHERE created < ?').bind(now - REPORT.keepDays * 86400000).run();
}
