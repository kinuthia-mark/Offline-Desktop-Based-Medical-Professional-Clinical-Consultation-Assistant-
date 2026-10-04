# ADR-008: Connecting the parts, the memory plan and startup checks

- Status: accepted
- Date: 2026-10-04
- Requirement IDs: NFR-03, NFR-04, NFR-07
- Evidence: `tests/test_app.py`, `docs/spikes/pipeline-mark-pc.json`, `spikes/pipeline_spike.py`

## Context
Each part (recorder, Whisper, input guard, MedGemma, vault, audit log) was built and tested on its
own behind a port. Something has to build the real parts and hand them to the controller. On an
8 GB PC, Whisper small (about 1 GB at its peak, ADR-007) and MedGemma 4B (2.7 GB loaded, ADR-002)
should not be in memory together. The proposal also needs the app to check, before a
consultation, that it can do its job on this PC (AMD-21).

## Options considered
1. **Let each part manage its own memory.** Simple, but the parts would need to know about each
   other.
2. **One composition root with a memory plan around the ports.** The controller stays unaware;
   the plan runs at the right moments.
3. **Run Whisper in a separate process.** Frees memory completely when the process ends, but adds
   start-up time and process handling.

## Decision
Option 2, in `app.py`.

- `build()` is the only place that creates real adapters. The interface asks it for a controller.
- `SequentialModels` frees MedGemma (Ollama `keep_alive: 0`) when recording starts, loads Whisper
  in the background while the clinician speaks, and frees Whisper as soon as the transcript is
  ready, also when transcription fails.
- `config.py` holds the settings, each with the reason for its default. Unknown names and wrong
  types are refused, so a typo cannot quietly switch off something like the audio setting.
- `startup.py` checks Python, the data folder, the speech model's checksum, Ollama and the model,
  free memory and the microphone. Only a missing speech model or an unwritable data folder stop
  the app; the rest are warnings, because the clinician can still record, review and write the
  note by hand.
- Memory warning thresholds come from measured cold-load times (ADR-002): a warning below 2 GB
  free and a stronger one below 1 GB.

## Evidence (reference PC, `docs/spikes/pipeline-mark-pc.json`)
Startup checks: all ok except the free-memory warning; about 0.5 s in total, of which 0.4 s is the
checksum of the 484 MB speech model.

End to end with the real parts (Whisper small, input guard, MedGemma 4B through Ollama, controller,
vault, audit log), on the synthetic consultations read by the Windows voices:

| Stage | Short (1 min 44 s) | Long (10 min 51 s) |
|---|---|---|
| Start recording (free MedGemma, start loading Whisper) | 0.3 s | 0.4 s |
| Transcribe, including the rest of Whisper's load | 21 s | 126 s |
| Input check and note draft | 49 s | 165 s |
| Finalize and save to the vault | 0.06 s | 0.03 s |
| **Total wait after the consultation** | **70 s** | **4.9 min** |
| Model attempts | 1 | 1 |
| Free memory at the start, lowest during the run | 1.36 GB, 0.02 GB | 0.55 GB, 0.00 GB |
| Audit chain verified afterwards | yes | yes |

The memory plan ran in the designed order both times: MedGemma freed, Whisper loaded, transcript
made, Whisper freed. Free memory reached zero during drafting because the PC started with very
little free (a browser and other programs were open). Windows moved memory to disk and nothing
failed, but this slows the run.

Mutation checks, all 10 caught: MedGemma not freed before recording; Whisper kept after use;
Whisper freed only on success; unknown setting accepted; 0 accepted as false; a missing language
model treated as a failure; memory thresholds ignored; a missing speech model only a warning;
failures not blocking start; one crashing check stopping the others.

## Limits
- One run per consultation, on one PC, under memory pressure. These times describe this machine
  in its normal state, not a clean one.
- Ollama's own memory figure does not include the memory-mapped model, so free system memory is
  the measure used here.
- After a discarded recording, Whisper stays loaded until the next transcription.
- The long note again contained an invented statement ("will bring her wife to follow-up
  appointments"), as in ADR-002, and no advisory flag caught it. The clinician writes the
  assessment; the model's text stays separate (FR-14).

## Consequences
- NFR-07 built. NFR-03 has its first end-to-end figures (target still to set with the
  supervisor). NFR-04: the memory plan is in place and measured. AMD-07 and AMD-21 applied in code.
- The interface shows the startup checks before login and uses `Services.new_controller()`.
