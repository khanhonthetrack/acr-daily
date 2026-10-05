-- the daily report of each finished day (src/recap.js)
CREATE TABLE IF NOT EXISTS recaps (
  date    TEXT PRIMARY KEY,
  created INTEGER NOT NULL,
  model   TEXT,
  title   TEXT NOT NULL,
  text    TEXT NOT NULL,
  facts   TEXT
);
