-- The live commentary is gone: its lines (and their index) with it. This deletes every stored line.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0012_no_commentary.sql
DROP TABLE IF EXISTS commentary;
