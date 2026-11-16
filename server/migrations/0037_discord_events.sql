-- Event sign-ups on Discord (src/discordrsvp.js): a card posted with /event, with Attending / Maybe / Not attending
-- buttons, and each member's answer (one per member and event; taking it back deletes the row).
CREATE TABLE IF NOT EXISTS discord_events (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id        TEXT NOT NULL,
  channel_id      TEXT NOT NULL DEFAULT '',
  title           TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  location        TEXT NOT NULL DEFAULT '',
  starts          INTEGER NOT NULL,           -- ms
  ends            INTEGER NOT NULL,           -- ms
  created_by      TEXT NOT NULL DEFAULT '',   -- the Discord user id of who posted it
  created_by_name TEXT NOT NULL DEFAULT '',
  scheduled_id    TEXT,                       -- the matching Discord server Event, once made
  created         INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS discord_rsvps (
  event_id INTEGER NOT NULL,
  user_id  TEXT NOT NULL,                     -- Discord user id
  name     TEXT NOT NULL DEFAULT '',
  answer   TEXT NOT NULL,                     -- 'yes' | 'maybe' | 'no'
  updated  INTEGER NOT NULL,
  PRIMARY KEY (event_id, user_id)
);
