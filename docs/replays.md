# Replays

Every run is kept on the driver's PC as a replay. A replay can be watched again in the game, sent to the server (a code), shared (a public page), and it can prove a finish the game lost, which takes the DNF back without asking the admin.

## Why not the game's own replay

The game records a replay in memory (the Replay button after a run). But:

- there is no way to save one in its menus;
- the format is Kunos' own, and only the game can read it;
- nothing in it can be checked by the server.

So ACR DAILY keeps its own: the car's pose and dash from the telemetry the app already reads. It plays back in the game through WATCH's machinery (a real car moved by the mod, the TV director's cameras), and on the website on the stage's map.

## The file

The file is `%APPDATA%\ACR Daily\replays\*.acrreplay`: gzip'd JSON.

| part | what |
|---|---|
| `head` | Driver, kind (`daily` / `event` / `tt` / `practice`), ref (`2026-11-26/1`, `event:<id>:<stage index>`), track, car, the game's stage / car ids, status, clock at the finish (`finMs`), resets, the game's penalty (read by the mod at the line and on the results screen). |
| `rows` | `[clockMs, x, y, z (cm), heading, pitch, roll (1e-4 rad), km/h×10, gear, rpm, throttle, brake (0–1000), steering (−1000..1000), airborne]`, one every 100 ms of stage clock. Ints only. A 5-minute stage is about 55 KB. |
| `live` | `{rid, nonce, commits: [[count, hash]]}` when the server followed the run (below). |
| `sig` | Ed25519 over `sha256("acr-replay/1\n" + canon(head) + "\n" + sha256(rows) + "\n" + rid)`. Made with the PC's own key (`replay-key.json`, created once; pure Python, `ed25519.py`). |
| `stamp` | The server's word once it checked the replay: `{code, verdict, at, mac}`. |

`canon` is `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True)`; the server has the same function (`src/replays.js canon`). `server/test/fixtures/replay-py.acrreplay` is made by the Python code and checked by the JS tests.

Kept: the newest 100 (SETTINGS > Replays: 25–500, on/off). Starred replays and ones received from others are never dropped. A run under way is written to `recording.part` every 5 s, so a crash keeps it (`recover()` at the next start).

## The proof: what the server checks

1. **Begin.** At a counted run's start (a daily that counts, an online rally's stage), the app sends `POST /api/replays/begin` with its public key. The driver is signed in. The server gives a run id and a nonce, keeps the key with the driver, and keeps its own clock at that moment.
2. **Commits.** Every 10 s while the stage runs, and at once at the finish line, the app sends the hash of the rows so far, chained from the nonce: `h₀ = sha256("acr-replay-chain|rid|nonce")`, `hₖ = sha256(hₖ₋₁ + "\n" + rows since)`. The server keeps each commit with its own clock. They are taken in order only, once each, for 4 hours.
3. **Upload.** The server recomputes the chain from the file's rows and checks:
   - it matches every commit;
   - no commit's stage clock is ahead of the server's clock since the begin (5 s slack);
   - the finish is inside what was committed at the line;
   - the signature matches the key the run began with;
   - the head matches the run (driver, track, car, ref).
4. **The road.** The rows are checked against the stage's route:
   - it starts at the start and finishes at the end;
   - at least 98 % of the checkpoints are passed;
   - no more than 3 s spent over 30 m off the road;
   - no cuts: the road's distance covered more than 30 m faster than the car moved in 5 s, while off the centre line;
   - no movement faster than 330 km/h;
   - the jumps (respawns) agree with the resets counted.

Verdict:

- `refused`: the signature, the chain, the timing or the head failed.
- `clean`: everything holds.
- `review`: everything else, such as no route, not followed live, or a flag on the road.

What this proves: the replay was recorded while the stage ran, by this driver's app (the key they signed in with), and it was not edited afterwards or sped up. And it is a clean drive of the whole road.

What it can't prove: that the PC itself is honest. A determined cheater can modify the open-source app to feed it a fake run in real time. That is the same bar the official result already has (the save file is on their PC too). The replay is checked more strictly than the normal result, and every DNF taken back stays on the admin's and stewards' lists with the replay to watch.

## DNFs taken back on their own (see also "Every way a finish gets lost" below)

`GET /api/replays/wanted` tells the app which replays the server wants. The app asks at start, 40 s / 2.5 min / 6.5 min after a counted run, and every 10 min.

- **A daily.** The run is a DNF whose result the game lost ("the game closed…", "no official result…", "restarted from the results screen…"), with the same stage clock as the replay's finish (±1.5 s). If the replay is clean, the admin's reinstate is done by itself: the clock plus the game's penalty, or 10 s a respawn if the penalty is unknown. The run gets the flag `reinstated by replay <code>` and stays on /admin's DNF list.
- **An online rally** (championship, rally, cup, 1V1). The entry is a DNF on that very stage, and this is the driver's first start of it. If the replay is clean, the stewards' "time" is done by itself, by "replay check": the finish plus the penalty. The entry goes on to the next stage, and the app refreshes so CONTINUE works. Everyone sees the decision on the event page. An unknown penalty with resets goes to the stewards instead.
- At most 5 DNFs taken back a week a driver. More, or a replay that isn't clean, goes to review: /admin (Replays sent), and the rally's owner gets an inbox notice with the link.

## Every way a finish gets lost, and what happens

