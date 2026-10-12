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
  set_by  TEXT,                  -- a driver who bought this daily in the shop (src/shop.js DAILY_SET), NULL: picked (0024)
  set_at  INTEGER,
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
  name     TEXT NOT NULL,          -- the name every page shows: custom_name, else the Steam name
  avatar   TEXT,                   -- the picture every page shows: their own (avatar_set), else Steam's
  created  INTEGER NOT NULL,
  banned   INTEGER NOT NULL DEFAULT 0,
  country  TEXT,                   -- ISO code from the in-game driver profile
  steam_name   TEXT,               -- as Steam has them (refreshed at each sign-in)
  steam_avatar TEXT,
  custom_name  TEXT,               -- the driver's own name (src/drivers.js); NULL: their Steam name
  name_key     TEXT,               -- custom_name folded (drivers.js nameKey): no two alike
  name_set     INTEGER,            -- when the name was last changed (one change a week)
  avatar_set   INTEGER,            -- when a picture of their own went up; NULL: Steam's
  ach_at       INTEGER             -- the last achievements check (src/achievements.js; 0021)
);
CREATE UNIQUE INDEX IF NOT EXISTS players_name_key ON players (name_key) WHERE name_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  steam_id   TEXT NOT NULL,
  created    INTEGER NOT NULL
);

-- Steam sign-ins under way: started by the app (back to it on 127.0.0.1:port with a one-time code, swapped for the
-- token with its verifier) or on the website (back to `next` with the cookie)
CREATE TABLE IF NOT EXISTS logins (
  state     TEXT PRIMARY KEY,
  token     TEXT,
  steam_id  TEXT,
  name      TEXT,
  created   INTEGER NOT NULL,
  next      TEXT,
  port      INTEGER,                    -- the app's: where it listens on 127.0.0.1
  challenge TEXT,                       -- the app's: sha256 (hex) of its verifier
  code      TEXT                        -- sha256 (hex) of the one-time code the browser takes back to the app
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
  who     TEXT NOT NULL,          -- the reporting driver's steam id, one report each (before 2026-10-13: a hashed IP)
  reason  TEXT,
  created INTEGER NOT NULL,
  PRIMARY KEY (run_id, who)
);

