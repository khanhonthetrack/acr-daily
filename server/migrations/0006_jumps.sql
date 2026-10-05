-- Jumps of a run: [[clockMs at take-off, airtime ms, metres along the route, km/h at take-off], ...]
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0006_jumps.sql
ALTER TABLE runs ADD COLUMN jumps TEXT;
