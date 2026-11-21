# ACR DAILY inside the game (0.2, private build)

Branch `ingame-app`, from v0.1.7. The whole app in the game: a small launcher (settings + PLAY) starts the game, and
the game's MULTIPLAYER page has an ACR DAILY tile that opens the app's pages, drawn by the game.

## Feasible: checked in the game (ACR 0.7, UE 5.4, UE4SS 3.0.1), 20 Nov 2026

- **The tile.** On MULTIPLAYER (the user's call: it's where online play is). MULTIPLAYER is `WB_RaceLayout_EA_C`,
  the third page of `WB_SelectWidget`'s `OptionSwitcher`; under SEARCH LOBBIES and CREATE LOBBY, its third place
  `FreePracticeContainer` (532 x 175) is empty and hidden. A new `WB_MainMenuListButton_C` (made with
  `WidgetBlueprintLibrary.Create`) goes in it, so the game's layout is kept. Take the live menu widgets by their
  `/Engine/Transient` path: `FindFirstOf` can return the blueprint's template. It is the game's own tile, so it has the game's
  red focus frame, hover and sound. Its picture is set on `ButtonImage` once the game has built the tile (alpha 1;
  the game leaves it at 0.2), and its words with `SetButtonText`.
- **A click on it.** `RegisterHook("/Script/CommonUI.CommonButtonBase:HandleButtonClicked")` sees the mouse click,
  and the tile's `MenuButtonId` is `ACRDaily`. Enter on the focused tile doesn't go through that function, so the mod
  watches Enter itself (`RegisterKeyBind`) while the tile has focus. **Not yet checked: a game pad.**
- **The pages.** A UserWidget made from nothing (as hud.lua) at z 400 over a blurred, darkened game, with the game's
  menu (`WB_MainMenu_C`) collapsed under it. Plain UMG `Button`s work by polling `IsHovered` / `IsPressed`; a press let
  go over the button is a click. `ScrollBox` scrolls with the mouse wheel. Typing works with `EditableText` (hud.lua,
  F9 comments). Esc closes the pages and the game doesn't act on it.
- No web view in the game (no CEF in its files), so pages are drawn with UMG, not HTML.

## How it works

- `client/acr_daily/ingameapp.py`: the app is still the brain. It holds the server, the save, the judge and the timer,
  so nothing about driving changes. Each tab is a module, `ig_<tab>.py` (page / click / text / opened), built from the
  app's own state with the nodes of `ingamekit.py` (its docstring is the contract; `ingamekit.check()` validates a
  page). The tree goes to `%APPDATA%\ACR Daily\ingame-app.txt` (`ACRAPP 1 <seq> <rev>` / json / `end <seq>`, the file
  kept open); what's done in the game comes back in `ingame-app-events.txt` (the last 20 events, in order: open,
  close, click, text). Buttons call the app's own methods, as its window does.
- **The app's questions in the game:** while the pages are open, `messagebox` / `simpledialog.askstring` are asked in
  the game instead of in windows behind it. YES (or a typed answer) does the click again with that question
  answered. Questions asked after a thread has answered (not during a click) can only show OK; COMPETITIONS does its
  three such flows step by step itself. The window's status line (what DRIVE is doing) shows under the header.
- `mod/ACRDailyGhosts/Scripts/appui.lua`: draws the tree (hudkit.lua), keeps each list's scroll place and the keyboard
  on the same button after a redraw, makes the tile, sends clicks and typed words (Enter or leaving the box; Esc in a
  box leaves it unsent; nothing is redrawn while typing). Keyboard: arrows move, Enter presses. A game pad's B is read
  by the app (XInput) and closes a question, then the pages. Loaded by main.lua; while
  `%APPDATA%\ACR Daily\app-dev.on` exists, it is loaded again when it changes, without restarting the game.
- `client/acr_daily/launcher.py`: the window opens small, with PLAY / TO THE GAME, the timer, ghost cars, AUTO, ALL
  SETTINGS and FULL WINDOW.
- `tools/probe_mod/`: a test-only UE4SS mod that runs `%APPDATA%\ACR Daily\probe\probe.lua` in the game. It is how all
  of the above was found. Install it by hand and take it out afterwards; it never ships. Reading a widget's
  SlateColor fields from Lua crashed the game: read only plain fields.

## In the game (checked in the game 20 Nov 2026 unless said)

| Tab | What's there |
| --- | --- |
| HOME | the window's tiles, words and badges; a click goes to that part |
| DAILIES, TIME TRIAL | cards, times (mine pinned), DRIVE asked in the game (the stake too) |
| RANKED | SERIES (my session, register, car), RESULTS and each report |
| COMPETITIONS | RALLIES (events, championships, codes, standings), 1V1 (challenges, the CHALLENGE A DRIVER form), CUPS |
| COMMUNITY | tracks, cars, liveries; nothing that changes the game's packages while it runs |
| INBOX | notices, conversations, a reply typed and sent (sending not tried: it would message a real driver) |
| PROFILE | profile, achievements, shop (looks, a daily of your own), customize |
| SETTINGS | every setting of the window's page |

