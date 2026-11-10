-- A league stage's start, sent again, is no second start (src/leaguesapi.js start / begin): the app sends when the stage
-- started (`at`, ms), kept here; the same start sent twice (a retry after the server had it, or two copies of the app
-- open: "DNF: SS2 started again" for a stage started once, 2026-11-09) is taken once. Needs 0014.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0031_stage_start_stamp.sql
ALTER TABLE league_entries ADD COLUMN stage_at INTEGER;   -- when on_stage started, as the app sent it (ms); NULL: not sent
