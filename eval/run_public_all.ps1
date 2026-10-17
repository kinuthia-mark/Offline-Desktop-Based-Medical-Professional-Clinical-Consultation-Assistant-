# Runs every public-dataset evaluation in order, then rescores and writes the reports (ADR-016).
# Each step resumes where it stopped, so this can be started again after an interruption.
#
#   powershell -ExecutionPolicy Bypass -File eval\run_public_all.ps1 -Label mark-pc
#
# Takes several hours on the reference PC (PriMock57 alone is about 8.6 hours of audio). Needs
# Ollama running with the model, the Whisper model in models\, and the datasets in datasets\.

param([string]$Label = "mark-pc")

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"
$results = "docs\eval\public"

function Step($text) { Write-Output ""; Write-Output "=== $(Get-Date -Format 'HH:mm') $text" }

Step "AfriSpeech-200, Kenyan accents (speech-to-text only)"
& $python eval\run_public.py afrispeech --label $Label
Step "ACI-Bench test set 1 (40 dialogues)"
& $python eval\run_public.py aci --label $Label --limit 40
Step "PriMock57 (57 consultations, from speech)"
& $python eval\run_public.py primock57 --label $Label
Step "Rescore and write the reports"
& $python eval\run_public.py rescore --file "$results\aci-bench-test1-$Label.json"
& $python eval\run_public.py rescore --file "$results\primock57-$Label-speech.json"
& $python eval\report_public.py (Get-ChildItem "$results\*.json" | ForEach-Object { $_.FullName })
Step "Done"
