// The app's time standing in for the game's (from app 0.1.4): the last line of support. A daily or a time trial stage
// is timed by the game's own result, read from its save once the driver goes on from its results screen (validate.js
// official). Sometimes the game never writes it: it hangs after the finish and is closed, or the stage is started again
// from its results screen (12-13 Nov 2026: eight finished runs lost so, restored by hand). The app then sends the run
// with its own stage clock (sub.appTime), and the server takes it, every time, with:
//   - the game's penalties it can't see estimated: APP_TIME.resetMs for each respawn the app saw (the game gave 9.9 s a
//     respawn on average over 31 such runs, 9-13 Nov; a clean run 0.6 s, mostly none);
//   - its mark on the run (runs.flags / tt_runs.reason), for the admin only: in the review's flags, so the admin can
//     take one off (reject) if it looks wrong. The boards and Discord show it like any other time.
// The app also sends the driver's report (client gamelog.py), as with every result the game loses.

export const APP_TIME = { resetMs: 10000 };
export const APP_FLAG = "app time: the game lost its official result; the app's stage clock + 10 s a respawn";
