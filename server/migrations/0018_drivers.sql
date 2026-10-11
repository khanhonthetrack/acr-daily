-- Driver pages (src/drivers.js): a name and a picture of one's own, teams; each daily's results and the driver rating
-- with its world ranking (src/rating.js). Needs 0017 first. Apply:
-- npx wrangler d1 execute acr-daily --remote --file=migrations/0018_drivers.sql
--
-- players.name and players.avatar stay what every page shows: the driver's own name / picture when they set one, else
-- Steam's (kept in steam_name / steam_avatar, refreshed at each sign-in).
ALTER TABLE players ADD COLUMN steam_name TEXT;
ALTER TABLE players ADD COLUMN steam_avatar TEXT;
ALTER TABLE players ADD COLUMN custom_name TEXT;      -- the driver's own name; NULL: their Steam name
ALTER TABLE players ADD COLUMN name_key TEXT;         -- custom_name folded (src/drivers.js nameKey): no two alike
ALTER TABLE players ADD COLUMN name_set INTEGER;      -- when the name was last changed (one change a week)
ALTER TABLE players ADD COLUMN avatar_set INTEGER;    -- when a picture of their own went up; NULL: Steam's
UPDATE players SET steam_name = name, steam_avatar = avatar;
CREATE UNIQUE INDEX IF NOT EXISTS players_name_key ON players (name_key) WHERE name_key IS NOT NULL;

-- A driver's own picture (square, made 256 x 256 by the website, at most 60 KB), served at /avatar/<steamId>
CREATE TABLE IF NOT EXISTS player_avatars (
  steam_id TEXT PRIMARY KEY,
  type     TEXT NOT NULL,                 -- image/jpeg, image/png or image/webp, from its bytes
  data     BLOB NOT NULL,
  updated  INTEGER NOT NULL
);

-- Teams: a coloured tag by their drivers' names (as in Trackmania); one team per driver, a captain, an invite code
CREATE TABLE IF NOT EXISTS teams (
  id       TEXT PRIMARY KEY,              -- 8 random characters (/t/<id>)
  name     TEXT NOT NULL,
  tag      TEXT NOT NULL,                 -- 2 to 4 letters or digits, shown by the names
  tag_key  TEXT NOT NULL UNIQUE,          -- the tag in capitals: no two teams alike
  color    TEXT NOT NULL,                 -- the tag's colour (src/drivers.js TEAM.colors)
  captain  TEXT NOT NULL,
  code     TEXT NOT NULL UNIQUE,          -- the invite code
  created  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS team_members (
  steam_id TEXT PRIMARY KEY,              -- one team per driver
  team_id  TEXT NOT NULL,
  joined   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS team_members_team ON team_members (team_id);

-- Each daily's results, kept once the day is over (the cron, src/rating.js): the driver pages read them
CREATE TABLE IF NOT EXISTS daily_done (
  date    TEXT NOT NULL,
  slot    INTEGER NOT NULL,
  rated   INTEGER NOT NULL,               -- 1: it changed the ratings (from RATING_FROM)
  created INTEGER NOT NULL,
  PRIMARY KEY (date, slot)
);
CREATE TABLE IF NOT EXISTS daily_results (
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  place    INTEGER,                       -- NULL: DNF
  field    INTEGER NOT NULL,              -- drivers on the board
  status   TEXT NOT NULL,                 -- finished / dnf
  total_ms INTEGER,
  gap_ms   INTEGER,
  run_id   INTEGER,
  track    TEXT,
  car      TEXT,
  delta    REAL,                          -- the rating it gave or took (NULL: not rated)
  PRIMARY KEY (steam_id, date, slot)
);
CREATE INDEX IF NOT EXISTS daily_results_day ON daily_results (date, slot);

-- The driver rating (like iRacing's iRating): from both dailies and cup matches
CREATE TABLE IF NOT EXISTS ratings (
  steam_id TEXT PRIMARY KEY,
  rating   REAL NOT NULL,
  races    INTEGER NOT NULL,
  peak     REAL NOT NULL,
  updated  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ratings_rating ON ratings (rating);
CREATE TABLE IF NOT EXISTS rating_history (
  steam_id TEXT NOT NULL,
  ref      TEXT NOT NULL,                 -- daily:<date>/<slot> or cup:<match id>
  delta    REAL NOT NULL,
  after    REAL NOT NULL,
  created  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, ref)
);
-- what has been rated (a daily, a cup match): once
CREATE TABLE IF NOT EXISTS rating_done (
  ref     TEXT PRIMARY KEY,
  created INTEGER NOT NULL
);
