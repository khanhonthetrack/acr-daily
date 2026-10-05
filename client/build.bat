@echo off
rem Builds dist\ACR-Daily.exe (one file, no Python needed on the player's PC).
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
python -m pip install --user --quiet pyinstaller
python make_icon.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ACR-Daily ^
  --icon acr_daily\icon.ico ^
  --add-data "acr_daily\icon.ico;acr_daily" ^
  --add-data "acr_daily\_server.txt;acr_daily" ^
  run.py
if errorlevel 1 exit /b 1
rem the website serves the download from server\public (deploy the server to publish it)
if not exist ..\server\public\download mkdir ..\server\public\download
copy /y dist\ACR-Daily.exe ..\server\public\download\ACR-Daily.exe >nul
rem the app's UPDATE button only installs a download that matches this checksum
powershell -NoProfile -Command "[IO.File]::WriteAllText('..\server\public\download\ACR-Daily.exe.sha256', (Get-FileHash dist\ACR-Daily.exe -Algorithm SHA256).Hash.ToLower())"
echo.
echo Built dist\ACR-Daily.exe for server:
type acr_daily\_server.txt
