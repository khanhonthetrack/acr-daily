-- Team names and tags styled with Trackmania's $ codes (src/tmtext.js): name and tag stay what they read as (checked,
-- compared, shown where styles can't be), the formatted text kept beside them (NULL: no codes). Needs 0021 first.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0022_team_styles.sql
ALTER TABLE teams ADD COLUMN name_fmt TEXT;
ALTER TABLE teams ADD COLUMN tag_fmt TEXT;
