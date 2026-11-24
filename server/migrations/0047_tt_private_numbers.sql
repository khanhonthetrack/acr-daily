-- Community (private) time trials numbered from TT3 again on each page (src/timetrial.js setTtPrivate), after the
-- numbers of any page open at the same time: a stage is its page + its number, no longer a number used once ever (the
-- user, 24 Nov 2026: "i dont want 6 time trials, i want 4 only"). SQLite can't change a primary key: the table made
-- again with the same rows.
CREATE TABLE tt_private_new (
  slot      INTEGER NOT NULL,
  page      TEXT NOT NULL,
  title     TEXT,
  starts_at INTEGER NOT NULL,
  ends_at   INTEGER NOT NULL,
  min_app   TEXT,
  created   INTEGER NOT NULL,
  listed    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (page, slot)
);
INSERT INTO tt_private_new (slot, page, title, starts_at, ends_at, min_app, created, listed)
  SELECT slot, page, title, starts_at, ends_at, min_app, created, listed FROM tt_private;
DROP TABLE tt_private;
ALTER TABLE tt_private_new RENAME TO tt_private;
CREATE INDEX IF NOT EXISTS tt_private_page ON tt_private (page);
CREATE INDEX IF NOT EXISTS tt_private_open ON tt_private (ends_at);
