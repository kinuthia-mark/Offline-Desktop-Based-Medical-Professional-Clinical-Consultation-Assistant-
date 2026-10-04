# ADR-002: Local LLM runtime, model and generation settings

- Status: accepted for development; settings are provisional until the evaluation harness
- Date: 2026-10-02
- Requirement IDs: FR-04, FR-05, FR-13, NFR-03, NFR-04
- Evidence: `docs/spikes/llm-results.md` and the `docs/spikes/llm-*.json` files,
  `spikes/llm_spike.py`, `tests/test_spike_llm.py`

## Context
The proposal specifies a quantized MedGemma model run locally through Ollama on a CPU-only,
offline Windows PC. It names a "2B" variant, which does not exist (AMD-01). We needed to know
whether a 4B model runs acceptably on a minimal clinic-class PC, what it costs in time and
memory, and how it fails.

## Options considered
1. `medgemma:4b` (Q4_K_M) through Ollama.
2. `medgemma1.5:4b` through Ollama.
3. In-process `llama-cpp-python`, which removes Ollama's loopback port but adds Windows build risk.
4. A smaller general-purpose model.

## Decision
Develop against option 1 behind an `LLMClient` interface, so the runtime and model can be
swapped. Compare option 2 on the evaluation set before the final model choice. Options 3 and 4
are not pursued now.

Provisional settings: context 8192; temperature 0.2; a hard cap on generated tokens; repetition
penalty 1.1 from the first attempt when the transcript is long (500 words or more) and on any
retry, otherwise none.

## Evidence
Reference PC: Ryzen 5 5625U (6 cores), 8 GB RAM (7.35 GB usable), Windows, CPU only
(`model_size_vram_gb` was 0 in every trial), Ollama 0.35.0, `medgemma:4b` Q4_K_M. Synthetic
input only. 22 short-consultation trials (about 400 prompt tokens) and 13 long-consultation
trials (2,045 prompt tokens).

| Measurement | Result |
|---|---|
| Model size | 3.11 GB on disk, 2.68 GB loaded (Ollama's report at context 4096) |
| Generation speed | 5.8 to 7.3 tokens/s across all trials |
| Prompt processing, fresh prompt | 45 to 55 tokens/s |
| Prompt processing, identical repeated prompt | about 900 tokens/s (cached), so repeated-prompt speeds are not used |
| Short consultation | valid SOAP JSON in 22 of 22 trials; warm note 25 to 30 s; cold start 37 to 58 s |
| Long consultation (1,472 words) | 156 to 189 s when it ends normally |
| Context 8192 versus 4096 | difference about 0.1 GB, inside the noise |

Long-consultation termination:

| Condition | Trials | Ended normally |
|---|---|---|
| No repetition penalty (plain, schema-constrained, no format, concise prompt; caps 700 and 1024) | 8 | 0 |
| Penalty 1.05 | 1 | 0 |
| Penalty 1.1 | 4 | 4 (632, 670, 737, 867 tokens) |

Without a penalty, the output repeated sentences until the token cap. Short consultations ended
normally with or without a penalty. Merged words ("healthand", "Temperatureis", "whenpassing") appear with and without the
penalty: in 4 of 5 penalised notes read and in 1 of 3 unpenalised short notes read. The penalty is
therefore not their only cause, and the cause is not yet known.

Memory: free RAM before every run was 0.67 to 3.59 GB. That is the reference PC's normal
condition with a browser, a messaging app and an editor open, and no more could be freed, so no
run reached the 4 GB we first wanted. The range is reported as the operating condition, not as
a clean baseline. When free
RAM started above 3 GB, system memory use rose by about 3.1 to 3.4 GB and free RAM fell to
nearly zero, so that figure is capped by what was available and is a floor. Nothing crashed. Cold
load took 7.7 to 10.8 s with 2 GB or more free, 10.6 to 14.5 s with 1.0 to 1.4 GB free, and
20.1 s with 0.67 GB free; warm notes were not affected.

Note quality (7 notes read by hand against the transcript; anecdotal): plan items were
accurate, but every note omitted allergies or pertinent negatives, 3 of 4 short notes stated a
diagnosis the doctor had not made, and individual notes misattributed the doctor's advice to the
patient, mislabelled readings, added units or pronouns the transcript did not contain, and put
content under the wrong heading.

Limits: one PC, one model, two synthetic consultations, 1 to 3 trials per setting, and manual
review of a few notes. These results choose what to test next. They are not accuracy figures.

Real generator runs on the reference PC (`scripts/try_note.py`, branch `feature/llm-soap`, with the
new prompt rules; one run each, so anecdotal):

| Run | Result |
|---|---|
| Short consultation, attempt 1, no penalty | OK in 50 s. Included allergies, long-term illness and pertinent negatives; assessment "not stated" (no invented diagnosis); one merged word ("whenpassing") |
| Long consultation, attempt 1, no penalty | Repetition detected after about 600 tokens; 132 s spent before the retry |
| Long consultation, attempt 2, penalty 1.1 | OK in 173 s (about 875 tokens) |

Errors in the long note, found by reading it against the transcript: home blood pressure written
as 150/94 (transcript: 150/90) and the clinic reading as 150/94 (transcript: 152/94); "no blurred
vision" although the patient described it; "the patient's wife is present" although she was not;
the blood tests and the paracetamol advice are missing from the plan; examination findings are
repeated under Subjective; a merged word ("tohypertension"). The advisory flags caught the
150/94 pair, the merged word and the pronoun, and nothing else. Long consultations without the
penalty have now looped in 9 of 9 runs.

## Consequences
- `feature/llm-soap` must implement FR-13: hard output cap, repetition detector with retry, schema
  check, and a failure state that keeps the transcript and offers manual entry.
- Generation speed bounds latency (about 6.5 tokens/s), so the interface streams output and shows
  progress. State measured times, not "fast".
- AI diagnosis suggestions stay separate from the clinician's assessment (FR-14), and required
  history is confirmed by the clinician (FR-15).
- A startup check warns on low free RAM (NFR-07). Set its threshold from a clean measurement.
- Long transcripts start with the penalty, because first attempts without it looped in 9 of 9
  runs. A retry therefore matters mainly for short transcripts that loop.
- Evaluation transcripts should be written as Whisper writes them (digits for numbers), because the
  number check compares the note with the transcript.
- Ollama remains a separate local process listening on loopback (see NFR-02 and ADR-001's note on
  residual risk).

## Open items
- Compare `medgemma1.5:4b` on the same transcripts (AMD-01).
- Memory could not be measured with 4 GB or more free on the reference PC. Record the loaded
  model size at context 8192 from Ollama's report (`model_size_gb` in the result files), and
  measure Whisper separately to confirm sequential load and unload (AMD-07).
- Test section-by-section generation: does a shared cached prefix cut total time, and does it
  improve faithfulness?
- Measure tokens per word for Swahili and mixed-language speech.
- Evaluate quality with scripted consultations, key-fact lists, and clinician scoring.
- Review the MedGemma licence terms and ship them with the model in the installer.
- Find the transcript length at which loops start (between 204 and 1,472 words) and whether the
  500-word threshold is right.
- Find the cause of merged words (JSON mode, sampling or quantisation) with an A/B run using
  `--format none`, counted with the dictionary check.
- Several errors need a faithfulness metric, not a flag: contradicted negations, invented
  statements and omitted orders. The evaluation harness must measure them.
