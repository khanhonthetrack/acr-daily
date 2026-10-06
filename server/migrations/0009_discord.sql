-- the Discord bot's messages (src/discord.js)
CREATE TABLE IF NOT EXISTS discord (
  key        TEXT PRIMARY KEY,
  message_id TEXT,
  hash       TEXT,
  date       TEXT,
  updated    INTEGER NOT NULL
);
