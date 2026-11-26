-- REPLAYS (src/replays.js): a counted run followed by the server while it is driven (its hash chain, on the server's
-- clock), the drivers' replay keys, the replays uploaded (a proof, a steward's request, one shared), and the stewards'
-- requests for one.
CREATE TABLE IF NOT EXISTS replay_keys (
  steam_id TEXT NOT NULL,
  key      TEXT NOT NULL,                        -- the app's Ed25519 public key (hex)
  created  INTEGER NOT NULL,
  PRIMARY KEY (steam_id, key)
);
CREATE TABLE IF NOT EXISTS replay_runs (
  rid        TEXT PRIMARY KEY,
  nonce      TEXT NOT NULL,
  steam_id   TEXT NOT NULL,
  kind       TEXT NOT NULL,                      -- daily | event
  ref        TEXT NOT NULL,                      -- a daily's id (2026-11-26/1), event:<id>:<stage index>
  track      TEXT NOT NULL,
  car        TEXT NOT NULL,
  key        TEXT NOT NULL,
  begin_ms   INTEGER NOT NULL,                   -- the server's clock at the begin
  begin_clock INTEGER NOT NULL,                  -- the stage clock the app said then (ms)
  commits    TEXT NOT NULL DEFAULT '[]',         -- JSON [[count, hash, server ms, stage clock ms], ...]
  fin_ms     INTEGER,                            -- the stage clock at the finish line, as the final commit said
  uploaded   TEXT                                -- the replay's code once uploaded
);
CREATE INDEX IF NOT EXISTS replay_runs_driver ON replay_runs (steam_id, begin_ms);
CREATE INDEX IF NOT EXISTS replay_runs_ref ON replay_runs (ref, steam_id, begin_ms);
CREATE TABLE IF NOT EXISTS replay_files (
  code      TEXT PRIMARY KEY,                    -- its address: /r/<code>
  rid       TEXT,
  steam_id  TEXT NOT NULL,
  kind      TEXT NOT NULL,
  ref       TEXT,
  track     TEXT NOT NULL,
  car       TEXT NOT NULL,
  status    TEXT NOT NULL,                       -- finished | dnf | ended...
  fin_ms    INTEGER,
  penalty_ms INTEGER,
  verdict   TEXT NOT NULL,                       -- clean | review | refused
  report    TEXT NOT NULL,                       -- JSON: the checks
  digest    TEXT NOT NULL,                       -- what the driver's key signed (hex)
  why       TEXT NOT NULL,                       -- dnf | steward | event | share
  public    INTEGER NOT NULL DEFAULT 0,
  action    TEXT,                                -- what it did: reinstated / time set / sent to review
  data      BLOB NOT NULL,                       -- the file as uploaded (gzip'd)
  size      INTEGER NOT NULL,
  views     INTEGER NOT NULL DEFAULT 0,
  created   INTEGER NOT NULL,
  expires   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS replay_files_driver ON replay_files (steam_id, created);
CREATE INDEX IF NOT EXISTS replay_files_ref ON replay_files (ref);
CREATE INDEX IF NOT EXISTS replay_files_expires ON replay_files (expires);
CREATE TABLE IF NOT EXISTS replay_requests (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id  INTEGER NOT NULL,
  stage_no  INTEGER NOT NULL,                    -- 0 = SS1
  steam_id  TEXT NOT NULL,                       -- the driver asked
  by        TEXT NOT NULL,                       -- the steward who asked
  reason    TEXT NOT NULL,
  state     TEXT NOT NULL DEFAULT 'open',        -- open | sent | none
  code      TEXT,                                -- the replay sent
  created   INTEGER NOT NULL,
  answered  INTEGER
);
CREATE INDEX IF NOT EXISTS replay_requests_driver ON replay_requests (steam_id, state);
CREATE INDEX IF NOT EXISTS replay_requests_event ON replay_requests (event_id);
