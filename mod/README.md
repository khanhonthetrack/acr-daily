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

## Install (Windows, Steam)

1. Get UE4SS, the experimental build (Unreal 5.4): `UE4SS_v3.0.1-...zip` from
   https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest (checked with build 1208-g6f8dc3cc).
2. Unzip it into `...\steamapps\common\Assetto Corsa Rally\acr\Binaries\Win64\` (`dwmapi.dll` and the `ue4ss`
   folder next to `acr.exe`).
3. Copy `ACRDailyGhosts` into `Win64\ue4ss\Mods\` and set `ue4ss\Mods\mods.txt` to start only it:
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
4. In the app: Ghost set-up, tick "Real cars in the game".

To remove it: delete `dwmapi.dll` and the `ue4ss` folder from `Win64`.

## Notes

- Keep UE4SS's hot reload off (`EnableHotReloadSystem = 0`): reloading while the game runs left stale callbacks
  that crashed it in testing.
- Never switch a ghost car's input off (`SetInputEnabled(false)`): the cars share one input set-up, and it switched
  off your own car's throttle and steering.
- The mod changes nothing in the game's files or saves. The game has no anti-cheat (only Epic's online services
  library), but its online features may not like a modded game: use it at your own risk.
