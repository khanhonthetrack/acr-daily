# ACR Daily

Two daily stages, random cars and one global leaderboard for **Assetto Corsa Rally**.
Players run a small Windows app next to the game. It reads the game's telemetry, judges the run, shows its
own timer over the game's timer, and sends finished runs to the server. The server checks each run again
and keeps a board per daily, plus a weekly hall of fame.

**Play:** <https://acr-daily.acr-daily-server.workers.dev> (download the app there).
**Run your own server:** [SETUP.md](SETUP.md).

Open source under the [MIT licence](LICENSE). Code: <https://github.com/khanhonthetrack/acr-daily>. Issues and pull requests are welcome.

## The rules

| | |
|---|---|
| Dailies | **Two per day**, new at 00:00 UTC. Each has its own stage (never the same one twice in a day), a **random car** from all 18 in the game (`server/src/cars.js`), **conditions** (weather + time of day, `server/src/conditions.js`) and its own board. The app's **DRIVE** button sets the daily up in the game's save (a backup is kept). |
| One shot | **Your first run counts.** Later runs are practice. A run that is started and never finished becomes a DNF after an hour. |
| Hall of fame | Monday to Sunday, 14 stages. WRC points 25-18-15-12-10-8-6-4-2-1, then 1 per finisher; DNF 0. Ties go to wins, then stages scored. |
| Flags | Your country comes from the in-game driver profile. |
| Steam account | Runs are sent under the Steam account that signed in to the app. |
| App version | Everyone is timed by the same rules: the server takes runs only from apps at or above `MIN_APP_VERSION` (`server/wrangler.toml`, from the daily `MIN_APP_FROM` on). Older apps get their UPDATE button. |
| Conditions | Set by DRIVE in the game's Single Stage set-up. The game doesn't report them, but its air temperature follows time of day, weather and height, so on the start line the app compares it with the other drivers' (> 3 °C apart = "check time / weather"). |
| New stages | Nobody records routes by hand: the app records every clean run (no resets, by the same rules as the timer). The first one on a stage without a driven route is sent to the server, checked (no jumps, plausible length and speed) and becomes that stage's route, and the stage joins the rotation with a random car. Routes taken from the game's files (`tools/gamefiles`) give way to the first driven one, which is matched to its stage by start and finish even when the game reports another name. |
| Stage names | The website and the app show each stage as the game's menu names it ("Peïra Cava - La Bollène-Vésubie", `server/src/stages.js`); the telemetry only reports a short one ("Monte Carlo Peïra Cava"). |
| Download | The app is served by the server itself: `/download/ACR-Daily.exe`. `client\build.bat` copies it to `server\public`, and a deploy publishes it. |
| Live map | While a run is LIVE the app sends its position every second. The website and the app's overlays draw everyone on the stage as moving dots, each driver in their own colour (with their flag on the website). |
| Live commentary | On the website, each start, split, reset and finish of a counted run gets a line written by Claude (`server/src/commentary.js`). The app doesn't show it. |
| Daily report | At 01:05 UTC Claude writes a short report of the day before for the website: both stages' results and splits, the fun records (top speed, the longest jump, the longest flat-out blast), the drivers' history and the hall of fame (`server/src/recap.js`). |
| Reset to the road | **+60 s** each. The game never reports its own penalties, so the board time is *stage clock + 60 s per reset*. |
| Restart / quit / stopping | **DNF**. Stopping means the clock frozen away from the finish (or the game gone) for more than 30 s. |
| Shortcuts | **Invalid**. A run has to pass at least 90 % of the route checkpoints (one every 100 m). |
| Wrong car or stage | The run doesn't start. |
| Joining late | The app has to see the clock start, so a run that was already going doesn't count. |

## In the game: the timer overlay

A small always-on-top window that sits over the game's own timer (drag it there once, then **Lock timer**
so clicks go through to the game):

```
▌ 2:14.31  [+60 s]              stage clock + penalties so far
  vs Kalle R.  +3.42            live gap to today's #1 (their full run, matched by distance)
  ──────────────────────
  SPLIT 2 / 3         P3 / 12   at each split (25 / 50 / 75 % of the stage), for 8 s:
  1   Kalle R.                  where you stand against every driver's best run today,
  2   Sami P.          +0.88    RallySimFans style: the leader, the driver ahead,
  3   YOU              +1.24    you, the driver behind
  4   Ott T.           +2.10
  vs your best today  −0.35
```

At the finish the same panel shows your provisional position until the next run starts. Split times
include reset penalties. The app and the server time splits the same way, interpolated between
readings, and agree within ~50 ms.

## How it works

```
 Player PC                                          Cloudflare (free tier)
┌──────────────────────────────────────┐           ┌───────────────────────────────────┐
│ ACR-Daily.exe (client/)              │  Steam    │ Worker (server/src/index.js)      │
│  telemetry.py  reads shared memory   │  sign-in  │  /auth/steam/*   OpenID sign-in   │
│  judge.py      start/reset/DNF/finish│ ────────► │  /api/challenge  today's stage    │
│  app.py        main window + timer   │  runs     │  /api/runs       re-checks traces │
│                window over the game  │ ────────► │  /api/leaderboard                 │
│  api.py        server + offline queue│ ◄──────── │  /               website          │
└──────────────────────────────────────┘           │ D1 database (server/schema.sql)   │
                                                   └───────────────────────────────────┘
```

**What the game provides** (checked on real runs; same layout as Assetto Corsa Competizione):

| Field | Where |
|---|---|
| Stage clock | `"MM:SS.mmm"` at graphics +12. Reads 0 on the start line, runs from the line, freezes at the finish. |
| Car position | graphics +256 |
| Speed | physics +28 |
| Car and stage names | static +68 / +134 |

