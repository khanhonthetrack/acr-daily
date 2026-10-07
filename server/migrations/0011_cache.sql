-- Built boards, weeks and stage stats, kept until their time is up or what they are built from changes (src/cache.js)
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0011_cache.sql
CREATE TABLE IF NOT EXISTS cache (
  key     TEXT PRIMARY KEY,
  body    TEXT NOT NULL,
  expires INTEGER NOT NULL
);
