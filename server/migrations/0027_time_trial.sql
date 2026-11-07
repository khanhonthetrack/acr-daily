-- The weekly time trial (src/timetrial.js, from TIME_TRIAL_FROM in wrangler.toml): each week's two stages, their
-- runs (each driver's best on the board), the entries, the weeks settled and who is on a stage now. Needs 0026 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0027_time_trial.sql
CREATE TABLE IF NOT EXISTS tt_schedule (
  week    TEXT NOT NULL,
  slot    INTEGER NOT NULL,              -- TT1 / TT2
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  weather TEXT,
  time    TEXT,
  PRIMARY KEY (week, slot)
);
-- finished runs only (the app keeps its DNFs and restarts to itself); the driver's best keeps its trace ("gz:..." as
-- runs.trace), and once the week is settled only the fastest few do
CREATE TABLE IF NOT EXISTS tt_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  week        TEXT NOT NULL,
  slot        INTEGER NOT NULL,
  steam_id    TEXT NOT NULL,
  track       TEXT NOT NULL,
  car         TEXT NOT NULL,
  status      TEXT NOT NULL,             -- finished | rejected
  reason      TEXT,
  clock_ms    INTEGER,
  resets      INTEGER,
  total_ms    INTEGER,                   -- the game's stage time + its penalty
  splits      TEXT,
  app_version TEXT,
  started_at  INTEGER,
  created     INTEGER NOT NULL,
  trace       TEXT
);
CREATE INDEX IF NOT EXISTS tt_runs_board ON tt_runs (week, slot, status, total_ms);
CREATE INDEX IF NOT EXISTS tt_runs_player ON tt_runs (steam_id, week, slot);
-- entries (credits on): the fee paid before the first run on a stage; settled: what came back (0: lost)
CREATE TABLE IF NOT EXISTS tt_entries (
  week     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  fee      INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  settled  INTEGER,
  paid     INTEGER,
  PRIMARY KEY (week, slot, steam_id)
);
-- each week's stage settled once (written in the same batch as its payouts)
CREATE TABLE IF NOT EXISTS tt_weeks (
  week    TEXT NOT NULL,
  slot    INTEGER NOT NULL,
  settled INTEGER NOT NULL,
  PRIMARY KEY (week, slot)
);
-- where drivers are on a time trial stage right now (the /tt page's live maps, the app's stage strip), as `live` for the
-- dailies: gone 2 minutes after the last update (the cron)
CREATE TABLE IF NOT EXISTS tt_live (
  steam_id TEXT NOT NULL,
  week     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  x        REAL,
  z        REAL,
  progress REAL NOT NULL DEFAULT 0,
  total_ms INTEGER,
  state    TEXT NOT NULL,                 -- live / finished / dnf
  updated  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, week, slot)
);
CREATE INDEX IF NOT EXISTS tt_live_week ON tt_live (week, slot);
