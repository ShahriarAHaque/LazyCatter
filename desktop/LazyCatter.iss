; inno setup script (optional)
; install inno setup 6 then compile this after scripts/build-windows.ps1
; has produced dist\LazyCatter\
; output: installer-out\LazyCatter-Setup.exe

#define MyAppName "LazyCatter"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "LilaNaCl"
#define MyAppExeName "LazyCatter.exe"
#define MyAppURL "https://github.com/ShahriarAHaque/LazyCatter"
#define MyAppSupportURL "https://github.com/ShahriarAHaque/LazyCatter/issues"

[Setup]
AppId={{A7C8E2F1-4B6D-4E9A-9C21-LAZYCATTER001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupportURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer-out
OutputBaseFilename=LazyCatter-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "..\dist\LazyCatter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch LazyCatter"; Flags: nowait postinstall skipifsilent
