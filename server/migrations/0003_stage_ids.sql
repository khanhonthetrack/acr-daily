-- The game's own id of each stage variant (e.g. AlsaceS4SaverneFullForward), so the app can set the daily
-- up in the game's save. Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0003_stage_ids.sql
ALTER TABLE routes ADD COLUMN stage_id TEXT;

-- from the player's own save records (stage id + car + the run's stage name in telemetry)
UPDATE routes SET stage_id = 'WelesS4HafrenSouthFullForward' WHERE track = 'Wales Afon Bidno';
UPDATE routes SET stage_id = 'AlsaceS4SaverneFullForward' WHERE track = 'Alsace Forêt';
UPDATE routes SET stage_id = 'AlsaceS4SaverneShort1Forward' WHERE track = 'Alsace Obersteigen';
