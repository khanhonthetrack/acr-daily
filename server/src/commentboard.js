// A daily's or a time trial stage's drivers' comments for its board (src/comments.js has the rest): a module of its own,
// so the time trial (src/timetrial.js) reads them without importing src/comments.js, which imports it.

/** target: '2026-11-15/1' (a daily) or 'tt:2026-11-09/2' -> Map steamId -> text (taken-down and taken-back ones left
 *  out; the boards leave banned drivers out themselves). Empty before migration 0034 (no comments table). */
export async function boardComments(env, target) {
  try {
    const { results } = await env.DB.prepare("SELECT steam_id, body FROM comments WHERE target = ? AND hidden = 0 AND body != ''")
      .bind(target).all();
    return new Map(results.map((r) => [r.steam_id, r.body]));
  } catch {
    return new Map();      // (no comments table yet: migration 0034 not applied; the board goes on without them)
  }
}
