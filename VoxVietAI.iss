#define MyAppName "VoxViet AI"
#define MyAppVersion "1.1.0"
#define MyAppExeName "VoxVietAI.exe"

[Setup]
AppId={{8CBB8F8C-904A-4E42-8C64-6A31C6537101}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=VoxViet AI
DefaultDirName={autopf}\VoxViet AI
DefaultGroupName=VoxViet AI
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=VoxVietAI-Setup-1.1.0
SetupIconFile=voxviet-ai.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\VoxVietAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VoxViet AI"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\VoxViet AI"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch VoxViet AI"; Flags: nowait postinstall skipifsilent