Left to the window: signing in, choosing a picture file, the community's tool / folder pickers.
Checked in the game: every tab draws, the private rally's code question with typing (CANCEL), keyboard moving and
Enter. Not checked in the game: the actions that change things on the server or in the save (DRIVE, join, stake,
send...); they are the window's own methods, tested offline with fakes.

## DRIVE without restarting the game (built 20 Nov 2026)

With the game in its menus and the mod in, DRIVE (a daily, a time trial, a championship's rally not started yet) no
longer closes and restarts the game: the app sends the set-up to the mod, the mod makes it in the running game through
the game's own calls and sends the game to the Service Park. The player presses START STAGE; everything after is as
before (the judge, the game's own result in its save). Checked in the game: SS1 (Greece, Zeli, 306 Maxi) and TT1
(Monte Carlo, Sommet de Turini, Polo GTI R5, light rain), the rules read back as the daily's (`S 11110102`), mode
"weekend"; DRIVE, QUIT to the menu, ACR DAILY again, DRIVE again: no crash.

- **App:** `client/acr_daily/ingamedrive.py` builds the set-up from what the save's set-up uses
  (`rallyweekend.check_itinerary`, `rule_values`, `WEATHERS`, `WETNESS`): preset, stages {track, day, service,
  weather, start, wet}, rules, one opponent, custom running order, first on the road, the car. Hooks: `app._drive_go`
  (dailies), `ttui._tt_drive_go`, `leagueui._league_drive_in_game` (only `leagues.plan` = 'setup'; setting a rally
  aside, resuming or throwing one away stays the save's job, with the game closed). `ready()`: the game running, the mod's
  pulse, and no Rally Weekend in progress in the save. When the mod says no, the reason is shown and RESTART THE GAME
  (the old way) offered: in the game when DRIVE was pressed there.
- **Mod:** `mod/ACRDailyGhosts/Scripts/drive.lua`, started by appui.lua on the app's `drive` command, a step a few
  frames apart, each checked: (1) in the main menu, `ServerSetRaceEventConfigurationId({DefaultRaceEventConfigurations,
  DefaultRally})` + `ServerExecuteFlow("FSM.Flow.SetupRaceEvent")`; (2) wait for the Rally Weekend's race event;
  (3) `SetRaceEventRallyWeekendCalendarPreset`, `AddDefaultedRallyWeekendSubEvent` per stage, then each sub-event's Day,
  PreRaceZoneConfigurationId and WeatherOptions written and read back, `SelectRallyWeekendSubEvent(0)` (the game copies
  the first stage's weather to the event), `IsRaceEventConsistent`; (4) the rules on the event's settings, read back;
  (5) `PlayerRaceConfiguration:ServerSetCar(id)`; (6) `AutoSetTiresAllocationForLocalPlayerParticipant`;
  (7) `ServerExecuteFlow("FSM.Flow.StartRaceEvent")`. Answers: `drive <n> step|ok|error <why>`.
- **Found while probing** (all in the game, 20 Nov 2026):
  - The car is `ServerSetCar` only (the garage's `SelectCar` and the profile's `SetRaceEventDefaultCar` change nothing).
  - A car id that isn't the game's crashes the game while loading the stage, and `IsRaceEventCarEligible` says yes to
    anything: only the server's own car ids are sent (e.g. `LanciaDeltaS4`, not its alias `LanciaDeltaS4GroupB`).
  - The game's `IsRallyInProgress` is true for any Rally Weekend set up in the menu; the save is the truth.
  - QUIT from the Service Park is `ServerExecuteFlow("FSM.Flow.Exit")`.
  - A Lua reference doesn't keep a texture or widget alive: after a level load their memory can hold other objects that
    IsValid() still calls valid. Using them crashed the game on the way back from a stage. Fixed: textures used again
    only if their full name is unchanged (hudkit), and every widget reference dropped when the world changes (appui).
  - UE4SS kept a `require`d module past a dev reload: appui loads drive.lua with `dofile` from its own folder.
  - Crashes while probing: walking struct fields through `GetStruct()` on a ClassProperty's class, and broad
    `ForEachProperty` with values. Read names first, then single plain values.
- **Not done / not checked:** START STAGE from the mod (left to the player); the Single Rally Stage kind of daily
  (none are made now); a DRIVE / CONTINUE done the old way (game restarted) doesn't reopen ACR DAILY afterwards.

## Championships in the game (tested 20-21 Nov 2026, private test rallies on the user's account, deleted after)

- **Judged on the stage as the game runs it.** The game's first save after a stage still holds the set-up before, so a
  run set up in the game is checked against the mod's live set-up (`ingame-setup.txt`: track, weather, start, speed,
  wetness, grip, random/dynamic, stage index; `ingamedrive.live_setup` / `setup_changed`), not the save.
- **CONTINUE** on a rally in progress (the game in its menus, `ingamedrive.can_resume`): the app sends `{resume: true}`;
  drive.lua presses the game's own buttons with `HandleButtonClicked()`: the RACING page's RALLY tile, RALLY WEEKEND
  (the 2nd `WB_SubSelectionButton_C`), then RESUME (the one `WB_ConfirmationButton_C` in the visible
  `WB_DialogConfirm_C`; CREATE NEW is another class). The game goes straight to the next stage's start line. (The
  `ResumeRaceEvent` flow alone loaded the Wales default.) Fails with "no rally in progress" after 15 s without the
  question; the app then says why and shows the game's own path.
- **Lost run, fast:** a finished stage whose time the game never saved (quit from the results screen) is a DNF once the
  game is back in its menus for 20 s (`app.back_in_menus`), not after 30 min.
- **Back to ACR DAILY** on the way to the main menu only after a stage ACR DAILY took the game to (a `drive <n> ok`
  since the last main menu); the game's own FREE PRACTICE etc. go back to its menu.
- **PAUSE:** the ACR strip is hidden while the game is paused (`GameplayStatics:IsGamePaused`, 4 times a second).
- **Cases run:** DRIVE before a car is picked (note in the game); SS1 → NEXT STAGE → SS2 → finished, counted
  (25:06.645); quit from SS2's results screen → DNF in 20 s; SS1, quit to the main menu at SS2's start, CONTINUE from
  ACR DAILY → SS2 → finished, counted (20:18.183); a DNF shown right; FREE PRACTICE → main menu stays the game's.
- **Not run in the game:** settings changed between stages (unit tests only); quit mid-stage (the judge as before).
- Fixed: on FREE PRACTICE of the same stage right after a finished event, the strip showed that event's FINISHED line.
  It now stays only while the game is still on that stage (not after the menus, not in another mode).

## Only stages ACR DAILY took the game to count (21 Nov 2026)

User: a Rally Weekend set up by hand with a daily's settings must do nothing. Before, with the app running, a by-hand
set-up identical to a daily counted (the save was checked, not who made it).

- **Mod (appui.lua):** a flag, on after `drive <n> ok` (in-game DRIVE or CONTINUE) or, for the old way (the app sets the
  save up and starts the game: `saveslot.launch_game(set_up=True)`), in the first main menu of a game started within
  5 min after it (`own` in ingame-app.txt). Off when the game's main menu is back from a stage. NEXT STAGE / the Service
  Park keep it. main.lua writes it last on the ACRSETUP line (`1`/`0`, `-` without appui).
- **App:** `set_up_here()` (None when the pages aren't in the game or the mod is older: as before). `mode_rw()` is False
  when the flag is 0, so dailies and time trials take the run for practice; an event's stage is ignored (`run['ignore']`,
  nothing sent; the button reads CONTINUE). Start line: NOT SET UP BY ACR DAILY in red. Ranked live sessions unchanged.
- **Tested in the game** (private multi-class rally H1 / Rally2/R5, deleted after): car picked in the game (Audi Quattro
  Gr4), SS1 counted in class H1; flag 1 through NEXT STAGE to SS2; quit, RALLY > RALLY WEEKEND > RESUME by hand: flag 0,
  red start line, "NOT COUNTING: not started from ACR DAILY" on the stage, nothing sent, ACR DAILY not reopened on the
  way back; CONTINUE from ACR DAILY: flag 1, THIS STAGE COUNTS. SS2 not driven to the end (the test autopilot kept
  getting stuck at 1 km).
- Left: a game the app started with its set-up counts until its first stage is left, even if the player sets up a
  Rally Weekend by hand in that first main menu instead of resuming.
- Test tooling: `RespawnRaceComponent:RespawnCarOnSpline(true, false)` respawns from Lua (no key needed).
- **Daily set up by hand, tested 21 Nov 2026** (today's SS1, Sweden Yxtjärnshöjden West / Delta S4, not driven by the
  user yet): the daily written into the save as a by-hand set-up would leave it, the game started normally, RALLY >
  RALLY WEEKEND > START RALLY by hand. Start line: NOT SET UP BY ACR DAILY in red; on the stage NOT COUNTING; log
  "taken there by ACR DAILY: no"; retired in the game: nothing on the server (no time, no DNF), no rally left in the
  save. Found on the way: a practice run's finish still waited for the game's result and counted it when found (the old
  "wrong mode" fallback); a by-hand identical set-up would have counted at the finish. Fixed (`practice_why` 'here',
  TT `t['here']`: no wait, nothing sent). Not seen in the game: the finish itself (the test autopilot can't get past
  1.2 km on that snow stage, and the server's route starts ~240 m from the game's start there).

## Next

1. A game pad tried for real (A / D-pad through the game's UI navigation, B by XInput).
2. A class event's car pick and settings changed between stages, tried in the game.
3. Questions asked after a thread answers: run them through the click that started them (ui() callbacks), so the
   three COMPETITIONS work-arounds can go.
4. Smaller redraws: the whole page is made again for each change, a short hitch in the menu only. Next step: update
   words in place.
5. Per-class standings in COMPETITIONS; the pages in the pause menu on a stage, if wanted.
6. A version number for the private build (it still says 0.1.7); new words to translate.