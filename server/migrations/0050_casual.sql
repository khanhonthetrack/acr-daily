-- CASUAL (src/casual.js): lobbies of up to 4 (the host drives, up to 3 co-drivers), no results; and the languages of COPILOT's lobbies.
ALTER TABLE copilot_lobbies ADD COLUMN langs TEXT;
CREATE TABLE IF NOT EXISTS casual_lobbies (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  token   TEXT NOT NULL UNIQUE,                  -- the pacenotes page's (/n/<token>)
  code    TEXT,                                  -- a private lobby's
  host    TEXT NOT NULL,
  track   TEXT NOT NULL,
  car     TEXT NOT NULL,
  weather TEXT NOT NULL,
  time    TEXT NOT NULL,
  langs   TEXT,                                  -- JSON list of language codes
  state   TEXT NOT NULL DEFAULT 'open',          -- open | started | finished | closed
  created INTEGER NOT NULL,
  updated INTEGER NOT NULL,
  started INTEGER
);
CREATE INDEX IF NOT EXISTS casual_lobbies_state ON casual_lobbies (state, created);
CREATE INDEX IF NOT EXISTS casual_lobbies_host ON casual_lobbies (host, state);
CREATE INDEX IF NOT EXISTS casual_lobbies_code ON casual_lobbies (code);
CREATE TABLE IF NOT EXISTS casual_members (
  lobby_id INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  seat     INTEGER NOT NULL CHECK (seat BETWEEN 0 AND 3),   -- 0 the host (the driver)
  ready    INTEGER NOT NULL DEFAULT 0,
  joined   INTEGER NOT NULL,
  PRIMARY KEY (lobby_id, steam_id),
  UNIQUE (lobby_id, seat)
);
CREATE INDEX IF NOT EXISTS casual_members_player ON casual_members (steam_id);
CREATE TABLE IF NOT EXISTS casual_signals (
  lobby_id INTEGER NOT NULL,
  from_id  TEXT NOT NULL,
  to_id    TEXT NOT NULL,
  data     TEXT NOT NULL,
  updated  INTEGER NOT NULL,
  PRIMARY KEY (lobby_id, from_id, to_id)
);
CREATE INDEX IF NOT EXISTS casual_signals_to ON casual_signals (lobby_id, to_id);
