# ADR-012: The Windows installer and the offline model bundle

- Status: accepted; a test installation on a second PC is still to do
- Date: 2026-10-05
- Requirement IDs: NFR-01, NFR-04, NFR-07, NFR-08 (proof of concept)
- Evidence: `release/`, `src/clinassist/bundle.py`, `src/clinassist/selftest.py`,
  `tests/test_bundle.py`, the build log of `release/build_release.ps1`

## Context
The product is a native Windows program (AMD-15); a clinic must be able to install it without the
internet and without a command line. Clinic PCs have no development tools, the models are large
(Whisper small 464 MB, MedGemma 4B 3.2 GB), and the firewall rules (ADR-010) need administrator
rights. The proposal does not describe distribution.

## Options considered
1. **One self-contained .exe with the models inside.** Simple to hand over, but over 4 GB, slow to
   build and to start, and close to Inno Setup's single-file limit.
2. **An installer plus a separate model bundle**, both on the same drive. The installer stays
   small; the bundle is checked file by file before anything is installed.
3. **Docker or a web install.** Rejected: Docker Desktop is heavy on clinic PCs and cannot easily
   reach the microphone (AMD-15); a web install needs the internet.

## Decision
Option 2.

- **PyInstaller, one folder** (`release/clinassist.spec`): `ClinAssist.exe` (the application, no
  console) and `ClinAssist-check.exe` (start-up checks, self-test and bundle check, for support
  staff and the installer). One folder rather than one file, so the program is not unpacked to a
  temporary folder at every start.
- **Offline bundle** (`clinassist.bundle`): the Whisper model, Ollama's manifest and model files for
  `medgemma:4b`, the model's licence text, and optionally Ollama's own installer. `manifest.json`
  lists every file's size and SHA-256. Ollama names each model file after its SHA-256, so a
  swapped file is caught even if the manifest were rewritten to match.
- **Inno Setup** (`release/clinassist.iss`): one administrator prompt; the MedGemma licence must be
  accepted; **the bundle is checked first** (`release/verify_bundle.ps1`, plain PowerShell) and
  nothing is installed if a file is missing or changed; the program goes to Program Files, the
  Whisper model next to it, and the Ollama model files to Ollama's default folder
  (`%USERPROFILE%\.ollama\models`); Ollama is installed silently if it is missing and its
  installer is in the bundle; **the firewall rules are created for `ClinAssist.exe` and Ollama**
  and removed again on uninstall. Patient records in the user's
  data folder are not touched by uninstalling.
- **The program finds its models next to itself**, wherever it is started from. The first version
  looked in a folder relative to the current directory, which would have failed once installed.
- **Self-test** (`--self-test`): uses each heavy part once (window library, encrypted database,
  password hashing, dictionary, microphone library, speech model with its silence detector).
  Packaging can leave out a library or data file without any start-up check noticing.
- **Model files go where Ollama looks by default.** A first version set the `OLLAMA_MODELS`
  variable instead; on a fresh PC, Ollama is started during the installation and would not have
  seen a variable set in the same session, so it would not have found the model until a restart.
  Files that already exist are left alone: they are named by their SHA-256, so they are identical,
  and a running Ollama may have them open.
- **A clean-machine test on every change to the installer** (`.github/workflows/installer.yml`):
  on a fresh GitHub Windows machine it builds the program and a stand-in bundle
  (`release/make_test_bundle.py`: same layout and checksums, tiny files), checks that a damaged
  bundle is refused with nothing installed, installs silently, checks every file and the firewall
  rule for `ClinAssist.exe`, runs the installed checks, then uninstalls and checks that the
  firewall rules are gone. Windows Sandbox would do the same locally, but it needs Windows Pro and
  the reference PC runs Windows 11 Home.
- **One build command** (`release/build_release.ps1`): tests, program folder, bundle, both bundle
  checks, the self-test of the built program, then the installer. It stops at the first failure.

## Evidence (reference PC)
| Item | Result |
|---|---|
| Installer (`ClinAssist-Setup.exe`) | 108 MB |
| Installed program folder | 368 MB |
| Offline bundle | 3.6 GB, 11 files, all with SHA-256 |
| Bundle check, Python and PowerShell | both "bundle_ok"; both flag the same one-bit change in tests |
| Self-test of the built program | all six parts work, including the speech model and silence detector |
| Start-up check of the built program | runs; reports the speech model missing until it is installed beside the program, as intended |

The build script stopped correctly at its first step once, when a new error code had no message
(the message-coverage test failed); the message was added and the build rerun.

Building the installer found a weakness in the air-gap check: it counted any ClinAssist firewall
rule, so a rule for `python.exe` would have made `ClinAssist.exe` look protected. The check now
requires a rule for the application itself (`airgap.rules_for_program`); `ClinAssist-check.exe`
looks for the rule of `ClinAssist.exe` beside it, not for its own.

The bundle check first used PowerShell's `Get-FileHash`, which was missing on GitHub's machines
(it is defined in a module that a different PowerShell module path hides). It now computes SHA-256
through .NET, which every Windows has, and checks the 3.6 GB bundle in about 5 s.

## Limits
- **Not yet installed on a second, clean PC.** The installer has been built and its parts tested,
  but an end-to-end installation on another Windows machine, ideally one that has never had
  Python or Ollama, is the real test.
- The Ollama model is installed for the user who runs the installer. Another Windows user on the
  same PC would need the model copied for them too.
- The installer is not code-signed, so Windows SmartScreen will warn that the publisher is unknown.
  Signing needs a certificate.
- Ollama's own installer is 1.58 GB and is added to the bundle only when needed (`-OllamaSetup`).
- The clean-machine test uses stand-in model files; the real models are tested by the build's
  self-test and by installing on the reference PC.

## Consequences
- AMD-15 is applied: a native Windows installer, no Docker.
- The firewall rules no longer need a command line on clinic PCs (ADR-010).
- Release steps for the report: build, copy `ClinAssist-Setup.exe` and `bundle\` together, install,
  run `ClinAssist-check.exe --self-test`.
