-- Things the cron does once, by key: a cup round's reminder ('remind:cup:<id>:<round>'). INSERT OR IGNORE: the first
-- run's row stays, and what goes with it is conditioned on its `at`.
CREATE TABLE IF NOT EXISTS marks (
  key TEXT PRIMARY KEY,
  at  INTEGER NOT NULL
);
