# ACR Daily

Two daily stages, random cars and one global leaderboard for **Assetto Corsa Rally**.
Players run a small Windows app next to the game. It reads the game's telemetry, judges the run, shows its
own timer over the game's timer, and sends finished runs to the server. The server takes each result as the
app sent it and keeps a board per daily, plus weekly results.

**Play:** <https://acrdaily.com> (download the app there).
**Discord:** <https://acrdaily.com/discord> (chat, ideas, bug reports; the live timing bot).
**Run your own server:** [SETUP.md](SETUP.md).

Open source under the [MIT licence](LICENSE). Code: <https://github.com/khanhonthetrack/acr-daily>. Issues and pull requests are welcome.

## The rules

| | |
|---|---|
| Dailies | **Two per day**, new at 00:00 UTC. Each has its own stage (never the same one twice in a day), a **random car** from all 18 in the game (`server/src/cars.js`), **conditions** (weather + time of day, `server/src/conditions.js`) and its own board. Each is a **one-stage Rally Weekend** in the game: the app's **DRIVE** button sets it up in the game's save (a backup is kept; `client/acr_daily/rallyweekend.py`) with the stage, car, weather and time of day (time standing still), penalty level Light, manual respawn on, damage on (light damage, light wear, no mechanical failures), one AI opponent and you first on the road. DRIVE never touches a Rally Weekend the player has in progress. |
| Your time | **The game's own.** After a Rally Weekend stage the game writes its official result into its save: stage time, penalty (respawns, cuts, jump starts) and splits. The game writes it once you go on from its results screen; the app reads it then and sends it, and the board time is *the game's stage time + its penalty*. A finished run waiting for it is kept on disk, so closing the app loses nothing: it is looked for again when the app opens. A finished run without the game's result (the game closed before saving it) is a DNF. |
| One shot | **Your first run counts.** Later runs are practice. A run that is started and never finished becomes a DNF after an hour. |
| Weekly results | Monday to Sunday, 14 stages. WRC points 25-18-15-12-10-8-6-4-2-1, then 1 per finisher; DNF 0. Ties go to wins, then stages scored. |
| Flags | Your country comes from the in-game driver profile. |
| Steam account | Runs are sent under the Steam account that signed in to the app. |
| App version | Everyone is timed by the same rules: the server takes runs only from apps at or above `MIN_APP_VERSION` (`server/wrangler.toml`, from the daily `MIN_APP_FROM` on). Older apps get their UPDATE button. |
| Conditions | Set by DRIVE in the game's Rally Weekend set-up. The game doesn't report them, so they aren't checked: its air temperature can't stand in for them, as the game draws it anew each time it sets a stage up (the same save, stage, time and weather gave 13.0 °C, then 15.7 °C; the set-up screen's forecast shows that session's figure). |
| New stages | Nobody records routes by hand: the app records every clean run (no resets, by the same rules as the timer). The first one on a stage without a driven route is sent to the server, checked (no jumps, plausible length and speed) and becomes that stage's route, and the stage joins the rotation with a random car. Routes taken from the game's files (`tools/gamefiles`) give way to the first driven one, which is matched to its stage by start and finish even when the game reports another name. |
| Stage names | The website and the app show each stage as the game's menu names it ("Peïra Cava - La Bollène-Vésubie", `server/src/stages.js`); the telemetry only reports a short one ("Monte Carlo Peïra Cava"). |
| Download | The app is served by the server itself: `/download/ACR-Daily.exe`. `client\build.bat` copies it to `server\public`, and a deploy publishes it. |
| Live map | While a run is LIVE the app sends its position every few seconds (5 by default; the server sets it, `LIVE_SEND_S` in `server/wrangler.toml`). The website and the app's overlays draw everyone on the stage as moving dots, each driver in their own colour (with their flag on the website). |
| Discord | A bot in the Discord server's #live-timing keeps one message up to date with who is on stage and today's two timing sheets, and posts each day's final results and the weekly results (`server/src/discord.js`, a webhook run every minute). |
| Restart / retire / quit / stopping | **DNF**. Stopping means the clock frozen away from the finish (or the game gone) for more than 30 s. |
| Pausing | Fine. A pause (clock frozen and the car not moving at all) can last up to 15 minutes; the run carries on with the clock. |
| Shortcuts | **Invalid**. A run has to pass at least 90 % of the route checkpoints (one every 100 m). |
| Wrong car or stage | The run doesn't start. |
| Joining late | The app has to see the clock start, so a run that was already going doesn't count. |

## Leagues

