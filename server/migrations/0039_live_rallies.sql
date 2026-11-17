-- Live rallies (src/liverallies.js): scheduled sessions of a series, every 2 hours, the two series in turn. Drivers sign
-- up in the 30 minutes before the hour; at the hour the session's rally is drawn (a league event of a hidden holder of
-- kind 'live', as a cup match's) and its start list published: car 1 at the hour + 5 minutes, one every 30 s. Each stage
-- after SS1 is a queue: a driver who finishes a stage gets the next 30-s slot on the next one, at least 2 minutes on.
CREATE TABLE IF NOT EXISTS live_signups (
  series   TEXT NOT NULL,                 -- the series' key (liverallies.js SERIES)
  starts   INTEGER NOT NULL,              -- the session's hour (ms)
  steam_id TEXT NOT NULL,
  car      TEXT NOT NULL,                 -- the car of the series' class they drive (its name in cars.js)
  at       INTEGER NOT NULL,              -- when they signed up
  PRIMARY KEY (series, starts, steam_id)
);
CREATE TABLE IF NOT EXISTS live_sessions (
  series   TEXT NOT NULL,
  starts   INTEGER NOT NULL,
  event_id INTEGER,                       -- its league event once published; 0: nobody signed up (or no stages); NULL: being published
  created  INTEGER NOT NULL,              -- when publishing began (taken over when it stalls)
  PRIMARY KEY (series, starts)
);
-- Each driver's start on each stage: SS1's from the start list, the later ones as they finish the one before.
CREATE TABLE IF NOT EXISTS live_slots (
  event_id   INTEGER NOT NULL,
  stage_no   INTEGER NOT NULL,            -- 0 = SS1
  steam_id   TEXT NOT NULL,
  slot_at    INTEGER NOT NULL,            -- ms: when they start
  moved      INTEGER NOT NULL DEFAULT 0,  -- times sent to the end of the queue for missing their start
  started    INTEGER,                     -- ms: when their stage clock started (server time, as the app sent it)
  penalty_ms INTEGER NOT NULL DEFAULT 0,  -- started this long before the slot (a league_penalties row too)
  out        TEXT,                        -- no longer queued: 'dns' (SS1 missed too often), 'dnf' (a later stage), 'retired'
  created    INTEGER NOT NULL,
  PRIMARY KEY (event_id, stage_no, steam_id)
);
CREATE INDEX IF NOT EXISTS live_slots_queue ON live_slots (event_id, stage_no, slot_at);
