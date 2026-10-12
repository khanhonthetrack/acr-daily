-- Multi-class league events and a league's divisions (src/leagues.js). Leagues and events made before keep one car or
-- one class and no divisions (the new columns NULL). Needs 0022 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0023_league_classes.sql
ALTER TABLE league_events ADD COLUMN car_classes TEXT;
ALTER TABLE leagues ADD COLUMN divisions TEXT;
ALTER TABLE league_members ADD COLUMN division TEXT;
