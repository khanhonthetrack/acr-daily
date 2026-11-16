-- A livery from another site with the file's own link there (src/liveryimport.js): ModsCloud's download button
-- (<page>?download=<id>&token=<t>, the same for everyone, sent on to the file), so the app installs it in one click.
ALTER TABLE liveries ADD COLUMN download_url TEXT;
