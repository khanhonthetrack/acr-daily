// A test build's daily run that doesn't count (the 0.1.5.x test builds: client app.OFFICIAL_ONLY, COMMIT_REQUIRED): started
// with START OFFICIAL RALLY and finished, but without the game's official time: driven in Practice or a Single Rally
// Stage, which keep no time, or a time the game lost (it can't be told which). Not a DNF: the app sends it with status
// 'void' and the server forgets that start (attempts: a daily's first start is its counted run, index.js countedRuns, and
// a start that never sends a run is an abandoned DNF after an hour), so the driver's next run can count. Each one is kept
// in voided_runs, for the admin. Public builds (three-part versions: 0.1.5) don't send it and are refused if they do:
// their rules are as before.

export const VOID_SAME_MS = 2000;   // the start forgotten is the one this run says it started at (index.js START_SAME_MS)

/** A test build: a four-part version (0.1.5.7), never offered to the public (client updater.is_test_build). */
export const testBuild = (v) => typeof v === 'string' && /^\d+\.\d+\.\d+\.\d+$/.test(v);

/** Forget the start of a run that doesn't count, and keep it in voided_runs (as many as there are: no limit).
 *  -> {status: 'void', forgot: whether the start was the daily's first (counted) one}, or {error, code}. */
export async function voidStart(env, { steamId, date, slot, startedAt, clockMs, reason, version, now = Date.now() }) {
  if (!testBuild(version)) return { error: "invalid run: only test builds can send a run that doesn't count", code: 403 };
  const why = String(reason || '').slice(0, 300);
  // a run of that start already in (a time or a DNF): it counts as it is, there is nothing to forget
  const lo = startedAt - VOID_SAME_MS, hi = startedAt + VOID_SAME_MS;
  const sent = await env.DB.prepare(`SELECT 1 AS x FROM runs WHERE steam_id = ? AND date = ? AND slot = ?
      AND started_at BETWEEN ? AND ? LIMIT 1`).bind(steamId, date, slot, lo, hi).first();
  if (sent) return { error: 'invalid run: that run was already sent', code: 409 };
  // its start, if it was the daily's first: forgotten (an earlier first start stays the counted one)
  const del = await env.DB.prepare('DELETE FROM attempts WHERE steam_id = ? AND date = ? AND slot = ? AND started BETWEEN ? AND ?')
    .bind(steamId, date, slot, lo, hi).run();
  const forgot = !!(del.meta && del.meta.changes);
  const n = (v) => (typeof v === 'number' && Number.isFinite(v) ? Math.round(v) : null);
  await env.DB.prepare(`INSERT INTO voided_runs (steam_id, date, slot, started_at, clock_ms, reason, app_version, forgot, created)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(steamId, date, slot, startedAt, n(clockMs), why, version, forgot ? 1 : 0, now).run();
  return { status: 'void', forgot };
}
