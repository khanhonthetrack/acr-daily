-- Achievements (src/achievements.js) and cup / league matches followed live on the website. Needs 0020 first. Apply:
-- npx wrangler d1 execute acr-daily --remote --file=migrations/0021_achievements_live.sql

-- Achievements (src/achievements.js): unlocked once, kept.
CREATE TABLE IF NOT EXISTS achievements (
  steam_id TEXT NOT NULL,
  id       TEXT NOT NULL,                 -- an id of ACHIEVEMENTS
  at       INTEGER NOT NULL,              -- when it was unlocked (the check that saw it)
  PRIMARY KEY (steam_id, id)
);
CREATE INDEX IF NOT EXISTS achievements_id ON achievements (id);
ALTER TABLE players ADD COLUMN ach_at INTEGER;   -- the driver's last achievements check (the cron's)

-- Where drivers are on a league event's stage right now (cup matches, 1V1s and league events, followed live on the
-- website): one row a driver and event, gone two minutes after its last update.
CREATE TABLE IF NOT EXISTS event_live (
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  stage_no INTEGER NOT NULL,              -- 0 = SS1
  x        REAL,
  z        REAL,
  progress REAL NOT NULL DEFAULT 0,       -- 0..1 of the stage
  total_ms INTEGER,                       -- the stage clock
  state    TEXT NOT NULL,                 -- live / finished / dnf
  updated  INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
CREATE INDEX IF NOT EXISTS event_live_updated ON event_live (updated);
