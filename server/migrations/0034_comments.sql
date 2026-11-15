-- Drivers' comments on their stages (src/comments.js, from app 0.1.6), as on RallySimFans: a line after a run. One per
-- driver and what it is on: a daily ('2026-11-15/1': shown with their time on its timing sheet and in Discord's
-- results), a time trial stage of a week ('tt:2026-11-09/2': on its board) or a stage of a league event
-- ('event:<id>/<0 = SS1>', cup and 1V1 matches too: read by the league's owner and admins, a cup's maker and the
-- site's admin). Needs 0014 (league events) first; numbered after 0033 (rallies).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0034_comments.sql
CREATE TABLE IF NOT EXISTS comments (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id TEXT NOT NULL,
  target   TEXT NOT NULL,               -- what it is on: '2026-11-15/1' (a daily), 'tt:2026-11-09/2', 'event:12/0'
  event_id INTEGER,                     -- a league event's (target event:...): who reads it comes from its league
  body     TEXT NOT NULL,               -- one line, at most 200 characters; '' = taken back by its driver
  created  INTEGER NOT NULL,
  updated  INTEGER NOT NULL,
  hidden   INTEGER NOT NULL DEFAULT 0,  -- taken down by the site's admin: shown to nobody but its driver
  UNIQUE (target, steam_id)
);
CREATE INDEX IF NOT EXISTS comments_event ON comments (event_id);
CREATE INDEX IF NOT EXISTS comments_updated ON comments (updated);
