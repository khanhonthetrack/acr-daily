@echo off
rem Builds dist\ACR-Daily\ (a folder: ACR-Daily.exe and its files beside it) and dist\ACR-Daily-<version>.zip, with the
rem SHA-256 of the exe and of the zip. Fewer false alarms from antivirus than the one-file exe (build.bat): nothing is
rem unpacked to a temp folder at each start, nothing is compressed or packed (no UPX), the exe carries its version
rem info. The same files as build.bat; the server URL as there:
rem   build_folder.bat https://acr-daily.YOURNAME.workers.dev
cd /d "%~dp0"
if not "%~1"=="" (
  >acr_daily\_server.txt echo %~1
)
if not exist acr_daily\_server.txt (
  echo No server URL yet: give it as the first argument, e.g. build_folder.bat https://acr-daily.you.workers.dev
  exit /b 1
)
python make_icon.py
python make_version_info.py
set SEVENZIP=
if exist acr_daily\7zip\7z.exe set SEVENZIP=--add-binary "acr_daily\7zip\7z.exe;acr_daily\7zip" --add-binary "acr_daily\7zip\7z.dll;acr_daily\7zip" --add-data "acr_daily\7zip\License.txt;acr_daily\7zip"
python -m PyInstaller --noconfirm --clean --onedir --windowed --name ACR-Daily %SEVENZIP% ^
  --icon acr_daily\icon.ico --version-file version_info.txt --noupx ^
  --add-data "acr_daily\icon.ico;acr_daily" ^
  --add-data "acr_daily\steam-*.png;acr_daily" ^
  --add-data "acr_daily\logo-*.png;acr_daily" ^
  --add-data "acr_daily\dcar-*.png;acr_daily" ^
  --add-data "acr_daily\coin-*.png;acr_daily" ^
  --add-data "acr_daily\icons;acr_daily\icons" ^
  --add-data "acr_daily\photos;acr_daily\photos" ^
  --add-data "acr_daily\series;acr_daily\series" ^
  --add-data "acr_daily\locales;acr_daily\locales" ^
  --add-data "acr_daily\_server.txt;acr_daily" ^
  --add-data "acr_daily\cameras.json;acr_daily" ^
  --add-data "acr_daily\mappings;acr_daily\mappings" ^
  --add-data "..\mod\ACRDailyGhosts\Scripts\*.lua;acr_daily\mod\ACRDailyGhosts\Scripts" ^
  run.py
if errorlevel 1 exit /b 1
for /f "delims=" %%v in ('python -c "import acr_daily; print(acr_daily.__version__)"') do set VER=%%v
powershell -NoProfile -Command ^
  "$z = 'dist\ACR-Daily-%VER%.zip'; if (Test-Path $z) { Remove-Item $z };" ^
  "Compress-Archive -Path 'dist\ACR-Daily\*' -DestinationPath $z -CompressionLevel Optimal;" ^
  "foreach ($f in 'dist\ACR-Daily\ACR-Daily.exe', $z) { $h = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(); [IO.File]::WriteAllText(\"$PWD\$f.sha256\", $h); \"$h  $f\" }"
echo.
echo Built dist\ACR-Daily\ and dist\ACR-Daily-%VER%.zip for server:
type acr_daily\_server.txt
