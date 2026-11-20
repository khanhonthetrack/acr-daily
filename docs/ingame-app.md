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
- **Not done / not checked:** a championship's DRIVE in the game (built, not run: it would start a real entry); a
  stage driven to the finish after an in-game DRIVE (the result read from the save, as before, but not yet seen);
  START STAGE from the mod (left to the player); the Single Rally Stage kind of daily (none are made now).
## Next

1. A game pad tried for real (A / D-pad through the game's UI navigation, B by XInput).
2. A stage driven to the finish after an in-game DRIVE, and a championship's in-game DRIVE, tried for real.
3. Questions asked after a thread answers: run them through the click that started them (ui() callbacks), so the
   three COMPETITIONS work-arounds can go.
4. Smaller redraws: the whole page is made again for each change, a short hitch in the menu only. Next step: update
   words in place.
5. Per-class standings in COMPETITIONS; the pages in the pause menu on a stage, if wanted.
6. A version number for the private build (it still says 0.1.7); new words to translate.