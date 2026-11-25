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
