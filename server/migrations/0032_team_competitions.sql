-- Team competitions (README: Teams): team championships in leagues, team 1V1s and team cups (src/teamscore.js,
-- leaguesapi.js, teamh2h.js, teamcups.js); a team's managers (team_members.role). Needs 0018 (teams) and 0029 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0032_team_competitions.sql
ALTER TABLE team_members ADD COLUMN role TEXT NOT NULL DEFAULT 'member';
ALTER TABLE leagues ADD COLUMN teams TEXT;
ALTER TABLE league_members ADD COLUMN team_id INTEGER;
ALTER TABLE league_seasons ADD COLUMN team_champ TEXT;
ALTER TABLE league_entries ADD COLUMN team_id INTEGER;

-- A league's teams (leagues.teams): its own (made by its admins) or ACR Daily's teams (one row each, made as their drivers
-- start the league's events)
CREATE TABLE IF NOT EXISTS league_teams (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id TEXT NOT NULL,
  name      TEXT NOT NULL,
  tag       TEXT,                         -- 2 to 4 letters or digits, shown by its drivers' names in the league
  color     TEXT NOT NULL,                -- one of src/drivers.js TEAM.colors
  manager   TEXT,                         -- a driver who runs it (its drivers, its nominations), NULL: the league's admins
  site_team TEXT,                         -- the ACR Daily team it stands for (the league's teams are those), NULL: the league's own
  created   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS league_teams_league ON league_teams (league_id);
CREATE UNIQUE INDEX IF NOT EXISTS league_teams_site ON league_teams (league_id, site_team);

-- The drivers a team nominates for a league event (a season whose team championship has nominations): only they count
CREATE TABLE IF NOT EXISTS league_nominations (
  event_id INTEGER NOT NULL,
  team_id  INTEGER NOT NULL,              -- league_teams.id
  steam_id TEXT NOT NULL,
  by       TEXT NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
CREATE INDEX IF NOT EXISTS league_nominations_team ON league_nominations (team_id, event_id);

-- The stewards' points penalties on a team in a season's team championship (negative: points given back)
CREATE TABLE IF NOT EXISTS league_team_penalties (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  season_id INTEGER NOT NULL,
  team_id   INTEGER NOT NULL,
  points    INTEGER NOT NULL,
  reason    TEXT NOT NULL,
  by        TEXT NOT NULL,
  created   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS league_team_penalties_season ON league_team_penalties (season_id);

-- Team 1V1s: a team's captain or a manager challenges another team to an event of their making, scored as they chose
CREATE TABLE IF NOT EXISTS team_h2h (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  challenger  TEXT NOT NULL,            -- the challenging team (teams.id)
  opponent    TEXT NOT NULL,            -- the challenged team
  by          TEXT NOT NULL,            -- who sent it
  spec        TEXT NOT NULL,            -- JSON: the event (checkEvent's value) + scoring (src/teamscore.js checkScoring)
  status      TEXT NOT NULL,            -- sent / accepted / declined / expired / cancelled / settled
  holder      TEXT,                     -- its holder league (kind th2h, made on accepting)
  event_id    INTEGER,
  winner      TEXT,                     -- settled: the winning team's id, NULL for no contest
  note        TEXT,
  result      TEXT,                     -- JSON: the teams' results as settled (teamResult)
  created     INTEGER NOT NULL,
  answer_by   INTEGER NOT NULL,
  answered    INTEGER,
  answered_by TEXT,
  settled     INTEGER
);
CREATE INDEX IF NOT EXISTS team_h2h_challenger ON team_h2h (challenger, status);
CREATE INDEX IF NOT EXISTS team_h2h_opponent ON team_h2h (opponent, status);
CREATE INDEX IF NOT EXISTS team_h2h_status ON team_h2h (status, answer_by);

-- Who drives for which team in a team match (a team 1V1's or a team cup's): its open roster, or the drivers it named
CREATE TABLE IF NOT EXISTS team_lineups (
  event_id INTEGER NOT NULL,              -- the match (league_events.id)
  team_id  TEXT NOT NULL,
  steam_id TEXT NOT NULL,
  by       TEXT,                          -- who named them (NULL: the roster, set when the match was made)
  at       INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
CREATE INDEX IF NOT EXISTS team_lineups_team ON team_lineups (team_id, event_id);

-- Team cups: a knockout of team matches (src/teamcups.js); no entry fee, no prizes, not rated
CREATE TABLE IF NOT EXISTS team_cups (
  id          TEXT PRIMARY KEY,         -- also its holder league's id (kind tcup)
  name        TEXT NOT NULL,
  about       TEXT NOT NULL DEFAULT '',
  owner       TEXT NOT NULL,            -- who made it ('acr-daily': an official one)
  size        INTEGER NOT NULL,         -- 4 / 8 / 16 / 32 / 64 teams at most
  spec        TEXT NOT NULL,            -- JSON: what each match races (checkEvent's value) + scoring + lineupFor (cup / match)
  roster_min  INTEGER NOT NULL,         -- each team signs up this many drivers at least...
  roster_max  INTEGER NOT NULL,         -- ...and this many at most
  starts      INTEGER NOT NULL,
  round_hours INTEGER NOT NULL,
  status      TEXT NOT NULL,            -- open / running / finished / cancelled
  round       INTEGER NOT NULL DEFAULT 0,
  round_at    INTEGER,
  created     INTEGER NOT NULL,
  settled     INTEGER,
  official    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS team_cups_status ON team_cups (status, starts);

CREATE TABLE IF NOT EXISTS team_cup_entries (
  cup_id  TEXT NOT NULL,
  team_id TEXT NOT NULL,
  by      TEXT NOT NULL,                  -- who signed it up (its captain or a manager)
  joined  INTEGER NOT NULL,
  seed    INTEGER,
  place   INTEGER,
  PRIMARY KEY (cup_id, team_id)
);

-- The drivers each team signed up for a cup: one team per driver per cup
CREATE TABLE IF NOT EXISTS team_cup_roster (
  cup_id   TEXT NOT NULL,
  team_id  TEXT NOT NULL,
  steam_id TEXT NOT NULL,
  joined   INTEGER NOT NULL,
  PRIMARY KEY (cup_id, steam_id)
);
CREATE INDEX IF NOT EXISTS team_cup_roster_team ON team_cup_roster (cup_id, team_id);

CREATE TABLE IF NOT EXISTS team_cup_matches (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  cup_id   TEXT NOT NULL,
  round    INTEGER NOT NULL,
  slot     INTEGER NOT NULL,
  a        TEXT,                          -- the teams (a: the higher seed); NULL: a bye
  b        TEXT,
  event_id INTEGER,
  winner   TEXT,
  note     TEXT,
  UNIQUE (cup_id, round, slot)
);
