# The second round of the public-dataset evaluation (ADR-016): the same datasets after the
# fixes found in the first round, and Whisper medium on the Kenyan clips. Resumes if restarted.
#
#   powershell -ExecutionPolicy Bypass -File eval\run_public_v2.ps1

$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"
$results = "docs\eval\public"

function Step($text) { Write-Output ""; Write-Output "=== $(Get-Date -Format 'HH:mm') $text" }

Step "PriMock57 after the fixes (57 consultations, from speech)"
& $python eval\run_public.py primock57 --label mark-pc-v2
Step "ACI-Bench after the fixes (40 dialogues)"
& $python eval\run_public.py aci --label mark-pc-v2 --limit 40
Step "AfriSpeech-200, Kenyan accents, Whisper medium"
& $python eval\run_public.py afrispeech --label mark-pc --whisper medium
Step "Rescore and write the reports"
& $python eval\run_public.py rescore --file "$results\primock57-mark-pc-v2-speech.json"
& $python eval\run_public.py rescore --file "$results\aci-bench-test1-mark-pc-v2.json"
& $python eval\report_public.py (Get-ChildItem "$results\*-mark-pc*.json" | Where-Object { $_.Name -notlike "*retry-window*" } | ForEach-Object { $_.FullName })
Step "Done"
