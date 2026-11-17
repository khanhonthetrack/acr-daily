-- Ranked rallies by turns (src/liverallies.js turnsOf): when each queue row's turn opened, so the turns that went by
-- stay as they were whatever comes after (a start on its way to the server, a driver queued later).
ALTER TABLE live_slots ADD COLUMN turn_at INTEGER;
