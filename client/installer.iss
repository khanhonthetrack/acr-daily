; ACR Daily's installer (Inno Setup 6): the app as a folder (build_folder.bat: dist\ACR-Daily\, PyInstaller one-dir,
; no UPX, its version info) put in the player's own programs folder, with a Start menu entry, a desktop shortcut if they
; want one, and an uninstaller in Windows' Apps list. No administrator rights: nothing outside the player's own folders.
; Why (the user, 24 Nov 2026: "Work on the app being, not clearly seen as virus for browsers and windows ... the end
; product should be a zip ... an installer (which installs things, and ask to make a desktop copy etc)"): a one-file exe
; that unpacks itself into a temp folder at every start is what antivirus heuristics flag most; an installed folder,
; a known installer and an uninstall entry are what ordinary programs look like. (Code signing: later, docs/installer.md.)
;
; Built by .github/workflows/release.yml:  iscc /DMyAppVersion=0.2.1 installer.iss  -> dist\ACR-Daily-Setup.exe
; The app's UPDATE (client/acr_daily/updater.py) runs it with /VERYSILENT /SUPPRESSMSGBOXES /UPDATE=1: the new
; version in place, the app started again.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{6C9F2E3A-8D41-4B7A-9E0C-ACDA11F00D02}
AppName=ACR Daily
AppVersion={#MyAppVersion}
AppVerName=ACR Daily {#MyAppVersion}
AppPublisher=ACR Daily (open source, MIT)
AppPublisherURL=https://acrdaily.com
AppSupportURL=https://acrdaily.com/report
AppUpdatesURL=https://acrdaily.com
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=ACR Daily installer
VersionInfoProductName=ACR Daily
DefaultDirName={localappdata}\Programs\ACR Daily
DefaultGroupName=ACR Daily
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=ACR-Daily-Setup
SetupIconFile=acr_daily\icon.ico
UninstallDisplayIcon={app}\ACR-Daily.exe
UninstallDisplayName=ACR Daily
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; GroupDescription: "Shortcuts:"

[InstallDelete]
; (the last version's files out first: a file it had and this one doesn't must not linger)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\ACR-Daily\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\ACR Daily"; Filename: "{app}\ACR-Daily.exe"
Name: "{autodesktop}\ACR Daily"; Filename: "{app}\ACR-Daily.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ACR-Daily.exe"; Description: "Start ACR Daily"; Flags: nowait postinstall skipifsilent
; (an update from the app itself: started again, as the one-file app's update does)
Filename: "{app}\ACR-Daily.exe"; Parameters: "--updated"; Flags: nowait; Check: IsUpdate

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function IsUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;
