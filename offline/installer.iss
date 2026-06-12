; ==================================================================
; Launchkey Mixer — Inno Setup installer
; ==================================================================
; Produces LaunchkeyMixerSetup.exe in offline\installer\
;
; Wraps the PyInstaller-built LaunchkeyMixer.exe with:
;   - Start menu shortcut
;   - Optional Desktop shortcut
;   - Toggle: "Start with Windows" (HKCU\Run registry key)
;   - Uninstaller
;
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php) installed.
; The build script (build_windows.bat) will call:
;     iscc /Qp installer.iss
; ==================================================================

#define MyAppName       "Launchkey Mixer"
#define MyAppVersion    "0.1.0"
#define MyAppPublisher  "ruskir1222"
#define MyAppURL        "https://github.com/ruskir1222/Launchkey25mk4Mixer"
#define MyAppExeName    "LaunchkeyMixer.exe"

[Setup]
AppId={{2A77BBD0-8C4F-4F0E-9E1E-7C7D2D5F9A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\LaunchkeyMixer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=LaunchkeyMixerSetup
OutputDir=installer
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";   Description: "Create a &desktop shortcut";  GroupDescription: "Additional shortcuts:"
Name: "startuptask";   Description: "Start {#MyAppName} when Windows starts (system tray)"; GroupDescription: "Auto-start:"

[Files]
; Main executable (produced by PyInstaller)
Source: "dist\{#MyAppExeName}";    DestDir: "{app}"; Flags: ignoreversion
; Bundle the README + extension folder so the user has docs handy
Source: "..\README.md";            DestDir: "{app}"; Flags: ignoreversion
Source: "..\extension\*";          DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";                Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}";      Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Auto-start at login (HKCU = current user, no admin required)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; \
    ValueData: """{app}\{#MyAppExeName}"""; Tasks: startuptask; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\extension"