| What went wrong | What the replay does |
|---|---|
| **The game hangs on its loading screen, or closes, after the finish.** DNF "no official result", "the game closed…", "left from the results screen…" | The finish was sent at the line. The server asks for the replay and the DNF is taken back on its own. |
| **The game freezes at the finish line** before the app saw the finish. DNF "lost the game" / "stopped (clock frozen…)" | The app keeps a last row at the exact clock where it stopped. The server checks the committed rows reach the road's end with every checkpoint passed, then takes the DNF back. |
| **The connection drops mid-stage** | The begin and the hashes go out in order from their own thread and are retried until they get through. If a reply is lost, the server says how far it has got (`409 {have}` or `GET /api/replays/run/<rid>`) and the app carries on from there. Hashes that arrive late still count. |
| **The connection is down at the start** | The begin is made late and the server follows the run from that clock. Within a minute of the start the DNF is still taken back on its own; later than that, it goes to review. |
| **The app is closed or crashes**, with hashes unsent | At the next start (and on every poll), `catch_up` sends them from the replay file. A run saved before its begin got through gets the server's part afterwards, and its file is signed again. A counted run never begun is begun from its file; it is followed only from its end, so it goes to review. |
| **The finish reaches the server more than 3 min late** (connection down through the finish) | The checks can be clean, but it goes to review, never back on its own: its rows could have been made in the meantime. The stewards or admin are told. |
| **No result ever comes from the app** (crash past the line, result lost on its way) | 30 min after the start, if the finish is on the server and nothing for that run is queued on the PC (results queue, rally queue, waiting for the game's time), the replay stands in. For a daily, a run is made and reinstated. For an online rally, the stage time is set and the rally goes on. |
| **The result fails to send** (server error) | Unchanged: the app's queues retry. Once they get through, the app asks the server about replays at once. |
| **A DNF the driver earned**: restart after the finish, settings changed, disqualified, retired by the stewards, missed | Never taken back (whitelist of reasons). |
| **A second attempt** | Only the first start of a stage or daily can be proven; a later attempt's replay never stands in. |

The car as it crossed the line (the mod's finish-line damage) is in the replay as `head.damage`, stored as life points × `damageScale`. When an online rally's stage is taken back, that damage is kept on the entry. CONTINUE then goes on from the next stage with that car (`leagues.recover`, `drive.lua`).

Tested:
- Server unit tests: 15.
- App unit tests: 22. These use a fake server whose connection can go down and whose replies can be lost.
- End to end (`client/tests/e2e_replays.py` with `server/test/harness_replays_e2e.mjs`): the app's real code against the Worker's real code, fed a real recorded run (Wales Afon Bidno, Mini) at 10×. Five scenarios, 22 checks.
- In the game, on 26 Nov 2026: after a replay took back SS1, CONTINUE set up SS2 in the running game. On the start line the car read Engine 72.5 / GearBox 80 / Radiator 60, exactly as recorded.

## Stewards and admins

- On an event's page, the stewards' form has **Ask for the replay** (driver + stage). The driver's app sends it by itself, or asks first (SETTINGS > Replays). The steward gets an inbox notice with `/r/<code>`. The decision "SSn replay asked for" is listed. If the driver's app has no replay of that stage, the steward is told.
- **Replays sent** on the event page lists every replay sent for it.
- A replay sent for an event is private to its driver, the admin and the event's owner and admins.
- /admin > DNFs > **Replays sent**: each one's verdict, what it did, and the notes. Opened in the same tab, the page uses the admin key from that tab.

## Sharing

- In the game, **REPLAY** (on HOME, in PROFILE's place, and in the header):
  - the list of replays (all / counted / starred / sent to me);
  - the selected one's time, checks and stats;
  - **WATCH IN THE GAME**;
  - **SEND** (a private code);
  - **SHARE** (public, link copied);
  - STAR, DELETE;
  - **OPEN A CODE** (someone's replay);
  - **OPEN FOLDER** (put a received file in `replays\import`).
- A replay of a stage that still counts can't be public until it no longer does: a daily after its day, a rally after it closes. So nobody's line can be copied while it counts.
- `/r/<code>` on the website:
  - the run on the stage's map: play, 0.5×–16×, scrub, click the map to jump;
  - speed and throttle/brake under it;
  - the checks, with the cuts circled on the map;
  - **race it against another replay** (its code): both cars, both speed traces, the gap at the same place on the road;
  - download, copy link, make public/private.
  
  A public one's link shows the driver, stage and time where it's posted (Discord, social media).

## Watching in the game

`replayplay.ReplayDriver` is a `LiveDriver` with the viewer's own clock. While a replay is watched, `Watch.drivers()` returns only it. `ghostui` writes it to the mod like a live driver, plus a `wrate <rate> <seq>` line. The mod's path clock runs at that speed (`main.lua play_clock`), so 0.25×–8× and pause stay smooth.

Spectator menu (Select): REPLAY play/pause, SPEED, camera, graphics, splits. Left/Right outside the menu: 10 s back/on.

## Not done / to check

- Not tried in the game: WATCH IN THE GAME on a real stage, the mod's `wrate`, a counted run's begin/commits against the live server.
- The new strings are in English only (the translation pass hasn't been run).
- Server: migration `0051_replays.sql` must be applied before deploying. Replays are stored in D1 (1.5 MB max a file). Shared ones are kept 90 days, proofs 365 days, 40 files a driver.
