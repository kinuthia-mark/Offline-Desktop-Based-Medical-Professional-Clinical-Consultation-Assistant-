# ADR-007: Speech-to-text with Faster-Whisper

- Status: accepted for development; model choice to revisit with recorded human speech
- Date: 2026-10-04
- Requirement IDs: FR-02, NFR-04, NFR-06
- Evidence: `tests/test_transcriber.py`, `docs/spikes/asr-mark-pc.json`, `spikes/asr_spike.py`,
  `spikes/make_speech.ps1`

## Context
UC-02 turns the recording into text on the PC. The proposal names Faster-Whisper. Open questions
from the handoff: which model size suits an 8 GB laptop without a graphics card, how much memory
it needs next to the language model (AMD-07), how accurate it is, whether it writes numbers as
digits or words, and how to make sure it never reaches for the internet.

## Options considered
1. **Faster-Whisper base** (74 M parameters, 145 MB). Fast, less accurate.
2. **Faster-Whisper small** (244 M parameters, 484 MB). Slower, more accurate.
3. **Medium or larger.** Over 1.5 GB of weights; too slow on this CPU for a consultation of
   10 minutes or more. Not measured.

## Decision
`WhisperTranscriber` in `adapters/transcriber.py`, implementing the `Transcriber` port, with
**small as the default** and base as a setting for slower PCs.

- Load from a folder in `models/`, never by name. Hugging Face's offline switches are set before
  the library is imported and `local_files_only` is on, so a missing model is an error
  (`asr_model_missing`), not a download.
- `model_files.py` records the SHA-256 of each model's weights as published by Hugging Face;
  `verify()` checks a folder before it is trusted (install and startup).
- CPU, 8-bit weights (int8), beam search of 5, English, voice-activity filter on (skips long
  silences, where Whisper is known to invent text), and no conditioning on previous text (stops
  one error repeating).
- Load on first use or early with `load()` (for example while recording), and `unload()` before
  the language model runs, so the two models are never in memory together (NFR-04, AMD-07).
- Report a confidence hint: the average probability the model gave its own words, weighted by
  speech duration. It is not accuracy; it is the definition behind the wireframe's "ASR Conf"
  label (AMD-28).

## Evidence (reference PC, `docs/spikes/asr-mark-pc.json`)
Audio: the two synthetic consultations read aloud by the Windows voices David (doctor) and Hazel
(patient), 16 kHz: 1 min 44 s (189 words) and 10 min 51 s (1,389 words). Free RAM before the runs
was 1.2 to 1.6 GB with other programs open. Each model ran in its own fresh process.

| Measurement | base | small |
|---|---|---|
| Weights checked against the published SHA-256 | ok | ok |
| Load time | 0.8 s | 1.7 s |
| Process memory once loaded | 147 MB | 315 MB |
| Peak memory, short / long consultation | 294 / 849 MB | 520 / 969 MB |
| Memory after `unload()` | 116 MB | 116 MB |
| Time to transcribe, short / long | 5.8 / 39.7 s | 17.1 / 108.7 s |
| Real-time factor (processing / audio length) | 0.06 | 0.17 |
| Word error rate, raw, short / long | 6.2% / 5.1% | 6.2% / 4.9% |
| Word error rate, normalised, short / long | 1.6% / 1.7% | 1.6% / 0.7% |
| Medicine names correct (11 mentions of 4 drugs) | 6 | 9 |
| Language detected | English, 1.00 | English, 1.00 |

"Normalised" treats British and American spellings, written-out units (milligrams/mg) and number
layout ("one fifty two"/"152") as the same, as speech-recognition scoring usually does. Most of the
raw errors were of these kinds. The real errors that remained were medicine names
(base: "amlotyping" for amlodipine three times, "parasetamol"; small: "parasetamol", "i bupren"),
a local food ("ugali" as "you galley"), and a few dropped or swapped small words ("sores" as
"sauce", "neck" as "next" with base).

Numbers: measurements and doses come out as digits ("38.6", "152 over 94", "11.2"); small counts
such as "one tablet" stay as words. The generator's number check reads both (ADR-002).

Mutation checks, all 12 caught: offline switch not set; fetching by name allowed; device not CPU;
no check that a model is present; `unload()` keeping the model; library error text passed on;
audio format not checked; confidence not weighted by duration; previous-text conditioning on;
WER ignoring insertions; number words not turned into digits; checksum never compared.

## Why small
On general words the two models are close. On medicine names small was right 9 of 11 times and
base 6 of 11, and a misheard drug name is the error that matters most in a note. The cost is time:
about 1.8 minutes instead of 0.6 for an 11-minute consultation, partly hidden by loading the model
while recording. Base stays available as a setting.

## Limits (state these in the report)
- **Computer voices are a best case.** They are clear, steady and free of background noise.
  Real consultations have accents, overlapping speech, coughing and room noise. These rates are
  not what the system will achieve with people. The next step is recordings of people reading the
  same scripts (synthetic content, real voices), which `asr_spike.py` can score as it is.
- **Small sample of medicine names**: 11 mentions of 4 drugs. Enough to show a difference, not
  to give a rate.
- **No speaker labels.** Whisper writes one block of text with no "Doctor:" or "Patient:". The
  note generator was tested on labelled scripts, and its errors included advice credited to the
  wrong person. See AMD-37.
- **English only.** Swahili and mixed speech are untested (AMD-35).
- One laptop, under memory pressure from other programs.

## Consequences
- FR-02 built; verified when CI is green. NFR-06 has its first measured WER (target still to set,
  after recorded human speech). NFR-04 and AMD-07: Whisper's memory is now measured.
- The evaluation harness must feed the note generator Whisper's real output (unlabelled, digits),
  not the labelled scripts, or it will overstate note quality.
- The composition root loads Whisper while recording, unloads it before the language model, and
  runs `verify()` on the model folder at startup.
