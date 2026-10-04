# ADR-006: Microphone recording

- Status: accepted
- Date: 2026-10-04
- Requirement IDs: FR-01
- Evidence: `tests/test_recorder.py`, `docs/spikes/mic-mark-pc.json`, `spikes/mic_spike.py`,
  `scripts/check_microphone.py`

## Context
UC-01 records the consultation from the PC's microphone. The proposal is inconsistent about where
the audio goes: UC-01 keeps it in a memory buffer, while section 2.6 and Figure 3.2 write a
temporary WAV file (AMD-23). Whisper works with 16 kHz mono audio. The reference PC lists the same
microphone several times and also offers "Stereo Mix", which records the PC's own sound output.

## Options considered
1. **sounddevice** (PortAudio). Prebuilt Windows wheel with PortAudio included; no compiler.
2. **PyAudio.** Also PortAudio; Windows wheels have lagged behind Python releases.
3. **Windows APIs directly** (WASAPI through comtypes). Most control, much more code.

## Decision
Option 1, `SoundDeviceRecorder` in `adapters/recorder.py`, implementing the `Recorder` port.

- Record at 16 kHz, mono, 16-bit, so no conversion is needed before Whisper.
- Keep audio in memory only. `stop()` returns WAV bytes (the header records the format) and
  clears the recorder's own copy, so only the caller holds the consultation. Writing audio to
  disk stays a separate, optional step that is off by default (ADR-003).
- Stop by itself after 45 minutes (about 86 MB) and report `limit_reached`.
- Measure every recording (peak, average, lost blocks). On Windows, a microphone blocked in the
  privacy settings usually records silence instead of failing, so a recording with a peak below
  0.0005 is reported as `silent` for the interface to explain.
- List each microphone once: only devices on the same Windows audio system as the default input,
  and never inputs that record the PC's output ("Stereo Mix", "What U Hear").
- Turn PortAudio errors into codes: `no_microphone`, `microphone_unavailable`,
  `sample_rate_not_supported`. The original message is not passed on.
- Always release the microphone, including when stopping fails and when a session is discarded.

## Evidence (reference PC, `docs/spikes/mic-mark-pc.json`)
Default input: the laptop's built-in microphone array (Realtek), Windows MME, PortAudio 19.7.0.

| Measurement | Result |
|---|---|
| Microphones offered | 2 (Windows default, built-in array); 12 inputs listed by Windows |
| 16 kHz accepted directly | yes, no resampling needed |
| Time to open the microphone, median of 5 | 128 ms |
| Audio missing at the start of each take | 0.1 s (one block while the device starts) |
| 60-second take | 59.9 s captured, 0 blocks lost |
| Quiet room, peak level | about 0.0013; silence threshold is 0.0005 |

Tests use a fake audio system, so CI needs no hardware. One test records 2 seconds from the real
microphone and runs only with `CLINASSIST_HARDWARE=1`; it passed on the reference PC.

Mutation checks, all 11 caught: recording at 44.1 kHz; stereo; no maximum length; microphone not
closed after stop; silence never reported; silence threshold set too high for a quiet room; Stereo
Mix offered; duplicate devices listed; raw PortAudio message passed on; audio kept after stop;
lost blocks not counted. The first run missed two of these; one exposed a redundant branch (now
removed) and one a missing privacy test (now added).

## Limits
- One laptop, one built-in microphone, ambient room sound. Speech quality through this microphone
  is measured when speech-to-text is added (FR-02), as word error rate.
- About 0.1 s is lost at the start of every recording. The interface should show "recording"
  only once the first block has arrived, so the clinician starts speaking after it.
- Bluetooth headsets in hands-free mode run at 8 kHz on this PC. They are listed but would give
  Whisper half the detail; this is untested.
- The silence check cannot tell a blocked microphone from a muted one; the message covers both.
- A 45-minute recording uses about 86 MB of memory, which matters on an 8 GB PC with the speech
  model loaded next (NFR-04, measured in FR-02).

## Consequences
- FR-01 built; verified when CI is green. AMD-23 (audio in memory, not a temporary file) is now
  true in code as well as in the storage design.
- The interface needs a device picker, a level meter (`level`), the elapsed time (`seconds`),
  and messages for each error code and for a silent recording.
