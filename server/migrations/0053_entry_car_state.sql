-- The whole car at the finish line of the driver's last counted stage of an event (27 Nov 2026): the game mod's copy
-- (body, panels off, scratches, lights, wear, tyres, every part), gzip + base64 from the app, with its stage:
-- {"no": <stage index>, "z": "<base64>"}. One per entry, replaced at each stage: a stage the game lost after its finish
-- goes on with it on any PC (client leagues.recover). ~4 KB each.
ALTER TABLE league_entries ADD COLUMN car_state TEXT;
