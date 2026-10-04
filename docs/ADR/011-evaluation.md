# ADR-011: Evaluating the notes with scripted consultations

- Status: accepted; clinician scoring and human-voice recordings still to do
- Date: 2026-10-05
- Requirement IDs: FR-05, NFR-03, NFR-06
- Evidence: `eval/scenarios/`, `eval/run_eval.py`, `src/clinassist/evaluation.py`,
  `tests/test_evaluation.py`, `docs/eval/results-mark-pc-speech.json`,
  `docs/eval/results-mark-pc-script.json`, `docs/eval/report-*.md`, `docs/eval/clinician-sheet-*.md`

## Context
Until now note quality rested on reading a handful of notes (ADR-002). The proposal asks for an
evaluation that matches the system's task (AMD-06). PubMedQA tests answering questions, not writing
notes, and public dialogue-to-note sets (ACI-Bench, PriMock57) are in English clinics abroad with
licences to check. The handoff asked for scripted consultations with key-fact lists, and ADR-007
showed the generator must be fed what Whisper really produces: unlabelled text with digits.

## Decision
- **Eight synthetic consultations** set in Kenyan primary care (`eval/scenarios/`): fever with
  malaria to be excluded, hypertension and diabetes follow-up (1,472 words), a child with diarrhoea
  (the mother answers), a bladder infection with a sulfa allergy, an asthma attack with an aspirin
  allergy, a possible tuberculosis, leg cellulitis with a penicillin allergy, and an antenatal
  visit. 168 key facts, 70 marked critical (allergies, medicines and doses, key readings, orders,
  safety-net advice).
- **Traps** in each script: a relative's illness (sister's chickenpox, cousin's TB, brother's
  smoking), a medicine the doctor decided against (ciprofloxacin, co-trimoxazole, amoxicillin), a
  diagnosis nobody made (TB not yet diagnosed, malaria only to be tested), and details a note might
  invent (the wife being present, a dose where none was given).
- **The real pipeline**: each script is read aloud by the Windows voices, transcribed by Whisper
  small, screened by the input guard and drafted by MedGemma through the real controller, with up
  to two attempts. A second run feeds the labelled script instead, to show what the missing speaker
  labels and speech-to-text errors cost.
- **Scoring** (`clinassist.evaluation`): both sides normalised (lower case, numbers as digits,
  British and American spelling, "500mg" and "500 mg"); a fact is found when every group of
  phrases matches; "no allergies" is found when allergies are mentioned and every mention is
  negated; denied symptoms mentioned without a negation are contradictions; traps fire on an
  un-negated, unexcused mention. Questions and "if" clauses state nothing and are skipped. Every
  flagged item is reported with the clause that triggered it, for a person to confirm.
- **A self-check**: scored against its own script, every scenario must find every fact and fire no
  trap. Two facts are listed as exceptions because the dialogue only implies them ("Any allergies?
  - No."; "I would like you to stop it").
- **A clinician scoring sheet** per run lists every note with four items to score from 1 to 5
  (accurate, complete, organised, safe after review). It is generated, not filled in.

## Evidence (reference PC, MedGemma 4B Q4_K_M, Whisper small, firewall rules on)
| Measure | From speech (Whisper) | From the labelled script |
|---|---|---|
| Notes produced | 8 of 8 | 8 of 8 |
| Needed the second attempt | 1 (child diarrhoea) | 1 (antenatal) |
| Key facts found | **89.9%** (151 of 168) | **92.3%** (155 of 168) |
| Critical facts found | **90.0%** (63 of 70) | **97.1%** (68 of 70) |
| Facts in the wrong SOAP section | 16 | 6 |
| Denied symptoms contradicted | 0 | 0 |
| Traps fallen into | 0 | 0 |
| Speech-to-text word error, normalised (mean of 8) | 2.5% | (same audio) |
| Median time to draft the note (about 230 words) | 53 s | 51 s |
| Long consultation (1,386 to 1,472 words), transcribe and draft | 111 s + 125 s | 131 s + 182 s |

**Critical facts missed from speech, each read in the note:**
- **Speech-to-text errors copied into the note.** "allergic to sulfur drugs" for sulfa;
  "Nitrofuranta 100 mg" for nitrofurantoin; "Glendamycin 300 mg" for clindamycin. Whisper misheard
  the words and the model faithfully kept them. Only the transcript review (gate 1) catches these.
- **Omissions by the model.** Allergies left out of the long hypertension note (in both runs, as in
  ADR-002); the child's age (18 months); the pregnancy test result; "speaks in full sentences" in
  the asthma examination (both runs).

**Scoring corrections made after reading the notes** (all recorded, to avoid quietly tuning the
test to the model): two traps had fired wrongly ("smoking cessation" read as a current smoker; "does
not think she is pregnant" matched an exact phrase), and three facts were too narrow ("coughing" for
"cough"; "does not have allergies" and "no medicines or allergies"; "gene expert", the way Whisper
writes GeneXpert). Allergy facts were then changed to the negation rule above. The first scores,
before any correction, were: from speech 87.5% of facts and 84.3% of critical facts, with 1 trap;
from the script 92.3% and 97.1%, with 1 trap. Both traps were the scorer's errors, not the notes'.

Building the self-check also exposed a bug in the shared number reading: "one hundred and four"
became "100 and 4". It is fixed (`metrics._digits`); recomputing ADR-007's word error rates from
the saved transcripts gave the same figures, because those two scripts contain no such numbers.

Tests: the self-check on all eight scripts, matching, negation, conditionals, questions, "not
stated", traps, exact traps, the denied-fact rule and section limits. Mutation checks, 9 of 9 caught
(the first run missed one: a test meant to check whole-word matching used an example that could
never fail; the example was replaced).

## Limits (state these in the report)
- **Synthetic speech.** The Windows voices are clear and steady. Real voices, accents, background
  noise and overlapping speech will produce more speech-to-text errors, and this run already shows
  that such errors flow straight into the note.
- **Eight consultations, one run each, one model.** Enough to find the kinds of error, not to give
  a rate with a confidence interval. Generation used a fixed seed, so repeated runs are similar but
  not a fresh sample.
- **The scripts and the fact lists were written by the same author as the scorer.** The facts are
  plausible, but a clinician should review them; scoring is by text rules, confirmed by reading.
- **Not measured automatically:** statements invented outside the traps, wrong but present values
  (a fact with a wrong number is simply missed), and clinical usefulness. The clinician sheet is
  for that.
- Suggestions (AMD-32) were off in these runs; `medgemma1.5:4b` was not compared (it needs a
  download, which the firewall rules block until they are lifted for it).

## Consequences
- FR-05 has a measured faithfulness check; NFR-03 and NFR-06 have figures on eight consultations.
- The strongest finding for the design is that speech-to-text errors in medicine names pass into
  the note unchanged. That supports gate 1 and suggests a further aid: flagging medicine names that
  are not in an offline medicines list (AMD-38).
- Next: recordings of people reading the same scripts (synthetic content, real voices), and the
  clinician sheet scored by at least two clinicians.
