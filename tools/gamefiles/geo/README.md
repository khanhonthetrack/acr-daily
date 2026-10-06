# Stages on Earth (experimental)

Where each stage is in the real world, for the satellite map at `/lab/map` (`server/src/labmap.js`).

The game files don't store this. The Single Rally Stage screen shows a "Start Location", but it isn't in any table
(and for Cwmbiga it is about 250 m off). So each map's routes are laid on the real roads instead:

- `fit.py`: for each map (all variants of a map share the game's coordinates), fetches the roads around a guessed
  real place from OpenStreetMap (Overpass API, cached in `osm_*.json`, gitignored) and searches the rotation and
  position that put the routes on them. Scale is 1:1 (the stages are laser scanned). Every map comes out mirrored in x
  (the game's left-handed axes) and turned about 265-275 degrees; leaving the rotation free gave convincing but wrong
  matches, so `--rot 264 276` holds it there.
- `build.py`: `map_fits.json` + the routes -> `geo_fits.json` per stage, with how far the route lies from the real
  roads (median and 90 %). `ok` = 90 % within 40 m.

The conversion (the same in `labmap.js` `toLL`):

```
xm = mirror == 'x' ? -x : x;   zm = mirror == 'z' ? -z : z
e = xm cos(r) - zm sin(r);     n = xm sin(r) + zm cos(r)        (metres east / north, r = rotDeg)
lat = lat0 + n / 111132.954;   lon = lon0 + e / (111319.49 cos(lat0))
```

`lat0` / `lon0` = where the game's (0, 0) is.

## Run

Needs numpy and scipy. Get the routes from the database first:

```bat
cd server
npx wrangler d1 execute acr-daily --remote --json --command "SELECT track, stage_id, points FROM routes" > ..\tools\gamefiles\geo\routes_full.json
cd ..\tools\gamefiles\geo
python fit.py WelesS3HafrenNorth           (finds the mirror; then the rest with the rotation held:)
python fit.py --rot 264 276 WelesS4HafrenSouth MonteCarloS2Sisteron MonteCarloS1Bollene GreeceS3Elatia ...
python build.py                             (-> geo_fits.json; copy it into server/src/geofits.js)
```

## Results (2026-10-06)

| Map | Variants | Median | 90 % within | |
|---|---|---|---|---|
| Wales Hafren North | 6 | 4 m | 10 m | ok |
| Wales Hafren South | 2 | 10 m | 29 m | ok, rough |
| Monte Carlo Sisteron | 6 | 2 m | 5 m | ok |
| Monte Carlo La Bollène | 8 | 2 m | 3-4 m | ok |
| Greece Elatia | 6 | 2-4 m | 6-9 m | ok |
| Alsace Munster | 6 | 18 m | 45 m | no: probably the wrong place |
| Alsace Saverne | 4 | 11-15 m | 34-53 m | no: wrong place |
| Greece Loutraki | 6 | 14-16 m | 45-59 m | no: wrong place |

For the last three, the next step is the in-game "Start Location" of one stage each as the search centre.
