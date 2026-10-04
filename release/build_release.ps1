# Builds the installer and the offline bundle (ADR-012). Run from the project folder:
#
#   powershell -ExecutionPolicy Bypass -File release\build_release.ps1
#   powershell -ExecutionPolicy Bypass -File release\build_release.ps1 -OllamaSetup C:\path\OllamaSetup.exe
#
# Steps, stopping at the first failure:
#   1. the full test suite
#   2. the application folder (PyInstaller)
#   3. the offline bundle (models with checksums; Ollama's installer if given)
#   4. the bundle check and the start-up check, run with the built program
#   5. the installer (Inno Setup)
# Output in build\: ClinAssist-Setup.exe and bundle\, to be copied together.

param([string]$OllamaSetup = "")

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"
$build = Join-Path (Get-Location) "build"

function Step($text) { Write-Output ""; Write-Output "=== $text" }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

Step "1. Tests"
& $python -m pytest -q -p no:cacheprovider; Check "Tests"

Step "2. Application folder"
& $python -m PyInstaller --noconfirm --clean release\clinassist.spec --distpath "$build\dist" --workpath "$build\work"
Check "PyInstaller"

Step "3. Offline bundle"
& $python -c "from clinassist.bundle import build_bundle; m = build_bundle(r'$build\bundle'); print(len(m['files']), 'files')"
Check "Bundle"
if ($OllamaSetup) {
    New-Item -ItemType Directory -Force "$build\bundle\ollama" | Out-Null
    Copy-Item $OllamaSetup "$build\bundle\ollama\OllamaSetup.exe"
}

Step "4. Checks with the built program"
& "$build\dist\ClinAssist\ClinAssist-check.exe" --verify-bundle "$build\bundle"; Check "Bundle check"
& powershell -NoProfile -ExecutionPolicy Bypass -File release\verify_bundle.ps1 -Bundle "$build\bundle"; Check "PowerShell bundle check"
# The self-test uses every heavy part of the built program. The speech model is put beside it
# the way the installer would, then removed again so it is not packed into the installer.
Copy-Item -Recurse "$build\bundle\models" "$build\dist\ClinAssist\models"
try {
    & "$build\dist\ClinAssist\ClinAssist-check.exe" --self-test; Check "Self-test"
} finally {
    Remove-Item -Recurse -Force "$build\dist\ClinAssist\models"
}

Step "5. Installer"
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 is not installed." }
& $iscc "/DBuildDir=$build" release\clinassist.iss; Check "Inno Setup"

Write-Output ""
Write-Output "Done: $build\ClinAssist-Setup.exe and $build\bundle\ (copy both together)."
