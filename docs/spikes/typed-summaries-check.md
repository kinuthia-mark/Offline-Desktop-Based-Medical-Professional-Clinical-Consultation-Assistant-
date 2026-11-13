# Check: drafting from typed summaries

13 Nov 2026, reference PC (Ryzen 5 5625U, 8 GB, CPU only), `medgemma:4b`, suggestions on, run
with `scripts/try_note.py --suggestions`.

The 16 summaries in `spikes/transcripts/typed/` are written the way a clinician types: history,
examination and bedside tests in short sentences, with no diagnosis. Four were drafted, one per
condition group:

| Summary | Attempt 1 | Attempt 2 (penalty 1.1) | First suggestion |
|---|---|---|---|
| 01 fever, chills, mRDT positive | note in 47 s, no flags | not needed | malaria |
| 08 burning urine, dipstick positive | repetition_detected after 35 s | note in 44 s, no flags | urinary tract infection |
| 11 hypertension review | repetition_detected after 52 s | note in 52 s, no flags | hypertension |
| 15 cough, fever, crackles | note in 48 s, no flags | not needed | pneumonia |

A note came out for all four within two attempts, and the first suggestion matched the assessment
written for the case each time. Two of four needed the second attempt, which in the app is the
"Try the model again" button. The AI assessment section reads "not stated" in every note because
the summaries contain no diagnosis; the diagnosis comes from the suggestions and the clinician.

Limits: four drafts, one run each, so this shows the summaries work, not how often attempt 1 fails
on typed input. The other 12 summaries were not drafted.
