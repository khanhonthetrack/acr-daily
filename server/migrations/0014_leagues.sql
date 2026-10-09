-- Leagues: groups of drivers that run their own multi-stage events (Rally Weekends in the game: several stages and days,
-- service parks, the damage carried from stage to stage), seasons with their championships, stewards' decisions and
-- the league's own Discord posts (src/leagues.js, src/leaguesapi.js).
-- Plus website sign-in: a Steam sign-in started on the website goes back to the page it came from (logins.next).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0014_leagues.sql
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

ALTER TABLE logins ADD COLUMN next TEXT;
