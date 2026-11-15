// A daily's or a time trial stage's drivers' comments for its board (src/comments.js has the rest): a module of its own,
// so the time trial (src/timetrial.js) reads them without importing src/comments.js, which imports it.

const DAY = 86400000;
/** When a board's comments are shown to everyone (ms): a daily's once its day is over (UTC), a time trial stage's once
 *  its week is; before that they would be hints for the drivers still to drive it (each sees their own: GET
 *  /api/comments/mine). target: '2026-11-15/1' or 'tt:2026-11-09/2'. */
export function commentsAt(target) {
  const m = /^(tt:)?(\d{4}-\d{2}-\d{2})\//.exec(String(target || ''));
  if (!m) return 0;
  return Date.parse(m[2] + 'T00:00:00Z') + (m[1] ? 7 : 1) * DAY;
}

/** target: '2026-11-15/1' (a daily) or 'tt:2026-11-09/2' -> Map steamId -> text (taken-down and taken-back ones left
 *  out; the boards leave banned drivers out themselves); none before commentsAt. Empty before migration 0034 (no
 *  comments table). */
export async function boardComments(env, target, now = Date.now()) {
  if (now < commentsAt(target)) return new Map();
  try {
    const { results } = await env.DB.prepare("SELECT steam_id, body FROM comments WHERE target = ? AND hidden = 0 AND body != ''")
      .bind(target).all();
    return new Map(results.map((r) => [r.steam_id, r.body]));
  } catch {
    return new Map();      // (no comments table yet: migration 0034 not applied; the board goes on without them)
  }
}
