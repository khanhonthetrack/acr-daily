-- What the stats page needs from a counted run's trace, stored when the run arrives (src/stats.js runProfile), so the
-- page no longer reads every trace (too much CPU for Workers Free).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0013_run_profile.sql
ALTER TABLE runs ADD COLUMN profile TEXT;
