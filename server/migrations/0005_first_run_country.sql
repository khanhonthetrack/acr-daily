-- First run counts (attempts are recorded when a run starts) + country flags.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0005_first_run_country.sql
ALTER TABLE players ADD COLUMN country TEXT;      -- ISO code from the in-game driver profile, e.g. 'vn'
ALTER TABLE runs ADD COLUMN started_at INTEGER;   -- PC time the stage clock started (ms)
CREATE TABLE IF NOT EXISTS attempts (
  steam_id TEXT NOT NULL,
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  started  INTEGER NOT NULL,                        -- first time the app said "on stage" for this daily
  PRIMARY KEY (steam_id, date, slot)
);
