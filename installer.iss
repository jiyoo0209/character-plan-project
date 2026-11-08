; Inno Setup 6 설치 스크립트
; 사용자 폴더(%LOCALAPPDATA%\Programs)에 설치 -> 관리자 권한 불필요,
; 설치 폴더\data\schedules.json 에 바로 쓸 수 있음.

#define AppName "CharacterPlan"
#define AppVersion "0.1.0"
#define AppExe "CharacterPlan.exe"

[Setup]
AppId={{8D1A6C1E-4B7E-4C2B-9E55-2F6B0C3A7D41}
AppName=캐릭터 일정 비서
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName=캐릭터 일정 비서
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename={#AppName}-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 만들기"; GroupDescription: "추가 옵션:"; Flags: unchecked

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data"

[Icons]
Name: "{group}\캐릭터 일정 비서"; Filename: "{app}\{#AppExe}"
Name: "{group}\제거"; Filename: "{uninstallexe}"
Name: "{userdesktop}\캐릭터 일정 비서"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; 자동 실행은 항상 켜짐 (앱도 실행될 때마다 같은 값을 다시 등록)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#AppName}"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "지금 실행"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillApp"
