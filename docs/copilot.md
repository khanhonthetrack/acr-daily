# COPILOT: the daily for two

A driver and a co-driver drive one stage together. It is EVENTS' third tab in the game, beside DAILIES and TIME TRIAL.

## How it plays

- Each day has one stage, car and weather, picked only from stages that have the game's own pacenotes. They stay
  hidden (a "?") until you have driven it, as driver or co-driver. Hardcore Mode is on.
- You can drive it once a day as the driver and once as the co-driver. A try is used as the stage starts. A start that
  never sends a result is a DNF after 90 minutes; a driver who leaves is a DNF at once.
- A lobby: pick your role, public or private (private lobbies get a 6-letter code and are never listed). The other
  player joins, both press READY, and the stage starts for both:
  - the driver's game goes to the stage, and the run is judged and sent as a time trial run is (the game's own time
    and penalties);
  - the co-driver's game goes to the same stage and watches the driver's car from inside it (no broadcast delay), with
    the stage's notes on the right. Up/Down moves one note, Left/Right moves five (keyboard, wheel or pad).
- Voice: push to talk (a key, or a wheel/pad button set in the page), open mic, or off. Headphones are recommended:
  there is no echo cancelling.
- The game's own co-driver is switched off for both while a crew's stage is on. The game mod reports it. If it is on
  at the driver's start, the run doesn't count (a DNF for the crew). If it comes back on during the stage for 3 s, it
  is a DNF.

## Where things are

| Part | File |
|---|---|
| Server: day pick, lobbies, tries, runs, board | `server/src/copilot.js`, migration `0048_copilot.sql`, tests `server/test/copilot.test.mjs` |
| The game's pacenotes (58 stages) | `server/src/pacenotes.js`, made by `tools/gamefiles/pacenotes.py` (run it again after a game update) |
| App: lobby, start for each role, notes cursor | `client/acr_daily/copilot.py` |
| Direct link between the two PCs (STUN + UDP hole punching, relay fallback) | `client/acr_daily/copilotlink.py` |
| Voice (winmm, IMA ADPCM 16 kHz, 8 KB/s) | `client/acr_daily/voice.py` |
| In-game page and the notes over the stage | `client/acr_daily/ig_copilot.py` |
| Driver's run: the time trial pipeline under `CP_SLOT` (never shown as a time trial) | `client/acr_daily/ttui.py`, `app.py` |
| Game's co-driver off, reported as `C <1/0>` on the camera line | `mod/ACRDailyGhosts/Scripts/main.lua` `codriver_off`, `appui.lua` |
| Relay: crew voice messages (`x`) in a `cp:<lobby>` room | `live/relay.py` |

## Ping

The lobby's server only introduces the two apps. Each asks a STUN server (Cloudflare's, Google's) for its public
address and puts it on the lobby; then both send to each other until one gets through. From then on, the car and the
voice go straight between the two PCs, so two players in Japan stay in Japan. If no direct path opens within 8 s
(strict routers, carrier NAT), the voice goes through the live relay and the car goes through it as usual.

## Switching it on

1. Apply migration `0048_copilot.sql` to D1.
2. Set `COPILOT_FROM` in `wrangler.toml` to the first day, then deploy the server.
3. Update the relay on the Pi with the new `live/relay.py` (only needed for the voice fallback).
4. Release an app with these changes (the in-game tab, link, voice and mod).

## Not checked yet

- Nothing has been run in the game. Still to check: the mod switching the game's co-driver off (class names come from
  the game's .usmap), the co-driver's in-car view and the notes overlay, push to talk from a wheel button.
- Voice has been tested with stand-in microphones and speakers only, not real devices.
- The direct link has been tested between two apps on one PC, not across the internet or real routers.
- Note distances count from the stage's first note, not from the start line.


## CASUAL (second mode, server/src/casual.js, migration 0050)

