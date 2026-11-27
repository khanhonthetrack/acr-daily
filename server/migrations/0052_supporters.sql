-- Supporters on Buy Me a Coffee (src/supporters.js): kept from its webhook, for the app's thank-you bar.
CREATE TABLE IF NOT EXISTS supporters (
  id      TEXT PRIMARY KEY,                     -- <object>:<Buy Me a Coffee id> (donation:98765, membership:12)
  kind    TEXT NOT NULL,                        -- coffee | shop | member | monthly
  name    TEXT NOT NULL,                        -- the name shown on Buy Me a Coffee ("Someone" when hidden)
  coffees INTEGER,
  level   TEXT,                                 -- a member's level
  active  INTEGER NOT NULL DEFAULT 1,           -- members / monthly: 0 once cancelled or paused
  at      INTEGER NOT NULL,                     -- unix seconds: given / started
  updated INTEGER NOT NULL                      -- ms
);
CREATE INDEX IF NOT EXISTS supporters_at ON supporters (at);
