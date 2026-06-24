; ============================================================================
; Multi Voice Studio - Inno Setup script
;   PyInstaller の onedir 出力（F:\mvs-build\dist\MultiVoiceStudio）を
;   1つのインストーラ（Setup.exe）にまとめる。MSIX の制約を回避できる方式。
;
;   使い方:
;     1) Inno Setup をインストール（https://jrsoftware.org/isdl.php）
;     2) このファイル（packaging\MultiVoiceStudio.iss）を Inno Setup で開く
;     3) メニューの Build → Compile（または F9）
;     4) 出力: F:\mvs-build\installer\MultiVoiceStudio-Setup.exe
;
;   ※ 17GB あるのでコンパイルに時間がかかり、出力も大きい（数GB）。
; ============================================================================

#define MyAppName "Multi Voice Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Hiroyura"
#define MyAppExe "MultiVoiceStudio.exe"
#define SourceDir "F:\mvs-build\dist\MultiVoiceStudio"

[Setup]
AppId={{9B6C9F60-1234-4ABC-9DEF-MULTIVOICESTUD}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=F:\mvs-build\installer
OutputBaseFilename=MultiVoiceStudio-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english";  MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; dist フォルダ一式をまるごと取り込む
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
