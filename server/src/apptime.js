// The app's time standing in for the game's (from app 0.1.3). A daily or a time trial stage is timed by the game's own
// result, read from its save once the driver goes on from its results screen (validate.js official). Sometimes the game
// never writes it: it hangs after the finish and is closed, or the stage is started again from its results screen
// (12-13 Nov 2026: eight finished runs lost so, restored by hand). The app then sends the run with its own stage clock
// (sub.appTime) and the server takes it, with:
//   - the game's penalties it can't see estimated: APP_TIME.resetMs for each respawn the app saw (the game gave 9.9 s a
//     respawn on average over 31 such runs, 9-13 Nov; a clean run 0.6 s, mostly none);
//   - at most APP_TIME.per such results counting in any APP_TIME.days days, dailies and time trial together: seeing
//     a penalty on the results screen and closing the game must not pay. Over it: a DNF (a daily) or refused (the
//     time trial), as before. Only a result that counts uses it up: a daily's counted run, a time trial run that is the
//     driver's best on its stage;
//   - its mark on the run (runs.flags / tt_runs.reason, shown on the boards and in the admin's review), so everyone
//     sees which times are the app's.
// The app also sends the driver's report (client gamelog.py), as with every result the game loses.

export const APP_TIME = { per: 1, days: 7, resetMs: 10000 };
export const APP_FLAG = "app time: the game lost its official result; the app's stage clock + 10 s a respawn";
export const APP_FLAG_FREE = "app time (not counted, none of the allowance used): the game lost its official result";
const MARK = 'app time: %';   // (APP_FLAG's start: runs.flags holds it JSON-quoted, tt_runs.reason as it is)

/** A board entry's mark: is this run's time the app's? (runs.flags JSON text, or tt_runs.reason): sent so by the app,
 *  or a lost result the admin reinstated with the app's stage clock by hand (12-13 Nov 2026). */
export const isAppTime = (text) => typeof text === 'string' && (text.includes('app time: ') || text.includes('app stage clock'));

/** The results the app's time stood in for that count, by a driver, in the APP_TIME.days before `now` (the run being
 *  sent left out). -> {used, next: when the oldest of them stops counting (ms) or null} */
export async function appTimeUsed(env, steamId, now, { runId = -1, ttId = -1 } = {}) {
  const since = now - APP_TIME.days * 86400000;
  const r = await env.DB.prepare(`SELECT COUNT(*) AS n, MIN(created) AS oldest FROM (
      SELECT created FROM runs WHERE steam_id = ?1 AND created >= ?2 AND id != ?3 AND status = 'finished'
        AND flags LIKE ?4
      UNION ALL
      SELECT created FROM tt_runs WHERE steam_id = ?1 AND created >= ?2 AND id != ?5 AND status = 'finished'
        AND reason LIKE ?6)`)
    .bind(steamId, since, runId, '%"' + MARK, ttId, MARK).first();
  const used = (r && r.n) || 0;
  return { used, next: used && r.oldest ? r.oldest + APP_TIME.days * 86400000 : null };
}

/** Words for the driver (and the run's DNF reason) when the allowance is used up. */
export function usedUpReason(next) {
  const when = next ? new Date(next).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'in a few days';
  return `the game lost its official result, and the app's time already stood in for one this week (again from ${when})`;
}
