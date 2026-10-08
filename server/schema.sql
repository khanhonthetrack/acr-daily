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

-- where everyone on a stage is right now (the app sends it every few seconds while LIVE); the cron deletes a row
-- 2 minutes after its last update, so the table only holds who is on a stage
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
-- the live map reads one day's rows (not `updated`: it changes on every position, and each index write is billed)
CREATE INDEX IF NOT EXISTS live_day ON live (date, slot);

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
  trace       TEXT,               -- counted runs only (src/traces.js): "gz:<base64 gzip>" of the JSON
                                  --   [[clockMs, x, z, kmh, resets, wallMs, physicsPackets,
                                  --     throttle, brake, steer, gear, rpm, airTempK], ...]
                                  -- (older runs: the plain JSON); NULL when in R2, or after 14 days but for the top 3
  sections    TEXT,               -- JSON stage clock at 10 %, 20 % ... 100 % of the route
  checks      TEXT,               -- JSON realism measurements (see src/realism.js)
  splits      TEXT,               -- JSON time incl. penalties at 25 / 50 / 75 % (live split standings)
  temps       TEXT,               -- JSON air temperature (K) at 10 %, 20 % ... (kept, not checked: the game draws it anew)
  jumps       TEXT,               -- JSON [[clockMs, airtime ms, metres along the route, km/h], ...]
  profile     TEXT                -- JSON what the stats page needs from the trace (src/stats.js runProfile; counted runs)
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

-- built boards, weeks and stage stats, kept until their time is up or what they are built from changes (src/cache.js)
CREATE TABLE IF NOT EXISTS cache (
  key     TEXT PRIMARY KEY,         -- board:<date>/<slot> | stats:<date>/<slot> | week:<monday>@<today>
  body    TEXT NOT NULL,            -- JSON
  expires INTEGER NOT NULL
);

-- the Discord bot's messages (src/discord.js): the live board it edits, and the days it has wrapped up
CREATE TABLE IF NOT EXISTS discord (
  key        TEXT PRIMARY KEY,     -- 'board' or 'day:<date>'
  message_id TEXT,
  hash       TEXT,                 -- the board's last content (it is edited only when that changes)
  date       TEXT,
  updated    INTEGER NOT NULL
);

-- the first time a player started each daily (first run counts; started and never finished = DNF)
CREATE TABLE IF NOT EXISTS attempts (
  steam_id TEXT NOT NULL,
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  started  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, date, slot)
);
-- every leaderboard reads one daily's attempts (the primary key starts with steam_id, so it can't)
CREATE INDEX IF NOT EXISTS attempts_day ON attempts (date, slot);
