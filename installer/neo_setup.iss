; Neo — Personal Intelligence Agent
; Inno Setup Script v1.0
;
; Prerequisites:
;   1. Build the Tauri app: cd frontend && npm run tauri build
;   2. Package Python backend: pyinstaller neo-server.spec
;   3. Run Inno Setup Compiler on this script
;
; Output: installer/output/NeoSetup-{version}.exe

#define MyAppName "Neo"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Natsuoo21"
#define MyAppURL "https://github.com/Natsuoo21/neo"
#define MyAppExeName "Neo.exe"

[Setup]
AppId={{B7E4F3A2-9D1C-4E8B-A5F6-7C3D2E1B0A94}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=NeoSetup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\frontend\src-tauri\icons\icon.ico
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Start Neo with Windows"; GroupDescription: "Startup:"

[Files]
; Tauri executable (built by `npm run tauri build`)
Source: "..\frontend\src-tauri\target\release\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Python backend sidecar (built by PyInstaller)
Source: "..\backend\dist\neo-server\*"; DestDir: "{app}\neo-server"; Flags: ignoreversion recursesubdirs createallsubdirs

; Data directory template
Source: "..\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; Skills
Source: "..\backend\neo\skills\public\*"; DestDir: "{app}\skills\public"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up logs but preserve user data by default
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Ask user whether to preserve data on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  KeepData: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    KeepData := MsgBox('Do you want to keep your Neo data (database, settings, plugins)?',
      mbConfirmation, MB_YESNO);
    if KeepData = IDNO then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      DelTree(ExpandConstant('{userdocs}\Neo'), True, True, True);
    end;
  end;
end;
