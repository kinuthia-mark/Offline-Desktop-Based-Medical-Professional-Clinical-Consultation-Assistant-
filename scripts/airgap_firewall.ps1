# Windows Firewall rules that stop the application and Ollama from sending anything out (NFR-01,
# AMD-10, ADR-010). Run once, in PowerShell opened with "Run as administrator":
#
#   powershell -ExecutionPolicy Bypass -File scripts\airgap_firewall.ps1 -Apply
#   powershell -ExecutionPolicy Bypass -File scripts\airgap_firewall.ps1 -Show
#   powershell -ExecutionPolicy Bypass -File scripts\airgap_firewall.ps1 -Remove
#
# One outbound "block" rule is made per program. Windows does not apply firewall rules to
# loopback traffic (127.0.0.1), so the application can still talk to Ollama on the same PC.
# Blocking Ollama also stops it downloading models or checking for updates; new models are added
# offline by an administrator (FR-10b).
#
# -Program adds further programs, for example the installed application's .exe.

param(
    [switch]$Apply,
    [switch]$Remove,
    [switch]$Show,
    [string[]]$Program = @()
)

$Prefix = "ClinAssist block outbound"

function Get-DefaultPrograms {
    $list = @()
    # The Python that runs the application. A virtual environment's python.exe is a small
    # launcher that starts the base interpreter, so the base interpreter is the one to block.
    $python = & python -c "import sys; print(getattr(sys, '_base_executable', sys.executable))" 2>$null
    if ($python) { $list += $python.Trim() }
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    foreach ($exe in @("ollama.exe", "ollama app.exe")) {
        $path = Join-Path $ollama $exe
        if (Test-Path $path) { $list += $path }
    }
    return $list
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Show -or -not ($Apply -or $Remove)) {
    $rules = Get-NetFirewallRule -DisplayName "$Prefix*" -ErrorAction SilentlyContinue
    if (-not $rules) { Write-Output "No ClinAssist rules."; exit 0 }
    foreach ($r in $rules) {
        $app = ($r | Get-NetFirewallApplicationFilter).Program
        Write-Output ("{0} | enabled: {1} | {2} {3} | {4}" -f $r.DisplayName, $r.Enabled, $r.Direction, $r.Action, $app)
    }
    exit 0
}

if (-not (Test-Admin)) {
    Write-Error "Run this in PowerShell opened with 'Run as administrator'."
    exit 1
}

if ($Remove) {
    Get-NetFirewallRule -DisplayName "$Prefix*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Write-Output "Removed the ClinAssist rules."
    exit 0
}

$programs = @(Get-DefaultPrograms) + $Program | Where-Object { $_ } | Select-Object -Unique
foreach ($path in $programs) {
    if (-not (Test-Path $path)) { Write-Warning "Not found, skipped: $path"; continue }
    $name = "$Prefix - " + [IO.Path]::GetFileName($path)
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $name -Direction Outbound -Action Block -Program $path `
        -Profile Any -Description "Offline clinical assistant: no traffic may leave this PC." | Out-Null
    Write-Output "Blocked outbound: $path"
}
