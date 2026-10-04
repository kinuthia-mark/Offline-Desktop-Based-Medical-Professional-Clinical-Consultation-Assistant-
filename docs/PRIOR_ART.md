# Prior art: MedgemmaV2

The previous version (`MedgemmaV2`, package `aegis`, about 740 lines) was an offline-first
voice-to-SOAP pipeline for Linux: a Docker container with `network_mode: none` watched an inbox
folder for WAV files, transcribed them with Faster-Whisper, screened and redacted the text, asked a
local MedGemma through Ollama for a SOAP JSON, validated it, and wrote a file to an outbox. It had no
login, no database, no interface and no human review step. The new system follows the proposal
instead (Windows desktop, microphone, clinician review, encrypted vault).

Reference copies of the useful files are in `prior_art/MedgemmaV2/` with a `.txt` ending, so they are
neither linted nor imported. The full repository is the author's own; keep a copy at
`../MedgemmaV2` when porting.

## What the new system took from it
| Old | New |
|---|---|
| Strict SOAP schema, repair retry | `soap_generator.parse_draft`; the retry became the controller's second attempt |
| Loopback-only LLM client | `adapters/ollama_client.py` |
| Offline fakes for tests | `tests/fake_ollama.py` and the port fakes |
| Errors as PHI-free codes | same rule everywhere (see "Rules the code follows" in the README) |
| Threat model table | to be rewritten for the desktop system (section below) |

## What was not carried over, and why
- Docker `network_mode: none`: the product is a Windows installer (AMD-15); enforcement becomes a
  firewall rule plus a startup check (NFR-01, NFR-02).
- The folder watcher and file outbox: the workflow is interactive.
- NeMo Guardrails (experimental in the old repo): not used.

## Still to port or fix (found by re-reading it for this cross-check)
1. **Ignore proxy settings.** The old client ignored proxy environment variables. The new client did
   not, so a proxy on a clinic PC could have sat between the app and the local model. **Fixed** in
   `ollama_client.py` with a test (`tests/test_ollama_client.py`).
2. **Per-request canary token.** The old system put a random marker in the system prompt and
   quarantined any output containing it, or any output containing a URL. Not ported yet: add it to
   the output checks in `feature/input-guard`.
3. **Transcript length cap** (60,000 characters), an audio length cap and an LLM timeout. The
   timeout exists; add the other two.
4. **Offline switches for the speech model.** The old code set Hugging Face offline mode and
   `local_files_only`, so Faster-Whisper never reaches for the network. Required in
   `feature/asr-whisper`: load from a local folder, never from a model name.
5. **The air-gap probe must not be ported as it is.** `airgap.py` tries real TCP connections to
   public addresses. On a connected clinic PC that is itself an outbound call, which breaks rule 1.
   Use passive checks instead: adapter state, the firewall rule, listening sockets.
6. **Guardrails need fixing, not just porting.**
   - Its instruction-override pattern is too broad: "disregard the earlier instructions from your
     last clinic" is quarantined. Quarantine on strong signals only, and measure the false-positive
     rate on benign transcripts.
   - Its personal-data rules are United States shaped (social security numbers, US phone numbers).
     Add Kenyan phone formats (+254 7xx, 07xx, 01xx) and 8-digit national identity numbers, and keep
     clinical numbers such as 120/80 and 98.6 untouched (its tests already check that).
   - It cannot find names or numbers spoken as words (its own threat model says so).
7. **Threat model.** Rewrite `THREAT_MODEL.md` for this system: microphone input, local vault,
   recovery code, administrator functions, installer and offline model bundle, and the residual
   risks measured in ADR-001 to ADR-003.
