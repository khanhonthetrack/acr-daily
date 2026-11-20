-- A private time trial page made public (src/timetrial.js setTtPrivate {listed}): while open, the main time trial page
-- (/tt) points to it, and its own page is no longer hidden from search engines. Its stages still go only to apps from
-- its min_app on. (The user, 20 Nov 2026: TT3 London + TT4 Lousã public from 21 Nov.)
ALTER TABLE tt_private ADD COLUMN listed INTEGER NOT NULL DEFAULT 0;
