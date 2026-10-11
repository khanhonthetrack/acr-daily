-- Credits (a prototype; on only with CREDITS_FROM in wrangler.toml): what drivers earn (welcome, daily bonus, the free
-- daily finished) and stake (the wager daily, league entry fees), every change a line in the ledger (src/credits.js).
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
  kind     TEXT NOT NULL,               -- welcome / daily / finish / wager / wager-win / wager-refund / fee / prize / fee-refund
  ref      TEXT,                        -- the daily ("2026-10-09/2") or the league event ("event:12")
  note     TEXT,
  created  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS credit_ledger_player ON credit_ledger (steam_id, id);

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

-- League entry fees: paid before the start, the pot goes to the event's top three
ALTER TABLE league_events ADD COLUMN fee INTEGER NOT NULL DEFAULT 0;
ALTER TABLE league_events ADD COLUMN fee_settled INTEGER;
CREATE TABLE IF NOT EXISTS league_fees (
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  fee      INTEGER NOT NULL,
  paid     INTEGER NOT NULL,
  PRIMARY KEY (event_id, steam_id)
);
-- The pots paid out (the cron) or refunded (the event deleted): written in the same batch as the credits, so a pot
-- goes out once, either way
CREATE TABLE IF NOT EXISTS league_pots (
  event_id INTEGER PRIMARY KEY,
  settled  INTEGER NOT NULL
);
