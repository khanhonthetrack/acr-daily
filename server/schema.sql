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

-- Steam sign-ins waiting for the app to pick up the token (or, started on the website, to go back to `next`)
CREATE TABLE IF NOT EXISTS logins (
  state    TEXT PRIMARY KEY,
  token    TEXT,
  steam_id TEXT,
  name     TEXT,
  created  INTEGER NOT NULL,
  next     TEXT
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

-- Leagues: groups of drivers running their own multi-stage events (Rally Weekends in the game), seasons with their
-- championships, stewards' decisions and the league's own Discord posts (src/leagues.js, src/leaguesapi.js)
CREATE TABLE IF NOT EXISTS leagues (
  id      TEXT PRIMARY KEY,           -- 8 random characters, in the league's address (/l/<id>)
  name    TEXT NOT NULL,
  about   TEXT NOT NULL DEFAULT '',
  owner   TEXT NOT NULL,              -- steam_id of who made it: the one who runs it
  public  INTEGER NOT NULL DEFAULT 1, -- 1: listed on /leagues, anyone can join; 0: only with the invite code
  code    TEXT NOT NULL UNIQUE,       -- the invite code (/join/<code>); a new one makes the old links stop working
  banner  INTEGER,                    -- when its banner was last set (ms; in the banner's address), NULL = none
  discord TEXT,                       -- a Discord webhook of the league's channel (the owner's; never sent back whole)
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS leagues_owner ON leagues (owner);

-- A league's banner: a picture across the top of its page (the website makes it 1200 x 400, at most 250 KB)
CREATE TABLE IF NOT EXISTS league_banners (
  league_id TEXT PRIMARY KEY,
  type      TEXT NOT NULL,              -- image/jpeg, image/png or image/webp, from its bytes
  data      BLOB NOT NULL,
  updated   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS league_members (
  league_id TEXT NOT NULL,
  steam_id  TEXT NOT NULL,
  joined    INTEGER NOT NULL,
  role      TEXT NOT NULL DEFAULT 'member',  -- member / admin (the owner is leagues.owner)
  PRIMARY KEY (league_id, steam_id)
);
CREATE INDEX IF NOT EXISTS league_members_player ON league_members (steam_id);

-- Drivers removed and kept out of a league (by its owner or an admin)
CREATE TABLE IF NOT EXISTS league_bans (
  league_id TEXT NOT NULL,
  steam_id  TEXT NOT NULL,
  reason    TEXT NOT NULL DEFAULT '',
  by        TEXT NOT NULL,
  created   INTEGER NOT NULL,
  PRIMARY KEY (league_id, steam_id)
);

-- A championship over some of a league's events
CREATE TABLE IF NOT EXISTS league_seasons (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id  TEXT NOT NULL,
  name       TEXT NOT NULL,
  points     TEXT NOT NULL,             -- JSON {table: [25, 18, ...] from P1, finisher: points for every other finisher}
  power      TEXT NOT NULL,             -- JSON [5, 4, 3, 2, 1]: the Power Stage bonus (each event's last stage), [] = none
  drop_worst INTEGER NOT NULL DEFAULT 0, -- each driver's worst rounds that don't count
  created    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS league_seasons_league ON league_seasons (league_id);

CREATE TABLE IF NOT EXISTS league_events (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id      TEXT NOT NULL,
  season_id      INTEGER,               -- its season, or NULL: a one-off
  name           TEXT NOT NULL,
  rally          TEXT NOT NULL,         -- the location (one per event, as in the game): Alsace / Greece / Monte Carlo / Wales
  car            TEXT,                  -- one car for everyone (its name in cars.js), or NULL and...
  car_class      TEXT,                  -- ...a class: each driver picks a car of it
  rules          TEXT NOT NULL,         -- JSON {penalty, respawn, damage, damageIntensity, wear, failures}
  stages         TEXT NOT NULL,         -- JSON [{track, day, service, weather, time}] in driving order
  opens          INTEGER NOT NULL,      -- ms: drivers can start from then...
  closes         INTEGER NOT NULL,      -- ...and must have finished every stage by then
  created        INTEGER NOT NULL,
  posted_open    INTEGER,               -- when the league's Discord was told it opened, 24 hours were left, its results
  posted_24h     INTEGER,
  posted_results INTEGER
);
CREATE INDEX IF NOT EXISTS league_events_league ON league_events (league_id, opens);
CREATE INDEX IF NOT EXISTS league_events_season ON league_events (season_id);

-- One entry per driver and event: the first start is the one that counts.
CREATE TABLE IF NOT EXISTS league_entries (
  event_id    INTEGER NOT NULL,
  steam_id    TEXT NOT NULL,
  car         TEXT NOT NULL,
  status      TEXT NOT NULL,            -- running / finished / dnf
  reason      TEXT,
  done        INTEGER NOT NULL DEFAULT 0,  -- stages finished
  on_stage    INTEGER,                     -- the stage started and not finished yet (0 = SS1): a second start = DNF
  total_ms    INTEGER NOT NULL DEFAULT 0,  -- their times + the game's penalties so far
  started     INTEGER NOT NULL,
  updated     INTEGER NOT NULL,
  app_version TEXT,
  dsq         TEXT,                     -- disqualified by the stewards: why (NULL = not)
  dsq_by      TEXT,
  dsq_at      INTEGER,
  PRIMARY KEY (event_id, steam_id)
);

CREATE TABLE IF NOT EXISTS league_stage_times (
  event_id   INTEGER NOT NULL,
  steam_id   TEXT NOT NULL,
  stage_no   INTEGER NOT NULL,          -- 0 = SS1
  time_ms    INTEGER NOT NULL,          -- the game's stage time
  penalty_ms INTEGER NOT NULL,          -- the game's penalties on the stage
  splits     TEXT,                      -- JSON: ms at the game's split points
  started    INTEGER,
  created    INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id, stage_no)
);

-- The stewards' time penalties (negative: time given back), on a stage or on the total
CREATE TABLE IF NOT EXISTS league_penalties (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  stage_no INTEGER,                     -- 0 = SS1; NULL = on the total
  ms       INTEGER NOT NULL,
  reason   TEXT NOT NULL,
  by       TEXT NOT NULL,               -- the steward (owner or admin)
  created  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS league_penalties_event ON league_penalties (event_id);

