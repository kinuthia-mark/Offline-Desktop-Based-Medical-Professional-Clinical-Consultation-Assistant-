# ADR-016: Evaluation on public datasets with real voices and clinicians' notes

- Status: accepted
- Date: 2026-10-16
- Requirement IDs: FR-02, FR-05, NFR-06 (AMD-06, AMD-30)
- Evidence: `docs/eval/public/`, `eval/run_public.py`, `eval/report_public.py`,
  `eval/ab_retry_window.py`, `src/clinassist/public_data.py`, `src/clinassist/public_scoring.py`,
  `tests/test_public_data.py`, `tests/test_public_scoring.py`

## Context
The first evaluation (ADR-011) used 8 consultations written for this project and read aloud by
the Windows computer voices. That tests the system's rules well, but it is a best case: synthetic
voices are clear, and the facts were written by the same person who wrote the scoring.

The proposal planned an evaluation on public dialogue-to-note data ("ACI-Bench or PriMock57,
check licences", AMD-06). Clinician scoring is not available for this project, so public data with
**real human voices** and **notes written by clinicians** becomes the main evidence of quality.

None of these datasets holds real patients' data. Medical dialogue datasets are recorded with
actors or simulated patients, because real consultations are protected health information. They
are real in what matters here: real voices, real accents, and real clinicians' notes.

## Datasets chosen
| Dataset | What it holds | Licence | What it tests |
|---|---|---|---|
| **PriMock57** (Korfiatis et al., ACL 2022; Babylon Health) | 57 mock primary-care consultations: real clinicians, actors as patients; audio per speaker, human transcripts, the clinician's note with highlights | CC BY 4.0 | the whole system from speech: Whisper, the gates, MedGemma; the note against the clinician's; whether the clinician's diagnosis is among the AI's suggestions |
| **AfriSpeech-200** (Olatunji et al., TACL 2023; Intron Health) | accented English, clinical and general, 13 African countries; 631 test clips from Kenyan speakers (Swahili, Luhya, Kikuyu, Kiswahili, Meru accents) | CC BY-NC-SA 4.0 | speech-to-text with Kenyan accents |
| **ACI-Bench** (Yim et al., Scientific Data 2023) | doctor-patient dialogues with expert-written notes; test set 1 has 40 | CC BY 4.0 | note writing from a typed dialogue |

Not used: the Fareez et al. 2022 OSCE recordings, whose licence could not be confirmed.

Every file was verified after download: PriMock57 audio by Git LFS's own check, AfriSpeech archives
against the SHA-256 Hugging Face publishes (three archives were cut off mid-download and were
resumed and verified). The datasets are kept in the git-ignored `datasets/` folder and never
committed. For AfriSpeech (share-alike) the committed results hold scores only; its sentences stay
beside the dataset, and the report quotes ten examples with the licence named.

## How it is scored
- **Speech-to-text:** word error rate against the human transcripts, after the same normalising as
  ADR-007. PriMock57's transcripts keep hesitations ("um"); these are removed from both sides.
  Many AfriSpeech readers said punctuation aloud ("comma", "full stop"), which the references
  leave out; both the raw rate and the rate without spoken punctuation are reported.
- **Note against the clinician's note:** ROUGE-1, ROUGE-2 and ROUGE-L (F1), the main automatic
  measure in the ACI-Bench paper, implemented in `public_scoring.py` (nothing could be installed
  offline). It rewards shared wording, so it is useful for comparing runs, not as a grade:
  PriMock57 clinicians write terse shorthand, the program writes full sentences.
- **Highlights:** PriMock57 clinicians marked each consultation's key points. A highlight counts
  as covered when most of its words are in the note, after clinical shorthand is spelled out
  ("3/7 hx" is three days' history, "LLQ" left lower quadrant).
- **Diagnosis:** the clinician's diagnosis is read from the note in the forms clinicians used
  ("Imp:", "DDx:", "Most likely diagnosis is", "suspecting"), with comments and ruled-out items
  dropped; 49 of 57 notes state one. A hit is the AI suggesting it, with typing slips
  ("labrynthitis") and a short list of exact synonyms ("chest infection" for LRTI) allowed, and
  related conditions not ("viral bronchitis" is not "upper respiratory infection").

All matching is automatic and approximate; each report lists every item so a person can check it.

## Round 1 results (reference PC, before any change)
| Measure | Result |
|---|---|
| **AfriSpeech, Kenyan speakers** (631 clips, 99.6 min, Whisper small) | 29.3% of words wrong raw, **20.0%** with spoken punctuation removed; clinical 21.6%, general 18.7% |
| **PriMock57** (57 consultations, from speech) | speech-to-text **14.6%** of words wrong; notes produced **48/57 (84%)**; the clinician's diagnosis among the AI's suggestions **21/41 (51%)**, always as the first suggestion; highlights covered 118/212 (56%); ROUGE-1/2/L 0.32/0.07/0.18; median 107 s speech-to-text and 98 s drafting |
| **ACI-Bench test 1** (40 dialogues) | notes produced **39/40**; ROUGE-1/2/L 0.42/0.17/0.24; median 73 s drafting |

For comparison, the synthetic voices of ADR-007 gave 0.7 to 1.6% of words wrong. Real speech is
an order of magnitude harder, and Kenyan-accented speech harder again.

Some AfriSpeech reference transcripts have their own errors (words run together, typing slips),
so the true word error rate is somewhat lower than reported; the report shows examples.

## What round 1 found, and what was changed
| Finding | Cause, found by keeping the model's raw output for the failed cases | Change |
|---|---|---|
| 11 of 48 PriMock57 notes had no suggestions, causing 10 of the 20 diagnosis misses; with suggestions present the clinician's diagnosis was the first suggestion in 21 of 31 | the instructions ended with "Reply with JSON only, with exactly these keys" (four sections), and the suggestions request came after it; on long consultations the model often obeyed the first | one format line listing every key, including suggestions (`FORMAT_WITH_SUGGESTIONS`) |
| A usable note rejected as invalid output | the model wrote the plan as a list of points | a section given as a list of text points is joined into lines; other shapes are still refused |
| 9 consultations without a note after two attempts, all "repetition detected" | real loops on long transcripts (1,100 to 2,900 words of natural speech), and the second attempt used the same settings as the first | the second attempt's repeat penalty looks back 256 tokens instead of Ollama's 64: on those 9 consultations, a note in 8 instead of 5, at the same speed (`primock57-retry-window-ab.json`) |
| Automatic matching missed correct diagnoses | strict word matching | typing slips and exact synonyms allowed (evaluation only) |

The prompt change is the smallest that removes the contradiction; ADR-013 showed that a longer
prompt made the suggestions worse.

## Round 2 results (after the changes)
The same datasets on the same PC, with the three changes above (`*-mark-pc-v2*`):

| Measure | Round 1 | Round 2 |
|---|---|---|
| PriMock57: notes produced | 48/57 (84%) | **56/57 (98%)** |
| PriMock57: needed the second attempt | 20 | 13 |
| PriMock57: clinician's diagnosis among the AI's suggestions | 21/41 (51%) | **38/48 (79%)**, 35 as the first suggestion (73%) |
| PriMock57: clinician's highlights covered | 118/212 (56%) | 129/238 (54%) |
| PriMock57: ROUGE-1 / ROUGE-2 / ROUGE-L | 0.32 / 0.07 / 0.18 | 0.33 / 0.08 / 0.18 |
| PriMock57: median drafting | 98 s | 99 s |
| ACI-Bench: notes produced | 39/40 | **40/40** |
| ACI-Bench: ROUGE-1 / ROUGE-2 / ROUGE-L | 0.42 / 0.17 / 0.24 | 0.43 / 0.17 / 0.24 |
| ACI-Bench: median drafting | 73 s | 78 s |

The changes did what they were for: almost every consultation now gets a note, and the AI's
suggestions include the clinician's diagnosis in four out of five, without slower drafting.
Highlight coverage and ROUGE did not move, which is expected: the changes were about getting a
complete reply, not about what the note says.

## Whisper medium on the Kenyan clips
| Kenyan speakers, 631 clips, 99.6 min | small (default) | medium |
|---|---|---|
| words wrong, raw / without spoken punctuation | 29.3% / **20.0%** | 24.8% / **16.2%** |
| clinical sentences (without spoken punctuation) | 21.6% | 18.0% |
| time to transcribe, against the length of the audio | 0.33 | 1.10 |

Medium makes about a fifth fewer errors but is 3.4 times slower on the reference PC's CPU: a
ten-minute consultation would take about six minutes to transcribe instead of under two. **Small
stays the default** for 8 GB clinic PCs. Medium is pinned in `model_files.py` and can be chosen
with `whisper_model` in the settings on a faster PC; it is not in the installer's bundle.

## Limits
- One PC, and memory was short during the runs (0.4 to 3.6 GB free at the start).
- ROUGE and the highlight and diagnosis matching are automatic: they count words, not meaning.
- PriMock57 speakers are British; AfriSpeech is read speech, not conversation. Neither is a
  Kenyan clinic consultation; together they cover real conversation and Kenyan accents
  separately.
- The diagnosis hit rate measures agreement with one clinician's impression, not correctness.
- Round 2 reuses the same 57 consultations that guided the changes, so its numbers favour the
  changes somewhat; ACI-Bench, which played no part in finding them, improved slightly too.
