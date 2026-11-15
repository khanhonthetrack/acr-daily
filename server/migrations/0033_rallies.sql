-- Rallies and Community organizers (src/leaguesapi.js, README "Rallies"): anyone signed in makes a rally (one event,
-- public or private with its invite link; a league row of kind 'event' holds it, as a 1V1's or a cup's matches are
-- held); a championship (a league: rounds, seasons, standings) is made by Community organizers only, a rank the admin
-- gives by hand (admin.py organizer). The drivers who run a championship already are organizers from the start.
-- Needs 0014 and 0018. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0033_rallies.sql
ALTER TABLE players ADD COLUMN organizer INTEGER;   -- when the admin made them a Community organizer (ms); NULL: not one
UPDATE players SET organizer = 1794700800000         -- (2026-11-15)
  WHERE organizer IS NULL AND steam_id IN (SELECT owner FROM leagues WHERE kind = 'league' AND official = 0);
-- the public rallies every app lists (GET /api/me/events)
CREATE INDEX IF NOT EXISTS leagues_kind ON leagues (kind, public);
