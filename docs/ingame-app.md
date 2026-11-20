# ACR DAILY inside the game (0.2, private build)

Branch `ingame-app`, from v0.1.7. The whole app in the game: a small launcher (settings + PLAY) starts the game, and
the game's HOME has an ACR DAILY tile that opens the app's pages, drawn by the game.

## Feasible: checked in the game (ACR 0.7, UE 5.4, UE4SS 3.0.1), 20 Nov 2026

- **The tile.** HOME is `WB_RaceLayout_C`, the first page of `WB_SelectWidget`'s `OptionSwitcher`. Its three tiles sit
  in `TilesContainer` (550 x 732 units). The box is made wider to the right, and a new `WB_MainMenuListButton_C` is
  added there (532 x 716), made with `WidgetBlueprintLibrary.Create`. It is the game's own tile, so it has the game's
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
  so nothing about driving changes. Each page is built from the app's own state as a tree of nodes (col, row, stack,
  box, txt, img, btn, scroll, size, sp). It goes to `%APPDATA%\ACR Daily\ingame-app.txt`
  (`ACRAPP 1 <seq> <rev>` / json / `end <seq>`, the file kept open), and clicks come back in `ingame-app-events.txt`.
  The window's message boxes (showinfo...) are said in the game while the pages are open. DRIVE asks its question in
  the game, the stake included, then runs the window's own DRIVE.
- `mod/ACRDailyGhosts/Scripts/appui.lua`: draws the tree (hudkit.lua), keeps each list's scroll place, makes the tile,
  and tells the app about clicks. It is loaded by main.lua. While `%APPDATA%\ACR Daily\app-dev.on` exists, it is loaded
  again when it changes, without restarting the game.
- `client/acr_daily/launcher.py`: the window opens small, with PLAY / TO THE GAME, the timer, ghost cars, AUTO, ALL
  SETTINGS and FULL WINDOW.
- `tools/probe_mod/`: a test-only UE4SS mod that runs `%APPDATA%\ACR Daily\probe\probe.lua` in the game. It is how all
  of the above was found. Install it by hand and take it out afterwards; it never ships.

## Ported so far

| Part | In the game |
| --- | --- |
| DAILIES: cards, today's times (mine pinned), DRIVE with its question and the stake | yes |
| TIME TRIAL: cards, the week's times, DRIVE | yes |
| RANKED, COMPETITIONS (rallies, 1V1, cups), COMMUNITY, INBOX, PROFILE, SETTINGS | not yet: OPEN THE WINDOW |
| HOME (the app's own tiles), the driver strip, what's new, the intro | not yet |
| Cards during a run (comment, next daily) | already drawn by hud.lua (in-game displays) |

## Next

1. A game pad and keyboard in the pages: focus on the first button, D-pad / arrows between buttons, A / Enter.
2. Port the rest page by page, in the app's order: RANKED, COMPETITIONS, COMMUNITY, INBOX (typing: EditableText),
   PROFILE, SETTINGS. Then the launcher keeps only what's needed before the game starts.
3. DRIVE without restarting the game: the game only reads the set-up when it starts, so for now DRIVE in the game
   restarts it, as the window's DRIVE does.
4. Smaller redraws: the whole page is made again for each change, a short hitch in the menu only. Next step: update
   words in place.
5. The pages in the pause menu on a stage, if wanted.
6. A version number for the private build (it still says 0.1.7).
