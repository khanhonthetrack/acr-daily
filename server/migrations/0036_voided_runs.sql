-- A test build's daily runs that didn't count (src/voids.js): started with START OFFICIAL RALLY and finished, but without
-- the game's official time (Practice, Single Rally Stage, or a time the game lost). Not DNFs: their start is forgotten
-- (attempts), so the driver's next run can count. Kept for the admin. Public builds never send them.
CREATE TABLE IF NOT EXISTS voided_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id    TEXT NOT NULL,
  date        TEXT NOT NULL,
  slot        INTEGER NOT NULL,
  started_at  INTEGER,
  clock_ms    INTEGER,
  reason      TEXT NOT NULL DEFAULT '',
  app_version TEXT NOT NULL DEFAULT '',
  forgot      INTEGER NOT NULL DEFAULT 0,      -- 1: it was the daily's first start, forgotten
  created     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS voided_runs_daily ON voided_runs (steam_id, date, slot);
