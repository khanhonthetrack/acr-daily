# ACR Daily ghost cars in the game (UE4SS mod)

With this mod the other drivers on your stage are real cars in the game, live: their own car, lit like the rest,
hidden behind trees and crests, in every camera. The ACR Daily app decides where they are (from the live relay)
and draws their names above them.

How it works: the app writes the drivers' positions and cars to `%APPDATA%\ACR Daily\ingame-ghosts.txt` about 60
times a second; `ACRDailyGhosts/Scripts/main.lua` spawns their car there (the game's class of it, loaded once;
yours if it is not known), with its physics and collisions off so there is nothing to hit, and moves it every
frame. A car without physics never moves its own wheels, so the mod sets them each frame too, where that car's
wheels sit at rest (`wheels.lua`, measured in the game for all 18 cars). The same car as yours also seats its crew
like yours; another car's crew is hidden. It writes the game's camera to `ingame-camera.txt`, which the app uses to
place the names exactly. Checked: a Hyundai i20 N driver shown as a Hyundai while driving the Skoda.

## The game's mode

`main.lua` `race_mode`: the game makes a race event for each loaded stage (its game state's
`RaceEventManagerComponent.RaceEvent`): a Rally Weekend's is `BC_RaceEventRally_C` with a
`RaceEventRaceSettingsRallyWeekendComponent`, a Single Rally Stage's `BC_RaceEventSingleEvent_C`, Free Practice's
`BC_RaceEventFreePractice_C`, Time Attack's `BC_RaceEventTimeAttack_C` (all four checked in the game, 2026-11-19, from
the Service Park / the session's start on). The mod writes it on its camera line twice a second
(`M weekend` / `single` / `practice` / `timeattack` / `championship` / `other`; `none` in the menus, where it keeps
writing), and the app counts a daily's or a
time trial's run only in `weekend` (`client/acr_daily/app.py` `game_mode`): the game's save can't tell the mode before the
stage is finished.

With it, `read_settings`: the race's settings as the game runs them (its race event's settings component; probed
2026-11-19, `docs/hardcore-and-assists.md`), `S <rdcwfpht> <seq>`, one digit each: manual respawn, damage on,
collisions, wear, mechanical failures, penalties, Hardcore, tyre damage (`S 11110102` on a daily as the app sets it
up). And `read_aids`: the player's driving aids, `A <gatbc> <seq>` as the race applies them (their race participant,
the one whose ID is the player state's `ParticipantId`: gearbox, ABS, TC, starting handbrake assist, clutch), and
`V <atgc> <seq>` as the car's dash shows them (the UI's race viewmodel: ABS, TC, gearbox, clutch; switched in the car
too).

The rule of thumb (2026-11-19): before the start the app checks the game against the event (a daily, a time trial
stage, a league stage) and says in red what's wrong, and that run won't count: settings changed in the game's menu
(`app.settings_changed`, `leagues.live_changed`), driving aids on that the event forbids (its rules' `assists: off`,
`leagues.aids_broken`). During a stage anything of it that changes is a DNF (`app._watch_run`,
`leagues.changed_during`), said on the start line before. Without the mod the game's save tells the settings once the
stage is over, as before. Checked in the game: `A 01101` / `V 1101` on a daily; TC switched off through the game's own
`OnRep_DrivingAids` showed in both, "traction control changed during the stage".

## The displays in the game

