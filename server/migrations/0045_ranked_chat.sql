-- A ranked session's chat (src/liverallies.js chatApi): the lines its drivers write, read in the app's chat window by
-- the session's drivers only. The name kept as it was when written (a name changed later doesn't rewrite the chat).
CREATE TABLE IF NOT EXISTS live_chat (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  series   TEXT NOT NULL,                 -- the session: its series' key and its hour (ms), as live_signups has them
  starts   INTEGER NOT NULL,
  steam_id TEXT NOT NULL,
  name     TEXT NOT NULL,                 -- the driver's name when they wrote it
  body     TEXT NOT NULL,                 -- one line, 200 characters at most
  created  INTEGER NOT NULL               -- ms
);
CREATE INDEX IF NOT EXISTS live_chat_session ON live_chat (series, starts, id);
