; Inno Setup Script for GridAnalyzer
; ---------------------------------------------------
; Esse script gera um instalador profissional que:
; 1. Copia a pasta descompactada para o PC do cliente (rápido!)
; 2. Cria atalhos na Área de Trabalho e Menu Iniciar
; 3. Cria um desinstalador
; 4. Torna a inicialização instantânea, pois não extrai arquivos toda vez que abre.

[Setup]
; Identificação do Programa
AppName=Grid Image Analyzer
AppVersion=1.0.0
AppPublisher=M4Fagundes
AppPublisherURL=https://github.com/m4Fagundes/grid-image-analyzer
AppSupportURL=https://github.com/m4Fagundes/grid-image-analyzer

; Instalar para o usuário atual sem precisar de administrador (opcional, bom para não pedir senha)
; Se quiser que instale no "Program Files" (requer Admin), mude para 'PrivilegesRequired=admin' e 'DefaultDirName={autopf}\GridAnalyzer'
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\GridAnalyzer
DefaultGroupName=Grid Image Analyzer

; Configurações do arquivo gerado
OutputDir=build_installer
OutputBaseFilename=GridAnalyzer_Setup
Compression=lzma2/ultra
SolidCompression=yes
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayIcon={app}\GridAnalyzer.exe

; Aparência
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; IMPORTANTE: Certifique-se de que rodou "pyinstaller main_release.spec" antes de gerar o instalador!
; Pega todos os arquivos gerados no modo "onedir" do PyInstaller
Source: "dist\GridAnalyzer\GridAnalyzer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\GridAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTA: Não use "ignoreversion" em arquivos de sistema compartilhados

[Icons]
Name: "{group}\Grid Image Analyzer"; Filename: "{app}\GridAnalyzer.exe"
Name: "{group}\{cm:UninstallProgram,Grid Image Analyzer}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Grid Image Analyzer"; Filename: "{app}\GridAnalyzer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GridAnalyzer.exe"; Description: "{cm:LaunchProgram,Grid Image Analyzer}"; Flags: nowait postinstall skipifsilent
