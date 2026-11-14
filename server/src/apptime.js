// The app's time standing in for the game's (from app 0.1.4): the last line of support. A daily or a time trial stage
// is timed by the game's own result, read from its save once the driver goes on from its results screen (validate.js
// official). Sometimes the game never writes it: it hangs after the finish and is closed, or the stage is started again
// from its results screen (12-13 Nov 2026: eight finished runs lost so, restored by hand). The app then sends the run
// with its own stage clock (sub.appTime), and the server takes it:
//   - only for a run without respawns: the game's penalty is then nearly always none (0.6 s on average over 370 such
//     runs, 9 Oct - 14 Nov 2026), and its stage clock is the time. With any respawn the game's penalty can't be known
//     (one respawn cost 0 to 27 s, 9.7 s on average, over 75 runs): a DNF on a daily, as before app 0.1.4; the time
//     trial, which takes finished runs only, refuses it;
//   - its mark on the run (runs.flags / tt_runs.reason), for the admin only: in the review's flags, so the admin can
//     take one off (reject) if it looks wrong. The boards and Discord show it like any other time.
// The app also sends the driver's report (client gamelog.py), as with every result the game loses.

export const APP_FLAG = "app time: the game lost its official result; the app's stage clock (no respawns)";
/** A lost result with respawns: the DNF's reason. */
export const appTimeDnf = (resets) =>
  `the game closed before saving its official result, and the app's time only counts without respawns (${resets} seen)`;
