-- Messages (src/social.js), head-to-heads (src/h2h.js) and cups (src/cups.js). Needs 0014 (leagues) and 0015
-- (credits) first. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0017_social.sql
--
-- A head-to-head or a cup is driven as league events (DRIVE in the app, the same stages, timing and standings): each
-- has a hidden holder in leagues (kind h2h / cup, never listed) whose events are its matches, each match open to its
-- two drivers only (league_events.only_ids).
ALTER TABLE leagues ADD COLUMN kind TEXT NOT NULL DEFAULT 'league';   -- league / h2h / cup
ALTER TABLE league_events ADD COLUMN only_ids TEXT;                   -- JSON [steamId, ...]: only they drive it; NULL: members

-- The inbox: notices from ACR Daily (from_id NULL) and 1:1 messages between drivers
CREATE TABLE IF NOT EXISTS messages (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  to_id   TEXT NOT NULL,
  from_id TEXT,                        -- the sender; NULL: a notice
  kind    TEXT NOT NULL,               -- msg / h2h / cup
  body    TEXT NOT NULL,
  ref     TEXT,                        -- what a notice is about: h2h:<id>, cup:<id>
  created INTEGER NOT NULL,
  read_at INTEGER
);
CREATE INDEX IF NOT EXISTS messages_to ON messages (to_id, id);
CREATE INDEX IF NOT EXISTS messages_from ON messages (from_id, id);

-- Drivers someone takes no messages or challenges from
CREATE TABLE IF NOT EXISTS blocks (
  steam_id TEXT NOT NULL,
  blocked  TEXT NOT NULL,
  created  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, blocked)
);

-- Messages reported to the site's admins
CREATE TABLE IF NOT EXISTS message_reports (
  message_id INTEGER PRIMARY KEY,
  by         TEXT NOT NULL,
  reason     TEXT,
  created    INTEGER NOT NULL
);

-- Head-to-heads: a challenge for one driver, the challenger's event, an equal stake each (0: a friendly)
CREATE TABLE IF NOT EXISTS h2h (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  challenger TEXT NOT NULL,
  opponent   TEXT NOT NULL,
  stake      INTEGER NOT NULL DEFAULT 0,
  spec       TEXT NOT NULL,            -- JSON: the event as the challenger set it (checkEvent's value)
  status     TEXT NOT NULL,            -- sent / accepted / declined / expired / cancelled / settled
  holder     TEXT,                     -- its holder league (made on accepting)
  event_id   INTEGER,
  winner     TEXT,                     -- settled: the winner's steam_id, NULL for no contest
  note       TEXT,
  created    INTEGER NOT NULL,
  answer_by  INTEGER NOT NULL,         -- not accepted by then: it expires (the stake goes back)
  answered   INTEGER,
  settled    INTEGER
);
CREATE INDEX IF NOT EXISTS h2h_challenger ON h2h (challenger, status);
CREATE INDEX IF NOT EXISTS h2h_opponent ON h2h (opponent, status);

-- Cups: a knockout of 1v1s anyone can make, with an entry fee the winners share
CREATE TABLE IF NOT EXISTS cups (
  id          TEXT PRIMARY KEY,        -- also its holder league's id
  name        TEXT NOT NULL,
  about       TEXT NOT NULL DEFAULT '',
  owner       TEXT NOT NULL,
  size        INTEGER NOT NULL,        -- 4 / 8 / 16 / 32 drivers at most
  fee         INTEGER NOT NULL DEFAULT 0,
  split       TEXT NOT NULL,           -- JSON: the pot's % by place, e.g. [60, 30, 5, 5]
  spec        TEXT NOT NULL,           -- JSON: what each match races (checkEvent's value)
  starts      INTEGER NOT NULL,        -- sign-ups close, round 1 opens
  round_hours INTEGER NOT NULL,        -- how long each round is open
  status      TEXT NOT NULL,           -- open / running / finished / cancelled
  round       INTEGER NOT NULL DEFAULT 0,   -- the round being driven (1..)
  created     INTEGER NOT NULL,
  settled     INTEGER
);
CREATE INDEX IF NOT EXISTS cups_status ON cups (status, starts);

CREATE TABLE IF NOT EXISTS cup_entries (
  cup_id   TEXT NOT NULL,
  steam_id TEXT NOT NULL,
  fee      INTEGER NOT NULL,
  joined   INTEGER NOT NULL,
  seed     INTEGER,                    -- 1 = the top seed (set at the start)
  place    INTEGER,                    -- settled: 1, 2, 3 (both losing semi-finalists), 5 ...
  PRIMARY KEY (cup_id, steam_id)
);

CREATE TABLE IF NOT EXISTS cup_matches (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  cup_id   TEXT NOT NULL,
  round    INTEGER NOT NULL,           -- 1..
  slot     INTEGER NOT NULL,           -- 0.. in the round: the winners of 2k and 2k+1 meet in slot k next round
  a        TEXT,                       -- the drivers (a: the higher seed); NULL: a bye
  b        TEXT,
  event_id INTEGER,
  winner   TEXT,
  note     TEXT,                       -- how it was decided
  UNIQUE (cup_id, round, slot)
);
