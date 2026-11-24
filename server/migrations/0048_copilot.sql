-- COPILOT (src/copilot.js): a daily for two, a driver and a co-driver.
-- Each day's stage, car and conditions (hidden in the app until you have driven it).
CREATE TABLE IF NOT EXISTS copilot_days (
  date    TEXT PRIMARY KEY,
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  weather TEXT,
  time    TEXT
);
-- A lobby: its host's role, the other who joined, both READY -> started. code: a private one's (never listed).
-- host_signal / guest_signal: each side's details for the apps' direct link (copilotlink.py).
CREATE TABLE IF NOT EXISTS copilot_lobbies (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  date         TEXT NOT NULL,
  code         TEXT,
  host         TEXT NOT NULL,
  host_role    TEXT NOT NULL CHECK (host_role IN ('driver', 'codriver')),
  guest        TEXT,
  host_ready   INTEGER NOT NULL DEFAULT 0,
  guest_ready  INTEGER NOT NULL DEFAULT 0,
  state        TEXT NOT NULL DEFAULT 'open',      -- open | started | finished | dnf | closed
  created      INTEGER NOT NULL,
  updated      INTEGER NOT NULL,
  started      INTEGER,
  host_signal  TEXT,
  guest_signal TEXT
);
CREATE INDEX IF NOT EXISTS copilot_lobbies_open ON copilot_lobbies (date, state);
CREATE INDEX IF NOT EXISTS copilot_lobbies_code ON copilot_lobbies (code);
-- Once a day in each role: a row as a lobby starts.
CREATE TABLE IF NOT EXISTS copilot_tries (
  date     TEXT NOT NULL,
  steam_id TEXT NOT NULL,
  role     TEXT NOT NULL CHECK (role IN ('driver', 'codriver')),
  lobby_id INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  PRIMARY KEY (date, steam_id, role)
);
CREATE INDEX IF NOT EXISTS copilot_tries_lobby ON copilot_tries (lobby_id);
-- A started lobby's run: the crew's (the driver's app sends it), or a DNF.
CREATE TABLE IF NOT EXISTS copilot_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  lobby_id    INTEGER NOT NULL UNIQUE,
  driver      TEXT NOT NULL,
  codriver    TEXT NOT NULL,
  status      TEXT NOT NULL,                       -- finished | dnf
  reason      TEXT,
  clock_ms    INTEGER,
  resets      INTEGER NOT NULL DEFAULT 0,
  total_ms    INTEGER,
  splits      TEXT,
  app_version TEXT,
  started_at  INTEGER,
  created     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS copilot_runs_date ON copilot_runs (date, status, total_ms);
