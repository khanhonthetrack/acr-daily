-- A league stage retired rather than driven (src/leaguesapi.js missed, from app 0.1.5): driven without the app watching
-- (the game's rally further on than the entry), in an event with the retirement rule (rules.retire). The entry goes on;
-- the standings count the stage as its slowest time + the rule's minutes (src/leagues.js eventStandings). Needs 0014.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0032_stage_retired.sql
ALTER TABLE league_stage_times ADD COLUMN retired TEXT;   -- why the stage counts as retired; NULL: driven, its time counts
