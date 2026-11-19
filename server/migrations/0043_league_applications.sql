-- Championships by application (src/leaguesapi.js): every championship is listed and can be opened; a public one is
-- joined straight away, a private one asked to join (an application), which its owner and admins accept or decline.
-- Invite codes no longer let anyone into a championship (a championship's old /join/<code> link opens its page);
-- a private rally's code is still what lets a driver in (leagues.code).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0043_league_applications.sql
CREATE TABLE IF NOT EXISTS league_applications (
  league_id TEXT NOT NULL,
  steam_id  TEXT NOT NULL,
  message   TEXT NOT NULL DEFAULT '',          -- a short word to the admins (optional)
  status    TEXT NOT NULL DEFAULT 'pending',   -- pending / declined (accepted: the row goes, they are a member)
  created   INTEGER NOT NULL,                  -- when they asked
  decided   INTEGER,                           -- declined: when (they can ask again LIMITS.reapplyDays after it)
  by        TEXT,                              -- declined: who
  PRIMARY KEY (league_id, steam_id)
);
CREATE INDEX IF NOT EXISTS league_applications_status ON league_applications (league_id, status);
CREATE INDEX IF NOT EXISTS league_applications_player ON league_applications (steam_id);
