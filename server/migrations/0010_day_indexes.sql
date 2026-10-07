-- The leaderboard and the live map read one daily's attempts / live positions. Both tables are keyed by steam_id
-- first, so without these every request read the whole table (every day ever played).
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0010_day_indexes.sql
CREATE INDEX IF NOT EXISTS attempts_day ON attempts (date, slot);
CREATE INDEX IF NOT EXISTS live_day ON live (date, slot);
-- live positions of past days are no longer needed (the cron deletes them from now on)
DELETE FROM live WHERE date < date('now', '-1 day');
