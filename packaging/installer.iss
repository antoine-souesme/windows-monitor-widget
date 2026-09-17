; Inno Setup script building setup_<version>.exe.
;
; Compile with:  ISCC.exe /DAppVersion=1.2.0 packaging\installer.iss
; It expects the PyInstaller output in dist\MonitorWidget.
;
; Installing over an existing copy is the upgrade path: same AppId, same
; directory, user settings in %APPDATA% are left untouched.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Monitor Widget"
#define ExeName "MonitorWidget.exe"

[Setup]
; Never change AppId: it is what ties an update to the previous install.
AppId={{7C1F9A42-5E3D-4C0B-9F2A-6B8D1E4A77C5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Antoine Souesme
VersionInfoVersion={#AppVersion}
; Per user install: no administrator rights, matches the HKCU startup key.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MonitorWidget
UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=setup_{#AppVersion}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#ExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Detects a running instance through the mutex the widget already creates.
AppMutex=Local\MonitorWidgetSingleInstance
CloseApplications=force

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Lancer Monitor Widget au démarrage de Windows"; GroupDescription: "Options :"
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Options :"; Flags: unchecked

[InstallDelete]
; Leftover of the versions named CPU Widget, installed in the same folder.
Type: files; Name: "{app}\CpuWidget.exe"

[Files]
Source: "..\dist\MonitorWidget\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#ExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#ExeName}"; Tasks: desktopicon

[Registry]
; Same value name the widget writes itself, so both stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "MonitorWidget"; ValueData: """{app}\{#ExeName}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#ExeName}"; Description: "Lancer Monitor Widget"; \
    Flags: nowait postinstall skipifsilent
; Silent run: the update started by the widget itself, which was killed above.
; Nothing else would bring it back, so it is relaunched here.
Filename: "{app}\{#ExeName}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
procedure StopRunningWidget();
var
  ResultCode: Integer;
begin
  { Belt and braces: the widget has no taskbar entry, so the Restart Manager
    cannot always close it politely. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im {#ExeName}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  { Same thing for the executable of the versions named CPU Widget. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im CpuWidget.exe', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    StopRunningWidget();
    { The application used to be called CPU Widget: drop its startup entry
      so an update does not leave two of them behind. }
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'CpuWidget');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    StopRunningWidget();
    { Remove the startup entry even when the widget wrote it by itself. }
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'MonitorWidget');
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'CpuWidget');
  end;
end;
