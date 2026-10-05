-- ACR Daily database (Cloudflare D1 / SQLite)

-- reference route of each stage, recorded with the app in admin mode
CREATE TABLE IF NOT EXISTS routes (
  track   TEXT PRIMARY KEY,
  points  TEXT NOT NULL,          -- JSON [[x, z], ...]
  length  REAL NOT NULL,          -- metres
  updated INTEGER NOT NULL,
  stage_id TEXT,                  -- the game's id of the stage variant, e.g. AlsaceS4SaverneFullForward
  contributed_by TEXT             -- steam id when recorded automatically by a player's app
);

-- stages the dailies rotate through; car '*' = a random car (src/cars.js) each time, or a fixed car name
CREATE TABLE IF NOT EXISTS pool (
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (track, car)
);

-- the two challenges of each day (slot 1 and 2), fixed once the day starts or set by an admin
CREATE TABLE IF NOT EXISTS schedule (
  date  TEXT NOT NULL,            -- YYYY-MM-DD (UTC)
  slot    INTEGER NOT NULL,
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  weather TEXT,                  -- conditions to drive in (src/conditions.js)
  time    TEXT,
  PRIMARY KEY (date, slot)
);

-- where everyone on a stage is right now (the app sends it every 3 s while LIVE)
CREATE TABLE IF NOT EXISTS live (
  steam_id   TEXT NOT NULL,
  date       TEXT NOT NULL,
  slot       INTEGER NOT NULL,
  x          REAL NOT NULL,
  z          REAL NOT NULL,
  progress   REAL NOT NULL,
  total_ms   INTEGER NOT NULL,
  resets     INTEGER NOT NULL,
  state      TEXT NOT NULL,          -- live | finished | dnf
  updated    INTEGER NOT NULL,
  PRIMARY KEY (steam_id, date, slot)
);

CREATE TABLE IF NOT EXISTS players (
  steam_id TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  avatar   TEXT,
  created  INTEGER NOT NULL,
  banned   INTEGER NOT NULL DEFAULT 0,
  country  TEXT                    -- ISO code from the in-game driver profile
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  steam_id   TEXT NOT NULL,
  created    INTEGER NOT NULL
);

-- Steam sign-ins waiting for the app to pick up the token
CREATE TABLE IF NOT EXISTS logins (
  state    TEXT PRIMARY KEY,
  token    TEXT,
  steam_id TEXT,
  name     TEXT,
  created  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  date        TEXT NOT NULL,
  slot        INTEGER NOT NULL DEFAULT 1,   -- daily 1 or 2
  steam_id    TEXT NOT NULL,
  track       TEXT NOT NULL,
  car         TEXT NOT NULL,
  status      TEXT NOT NULL,      -- finished | dnf | invalid | rejected
  reason      TEXT,
  clock_ms    INTEGER,
  resets      INTEGER,
  total_ms    INTEGER,
  flags       TEXT,               -- JSON list of soft warnings for review
  app_version TEXT,
  created     INTEGER NOT NULL,
  started_at  INTEGER,            -- PC time the stage clock started (ms)
  trace       TEXT,               -- JSON [[clockMs, x, z, kmh, resets, wallMs, physicsPackets,
                                  --        throttle, brake, steer, gear, rpm, airTempK], ...] (finished runs only)
  sections    TEXT,               -- JSON stage clock at 10 %, 20 % ... 100 % of the route
  checks      TEXT,               -- JSON realism measurements (see src/realism.js)
  splits      TEXT,               -- JSON time incl. penalties at 25 / 50 / 75 % (live split standings)
  temps       TEXT,               -- JSON air temperature (K) at 10 %, 20 % ... (conditions check)
  jumps       TEXT                -- JSON [[clockMs, airtime ms, metres along the route, km/h], ...]
);
CREATE INDEX IF NOT EXISTS runs_board ON runs (date, status, total_ms);
CREATE INDEX IF NOT EXISTS runs_board2 ON runs (date, slot, status, total_ms);
CREATE INDEX IF NOT EXISTS runs_player ON runs (steam_id, date);
CREATE INDEX IF NOT EXISTS runs_stage ON runs (steam_id, track, car, status);

-- "this run looks wrong" reports from the website's run viewer
CREATE TABLE IF NOT EXISTS reports (
  run_id  INTEGER NOT NULL,
  who     TEXT NOT NULL,          -- hashed IP (one report per person per run)
  reason  TEXT,
  created INTEGER NOT NULL,
  PRIMARY KEY (run_id, who)
);

-- live commentary lines (src/commentary.js): written by Claude from run events, the last few shown live
CREATE TABLE IF NOT EXISTS commentary (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  kind     TEXT NOT NULL,          -- start | split | reset | finish | dnf
  steam_id TEXT,
  text     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS commentary_day ON commentary (date, slot, id);

-- the first time a player started each daily (first run counts; started and never finished = DNF)
CREATE TABLE IF NOT EXISTS attempts (
  steam_id TEXT NOT NULL,
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  started  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, date, slot)
);
