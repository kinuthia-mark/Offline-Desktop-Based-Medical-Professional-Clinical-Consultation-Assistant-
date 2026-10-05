# ADR-013: Diagnosis suggestions on, and a check for misheard medicine names

- Status: accepted; clinician scoring of the suggestions is still to do
- Date: 2026-10-05
- Requirement IDs: FR-05, FR-13, NFR-02 (AMD-32, AMD-38)
- Evidence: `docs/eval/report-mark-pc-suggestions-speech.md`,
  `docs/eval/report-mark-pc-suggestions-v2-speech.md`, `docs/spikes/asr-prompt-mark-pc.json`,
  `src/clinassist/medcheck.py`, `src/clinassist/vocabulary.py`, `tests/test_medcheck.py`,
  `tests/test_soap_generator.py`

## Context
The proposal's core output is a list of probable diagnoses with management strategies (section
1.3.1). They were off by default because they add generated text and so drafting time (ADR-002).
In the first test installation the Diagnostics tab was empty, and with no diagnosis stated by the
clinician the AI assessment read "not stated", so the program looked as if the AI did nothing.

The evaluation (ADR-011) also showed that speech-to-text mistakes in medicine names pass into the
note unchanged: "Glendamycin" for clindamycin, "Nitrofuranta" for nitrofurantoin. The note
generator copies the transcript faithfully, which is what it should do, so the fix has to come
earlier.

## Suggestions: what was measured
All runs: the 8 synthetic consultations read by the Windows voices, Whisper small, MedGemma 4B,
reference PC (ADR-011).

| Run | Fact recall | Critical recall | Median draft time | Retries |
|---|---|---|---|---|
| Suggestions off | 89.9% | 90.0% | 53.3 s | none |
| Suggestions on, short prompt | 91.1% | 91.4% | 76.1 s | none |
| Suggestions on, longer prompt ("v2") | 91.7% | 90.0% | 118.3 s | 3 of 8 |

- **The note itself did not get worse** with suggestions on. Drafting took about 23 seconds longer.
- The run with suggestions shows 3 "contradicted negatives" in one consultation. They come from the
  return precautions ("come back if you have vomiting, chest pain...") written under Subjective;
  the scorer reads them as symptoms. It is a section mistake rather than an invented symptom, and
  the clinician sees and edits it at review.
- **The longer prompt was worse.** It listed what not to suggest (allergies, prevention,
  conditions a test ruled out). The model then listed symptoms ("Fever; Headache") instead of
  conditions, needed a second attempt in 3 of 8 consultations, and drafting took 55% longer. It was
  dropped.
- **Non-diagnoses are removed in code instead.** In the short-prompt run, 6 of 24 suggestions were
  not conditions (for example a sulfa allergy or "tetanus prevention" listed as a diagnosis).
  `soap_generator._NOT_A_DIAGNOSIS` removes a suggestion whose diagnosis names an allergy,
  intolerance, exposure, prevention, vaccination or risk. Two doubtful suggestions remain
  ("Pregnancy", "Tetanus" after a wound); the clinician decides on those.

## Medicine names: what was measured
1. **A vocabulary hint for Whisper did not help.** Whisper can be given a short text to expect
   (`initial_prompt`); the hint listed 75 common medicines (`vocabulary.speech_prompt`). On the 8
   consultations, medicine names heard correctly went from 16 of 23 to 17 of 23, word error rate
   was unchanged (2.5% and 2.6%), and transcription was 7% slower
   (`spikes/asr_prompt_spike.py`). The option stays in the code, off.
2. **A check at transcript review was built instead** (`clinassist.medcheck`). A word is flagged
   when it is six letters or longer, not an English word (the offline dictionary already in the
   program), not a known medicine, and close in spelling to one (Python's `difflib`, similarity
   0.70 or more). The flag appears above the transcript, for example
   `"Glendamycin" (clindamycin?)`. Nothing is changed automatically.
3. **Threshold.** Tried on 40 texts: the 8 correct scripts and the 32 notes from four evaluation
   runs. At 0.65, 0.70 and 0.75 the same words were flagged, with no flag on any correct script.
   0.70 was kept because it also catches "amlotyping" (amlodipine), which scores exactly 0.70. The
   flags included the real mistakes (Nitrofuranta, Glendamycin, bechlametisone, Coetrimoxazole,
   fluocloxicillin) and two false ones, an American spelling ("beclomethasone") and a drug class
   ("statin"); valid spellings and class names are now listed in `vocabulary.ALSO_CORRECT`.

## Decision
- Suggestions are **on by default** (`config.ai_suggestions`), with the short prompt and the
  code filter. They appear in the Diagnostics tab, marked as AI suggestions for the clinician, and
  never go into the assessment the clinician approves (FR-13).
- When the clinician states no diagnosis, the AI assessment box explains that it is blank because
  nothing was stated, and points to the Diagnostics tab.
- The medicine-name check runs on the transcript as it is reviewed and edited.

## MedGemma terms
MedGemma is distributed under the Health AI Developer Foundations terms. The installer shows the
use restrictions those terms require redistributors to pass on (section 3.2) before installation,
installs the full terms and the required notice in `licences\`, and states that the program is not
a medical device and its output is a draft for a qualified clinician (`release/terms.txt`,
`release/NOTICE.txt`).

## Limits
- The suggestions are scored by the harness only for the note around them; whether they are
  clinically sensible needs the clinician scoring sheet (`docs/eval/clinician-sheet-*.md`, which
  now has a row for them).
- The medicine check misses a mishearing that produces a real English word ("sulfur" for sulfa),
  and cannot suggest a medicine missing from the list. The list is a working list for this
  prototype; a pharmacist should review it.
- Synthetic voices are clearer than real consultations. Real voices may produce more misheard
  names, and more flags.
