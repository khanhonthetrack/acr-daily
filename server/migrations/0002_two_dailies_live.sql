-- Two dailies a day (slot 1 and 2), random cars, live positions on the website map.
-- Apply once:  npx wrangler d1 execute acr-daily --remote --file=migrations/0002_two_dailies_live.sql

ALTER TABLE runs ADD COLUMN slot INTEGER NOT NULL DEFAULT 1;
ALTER TABLE runs ADD COLUMN temps TEXT;   -- air temperature (K) at 10 %, 20 % ... of the stage: conditions check
CREATE INDEX IF NOT EXISTS runs_board2 ON runs (date, slot, status, total_ms);

-- the schedule now has two challenges per day
DROP TABLE IF EXISTS schedule;
CREATE TABLE schedule (
  date  TEXT NOT NULL,
  slot    INTEGER NOT NULL,
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  weather TEXT,                  -- conditions to drive in (src/conditions.js)
  time    TEXT,
  PRIMARY KEY (date, slot)
);

-- the pool is now a list of stages; car '*' = a random car every time
UPDATE pool SET car = '*';
DELETE FROM pool WHERE rowid NOT IN (SELECT MIN(rowid) FROM pool GROUP BY track);

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
