# ADR-017: Targets for speed, memory and speech accuracy

- Status: accepted
- Date: 2026-10-17
- Requirement IDs: NFR-03, NFR-04, NFR-06 (AMD-04, AMD-33)
- Evidence: ADR-002, ADR-007, ADR-008, ADR-016; `docs/eval/public/primock57-mark-pc-v2-speech.json`,
  `docs/eval/public/afrispeech-ke-mark-pc.json`, `docs/eval/public/afrispeech-ke-mark-pc-medium.json`

## Context
The proposal asks for latency, memory and transcription accuracy "within a target", but sets no
numbers. The requirements stayed in progress because of that, although everything had been
measured. A target set after looking at the results can be chosen to pass. To avoid that, each
target below is set from what a clinic needs, written down with its reason, and then compared
with the measurements as they are, including the one it misses.

## Targets
| Requirement | Target | Why this number |
|---|---|---|
| NFR-03 speed | For a consultation of up to 10 minutes, the draft note is ready within **5 minutes** of the end of the consultation, in at least **9 of 10** consultations, on the reference PC | the clinician reviews the transcript in the meantime and the patient is usually still in the room; much longer and the note is written after the patient has gone, which defeats the purpose |
| NFR-04 memory | The models never need more than **4 GB** at once on the 8 GB reference PC | half of the PC's memory, leaving the rest for Windows, the program and the other programs a clinic PC runs |
| NFR-06 speech accuracy | At most **15%** of words wrong on natural conversation, and at most **20%** on Kenyan-accented clinical speech | at about one word in seven or better, correcting the transcript is quicker than typing it; a fifth is the most a clinician would correct rather than retype |

## Measurements against the targets
| Requirement | Measured (reference PC: Ryzen 5 5625U, 8 GB, CPU only) | Result |
|---|---|---|
| NFR-03 | PriMock57, real voices through the whole system after the round 2 fixes: of the 38 consultations up to 10 minutes long, **36 (95%)** had a draft within 5 minutes; median for all 57, 3.5 minutes | **met** |
| NFR-04 | MedGemma 4B 2.68 GB in memory (ADR-002); Whisper small at most 0.97 GB (ADR-007); the two are never loaded together (ADR-008) | **met** (2.68 GB at most) |
| NFR-06, conversation | PriMock57 (natural conversation, British speakers): 14.6% of words wrong | **met** |
| NFR-06, Kenyan accents | AfriSpeech-200, 631 clips from Kenyan speakers, clinical sentences, spoken punctuation removed: Whisper small **21.6%**; Whisper medium 18.0% | **not met** with the default model; met with medium, which is 3.4 times slower |

## Decision
- NFR-03 and NFR-04 are verified against these targets.
- NFR-06 stays open. Its conversation target is met, but on Kenyan clinical speech the default
  speech model misses the target by 1.6 points. Whisper medium meets it, but at 3.4 times the
  time, a ten-minute consultation would take about six minutes to transcribe and the NFR-03
  target would then be missed. On the reference PC the two targets cannot both be met; speed
  is kept, and the transcript review (FR-03) with the medicine-name check (ADR-013) is how
  misheard words are caught. On a faster PC, `whisper_model = "medium"` meets both.

## Limits
- One PC. Free memory at the start of the runs was 0.4 to 3.6 GB because other programs were
  open; with more free memory the times are shorter (ADR-002).
- Consultations of 10 to 14 minutes took up to 6.3 minutes to draft. The target covers up to 10.
- The Kenyan figure is read speech (AfriSpeech), not conversation; some of its reference
  transcripts contain errors, so the true word error rate is somewhat lower (ADR-016).
- The targets are the author's, set from the reasons above; they are not from a standard.
