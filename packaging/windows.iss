#ifndef AppVersion
  #define AppVersion "0.10.0"
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
DefaultDirName={localappdata}\Programs\Classic Price Lens
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
UninstallDisplayIcon={app}\lupin.ico
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

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc,*.sqlite*,build-manifest.json"

[Icons]
Name: "{group}\Lupin"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; IconFilename: "{app}\lupin.ico"; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"
Name: "{autodesktop}\Lupin"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; IconFilename: "{app}\lupin.ico"; Tasks: desktopicon; AppUserModelID: "io.github.zhuffman68.ClassicPriceLens"

[InstallDelete]
Type: files; Name: "{app}\classic-price-lens.ico"
Type: files; Name: "{userprograms}\Classic Price Lens\Classic Price Lens.lnk"
Type: dirifempty; Name: "{userprograms}\Classic Price Lens"
Type: files; Name: "{autodesktop}\Classic Price Lens.lnk"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-B -m price_lens"; WorkingDir: "{app}"; Description: "Launch Lupin"; Flags: nowait postinstall skipifsilent

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
    Result := 'Close Lupin, then try the installation again.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := CloseLens();
  if not Result and not UninstallSilent() then
    MsgBox('Close Lupin, then try uninstalling again.', mbError, MB_OK);
end;
