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
Name: "install_ollama"; Description: "Download and install Ollama for local AI (recommended)"; GroupDescription: "Optional components:"; Flags: unchecked

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

// ── Ollama detection ──

function OllamaAlreadyInstalled(): Boolean;
var
  OllamaPath: String;
  RegPath: String;
begin
  // Check common install location
  OllamaPath := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if FileExists(OllamaPath) then
  begin
    Result := True;
    Exit;
  end;

  // Check registry (machine-wide install)
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Ollama',
    'InstallLocation', RegPath) then
  begin
    if FileExists(RegPath + '\ollama.exe') then
    begin
      Result := True;
      Exit;
    end;
  end;

  // Check if ollama is in PATH
  if FileExists(ExpandConstant('{sys}\ollama.exe')) then
  begin
    Result := True;
    Exit;
  end;

  Result := False;
end;

procedure InitializeWizard();
begin
  // If Ollama is already installed, uncheck and disable the task
  if OllamaAlreadyInstalled() then
  begin
    WizardForm.TasksList.ItemCaption[WizardForm.TasksList.Items.Count - 1] :=
      'Download and install Ollama for local AI (already installed)';
    WizardForm.TasksList.Checked[WizardForm.TasksList.Items.Count - 1] := False;
    WizardForm.TasksList.ItemEnabled[WizardForm.TasksList.Items.Count - 1] := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OllamaInstallerPath: String;
  ResultCode: Integer;
  DownloadUrl: String;
begin
  if CurStep = ssPostInstall then
  begin
    if IsTaskSelected('install_ollama') then
    begin
      DownloadUrl := 'https://ollama.com/download/OllamaSetup.exe';
      OllamaInstallerPath := ExpandConstant('{tmp}\OllamaSetup.exe');

      // Download Ollama installer
      try
        DownloadTemporaryFile(DownloadUrl, 'OllamaSetup.exe', '', nil);
      except
        Log('Ollama download failed: ' + GetExceptionMessage);
        MsgBox('Ollama download failed. You can install it later from https://ollama.com',
          mbInformation, MB_OK);
        Exit;
      end;

      // Run Ollama installer silently
      if not Exec(OllamaInstallerPath, '/VERYSILENT /SUPPRESSMSGBOXES', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        Log('Ollama install exec failed');
        MsgBox('Ollama installation failed. You can install it later from https://ollama.com',
          mbInformation, MB_OK);
        Exit;
      end;

      if ResultCode <> 0 then
      begin
        Log('Ollama installer exited with code: ' + IntToStr(ResultCode));
        MsgBox('Ollama installation failed (exit code ' + IntToStr(ResultCode) +
          '). You can install it later from https://ollama.com',
          mbInformation, MB_OK);
        Exit;
      end;

      Log('Ollama installed successfully');

      // Pull default model (non-blocking — runs in background)
      Exec(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'),
        'pull qwen2.5:3b', '', SW_HIDE, ewNoWait, ResultCode);
      Log('Started background model pull: qwen2.5:3b');
    end;
  end;
end;

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
