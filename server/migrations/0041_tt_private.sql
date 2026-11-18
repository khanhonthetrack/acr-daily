-- Private time trials (src/timetrial.js setTtPrivate): stages of their own, each open from starts_at to ends_at, on a
-- page only its link reaches (/tt/p/<code>) and in the app from min_app on. The stage itself is a tt_schedule row with
-- the page's key ('p-<code>') for the week; its runs, boards and live maps are tt_runs / tt_live rows with that key.
-- slot: TT3, TT4... one number per private stage, never used twice (the app keeps its stages by slot).
CREATE TABLE IF NOT EXISTS tt_private (
  slot      INTEGER PRIMARY KEY,
  page      TEXT NOT NULL,
  title     TEXT,
  starts_at INTEGER NOT NULL,
  ends_at   INTEGER NOT NULL,
  min_app   TEXT,
  created   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tt_private_page ON tt_private (page);
CREATE INDEX IF NOT EXISTS tt_private_open ON tt_private (ends_at);
