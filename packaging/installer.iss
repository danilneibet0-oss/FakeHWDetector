; Windows installer for the program folder built by tools/build_exe.py.
; Names, version and paths are passed by that script as /D defines (from fakehw/branding.py and
; fakehw/__init__.py), so nothing product-specific is hardcoded here. Build with:  python tools/build_exe.py

#ifndef AppName
  #error Compile through tools/build_exe.py: it passes AppName, AppVersion, Tagline, SourceDir, OutputDir, OutputName, PortableMarker
#endif

[Setup]
; AppId ties upgrades and the uninstaller to earlier installations: never change it, even if the product is renamed.
AppId={{FF4724B4-942C-47A7-92EA-CBDCC6A3638F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppComments={#Tagline}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install without administrator rights by default; the first page offers "all users" instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppName}.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; runtime files of an older version must not mix with the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; the portable marker never goes into an installation: installed copies keep settings in the user profile
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "{#PortableMarker}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Comment: "{#Tagline}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Comment: "{#Tagline}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
