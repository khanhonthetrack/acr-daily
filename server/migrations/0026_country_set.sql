-- Drivers pick their flag on their own driver page (src/drivers.js, POST /api/me/country): when they last did. Once
-- set, the country the app reads from the in-game driver profile no longer changes it; until then it still does.
-- NULL: never picked. Needs 0018 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0026_country_set.sql
ALTER TABLE players ADD COLUMN country_set INTEGER;
