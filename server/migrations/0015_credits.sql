-- Credits (a prototype; on only with CREDITS_FROM in wrangler.toml): what drivers earn (welcome, daily bonus, the free
-- daily finished) and stake (the wager daily), every change a line in the ledger (src/credits.js). Leagues are free.
-- Needs 0014 (leagues) first. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0015_credits.sql
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
