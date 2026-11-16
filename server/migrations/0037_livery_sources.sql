-- Liveries from another site, kept in step with it (src/liveryimport.js): ModsCloud.net's Assetto Corsa Rally skins, each
-- with its author's credit and its page (the download is there); its preview stays on that site (shot_url).
ALTER TABLE liveries ADD COLUMN source TEXT;        -- 'modscloud' (NULL: sent by a driver)
ALTER TABLE liveries ADD COLUMN source_id TEXT;     -- its id there (the post's)
ALTER TABLE liveries ADD COLUMN shot_url TEXT;      -- its preview there (https), instead of livery_shots
CREATE UNIQUE INDEX IF NOT EXISTS liveries_source ON liveries (source, source_id) WHERE source IS NOT NULL;