Clubs, as in DiRT Rally and EA WRC: groups of drivers running their own multi-stage events (`server/src/leagues.js`,
`client/acr_daily/leagues.py`).

| | |
|---|---|
| A league | Made on the website (`/leagues`) after signing in there with Steam. A name, a description and who can join: **public** (listed, anyone can join) or **private** (only with its invite link `/join/<code>`: eight letters and digits without look-alikes; a new code makes the old link stop working), and a banner. A driver can run 5 leagues. |
| Roles | The **owner** changes the league's settings, banner and Discord posts, makes members admins (or members again) and can delete it. **Admins** (and the owner) make events and seasons, renew the invite code, remove or ban members (a removed driver's event under way ends as a DNF; their results stay) and steward. |
| An event | A **Rally Weekend** in the game, so it follows the game's rules: one location; 1 to 16 stages over up to 4 days, each day opening with a service park, more service parks between stages if wanted; each stage's weather and start time; one car for everyone or a class (each driver picks a car of it); the penalty, respawn, damage, wear and failure settings; when it opens and closes (62 days at most). Once someone has started it, only its name, its season and a later close can change. **Copy as the next round** fills the builder with the event (its next number, opening when it closes) to change its stages and save. |
| Driving it | The app's **LEAGUES** view lists the open and coming events of your leagues. DRIVE sets the whole rally up in the game's save, then Racing › Rally › Rally Weekend › Start Rally. The game keeps the rally between stages and sessions (Rally Weekend › Resume), repairs the car in the service parks and carries the damage between them. Each stage is judged like a daily and sent with the game's own stage time + penalty. The game holds one Rally Weekend at a time: a league rally in progress is set aside while a daily is set up, and put back by CONTINUE on the event. |
| DNF | Retiring or restarting a stage, starting a stage a second time (the server keeps each stage's first start), a stage driven without the app watching or outside the event's rally, or not finishing before the event closes. |
| Stewards | The owner and admins can add a time penalty (on a stage, which moves its positions, or on the total; a negative one gives time back) or disqualify an entry (DSQ: no position, no points). Each decision shows on the event page with its reason and who made it, and can be taken back. |
| Standings | Per event: the totals (stage times + the game's penalties + the stewards'), stage by stage positions and the position after each stage. |
| Seasons | A league's championships: each season takes some of its events (an event outside any season is a one-off) and has its own points: a table from P1 then points for every other finisher (WRC 25-18-15-12-10-8-6-4-2-1 + 1 per finisher by default), an optional **Power Stage** bonus for the fastest on each event's last stage (5-4-3-2-1 as in the WRC), and each driver's worst rounds dropped. |
| Discord | The owner can paste a webhook of one of the league's Discord channels: the server posts there when an event opens, when it has 24 hours left (events open 30 hours or more), and its results with the season's standings (`server/src/leaguediscord.js`, from the cron every minute). |
| App version | Driving league events needs an app from `LEAGUES_MIN_APP` on (`server/wrangler.toml`). |

## In the game: the timer overlay

A small always-on-top window that sits over the game's own timer (drag it there once, then **Lock timer**
so clicks go through to the game):

```
▌ 2:14.31                       stage clock (the game's penalties come with its official time)
  vs Kalle R.  +3.42            live gap to today's #1 (their full run, matched by distance)
  ──────────────────────
  SPLIT 2 / 3         P3 / 12   at each split (25 / 50 / 75 % of the stage), for 8 s:
  1   Kalle R.                  where you stand against every driver's best run today,
  2   Sami P.          +0.88    RallySimFans style: the leader, the driver ahead,
  3   YOU              +1.24    you, the driver behind
  4   Ott T.           +2.10
  vs your best today  −0.35
```

At the finish the same panel shows your provisional position, then your official one once the game has saved its
result. Split times are stage clock. The app and the server time splits the same way, interpolated between
readings, and agree within ~50 ms.

## How it works

```
 Player PC                                          Cloudflare
┌──────────────────────────────────────┐           ┌───────────────────────────────────┐
│ ACR-Daily.exe (client/)              │  Steam    │ Worker (server/src/index.js)      │
│  telemetry.py  reads shared memory   │  sign-in  │  /auth/steam/*   OpenID sign-in   │
│  judge.py      start/reset/DNF/finish│ ────────► │  /api/challenge  today's stage    │
│  app.py        main window + timer   │  runs     │  /api/runs       stores runs      │
│                window over the game  │ ────────► │  /api/leaderboard                 │
│  api.py        server + offline queue│ ◄──────── │  /               website          │
└──────────────────────────────────────┘           │ D1 database (server/schema.sql)   │
                                                   │ (R2 bucket for the traces: option)│
                                                   └───────────────────────────────────┘
```

