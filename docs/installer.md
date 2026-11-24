# The installer, and antivirus false alarms

The user, 24 Nov 2026: "Work on the app being not clearly seen as virus for browsers and windows. The end product should
be a zip. Consider building an app as an installer (which installs things, and ask to make a desktop copy etc). Signing /
having a certificate is for later."

## What a release has now (.github/workflows/release.yml)

| File | What | Who uses it |
|---|---|---|
| `ACR-Daily-<version>.zip` | `ACR-Daily-Setup.exe` + `README.txt` | the website's download (switch `DOWNLOAD_URL` in server/wrangler.toml to it with the first release that has it) |
| `ACR-Daily-Setup.exe` | Inno Setup installer (client/installer.iss) of the one-dir build (client/build_folder.bat) | new players; installed apps' UPDATE (updater.py `download_setup` / `run_setup`, silent, `/UPDATE=1`) |
| `ACR-Daily.exe` | the one-file exe, as before | the apps already out there: their UPDATE swaps this file in |

Each with its `.sha256` and a GitHub build attestation (`gh attestation verify <file> --repo khanhonthetrack/acr-daily`).

The installer: per user (`{localappdata}\Programs\ACR Daily`, no administrator, no UAC prompt), Start menu entry, a
**desktop shortcut if the player ticks it** (asked on its Tasks page), an uninstaller in Windows' Apps list.

## Why this helps

Heuristic antivirus engines (and Chrome / Edge's download checks) weigh, among others:

1. **Self-extracting one-file exes** (PyInstaller `--onefile` unpacks a Python runtime into `%TEMP%` at every start):
   the most-flagged pattern. The installed app is `--onedir`: nothing unpacked at start.
2. **Packers** (UPX): not used (`--noupx`).
3. **No version info**: the exe carries it (make_version_info.py); the installer too.
4. **Unknown installers vs known ones**: Inno Setup is one of the most common installers on Windows; engines know it.
5. **Reputation** (SmartScreen, Chrome): grows with downloads of the *same* file; signing carries it across versions.

## Next steps (in this order)

1. **Release with the installer**, then point the website's download (`DOWNLOAD_URL`) at the zip.
2. **Report false positives** for each release the day it is out (free, usually cleared in 1-3 days):
   - Microsoft Defender: https://www.microsoft.com/wdsi/filesubmission (as "Software developer", "Incorrectly detected")
   - VirusTotal: upload the zip, then use each flagging vendor's false-positive form (the VirusTotal page links them).
3. **Code signing (later)**: **SignPath Foundation** signs open-source projects for free (https://signpath.org: apply
   with the GitHub repository; signing then runs in the release workflow). Otherwise Azure Trusted Signing (about
   USD 10 a month) or an OV certificate. A signed installer + signed exe removes "Unknown publisher" and builds
   SmartScreen reputation across versions.
