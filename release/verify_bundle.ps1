# Checks every file of the offline model bundle against manifest.json before installation
# (ADR-012). The installer runs this first; if anything is missing or changed, nothing is
# installed. Plain PowerShell, so it works before the application itself is on the PC.
#
#   powershell -ExecutionPolicy Bypass -File release\verify_bundle.ps1 -Bundle D:\bundle
#
# Exit code 0: every file present and unchanged. 1: a problem, listed on the screen.

param([Parameter(Mandatory = $true)][string]$Bundle)

$manifestPath = Join-Path $Bundle "manifest.json"
if (-not (Test-Path $manifestPath)) {
    Write-Output "The model bundle was not found next to the installer: $manifestPath"
    exit 1
}
$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
$problems = @()
foreach ($entry in $manifest.files.PSObject.Properties) {
    $path = Join-Path $Bundle ($entry.Name -replace "/", "\")
    if (-not (Test-Path $path)) { $problems += "missing: $($entry.Name)"; continue }
    if ((Get-Item $path).Length -ne $entry.Value.bytes) { $problems += "wrong size: $($entry.Name)"; continue }
    $hash = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower()
    if ($hash -ne $entry.Value.sha256) { $problems += "changed: $($entry.Name)" }
}
if ($problems.Count) {
    Write-Output "The model bundle is damaged. Copy it again, then run the installer again."
    $problems | ForEach-Object { Write-Output "  $_" }
    exit 1
}
Write-Output "bundle_ok"
exit 0
