-- Official leagues (src/officialleagues.js): ACR Daily's own championships, made by the site's admin (POST
-- /api/admin/league, tools/admin.py league), never by a driver, as official cups are (0019). Owned by "acr-daily"; the
-- drivers it names run it on the website as its admins. Its page and the leagues list say "official".
-- Needs 0014 (leagues) first. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0030_official_leagues.sql
ALTER TABLE leagues ADD COLUMN official INTEGER NOT NULL DEFAULT 0;   -- 1: ACR Daily's own (owner 'acr-daily')
