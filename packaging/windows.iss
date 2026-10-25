#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef StageDir
  #define StageDir "..\dist\ClassicPriceLens-Windows-x64"
#endif

[Setup]
AppId={{1E77CC5D-AE19-4808-AD70-E009B578BA74}
AppName=Classic Price Lens
AppVersion={#AppVersion}
AppPublisher=zhuffman68
AppPublisherURL=https://github.com/zhuffman68/classic-price-lens
AppSupportURL=https://github.com/zhuffman68/classic-price-lens/issues
AppUpdatesURL=https://github.com/zhuffman68/classic-price-lens/releases
DefaultDirName={localappdata}\Programs\Classic Price Lens
DefaultGroupName=Classic Price Lens
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=ClassicPriceLens-{#AppVersion}-Windows-x64-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\classic-price-lens.ico
UninstallDisplayName=Classic Price Lens
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=2
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.sqlite*,build-manifest.json"

[Icons]
Name: "{group}\Classic Price Lens"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens --capture"; WorkingDir: "{app}"; IconFilename: "{app}\classic-price-lens.ico"; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"
Name: "{autodesktop}\Classic Price Lens"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens --capture"; WorkingDir: "{app}"; IconFilename: "{app}\classic-price-lens.ico"; Tasks: desktopicon; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens --capture"; WorkingDir: "{app}"; Description: "Launch Classic Price Lens"; Flags: nowait postinstall skipifsilent

[Code]
function CloseLens(): Boolean;
var
  Runtime: String;
  ExitCode: Integer;
begin
  Runtime := ExpandConstant('{app}\runtime\pythonw.exe');
  Result := True;
  if FileExists(Runtime) then
    Result := Exec(Runtime, '-B -m price_lens --quit', ExpandConstant('{app}'), SW_HIDE,
                   ewWaitUntilTerminated, ExitCode) and (ExitCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not CloseLens() then
    Result := 'Close Classic Price Lens, then try the installation again.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := CloseLens();
  if not Result and not UninstallSilent() then
    MsgBox('Close Classic Price Lens, then try uninstalling again.', mbError, MB_OK);
end;
