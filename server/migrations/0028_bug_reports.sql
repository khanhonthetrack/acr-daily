-- Bug reports (src/reports.js, the /report page): what a signed-in driver writes, and the screenshots, logs and saves
-- they attach. (The runs' "Report this run" is the older table `reports`.) Needs nothing before it.
-- Apply: npx wrangler d1 execute acr-daily --remote --file=migrations/0028_bug_reports.sql
CREATE TABLE IF NOT EXISTS bug_reports (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  steam_id    TEXT NOT NULL,             -- who sent it (signed in with Steam)
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,             -- what happened, what they expected
  area        TEXT NOT NULL,             -- daily / time trial / league / 1v1 / cup / app / website / other
  app_version TEXT,                      -- e.g. 0.0.24
  event_url   TEXT,                      -- the event, run or page it happened on
  happened    TEXT,                      -- when, in their words
  system      TEXT,                      -- Windows, screen, wheel..., in their words
  status      TEXT NOT NULL,             -- new / seen / needs-info / pr / fixed / closed (src/reports.js STATUSES)
  note        TEXT,                      -- for the reporter: a question, what was done
  pr_url      TEXT,                      -- the fix proposed
  created     INTEGER NOT NULL,
  updated     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS bug_reports_driver ON bug_reports (steam_id, created);
CREATE INDEX IF NOT EXISTS bug_reports_status ON bug_reports (status, id);
CREATE INDEX IF NOT EXISTS bug_reports_created ON bug_reports (created);

-- A report's files, each its own row (D1: 2 MB a row), packed by the browser: pictures as images, the rest gzipped
CREATE TABLE IF NOT EXISTS bug_files (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL,
  name      TEXT NOT NULL,               -- as the driver's PC named it
  kind      TEXT NOT NULL,               -- screenshot / log / save / other
  type      TEXT NOT NULL,               -- image/jpeg / image/png / image/webp / application/gzip
  size      INTEGER NOT NULL,            -- before the browser packed it
  stored    INTEGER NOT NULL,            -- as kept
  data      BLOB NOT NULL,
  created   INTEGER NOT NULL             -- deleted REPORT.keepDays after (the report's text stays)
);
CREATE INDEX IF NOT EXISTS bug_files_report ON bug_files (report_id);
CREATE INDEX IF NOT EXISTS bug_files_created ON bug_files (created);
