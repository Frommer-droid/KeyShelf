#define AppVersion "0.3.0"
#define AppName "KeyShelf"

[Setup]
AppId={{1CFC496A-A63C-4599-83C2-2416506C7F30}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Frommer
DefaultDirName={code:DefaultPath}
DefaultGroupName={#AppName}
UsePreviousAppDir=no
PrivilegesRequired=admin
LanguageDetectionMethod=none
ShowLanguageDialog=no
OutputBaseFilename=KeyShelf_v{#AppVersion}_Setup
SetupIconFile=..\logo.ico
UninstallDisplayIcon={app}\KeyShelf.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: unchecked

[Files]
Source: "..\KeyShelf\*"; DestDir: "{app}"; Excludes: "\settings.json,\*.log,\*.kdbx,\*.kdbx.*,__pycache__\*,*.pyc"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\KeyShelf.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\KeyShelf.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\KeyShelf.exe"; Description: "Запустить приложение"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
function DefaultPath(Param: String): String;
begin
  if DirExists('D:\') then
    Result := 'D:\Apps\KeyShelf'
  else
    Result := 'C:\Apps\KeyShelf';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ProcessPath, Command, StartupPath: String;
  ExitCode: Integer;
  Shell, Link: Variant;
begin
  if CurUninstallStep = usUninstall then
  begin
    ProcessPath := ExpandConstant('{app}\KeyShelf.exe');
    StringChangeEx(ProcessPath, '''', '''''', True);
    Command := 'Get-Process | Where-Object { $_.Path -eq ''' + ProcessPath + ''' } | Stop-Process -Force';
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + Command + '"', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    StartupPath := ExpandConstant('{userstartup}\KeyShelf.lnk');
    if FileExists(StartupPath) then
    begin
      try
        Shell := CreateOleObject('WScript.Shell');
        Link := Shell.CreateShortcut(StartupPath);
        if Link.Description = 'KeyShelf managed startup' then
          if CompareText(Link.TargetPath, ExpandConstant('{app}\KeyShelf.exe')) = 0 then
            DeleteFile(StartupPath);
      except
        Log('Could not inspect the current-user Startup shortcut');
      end;
    end;
  end;
end;
