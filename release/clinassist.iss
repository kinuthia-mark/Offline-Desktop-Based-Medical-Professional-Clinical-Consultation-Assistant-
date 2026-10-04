; Windows installer for the Offline Clinical Consultation Assistant (Inno Setup 6, ADR-012).
;
; What a clinic receives, for example on a USB drive:
;   ClinAssist-Setup.exe      this installer (the application, about 600 MB)
;   bundle\                   the offline models, made by clinassist.bundle.build_bundle:
;                               manifest.json, models\, ollama-models\, licences\,
;                               and ollama\OllamaSetup.exe if Ollama should be installed too
;
; The models stay outside the .exe (about 3.6 GB) and are copied from bundle\ after every file has
; been checked against manifest.json. Nothing is downloaded during installation.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\build"
#endif

[Setup]
AppId={{6B0C2B8A-4E7B-4F57-9C6A-3D2B1F0C9A11}
AppName=Offline Clinical Consultation Assistant
AppVersion={#AppVersion}
AppPublisher=Mark Kinuthia
DefaultDirName={autopf}\ClinAssist
DefaultGroupName=Clinical Consultation Assistant
; Administrator rights are needed once: for Program Files and for the firewall rules.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BuildDir}
OutputBaseFilename=ClinAssist-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The model's licence terms must be accepted before installing.
LicenseFile={#BuildDir}\bundle\licences\medgemma.txt
; OLLAMA_MODELS is set below; other programs are told the environment changed.
ChangesEnvironment=yes
UninstallDisplayName=Offline Clinical Consultation Assistant

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The application folder built by PyInstaller.
Source: "{#BuildDir}\dist\ClinAssist\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; The bundle checker, unpacked to a temporary folder and run before anything is installed.
Source: "verify_bundle.ps1"; Flags: dontcopy
; Models, copied from the bundle beside the installer ("external": not inside the .exe).
Source: "{src}\bundle\models\*"; DestDir: "{app}\models"; Flags: external recursesubdirs
Source: "{src}\bundle\ollama-models\*"; DestDir: "{commonappdata}\ClinAssist\ollama-models"; Flags: external recursesubdirs
Source: "{src}\bundle\licences\*"; DestDir: "{app}\licences"; Flags: external recursesubdirs

[Registry]
; Ollama reads its models from here, for every user of the PC.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: string; ValueName: "OLLAMA_MODELS"; ValueData: "{commonappdata}\ClinAssist\ollama-models"; Flags: uninsdeletevalue

[Icons]
Name: "{group}\Clinical Consultation Assistant"; Filename: "{app}\ClinAssist.exe"
Name: "{autodesktop}\Clinical Consultation Assistant"; Filename: "{app}\ClinAssist.exe"; Tasks: desktopicon

[Run]
; Install Ollama silently if the bundle includes it and it is not already on the PC.
Filename: "{src}\bundle\ollama\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART"; StatusMsg: "Installing the local model service (Ollama)..."; Check: NeedsOllama; Flags: waituntilterminated
; Block outbound traffic for the application and Ollama (ADR-010). Loopback still works.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\airgap_firewall.ps1"" -Apply -Program ""{app}\ClinAssist.exe"""; StatusMsg: "Turning on offline protection..."; Flags: runhidden waituntilterminated
Filename: "{app}\ClinAssist.exe"; Description: "Start the application"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Remove the firewall rules this installer created.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\airgap_firewall.ps1"" -Remove"; RunOnceId: "RemoveFirewallRules"; Flags: runhidden waituntilterminated

[Code]
function NeedsOllama: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\bundle\ollama\OllamaSetup.exe')) and
    not FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'));
end;

// Check the bundle before installing anything. If a file is missing or changed, stop here.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  ExtractTemporaryFile('verify_bundle.ps1');
  if not Exec('powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\verify_bundle.ps1') +
      '" -Bundle "' + ExpandConstant('{src}\bundle') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    Result := 'The model bundle next to this installer is missing or damaged. ' +
      'Copy the whole "bundle" folder again, then run the installer again.';
end;
