; RedForge — Inno Setup script (Windows installer)
; Build:  iscc installers\windows\redforge.iss
; Requires: the release folder at releases\redforge-{version}\ (run build_release.py first),
;           Inno Setup 6 (https://jrsoftware.org/isinfo.php).
; Runtime: end users need Python 3.11+ and Ollama. Node.js is NOT required.

#define AppVersion "1.0.0"
#define AppName "RedForge"
#define StageDir "..\..\releases\redforge-" + AppVersion

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BRGOVIND
DefaultDirName={autopf}\RedForge
DefaultGroupName=RedForge
OutputDir=..\..\releases
OutputBaseFilename=RedForge-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\RedForge"; Filename: "{app}\start.cmd"; WorkingDir: "{app}"
Name: "{group}\RedForge Doctor"; Filename: "cmd.exe"; Parameters: "/k set PYTHONPATH={app}\cli & python -m redforge doctor"; WorkingDir: "{app}"
Name: "{autodesktop}\RedForge"; Filename: "{app}\start.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
; Install Python dependencies after copying files.
Filename: "{cmd}"; Parameters: "/c cd /d ""{app}"" && python -m pip install -r backend\requirements.txt"; \
  StatusMsg: "Installing dependencies (needs Python 3.11+)..."; Flags: runhidden
Filename: "{app}\start.cmd"; Description: "Launch RedForge now"; Flags: postinstall nowait skipifsilent
