-- A daily of one's own, bought in the shop (src/shop.js DAILY_SET): who set a day's daily and when. NULL: picked
-- from the pool as before. Needs 0023 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0024_daily_set.sql
ALTER TABLE schedule ADD COLUMN set_by TEXT;
ALTER TABLE schedule ADD COLUMN set_at INTEGER;
