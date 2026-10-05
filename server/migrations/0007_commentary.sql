-- live commentary lines (src/commentary.js)
CREATE TABLE IF NOT EXISTS commentary (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  date     TEXT NOT NULL,
  slot     INTEGER NOT NULL,
  created  INTEGER NOT NULL,
  kind     TEXT NOT NULL,
  steam_id TEXT,
  text     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS commentary_day ON commentary (date, slot, id);