A lobby of up to 4 for any day, on COPILOT_FROM like CODRIVER. The host is the driver and picks a stage (any with the game's
pacenotes: the dailies' pool), car, weather, time of day, up to 3 languages (ISO 639-1; `LANGS` in copilot.js) and public or
private (6-letter code). Up to 3 co-drivers join and press READY (informational). The host presses START at any time, alone
too; only members present then take part, later joins are refused. No results, board or tries. An open lobby is closed after
3 h, a started one finished 3 h after its start (`CX`, cron `casualTick` and lazily on the lists). One lobby at a time per
player (creating or joining leaves the others). Languages were added to CODRIVER lobbies too (`langs` on
`POST /api/copilot/lobbies`, returned in its lobbyOut).

Tables: `casual_lobbies` (token, code, host, track, car, weather, time, langs, state open|started|finished|closed),
`casual_members` (lobby, steam id, seat 0..3, ready; seat 0 = host; a freed seat is given to the next joiner),
`casual_signals` (lobby, from, to, data: one row per ordered pair for the apps' direct voice links).

API (JSON, signed in like /api/copilot; 404 when off):
- `GET /api/casual/options` -> `{stages:[{track,stageName,menuName,rally,lengthM}], cars:[{id,name,cls}], weather:[{code,label}], times:[{code,label}]}`
- `GET /api/casual` -> `{on, signedIn, lobbies:[public, open + started, newest first, max 40; mine incl. private], lobby: mine|null}`
- `POST /api/casual/lobbies {track,car,weather,time,langs,private}` -> `{ok, lobby}`
- `POST /api/casual/join {id?, code?}`; `GET /api/casual/lobbies/:id`; `POST .../ready {ready}`; `.../start`; `.../leave`;
  `.../signal {to, data}` (data a string or JSON, 2000 characters at most)
- lobbyOut: `{id, private, state, created, started, max:4, langs, stage, car:{id,name,cls}, weather:{code,label}, time:{code,label},
  host, members:[{steamId,name,avatar,country,role,seat,ready}], count, free}`; for a member also `me`, `code` (private),
  `notesUrl` (`/n/<token>`), `signals` (`{<from steamId>: data}` for me); when started also `ch` (the stage for the app:
  id `cx:<lobby>`, kind `casual`, mode weekend, hardcore false, route) and `notes`.

Pacenotes page for people without the game: `GET /n/<token>` (HTML, no login, phone-first, dark, noindex) and
`GET /api/n/<token>` -> `{stage, car, notes}`. The token (12 chars) is made with the lobby; valid while it is open or started
and 2 h after it ends, then 404 (a small friendly page). The page's script is a plain string (src/casualpage.js).


## CASUAL and the crew, in the app (25 Nov 2026)

CODRIVER has two tabs in the game: CODRIVER DAILY and CASUAL (`ig_copilot.py` hosts both; `ig_casual.py` is CASUAL's page).

- **CASUAL** (`client/acr_daily/casual.py`, a `Copilot` subclass): the host (the driver) picks stage, car, weather, time, up to
  three languages and public / private; up to 3 co-drivers join; START (alone is fine: then the game's own co-driver stays on).
  No results. The driver's stage runs under `CP_SLOT` as the daily crew's does (challenge id `cx:<lobby>`, never sent);
  the co-drivers WATCH from the passenger seat with the notes. Relay room `cp:<1000000 + lobby>`.
- **Languages** show as flags (a country for each language: `casual.LANG_FLAG`) in the lobby browser, for both modes; the daily
  lobby's host picks them too.
- **Passenger seat**: the co-driver's camera is the `seat` shot (mod `main.lua`): the driver's eye point mirrored across the car's
  centre line, the co-driver's own figure hidden, the driver's shown. Not yet seen in the game.
- **Voice** (`voice.py`, `crew.py`): a microphone by name and its volume in SETTINGS › CODRIVER VOICE (with a TEST level bar);
  each speaker has a seat (0 driver, 1..3 co-drivers) and their own queue, mixed; the driver is the hub (one `copilotlink.Link`
  to each co-driver) and passes a co-driver's voice on to the others. Small speaker icons on the side of the stage (one dot and
  name each, lit while that person talks, "You" while you send) show who is heard.
- **Notes for someone without the game**: the lobby shows a QR code (`qrcode_min.py`, no packages) for `https://acrdaily.com/n/<token>`,
  a phone page with this lobby's stage notes (`server/src/casualpage.js`). Chosen over one big notes library on the website because
  the right stage is already picked (scan, read), it works for a private lobby, and nobody has to find the stage.
- **The daily crew's stage UI**: the driver gets the dailies' timer (start line: "Good luck! One go", running: the gap to the leader
  worked out from the leader's splits, split standings under the timer, finish: "P2 OF 5 CREWS" / DNF); the co-driver's overlay shows
  the driver's clock, gap and finish through the link's status line (`Copilot.status_line`).

Not checked in the game: the passenger-seat camera, the speaker icons over a real stage, a mic picked by name on real hardware,
three links at once across real routers.


## Checked in the game (26 Nov 2026, local server + local relay, a recorded driver replayed as the host)

- CASUAL: set up (stage picture, car, weather, time, languages by name with flags), the lobby browser with flags and
  seats, a co-driver joining (live), START: the driver's game to the Service Park, the start line with the timer's strip
  ("Good luck!"), the speaker names on the left, the game's own co-driver off (`C 1`) alone or not.
- The co-driver: the game to the Service Park on the host's stage, the notes beside it, the camera in the **passenger
  seat** of the host's car (`W seat`), the co-driver's own figure hidden, the driver's arm and the notes book in view.
- The host leaving mid-stage: WATCH over, the game back to its main menu (the mod's cmd `menu` = the game's flow
  `FSM.Flow.Exit`; `FSM.Flow.ExitToMain` did nothing from a stage), ACR DAILY open on CASUAL saying the host left.
- The phone page: the note on now as an orange bar in the middle, NEXT / BACK / JUMP.
- Found and fixed then: the QR drawn red (a grey PNG: now RGB), speaker dots of no size, the voice line twice, "Good luck!"
  twice on the start line.
- The relay (Pi updated 26 Nov, backup `relay.py.bak-20261125`): a crew's own room (`{"t": "crew", "room": "cp:<n>"}`)
  so the voice through the relay works in the menus too, 260 crew messages a second (a driver passing on 3 co-drivers).
- The direct link: one dual-stack IPv6 socket (IPv6 addresses offered too), 4 STUN servers, the next 3 ports of a
  router's public one tried.

Not checked: real voice between two PCs, a real second player, the daily crew's leader gap while driving (the test car
would not move from the keyboard), Windows' microphone question: it comes up over the game the first time a lobby's voice
starts (the packaged app asks once for ACR-Daily.exe).

**The co-driver's fuller overlay (26 Nov 2026, checked in the game):** under the notes, WATCH's broadcast parts for the
driver's car: the dial (speed, revs, gear, brake and throttle) and the driver bar (the stage across with its splits,
where the car is, the driver, the car, the time; daily: the gap to the day's #1 from the leader's splits and the place it
would have, a split's time as it is passed). The notes' top line keeps the start ("Good luck!"), the finish and a DNF.
