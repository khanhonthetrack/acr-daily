-- Official cups (src/cups.js): run by ACR Daily itself, made by the site's admin (POST /api/admin/cup, tools/admin.py
-- cup), never by a driver. Their page and the cups list say so; ACR Daily may put credits of its own in the pot.
-- Needs 0017 (cups) first. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0019_official_cups.sql
ALTER TABLE cups ADD COLUMN official INTEGER NOT NULL DEFAULT 0;   -- 1: ACR Daily's own (owner 'acr-daily')
ALTER TABLE cups ADD COLUMN prize INTEGER NOT NULL DEFAULT 0;      -- credits ACR Daily adds to the pot (shared as the fees)
