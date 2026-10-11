-- The shop (credits, src/shop.js): looks bought with credits (a colour, a badge, a frame), kept for good, one of each
-- kind worn at a time. Needs 0015 (credits) first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0016_shop.sql
CREATE TABLE IF NOT EXISTS shop_owned (
  steam_id TEXT NOT NULL,
  item     TEXT NOT NULL,               -- an id in src/shop.js ITEMS, e.g. color:gold
  price    INTEGER NOT NULL,            -- what it cost then
  bought   INTEGER NOT NULL,
  PRIMARY KEY (steam_id, item)
);

-- What each driver wears (item ids; NULL: nothing of that kind)
CREATE TABLE IF NOT EXISTS looks (
  steam_id TEXT PRIMARY KEY,
  color    TEXT,
  badge    TEXT,
  frame    TEXT,
  updated  INTEGER NOT NULL
);