-- built boards, weeks and stage stats, kept until their time is up or what they are built from changes (src/cache.js)
CREATE TABLE IF NOT EXISTS cache (
  key     TEXT PRIMARY KEY,         -- board:<date>/<slot> | stats:<date>/<slot>
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
  created INTEGER NOT NULL,
  kind    TEXT NOT NULL DEFAULT 'league',  -- league; h2h / cup: the hidden holder of a head-to-head's or a cup's events
  divisions TEXT                      -- JSON ["PRO", "AM"]: its divisions, each with its own standings; NULL: none (0023)
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
  division  TEXT,                            -- one of leagues.divisions, NULL: none (0023)
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
  car_class      TEXT,                  -- ...a class: each driver picks a car of it, or NULL and...
  car_classes    TEXT,                  -- ...JSON ["Rally2/R5", "Rally4"]: several, each its own standings (0023)
  rules          TEXT NOT NULL,         -- JSON {penalty, respawn, damage, damageIntensity, wear, failures}
  stages         TEXT NOT NULL,         -- JSON [{track, day, service, weather, time}] in driving order
  opens          INTEGER NOT NULL,      -- ms: drivers can start from then...
  closes         INTEGER NOT NULL,      -- ...and must have finished every stage by then
  created        INTEGER NOT NULL,
  posted_open    INTEGER,               -- when the league's Discord was told it opened, 24 hours were left, its results
  posted_24h     INTEGER,
  posted_results INTEGER,
  only_ids       TEXT                   -- JSON [steamId, ...]: only they drive it (a 1v1); NULL: every member
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

-- Credits (a prototype, on only with CREDITS_FROM): src/credits.js
CREATE TABLE IF NOT EXISTS credits (
  steam_id TEXT PRIMARY KEY,
  balance  INTEGER NOT NULL DEFAULT 0,
  streak   INTEGER NOT NULL DEFAULT 0,  -- days in a row the daily bonus was claimed
  last_day TEXT                         -- the last day it was claimed (UTC, YYYY-MM-DD)
);

CREATE TABLE IF NOT EXISTS credit_ledger (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id TEXT NOT NULL,
  delta    INTEGER NOT NULL,
  kind     TEXT NOT NULL,               -- welcome / daily / finish / finish-back / wager / wager-win / wager-refund / shop
  ref      TEXT,                        -- the daily ("2026-10-09/2"), or what was bought ("color:gold")
  note     TEXT,
  created  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS credit_ledger_player ON credit_ledger (steam_id, id);
-- the free daily's finish bonus: once per driver and daily (paid as the run comes in)
CREATE UNIQUE INDEX IF NOT EXISTS credit_ledger_finish ON credit_ledger (steam_id, ref) WHERE kind = 'finish';

-- Stakes on the wager daily
CREATE TABLE IF NOT EXISTS wagers (
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  stake    INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  settled  INTEGER,
  paid     INTEGER,                     -- what came back (0: lost)
  PRIMARY KEY (date, slot, steam_id)
);

-- The dailies already settled (finish bonuses, wagers)
CREATE TABLE IF NOT EXISTS credit_days (
  date    TEXT NOT NULL,
  slot    INTEGER NOT NULL,
  settled INTEGER NOT NULL,
  PRIMARY KEY (date, slot)
);

-- The shop (credits, src/shop.js): looks bought with credits, kept for good, one of each kind worn at a time
CREATE TABLE IF NOT EXISTS shop_owned (
  steam_id TEXT NOT NULL,
  item     TEXT NOT NULL,               -- an id in src/shop.js ITEMS, e.g. color:gold
  price    INTEGER NOT NULL,            -- what it cost then
  bought   INTEGER NOT NULL,
  PRIMARY KEY (steam_id, item)
);
CREATE TABLE IF NOT EXISTS looks (
  steam_id TEXT PRIMARY KEY,
  color    TEXT,
  badge    TEXT,
  frame    TEXT,
  updated  INTEGER NOT NULL
);

-- Messages (src/social.js), head-to-heads (src/h2h.js) and cups (src/cups.js)
-- The inbox: notices from ACR Daily (from_id NULL) and 1:1 messages between drivers
CREATE TABLE IF NOT EXISTS messages (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  to_id   TEXT NOT NULL,
  from_id TEXT,                        -- the sender; NULL: a notice
  kind    TEXT NOT NULL,               -- msg / h2h / cup
  body    TEXT NOT NULL,
  ref     TEXT,                        -- what a notice is about: h2h:<id>, cup:<id>
  created INTEGER NOT NULL,
  read_at INTEGER
);
CREATE INDEX IF NOT EXISTS messages_to ON messages (to_id, id);
CREATE INDEX IF NOT EXISTS messages_from ON messages (from_id, id);

-- Drivers someone takes no messages or challenges from
CREATE TABLE IF NOT EXISTS blocks (
  steam_id TEXT NOT NULL,
  blocked  TEXT NOT NULL,
  created  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, blocked)
);

-- Messages reported to the site's admins
CREATE TABLE IF NOT EXISTS message_reports (
  message_id INTEGER PRIMARY KEY,
  by         TEXT NOT NULL,
  reason     TEXT,
  created    INTEGER NOT NULL
);

-- Head-to-heads: a challenge for one driver, the challenger's event, an equal stake each (0: a friendly)
CREATE TABLE IF NOT EXISTS h2h (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  challenger TEXT NOT NULL,
  opponent   TEXT NOT NULL,
  stake      INTEGER NOT NULL DEFAULT 0,
  spec       TEXT NOT NULL,            -- JSON: the event as the challenger set it (checkEvent's value)
  status     TEXT NOT NULL,            -- sent / accepted / declined / expired / cancelled / settled
  holder     TEXT,                     -- its holder league (made on accepting)
  event_id   INTEGER,
  winner     TEXT,                     -- settled: the winner's steam_id, NULL for no contest
  note       TEXT,
  created    INTEGER NOT NULL,
  answer_by  INTEGER NOT NULL,         -- not accepted by then: it expires (the stake goes back)
  answered   INTEGER,
  settled    INTEGER
);
CREATE INDEX IF NOT EXISTS h2h_challenger ON h2h (challenger, status);
CREATE INDEX IF NOT EXISTS h2h_opponent ON h2h (opponent, status);

-- Cups: a knockout of 1v1s anyone can make, with an entry fee the winners share
CREATE TABLE IF NOT EXISTS cups (
  id          TEXT PRIMARY KEY,        -- also its holder league's id
  name        TEXT NOT NULL,
  about       TEXT NOT NULL DEFAULT '',
  owner       TEXT NOT NULL,
  size        INTEGER NOT NULL,        -- 4 / 8 / 16 / 32 / 64 / 128 drivers at most
  fee         INTEGER NOT NULL DEFAULT 0,
  split       TEXT NOT NULL,           -- JSON: the pot's % by place, e.g. [60, 30, 5, 5]
  spec        TEXT NOT NULL,           -- JSON: what each match races (checkEvent's value)
  starts      INTEGER NOT NULL,        -- sign-ups close, round 1 opens
  round_hours INTEGER NOT NULL,        -- how long each round is open
  status      TEXT NOT NULL,           -- open / running / finished / cancelled
  round       INTEGER NOT NULL DEFAULT 0,   -- the round being driven (1..)
  round_at    INTEGER,                 -- when that round was opened (the cron run's mark)
  created     INTEGER NOT NULL,
  settled     INTEGER,
  official    INTEGER NOT NULL DEFAULT 0,   -- 1: ACR Daily's own (owner 'acr-daily', made by the admin; 0019)
  prize       INTEGER NOT NULL DEFAULT 0    -- credits ACR Daily adds to the pot (shared as the fees)
);
CREATE INDEX IF NOT EXISTS cups_status ON cups (status, starts);

CREATE TABLE IF NOT EXISTS cup_entries (
  cup_id   TEXT NOT NULL,
  steam_id TEXT NOT NULL,
  fee      INTEGER NOT NULL,
  joined   INTEGER NOT NULL,
  seed     INTEGER,                    -- 1 = the top seed (set at the start)
  place    INTEGER,                    -- settled: 1, 2, 3 (both losing semi-finalists), 5 ...
  PRIMARY KEY (cup_id, steam_id)
);

CREATE TABLE IF NOT EXISTS cup_matches (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  cup_id   TEXT NOT NULL,
  round    INTEGER NOT NULL,           -- 1..
  slot     INTEGER NOT NULL,           -- 0.. in the round: the winners of 2k and 2k+1 meet in slot k next round
  a        TEXT,                       -- the drivers (a: the higher seed); NULL: a bye
  b        TEXT,
  event_id INTEGER,
  winner   TEXT,
  note     TEXT,                       -- how it was decided
  UNIQUE (cup_id, round, slot)
);

-- Driver pages (src/drivers.js), results and the rating (src/rating.js)
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
  created  INTEGER NOT NULL,
  name_fmt TEXT,                          -- the name / the tag with Trackmania's $ codes (src/tmtext.js; 0022), NULL: none
  tag_fmt  TEXT
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

-- things the cron does once, by key: a cup round's reminder ('remind:cup:<id>:<round>'); the first run's row stays
CREATE TABLE IF NOT EXISTS marks (
  key TEXT PRIMARY KEY,
  at  INTEGER NOT NULL
);

-- achievements (src/achievements.js): unlocked once, kept (players.ach_at: the driver's last check)
CREATE TABLE IF NOT EXISTS achievements (
  steam_id TEXT NOT NULL,
  id       TEXT NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (steam_id, id)
);
CREATE INDEX IF NOT EXISTS achievements_id ON achievements (id);

-- where drivers are on a league event's stage right now (cup matches followed live): gone 2 minutes after the last update
CREATE TABLE IF NOT EXISTS event_live (
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  stage_no INTEGER NOT NULL,
  x        REAL,
  z        REAL,
  progress REAL NOT NULL DEFAULT 0,
  total_ms INTEGER,
  state    TEXT NOT NULL,                 -- live / finished / dnf
  updated  INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
CREATE INDEX IF NOT EXISTS event_live_updated ON event_live (updated);