`hud.lua` (with its building blocks, `hudkit.lua`), run by `main.lua` every frame: always from 0.1.5.50 (before, with
SETTINGS › Timer › "Drawn by the game" on; "Show the timer" and the displays' own switches still say what is shown;
the place in SETTINGS › Timer › "Place in the game"), the app writes what its displays say to
`%APPDATA%\ACR Daily\ingame-hud.txt` (`client/acr_daily/ingamehud.py`: display by display, its words and colours, the
file kept open as the ghosts' one), and the mod lays them out as the game's own widgets, in the game's look. While the
mod runs (its camera file moving on), the app's windows over the game stand down: nothing sits over the game
(FreeSync / G-SYNC stay on), and in VR UEVR shows them on its UI plane like the game's HUD.

- **ACR strip**, docked under the game's own timer block and its PENALTY row (which it covered at first; its HUD keeps
  to the middle 16:9 of the screen, measured on a stage at 3440x1440): ACR Daily's red D (the app's `dcar-128.png`,
  from `client/make_icon.py`, copied to `%APPDATA%\ACR Daily\hud\`), whether the
  run counts (LIVE, READY, NOT COUNTING, FINISHED...), the place at the last split, and always a second row (the gap to
  P1 and which way it goes, what to do, or good luck / good job). No second race clock:
  the game's is right above it ("Our clock in the game" adds ours, for a driver who hides the game's HUD). Not in the
  game's menus (the mod's mode `none`): the strip and the ticks are a stage's.
- **Note** and **split board** under it: save your time (with a bar while it comes), this run counts / won't, the
  split's standings, rows sliding in one after another.
- **Start board** (RANKED), top middle under the game's km bar: the series' logo (a PNG the app copies to
  `%APPDATA%\ACR Daily\hud\`, loaded with `KismetRenderingLibrary.ImportFileAsTexture2D`), one word, the time left
  counted down here every frame with a draining bar, one line, three of the queue (the turn, you, the next), the rule a
  start on red breaks. The mode's colour fades in, the word pops; on your turn the edge breathes, the last 5 s pop (and
  the app beeps).
- **Ticks** under the game's km bar: the drivers on the stage now (their colour), the ghosts (hollow), the splits;
  only with the stage strip display on.

- **Cards that take keys**, under the strip: the comment on a run and the next daily / time trial. **F8** DRIVE the
  next one (it restarts the game; a stake the next daily needs is said on it, and the key is the yes), **F9** write a
  comment (a box in the game takes the keyboard: Enter sends, the close key or Esc doesn't; the game gets none of the
  letters typed: checked, "E" didn't switch its tabs), **F10** close; other keys can be picked in SETTINGS › Timer ›
  Keys in the game (each card row says its key and its action; F1 to F12 are caught). Caught by
  UE4SS (`RegisterKeyBind`), said back to the app in `%APPDATA%\ACR Daily\ingame-actions.txt`
  (`ACRACT <session>.<n> <card id> <action> [<text>]`, `ingamehud.Actions`), which does the card's button; meanwhile
  the cards' windows are put away. The strip names the game's mode too (RALLY WEEKEND in green, another in orange).

A running clock comes as ms at the app's moment, mapped onto the mod's clock as the ghosts' poses are: smooth at any
frame rate. Checked in the game (2026-11-19): what UMG can do from UE4SS Lua here (rounded panels with an outline,
pictures from files, the game's font in its five weights with Japanese and Chinese through its own fallback,
progress bars, blur, shear, opacity / position / scale), every display and state at the main menu, and the strip, the
ticks and the start board on a stage, lined up with the game's own HUD. Not yet in a headset.

Working on it: while `%APPDATA%\ACR Daily\hud-dev.on` exists, `hud.lua` and `hudkit.lua` are loaded again when they
change on disk (their widget taken off first), without restarting the game. UE4SS's own hot reload crashed the game.

## Install

The app does it, always from 0.1.5.50 (its displays are drawn by the game, and the mod tells the game's mode): it
puts UE4SS and this mod into the game's `acr\Binaries\Win64` folder (`client/acr_daily/modinstall.py`, `app.IN_GAME`;
before 0.1.5.50 only with ghost cars' "Real cars in the game" or "Drawn by the game" on, and it took them out again
when both were off). Ghost cars on or off now only says whether the mod draws them. UE4SS comes from `ue4ss/UE4SS_v3.0.1-1208-g6f8dc3cc.zip` here (also on each
release), checked against its SHA-256; the mod files come inside the app. If you already have UE4SS, only this mod
and its line in `mods.txt` are added. Windows won't swap a DLL the game is using, so some steps wait until the game
is closed, and the cars show up the next time the game starts.

By hand (Windows, Steam):

1. Unzip `ue4ss/UE4SS_v3.0.1-1208-g6f8dc3cc.zip` (UE4SS, MIT licence; the experimental build for Unreal 5.4) into
   `...\steamapps\common\Assetto Corsa Rally\acr\Binaries\Win64\` (`dwmapi.dll` and the `ue4ss` folder next to
   `acr.exe`).
2. Copy `ACRDailyGhosts` into `Win64\ue4ss\Mods\` and set `ue4ss\Mods\mods.txt` to start only it:
   ```
   CheatManagerEnablerMod : 0
   ConsoleCommandsMod : 0
   ConsoleEnablerMod : 0
   SplitScreenMod : 0
   LineTraceMod : 0
   BPML_GenericFunctions : 0
   BPModLoaderMod : 0
   ACRDailyGhosts : 1
   Keybinds : 0
   ```
3. Nothing to tick in the app (0.1.5.50 on): it uses the mod as soon as the game runs it.

To remove it by hand: delete `dwmapi.dll` and the `ue4ss` folder from `Win64`.

Smooth: the app plays each driver back a little in the past (as far as their positions arrive late), along a smooth
curve through them, and writes each car's speed and the moment it is for (its clock) with its pose. The mod moves
every car every frame (not on a timer) from that moment on at that speed, and eases out any small difference when
the next pose comes instead of jumping (`livelink.py`, `ghostui.py`, `main.lua`).

## Notes

- A ghost's dash screen (its `GaugeComponent`) is stopped when it appears: while one ticked, YOUR car's gear screen
  on the dash went black (any ghost car with one, seen 2026-11-10); it came back as soon as the ghost's stopped.
- The cars are moved, not teleported, each frame: then the game knows how they move (motion blur, DLSS / TAA,
  frame generation), as for any other car.
- The two files are kept open by the app and the mod for good and overwritten in place, each update's number on every
  line (a half-written one is skipped): opening a file just changed costs several ms each time (Windows' virus
  check), and the game thread went from 5 to 10 ms a frame with the app's 60 updates a second.
- Many cars (measured with 10 moving round in front of you, 2026-11-10): each ghost is trimmed when it appears (its
  own update, sound, dust and smoke, damage, crew animations and the update of its ~40 models stopped; its lights and
  suspension go on), its crew and inside drawn only within 40 m, and the app sends the nearest 10 at most. The game
  thread's time a frame: 22.9 ms before, 8.4 ms after (4.5 ms without them).
- Making a ghost car costs the game about 45 ms (a hitch). Ghosts that go are hidden and kept (10 at most, 2 minutes)
  for the next car of their model, and while you stand still (waiting at the start) the models the app says are on the
  stage ("warm" lines) are made ahead. 30 drivers setting off past you 2 s apart: 30 hitches before, 10 (made while
  waiting) after; 10 kept cars cost about 1 ms a frame.
- 30 on one stage (stress test 2026-11-11, `live/relay.py` on the Pi): the relay sends each driver only the 12 nearest
  within 600 m in full, the others once a second: 0.8 MB/s out instead of 1.8 (50 drivers: 1.4 instead of 3.8), 14 %
  of a Pi 5 core.
- `%APPDATA%\ACR Daily\ghost-trace.on` (for testing): while it exists, the mod writes each frame's cars to
  `ghost-trace.txt` (frame, its clock, X, Y, Z, yaw).

- Keep UE4SS's hot reload off (`EnableHotReloadSystem = 0`): reloading while the game runs left stale callbacks
  that crashed it in testing.
- Never switch a ghost car's input off (`SetInputEnabled(false)`): the cars share one input set-up, and it switched
  off your own car's throttle and steering.
- The mod changes nothing in the game's files or saves. The game has no anti-cheat (only Epic's online services
  library), but its online features may not like a modded game: use it at your own risk.
