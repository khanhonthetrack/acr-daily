-- Live splits on a multi-stage event's stages (league_events.rules.splits, off unless its admins turn it on): the app's
-- own split times on each stage run (ms at the route's fractions, as the dailies'), so every driver compares at the
-- same points. The game's own splits stay in `splits`.
ALTER TABLE league_stage_times ADD COLUMN live_splits TEXT;
