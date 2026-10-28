#ifndef AppVersion
  #define AppVersion "0.14.2"
#endif
#ifndef StageDir
  #define StageDir "..\dist\Lupin-Windows-x64"
#endif

[Setup]
AppId={{1E77CC5D-AE19-4808-AD70-E009B578BA74}
AppName=Lupin
AppComments=Tools for MapleStory Classic World
ChangesAssociations=yes
AppVersion={#AppVersion}
AppPublisher=zhuffman68
AppPublisherURL=https://github.com/zhuffman68/lupin
AppSupportURL=https://github.com/zhuffman68/lupin/issues
AppUpdatesURL=https://github.com/zhuffman68/lupin/releases
DefaultDirName={code:InstallDirectory}
UsePreviousAppDir=no
DefaultGroupName=Lupin
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=Lupin-{#AppVersion}-Windows-x64-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\lupin-scaled.ico
UninstallDisplayName=Lupin
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Dirs]
Name: "{app}"; Flags: uninsalwaysuninstall

[Files]
Source: "{#StageDir}\bin\lupin-market-fetch.exe"; Flags: dontcopy
Source: "{#StageDir}\bin\WebView2Loader.dll"; Flags: dontcopy
Source: "{#StageDir}\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.sqlite*,build-manifest.json"

[Icons]
Name: "{group}\Lupin"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; IconFilename: "{app}\lupin-scaled.ico"; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"
Name: "{autodesktop}\Lupin"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; IconFilename: "{app}\lupin-scaled.ico"; Tasks: desktopicon; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"

[InstallDelete]
#include "..\dist\windows-trim-delete.iss"
Type: files; Name: "{app}\classic-price-lens.ico"
Type: files; Name: "{app}\bin\classic-screen-reader.exe"
Type: files; Name: "{app}\price_lens\provider_index.py"
Type: files; Name: "{app}\tests\test_provider_index.py"
Type: files; Name: "{app}\price_lens\snapshot_browser.py"
Type: files; Name: "{app}\lupin.ico"
Type: files; Name: "{userprograms}\Classic Price Lens\Classic Price Lens.lnk"
Type: dirifempty; Name: "{userprograms}\Classic Price Lens"
Type: files; Name: "{autodesktop}\Classic Price Lens.lnk"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; Description: "Launch Lupin"; Flags: nowait postinstall skipifsilent

[Code]
var
  MigratedFrom, MigratedTo: String;
  InstallCommitted: Boolean;
  Uninstalling: Boolean;

function PreviousInstallDirectory(): String;
begin
  Result := '';
  RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{1E77CC5D-AE19-4808-AD70-E009B578BA74}_is1', 'InstallLocation', Result);
end;

function LegacyDirectory(const Directory: String): Boolean;
begin
  Result := CompareText(ExtractFileName(RemoveBackslashUnlessRoot(Directory)), 'Classic Price Lens') = 0;
end;

function InstallDirectory(Param: String): String;
var Previous: String;
begin
  Previous := PreviousInstallDirectory();
  if (Previous <> '') and not LegacyDirectory(Previous) then
    Result := Previous
  else if Previous <> '' then
    Result := AddBackslash(ExtractFileDir(RemoveBackslashUnlessRoot(Previous))) + 'Lupin'
  else
    Result := ExpandConstant('{localappdata}\Programs\Lupin');
end;

function CloseLens(): Boolean;
var
  Runtime: String;
  ExitCode: Integer;
begin
  if Uninstalling then
    Runtime := ExpandConstant('{app}\bin\lupin-market-fetch.exe')
  else begin
    ExtractTemporaryFile('lupin-market-fetch.exe');
    Runtime := ExpandConstant('{tmp}\lupin-market-fetch.exe');
  end;
  Result := Exec(Runtime, '--close-panel', ExtractFileDir(Runtime), SW_HIDE,
                 ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
end;

function PrepareMarketRuntime(): String;
var ExitCode: Integer;
begin
  Result := '';
  // An explicit offline/installer-test opt-out. Normal setup prepares the runtime.
  if ExpandConstant('{param:SKIPWEBVIEW2|0}') = '1' then Exit;
  ExtractTemporaryFile('lupin-market-fetch.exe');
  ExtractTemporaryFile('WebView2Loader.dll');
  if Exec(ExpandConstant('{tmp}\lupin-market-fetch.exe'), '--runtime-check',
          ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0) then Exit;
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  WizardForm.StatusLabel.Caption := 'Preparing market updates...';
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install',
              ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    Result := 'The market runtime could not be installed. Connect to the internet and try again.';
    Exit;
  end;
  if not (Exec(ExpandConstant('{tmp}\lupin-market-fetch.exe'), '--runtime-check',
               ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) and (ExitCode = 0)) then
    Result := 'The market runtime is not ready. Connect to the internet and try again.';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Previous, Target: String; Attempt: Integer;
begin
  Result := PrepareMarketRuntime();
  if Result <> '' then Exit;
  if not CloseLens() then
    Result := 'Close Lupin, then try the installation again.';
  if Result <> '' then Exit;
  Previous := PreviousInstallDirectory(); Target := ExpandConstant('{app}');
  if (Previous <> '') and LegacyDirectory(Previous) and DirExists(Previous) and
     (CompareText(RemoveBackslashUnlessRoot(Previous), RemoveBackslashUnlessRoot(Target)) <> 0) then begin
    if DirExists(Target) then begin
      Result := 'Choose an empty Lupin folder so the existing installation can be moved safely.';
      Exit;
    end;
    ForceDirectories(ExtractFileDir(Target));
    for Attempt := 1 to 30 do begin
      if RenameFile(Previous, Target) then begin
        MigratedFrom := Previous; MigratedTo := Target;
        Log('Moved the existing application folder to Lupin.');
        Exit;
      end;
      Sleep(100);
    end;
    Result := 'The previous application folder is still in use. Close Lupin and retry.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then InstallCommitted := True;
end;

procedure DeinitializeSetup();
begin
  if not InstallCommitted and (MigratedFrom <> '') and
     DirExists(MigratedTo) and not DirExists(MigratedFrom) then
    RenameFile(MigratedTo, MigratedFrom);
end;

function InitializeUninstall(): Boolean;
begin
  Uninstalling := True;
  Result := CloseLens();
  if not Result and not UninstallSilent() then
    MsgBox('Close Lupin, then try uninstalling again.', mbError, MB_OK);
end;

procedure RemoveEmptyDirectories(const Directory: String);
var Entry: TFindRec; Child: String;
begin
  if FindFirst(AddBackslash(Directory) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') and
           ((Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and
           ((Entry.Attributes and $400) = 0) then begin
          Child := AddBackslash(Directory) + Entry.Name;
          RemoveEmptyDirectories(Child);
          RemoveDir(Child);
        end;
      until not FindNext(Entry);
    finally FindClose(Entry); end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // A renamed installation's directories predate this install transaction.
  // Remove empty residue only; additional user files are never deleted.
  if CurUninstallStep = usPostUninstall then begin
    RemoveEmptyDirectories(ExpandConstant('{app}'));
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
