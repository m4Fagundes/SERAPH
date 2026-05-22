; Inno Setup Script for GridAnalyzer
; ---------------------------------------------------
; This script generates a professional installer that:
; 1. Copies the unpacked folder to the client's PC (fast!)
; 2. Creates shortcuts on the Desktop and Start Menu
; 3. Creates an uninstaller
; 4. Makes startup instant, as it doesn't extract files every time it opens.

[Setup]
; Program Identification
AppName=Grid Image Analyzer
AppVersion=1.2.4
AppPublisher=M4Fagundes
AppPublisherURL=https://github.com/m4Fagundes/grid-image-analyzer
AppSupportURL=https://github.com/m4Fagundes/grid-image-analyzer

; Install for the current user without needing administrator privileges (optional, good for not asking for a password)
; If you want to install in "Program Files" (requires Admin), change to 'PrivilegesRequired=admin' and 'DefaultDirName={autopf}\GridAnalyzer'
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\GridAnalyzer
DefaultGroupName=Grid Image Analyzer

; SourceDir: base for all Source paths in [Files].
; This .iss lives in docs/build/ so ..\..\  resolves to the repo root
; where PyInstaller outputs dist\GridAnalyzer\.
SourceDir=..\..

; Output file settings — relative to the .iss file directory (docs/build/)
; so ..\..\build_installer places the setup exe at repo root/build_installer/
OutputDir=..\..\build_installer
OutputBaseFilename=GridAnalyzer_Setup
Compression=lzma2/ultra
SolidCompression=yes
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayIcon={app}\GridAnalyzer.exe

; Appearance
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; IMPORTANT: Ensure you ran "pyinstaller main_release.spec" before generating the installer!
; Gets all files generated in PyInstaller's "onedir" mode
Source: "dist\GridAnalyzer\GridAnalyzer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GridAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Do not use "ignoreversion" on shared system files

[Icons]
Name: "{group}\Grid Image Analyzer"; Filename: "{app}\GridAnalyzer.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,Grid Image Analyzer}"; Filename: "{uninstallexe}"; WorkingDir: "{app}"
Name: "{autodesktop}\Grid Image Analyzer"; Filename: "{app}\GridAnalyzer.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\GridAnalyzer.exe"; Description: "{cm:LaunchProgram,Grid Image Analyzer}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