**What the game provides** (checked on real runs; same layout as Assetto Corsa Competizione):

| Field | Where |
|---|---|
| Stage clock | `"MM:SS.mmm"` at graphics +12. Reads 0 on the start line, runs from the line, freezes at the finish. |
| Car position | graphics +256 |
| Speed | physics +28 |
| Car and stage names | static +68 / +134 |

Penalties, the final time, assists and settings are **not** provided. (A Rally Weekend stage's official time and
penalty are, afterwards: the game writes them into its save, which `rallyweekend.py` reads.)

**Judging a run.** The app is the only judge (`client/acr_daily/judge.py`). It reads the telemetry 20 times a second and decides:

| | |
|---|---|
| Start | The run starts when the stage clock does, on the daily's stage and car. The car has to be within 60 m of the route's start (further away = **INVALID**). A clock that was already running doesn't count. |
| Resets | Counted for the record (the game's own respawn penalty is in its official time). A reset is either the car jumping further than it could drive between two readings (15 m, or 3 m when nearly stopped, plus 1.5 × the distance its speed covers), or the car going from 30 km/h or more in gear to standing still in neutral within 0.6 s. The game puts a reset car down stopped in neutral, sometimes only a few metres from where it left the road. A reset counts once the run is still going 1.5 s later, and never twice within 3 s. |
| DNF | The clock goes back (a restart), the stage or car changes, the clock stays frozen away from the finish with the car moving (or the game is gone) for more than 30 s, or a pause lasts more than 15 minutes. |
| Pause | The clock frozen and the car not moved more than 2 m since (the game's pause menu freezes the car) = paused: no DNF, and never taken for the finish. |
| Finish | The clock stops near the end of the route while the car rolls on. The run has to pass within 40 m of at least 90 % of the route's checkpoints (one every 100 m), or it is **INVALID**. |

It then sends its result (status and reason, stage clock, resets, splits, jumps) and the whole run trace,
4 samples a second:

- stage clock, PC clock and the game's physics step counter;
- position and speed;
- throttle, brake, steering, gear and rpm;
- air temperature;
- resets so far.

**The server takes the result as sent** (`server/src/validate.js`, `submitRun` in `server/src/index.js`):

| | |
|---|---|
| Time | The game's own stage time + penalty, as the app read them from the game's save (a finished run without them is refused). Not checked against the trace. |
| App version | Apps older than `MIN_APP_VERSION` can't send runs, live positions or new routes (HTTP 426, for the dailies from `MIN_APP_FROM` on; both in `server/wrangler.toml`). So every run on a board was judged by the same rules. |
| First run counts | A driver's first run of a daily goes on its board; later ones are practice. A start that never sends a result is a DNF once a later run arrives, or after an hour. |
| Sanity checks | A run needs a signed-in Steam account that isn't banned, today's daily (yesterday's until 00:30 UTC) with its stage and car, a known status, 0–99 resets and a clock under 4 h. A driver can send 300 runs a day. |
| The trace | Kept for the counted run only, gzipped (`server/src/traces.js`), not judged. It feeds the run viewer, the split standings, section times, the stats page and the live gap to #1. After 14 days only each daily's top 3 keep theirs; the others keep their times, splits and sections. |

**Reports and review.** Every counted run has a public viewer page (`/run/<id>`) showing:

- the map against the day's #1;
- speed, gap, throttle, brake and steering charts with a shared crosshair;
- section times;
- a **Report this run** button.

Three reports (one per IP address) put a run **under review**: it stays on the board, marked UNDER REVIEW.
An admin then decides with `tools/admin.py` ([SETUP.md](SETUP.md#5-looking-after-it)): `state` lists every reported
run, `run <id>` shows one, `reject <id>` takes it off the board, and `ban <steamId>` blocks a player (their runs leave
the boards and new ones are refused). For the dailies before 2026-10-09, which the app timed itself: for a reset the
app missed, `resets <id>` finds the resets in the run's trace and `fix-run <id> <resets> [stage clock of each]`
corrects its resets, total and splits (`--dry-run` first).

**No longer checked.** The server used to re-run the app's rules on the trace and test whether it behaved like a car
in the game (`server/src/realism.js`). Those checks refused or flagged real runs, so they were removed. The server no
longer checks:

- that the trace starts at the start, reaches the finish at the reported time and passes the checkpoints;
- that the clock only goes forwards, with no gaps;
- that every jump in the trace was counted as a reset;
- the stage clock against the PC clock and the game's physics steps;
- speed, acceleration, braking, cornering, throttle, rpm and steering against what a car can do;
- section times against the other drivers' and the driver's own best;
- the air temperature against the other drivers' (the game draws it anew each session, so the same set-up differs);
- that the game ran under the Steam account that signed in.

Runs those checks flagged keep their UNDER REVIEW mark.

What this catches: restarts, resets, shortcuts, the wrong car or stage and joining late, judged by the same rules
for everyone. What it can't catch: a modified app or a made-up upload, because the server takes the app's word for
it. The viewer and the reports exist so people can spot those.

## Folders

```
client/              the Windows app (Python 3.13 + tkinter, built with PyInstaller)
  acr_daily/         telemetry, judge, route, recorder, saveslot (game save), rallyweekend (the game's Rally Weekend
                     set-up and results in its save), leagues (league events in the save), autodrive, ghosts,
                     widgets, api, app (UI), leagueui (its LEAGUES view)
  tests/             unit tests (judge, standings, names, save slot, route recorder)
  build.bat          builds dist/ACR-Daily.exe with the server URL baked in
  make_icon.py       draws the app icon (acr_daily/icon.ico) and the header logo (acr_daily/logo-*.png)
server/              Cloudflare Worker + D1 + R2
  src/               index.js (API + auth), validate.js (stores runs), realism.js (splits, sections,
                     temperatures), cars.js, conditions.js, stages.js (menu names), week.js, steam.js,
                     traces.js (run traces), cache.js (kept boards, weeks, stats), discord.js (the Discord bot),
                     leagues.js (leagues: rules, standings, seasons), leaguesapi.js (their API), leaguediscord.js (their Discord posts); pages: site.js, viewer.js, statspage.js, weekpage.js,
                     leaguepages.js; logo.js (logo + favicon)
  test/              *.test.mjs (node --test), e2e*.py (against `wrangler dev`), fixtures/ (real runs)
  schema.sql         full schema; migrations/ upgrade older databases
tools/admin.py       routes, pool, schedule, reject runs, ban players, pack old traces
routes/              reference routes (Alsace Obersteigen, Alsace Forêt, Wales Afon Bidno)
brand/               the logo and app icon as SVG
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

:: local server with a local database (--local-upstream: without it the Worker sees every request as one to acrdaily.com,
:: the route in wrangler.toml, and a Steam sign-in comes back to the real site: "Sign-in expired")
copy .dev.vars.example .dev.vars
npx wrangler d1 execute acr-daily --local --file=schema.sql
npx wrangler dev --port 8790 --ip 127.0.0.1 --local-upstream 127.0.0.1:8790
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
- **Free tier.** ACR Daily is built to stay on Cloudflare's free plan with about 100 drivers a day:
  - *100,000 requests a day.* While driving the app sends its position every 5 s (the other drivers come back in the
    same answer); otherwise it asks for the boards every 2 minutes with the game running, 5 without, and the rest every
    10–60 minutes. That is roughly 400 requests per driver per day. The pace is set on the server (`LIVE_SEND_S` ...
    in `server/wrangler.toml`): if the daily count gets close to the limit (dashboard > Workers > acr-daily > Metrics),
    raise them and deploy; the apps follow within 10 minutes.
  - *100,000 rows written, 5 million read a day.* Boards, the week and the stage stats are built once and kept
    (`server/src/cache.js`), live positions are deleted 2 minutes after their last update, and the stats page uses
    each run's small profile instead of its trace.
  - *10 ms of CPU a request.* Nothing reads more than two traces at once.
  - *500 MB of database.* Only counted runs keep a trace, gzipped (~50 KB a run); after 14 days only each daily's
    top 3 do (`TRACE_DAYS`, `TRACE_TOP` in `server/src/traces.js`). With 100 counted runs a day the database is about
    300 MB after a year.
  The paid plan ($5 a month) lifts all of these; with it an R2 bucket can hold the traces (`server/wrangler.toml`).

## Licence and disclaimer

ACR Daily is released under the [MIT licence](LICENSE).

It is a fan-made community project and is not affiliated with, endorsed by or connected to Supernova Games
Studios, Kunos Simulazioni, 505 Games or Valve. *Assetto Corsa Rally* and all car, stage and brand names are
trademarks of their respective owners. The app only reads the telemetry the game publishes, edits the
player's own single-stage and Rally Weekend set-ups in their save file (with a backup) and reads the game's own
results from it; it does not modify the game.