Penalties, the final time, assists and settings are **not** provided.

**Anti-cheat.** The app uploads the whole run trace, 4 samples a second:

- stage clock, PC clock and the game's physics step counter;
- position and speed;
- throttle, brake, steering, gear and rpm;
- resets so far.

The server checks the run again from scratch in two layers.

*Rules* (`server/src/validate.js`). These refuse the run outright:

- the start and the finish are on the route, and the checkpoints were passed;
- the clock only goes forwards, with no gaps in the trace;
- there are no jumps the car couldn't have driven unless a reset was counted for them;
- the totals add up.

*Realism* (`server/src/realism.js`). The limits were set from real runs:

| Check | Real runs | Refused | Flagged for review |
|---|---|---|---|
| Stage clock vs PC clock | 99.8–100.0 % | outside 97–103 % | |
| Game physics steps per clock second | 332–333 | outside 316–350 | outside 326–340 |
| Speed reading vs actual movement | 0.4–0.5 % error | > 8 % | > 3 % |
| Acceleration / braking (99th pct) | ≤ 0.5 g / ≤ 1.8 g | > 1.3 g / > 2.6 g | > 0.8 g / > 1.8 g |
| Cornering (95th pct) | 0.55–1.08 g | > 2.4 g | > 1.7 g |
| Throttle | used | never above 30 % | speeding up without it |
| Rpm follows speed within a gear | 0.66 gravel, 0.91 tarmac | | < 0.4 |
| Steering | used | | none |
| Section times vs other drivers today | | | fastest in every section, or evenly X % faster everywhere |
| Own history | | | > 15 % faster than your previous best on that stage + car |

Flagged runs stay on the board marked **⚑ review**. Every run has a public viewer page (`/run/<id>`)
showing:

- the map against the day's #1;
- speed, gap, throttle, brake and steering charts with a shared crosshair;
- section times;
- the check table;
- a **Report this run** button. Three reports also put a run under review.

`admin.py state` lists every run to review, `admin.py run <id>` shows its measurements, and `admin.py reject <id>` removes it.
`admin.py resets <id>` finds the resets in a run's trace, and `admin.py fix-run <id> <resets> [stage clock of each]`
corrects a run's resets, total and splits (`--dry-run` first).

What this stops: edited times, speed/slow-motion hacks, hidden resets, shortcuts, made-up or replayed-and-scaled
traces, and anything that doesn't behave like a car. What it can't stop: someone who builds a fully
consistent fake simulation of a run. That needs kernel-level anti-cheat, which no community tool has.
The viewer and the reports exist so people can spot that.

## Folders

```
client/              the Windows app (Python 3.13 + tkinter, built with PyInstaller)
  acr_daily/         telemetry, judge, route, recorder, saveslot (game save), ghosts, widgets, api, app (UI)
  tests/             unit tests (judge, standings, names, save slot, route recorder)
  build.bat          builds dist/ACR-Daily.exe with the server URL baked in
server/              Cloudflare Worker + D1
  src/               index.js (API + auth), validate.js + realism.js (run checks), cars.js, conditions.js,
                     stages.js (menu names), week.js, steam.js, commentary.js + recap.js (written by Claude);
                     pages: site.js, viewer.js, statspage.js, weekpage.js
  test/              *.test.mjs (node --test), e2e.py (against `wrangler dev`), fixtures/ (real runs)
  schema.sql         full schema; migrations/ upgrade older databases
tools/admin.py       routes, pool, schedule, reject runs, ban players
routes/              reference routes (Alsace Obersteigen, Alsace Forêt, Wales Afon Bidno)
CATALOG.md           every stage, car, weather and time the game offers
```

## Development

```bat
:: client tests (judge tests on raw recordings run when ACR_DAILY_RECORDINGS points at them)
cd client && python -m unittest discover -s tests

:: run the app from source; a JSONL telemetry dump can stand in for the game:
set ACR_DAILY_REPLAY=<path to dump.jsonl>
set ACR_DAILY_REPLAY_FROM=55
python run.py

:: server tests
cd server && npm install && npm test

:: local server with a local database
copy .dev.vars.example .dev.vars
npx wrangler d1 execute acr-daily --local --file=schema.sql
npx wrangler dev --port 8790 --ip 127.0.0.1
python test\e2e.py http://127.0.0.1:8790 local-test-admin-key-0123456789abcdef
```

**Admin mode in the app.** In `%APPDATA%\ACR Daily\settings.json`, set `"admin": true` and `"adminKey": "<ADMIN_KEY>"`.
This adds two buttons:

- **Record route:** drive a stage once, cleanly. The route is saved to `%APPDATA%\ACR Daily\routes`.
- **Upload route:** sends the recorded route to the server.

## Limits worth knowing

- The timer window can only sit over the game in **borderless or windowed** mode, not exclusive fullscreen.
- **Game updates.** A patch could move telemetry fields. If that happens, `telemetry.py` is the only file to fix.
- **Assists and settings.** The game doesn't report assists, gearbox or difficulty, so they can't be enforced. Put a note on the website asking people to drive fairly.
- **Free tier.** Cloudflare's free plan allows 100,000 requests a day. A running app makes roughly 2 requests a minute, so that's enough for a few dozen players driving all day. The paid plan is $5 a month.

## Licence and disclaimer

ACR Daily is released under the [MIT licence](LICENSE).

It is a fan-made community project and is not affiliated with, endorsed by or connected to Supernova Games
Studios, Kunos Simulazioni, 505 Games or Valve. *Assetto Corsa Rally* and all car, stage and brand names are
trademarks of their respective owners. The app only reads the telemetry the game publishes and edits the
player's own single-stage setup in their save file (with a backup); it does not modify the game.
