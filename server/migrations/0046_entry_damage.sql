-- The car's damage after the driver's last counted stage of an event (24 Nov 2026): {"no": <stage index>, "parts":
-- {"<part>": <life points 0-100>, ...}} (only parts below 100), as the app read it at the finish line (the game mod).
-- A driver whose game crashed after the finish (the stage counted from its finish-line time) goes on from the next stage
-- with this car, not a repaired one (src/leaguesapi.js eventAction 'stage' / 'dnf'; client leagues.py recover).
ALTER TABLE league_entries ADD COLUMN damage TEXT;

-- A championship's owner and admins, a rally's maker: their decisions on entries (24 Nov 2026, "modify and/or cancel
-- DNFs, as any proper league admin panel should provide"): op 'reinstate' (a DNF taken back: the driver goes on from
-- the stage after their last counted one), 'retire' (the entry ended: DNF), 'time' (a stage's time set: a lost one
-- entered, or one corrected). Shown to everyone with the event's other decisions.
CREATE TABLE IF NOT EXISTS league_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  op TEXT NOT NULL,
  stage_no INTEGER,
  ms INTEGER,
  penalty_ms INTEGER,
  reason TEXT NOT NULL,
  by TEXT NOT NULL,
  created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS league_decisions_event ON league_decisions (event_id);
