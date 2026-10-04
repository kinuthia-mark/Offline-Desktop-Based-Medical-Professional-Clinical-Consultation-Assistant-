# Read a synthetic consultation aloud with the Windows text-to-speech voices and save it as a
# 16 kHz mono WAV, for measuring speech-to-text (ADR-007).
#
#   powershell -File spikes/make_speech.ps1 spikes/transcripts/synthetic_consult_01.txt spikes/audio/consult_01.wav
#
# Lines starting with "Doctor:" use one voice and "Patient:" another, so the two speakers sound
# different. The speaker labels themselves are not spoken. Lines starting with "#" are skipped.
# The output folder is ignored by git (*.wav); audio is never committed.

param(
    [Parameter(Mandatory = $true)][string]$Transcript,
    [Parameter(Mandatory = $true)][string]$OutWav,
    [string]$DoctorVoice = "Microsoft David Desktop",
    [string]$PatientVoice = "Microsoft Hazel Desktop"
)

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)

$dir = Split-Path -Parent $OutWav
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

$prompt = New-Object System.Speech.Synthesis.PromptBuilder
foreach ($line in Get-Content -Encoding UTF8 $Transcript) {
    if ($line -match '^\s*#' -or $line.Trim() -eq '') { continue }
    if ($line -match '^\s*(Doctor|Patient)\s*:\s*(.*)$') {
        $voice = if ($Matches[1] -eq 'Doctor') { $DoctorVoice } else { $PatientVoice }
        $prompt.StartVoice($voice)
        $prompt.AppendText($Matches[2])
        $prompt.EndVoice()
    } else {
        $prompt.AppendText($line)
    }
    $prompt.AppendBreak([System.Speech.Synthesis.PromptBreak]::Medium)
}

$synth.SetOutputToWaveFile((Resolve-Path -LiteralPath $dir).Path + "\" + (Split-Path -Leaf $OutWav), $format)
$synth.Speak($prompt)
$synth.SetOutputToNull()
$synth.Dispose()
Write-Output "Wrote $OutWav"
