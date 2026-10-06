@echo off
rem Builds dist\ACR-Daily.exe (one file, no Python needed on the player's PC). For testing on this PC;
rem the exe people download is built by GitHub Actions from a tagged commit (see .github\workflows\release.yml).
rem   build.bat https://acr-daily.YOURNAME.workers.dev
rem The URL is baked into the exe; run it again with the same URL for every new version.
cd /d "%~dp0"
if not "%~1"=="" (
  >acr_daily\_server.txt echo %~1
)
if not exist acr_daily\_server.txt (
  echo No server URL yet: give it as the first argument, e.g. build.bat https://acr-daily.you.workers.dev
  exit /b 1
)
python -m pip install --user --quiet pyinstaller pillow==12.3.0
python make_icon.py
python make_version_info.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ACR-Daily ^
  --icon acr_daily\icon.ico --version-file version_info.txt --noupx ^
  --add-data "acr_daily\icon.ico;acr_daily" ^
  --add-data "acr_daily\steam-*.png;acr_daily" ^
  --add-data "acr_daily\logo-*.png;acr_daily" ^
  --add-data "acr_daily\_server.txt;acr_daily" ^
  run.py
if errorlevel 1 exit /b 1
rem Official releases are built by GitHub (.github\workflows\release.yml), not here: push a tag v<version>.
echo.
echo Built dist\ACR-Daily.exe for server:
type acr_daily\_server.txt
