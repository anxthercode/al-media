#define MyAppName "AL Media"
#ifndef MyAppVersion
  #error Run scripts/make-installer.ps1 to provide the application version
#endif
#define MyAppExeName "ALMedia.exe"
[Setup]
AppId={{1B4E79C7-06E4-43D9-A1EF-6C4D821F4390}
AppName={#MyAppName}
AppPublisher=AnyLoad Media
AppComments=AnyLoad Media — video and audio downloader
AppVersion={#MyAppVersion}
UninstallDisplayName={#MyAppName}
DefaultDirName={localappdata}\Programs\ALMedia
DefaultGroupName={#MyAppName}
UsePreviousGroup=no
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ALMedia-{#MyAppVersion}-Setup-win-x64
SetupIconFile=..\assets\app.ico
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=AL Media Installer
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut / Ярлык на рабочем столе"; GroupDescription: "Shortcuts / Ярлыки:"; Flags: checkedonce

[Files]
Source: "..\dist\ALMedia\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Preserve the installer AppId so this rebrand upgrades existing installations.
; Only obsolete application files and shortcuts are removed; profiles and downloads stay intact.
Type: files; Name: "{app}\UniversalMediaStudio.exe"
Type: files; Name: "{autodesktop}\Universal Media Studio.lnk"
Type: files; Name: "{userprograms}\Universal Media Studio\Universal Media Studio.lnk"
Type: dirifempty; Name: "{userprograms}\Universal Media Studio"
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icudt78.dll"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "AnyLoadMedia.ALMedia"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; AppUserModelID: "AnyLoadMedia.ALMedia"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch AL Media"; Flags: nowait postinstall skipifsilent
