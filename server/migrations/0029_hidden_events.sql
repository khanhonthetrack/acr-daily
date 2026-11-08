-- Hidden events (README, Leagues › Hidden): a league event's, a 1V1's or a cup's weather and time of day, stage times
-- (the drivers' results) and stage names can be kept from the drivers until it ends, so nobody hotlaps it beforehand.
-- Events made before this keep everything shown (hide NULL). Needs nothing before it.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0029_hidden_events.sql
ALTER TABLE league_events ADD COLUMN hide TEXT;         -- JSON {weather, times, stages}; NULL: nothing hidden
CREATE TABLE IF NOT EXISTS event_reveals (             -- a hidden event's details given to a driver (DRIVE in the app)
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
