-- Liveries (src/liveries.js, the /liveries page, the app's COMMUNITY > LIVERIES): liveries the drivers made (with ACR
-- Livery Tool or by hand), each a card with a preview, a download link where its author put the file, the drivers'
-- stars and the downloads. A driver sends one; it shows once the admin has published it. Needs nothing before it.
-- (0035: 0033 is rallies', 0034 comments'.)
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0035_liveries.sql
CREATE TABLE IF NOT EXISTS liveries (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id    TEXT NOT NULL,             -- who sent it (signed in with Steam)
  car         TEXT NOT NULL,             -- the car's id (src/cars.js: the game's own name for it)
  title       TEXT NOT NULL,             -- the livery's name
  author      TEXT NOT NULL,             -- who painted it, as the sender gives it (their driver name by default)
  description TEXT,
  link        TEXT,                      -- where the file is (https); NULL: shown only, not shared
  status      TEXT NOT NULL,             -- pending / published / rejected / hidden (src/liveries.js STATUSES)
  note        TEXT,                      -- for the sender: why it was turned down or taken off
  clicks      INTEGER NOT NULL DEFAULT 0,   -- downloads (the website's button, the app's INSTALL)
  votes       INTEGER NOT NULL DEFAULT 0,   -- kept with livery_votes
  stars_sum   INTEGER NOT NULL DEFAULT 0,
  flags       INTEGER NOT NULL DEFAULT 0,   -- "link not working" since the admin last looked (livery_flags)
  shot_v      TEXT,                      -- the preview's version (its address changes with it, so it can be kept for good)
  created     INTEGER NOT NULL,
  updated     INTEGER NOT NULL,
  published   INTEGER                    -- first shown
);
CREATE INDEX IF NOT EXISTS liveries_status ON liveries (status, car);
CREATE INDEX IF NOT EXISTS liveries_driver ON liveries (steam_id, created);
CREATE INDEX IF NOT EXISTS liveries_created ON liveries (created);

-- A livery's preview, squeezed by the browser (JPEG, at most 1600 px wide), apart so the lists never read it
CREATE TABLE IF NOT EXISTS livery_shots (
  livery_id INTEGER PRIMARY KEY,
  type      TEXT NOT NULL,               -- image/jpeg / image/png / image/webp
  data      BLOB NOT NULL,
  created   INTEGER NOT NULL
);

-- One vote a driver a livery (1 to 5 stars; a second vote changes the first)
CREATE TABLE IF NOT EXISTS livery_votes (
  livery_id INTEGER NOT NULL,
  steam_id  TEXT NOT NULL,
  stars     INTEGER NOT NULL,
  created   INTEGER NOT NULL,
  PRIMARY KEY (livery_id, steam_id)
);

-- "Link not working?": one a driver a livery, until the admin has looked (then cleared)
CREATE TABLE IF NOT EXISTS livery_flags (
  livery_id INTEGER NOT NULL,
  steam_id  TEXT NOT NULL,
  created   INTEGER NOT NULL,
  PRIMARY KEY (livery_id, steam_id)
);
