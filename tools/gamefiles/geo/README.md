# Stages on Earth (experimental)

Where each stage is in the real world, for the satellite map at `/lab/map` (`server/src/labmap.js`).

The game files don't store this. The Single Rally Stage screen shows a "Start Location", but it isn't in any table
(read it off the screen). Each map's routes are laid on the real roads:

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

All 44 variants line up. Munster, Saverne, Loutraki (and Elatia, as the check) were placed from the start coordinates the
game menu shows (Single Rally Stage > Change rally stage, per variant; read from the screen, `anchor.py`), then fine
fitted on the roads (`refine.py`). The menu coordinates are good to about 20 m (Elatia, Munster) to 50-70 m (Loutraki).

| Map | Variants | Scale from the starts | Median | 90 % within | Real terrain vs menu elevation |
|---|---|---|---|---|---|
| Wales Hafren North | 6 | | 4 m | 10 m | |
| Wales Hafren South | 2 | | 10 m | 29 m | |
| Monte Carlo Sisteron | 6 | | 2 m | 5 m | |
| Monte Carlo La Bollène | 8 | | 2 m | 3-4 m | |
| Greece Elatia | 6 | 1.000 | 2 m | 3-5 m | 241-724 m vs 241-731 m |
| Greece Loutraki | 6 | 1.001 | 2-3 m | 4-6 m | 291-744 m vs 291-750 m |
| Alsace Munster | 6 | 0.999 | 4-7 m | 9-19 m | 473-1164 m vs 475-1160 m |
| Alsace Saverne | 4 | 1.040 | 5-12 m | 21-36 m | 346-473 m vs 355-456 m |

Saverne is the one stage the game changed: its long variants' first 3.5 km run up to ~80 m beside the real road (it is
visible on the satellite photo, so it isn't missing from OpenStreetMap); the rest is within a few metres. It is stored
2 % larger (`scale: 1.02`), the best compromise.

Menu start coordinates (variant: start, elevation range):

- Munster: Descente / Col du petit Ballon 47°58'47.49"N 7°6'7.09"E; Montée / Luttenbach 48°1'49.84"N 7°7'18.73"E;
  Forêt de Munster 47°59'27.21"N 7°7'44.51"E; Sommet 48°0'24.51"N 7°8'0.68"E (475-1160 m)
- Saverne: Steigenbach / La Mossig 48°37'43.00"N 7°18'22.24"E; Forêt de Saverne 48°40'14.80"N 7°18'16.11"E;
  Obersteigen 48°38'47.11"N 7°18'42.43"E (355-456 m)
- Loutraki: Loutraki - Aghii Theodori / New Loutraki 37°58'30.76"N 23°2'7.17"E; Aghii Theodori - Loutraki / Aghii Theodori
  Reverse 38°1'8.68"N 23°5'19.53"E; New Loutraki Reverse 37°59'29.11"N 23°4'7.34"E; Aghii Theodori 37°59'14.10"N 23°4'0.12"E
  (291-750 m)
- Elatia: Elatia - Zeli / Elatia 38°37'41.38"N 22°47'34.50"E; Zeli - Elatia / Zeli Reverse 38°39'51.52"N 22°52'14.56"E;
  Elatia Reverse 38°38'35.40"N 22°49'48.05"E; Zeli 38°38'36.16"N 22°49'45.78"E (241-731 m)
- Hafren North: Cwmbiga - Fedw Fain 52°29'15.00"N 3°42'48.99"W (365-514 m)
