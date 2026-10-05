-- Routes recorded automatically by players' apps (first clean run of a stage without a route).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0004_route_contributions.sql
ALTER TABLE routes ADD COLUMN contributed_by TEXT;
