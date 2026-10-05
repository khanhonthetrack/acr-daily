# Stage routes from the game's own files

Every stage variant's route, read from Assetto Corsa Rally's data instead of driven by hand. Run from this folder;
everything it unpacks goes to `ext\` (gitignored, a few GB while it runs).

## What it reads

- The game's IoStore containers (`acr\Content\Paks\*.utoc/.ucas`, UE 5.4, not encrypted, Oodle compressed).
  `iostore.py` lists and extracts files; `ooz\` is a tiny Rust helper around the open-source
  [oozextract](https://crates.io/crates/oozextract) Oodle decoder (`cargo build --release` in `ooz\`).
- `zen.py` reads a package's name map and export table.
- Each stage map (`Levels/<Rally>S<n><Stage>.umap`) is world-partitioned into generated cells. One cell per
  direction holds a `SplinesActor` with `CenterSpline` / `IdealSpline` (points every 79 bytes: key, position,
  arrive and leave tangents). Start lines are `BC_StartSequenceTrigger_C`, the end-of-stage zones
  `BC_EndSequenceTrigger_C`.
- Which trigger belongs to which variant: the cell's data layers (in the persistent map's runtime cell records),
  named through each variant's `PacenoteSetupActor` label (`variants.py`).
- Names: `Data/Localization/ContentTexts/ST_Track` (`sttrack.py`). The telemetry reports "<location> <short name>",
  e.g. "Alsace Forêt", "Wales Afon Bidno".

## Run

```bat
python sttrack.py ext\ST_Track.uasset st_track.json      (after: python iostore.py ext "Localization/ContentTexts/ST_Track.uasset")
python getcells.py . AlsaceS4Saverne                       (per stage map: extracts its cells)
python geometry.py ext\AlsaceS4Saverne                     (centre lines + start / end triggers -> geometry.json)
python build_routes.py                                     (-> game_routes.json, every variant)
python validate_routes.py                                  (against the recorded routes in ..\..\routes and real runs)
set ACR_DAILY_ADMIN_KEY=...
python upload_routes.py                                    (adds missing stages to the server + daily pool)
```

## Accuracy

The route is the centre line from the start trigger to 140 m before the end trigger (where the stage clock
stopped on Saverne; on Wales Hafren South it is 223 m, so some routes run on a bit past the finish line: the app
accepts a finish up to 400 m before the route's end). Checked on the three driven stages: start within 5 m, the
driven line a median 2 m from the centre line, and every real run judged with the right time.

Uploaded routes are marked `contributed_by = 'game-files'`: the first clean driven run of such a stage replaces it.
Stage ids (for the app's DRIVE set-up) are only set where a real save confirmed them; the others fill in from
players' saves as they drive.
