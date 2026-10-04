# Requirements traceability matrix

Status values: planned, in progress, verified. A row is "verified" only when the test passes
in CI and any listed measurement is recorded. UC numbers come from the proposal; UC-03 is
assumed to be transcript review (confirm against the use case diagram).

| ID | Requirement | UC | Branch | Test / measurement | Status |
|---|---|---|---|---|---|
| FR-01 | Record consultation audio from the local microphone | UC-01 | feature/audio-recorder | fake-device tests | planned |
| FR-02 | Transcribe audio locally | UC-02 | feature/asr-whisper | WER on scripted audio | planned |
| FR-03 | Clinician reviews and edits the transcript | UC-03 | feature/ui-dashboard | UI tests | planned |
| FR-04 | Load the quantized model locally | UC-04 | spike/ollama-medgemma, feature/llm-soap | client, loopback and unload tests; memory table under typical load | in progress (client done) |
| FR-05 | Generate a structured SOAP draft with differentials | UC-05 | spike/ollama-medgemma, feature/llm-soap, feature/input-guard | schema, retry, and flag tests (numbers, merged words) done on real outputs; injection tests pending (feature/input-guard) | in progress (generator done; guard pending) |
| FR-06 | Clinician reviews, edits and finalizes the note | UC-06 | feature/ui-dashboard | UI tests | planned |
| FR-07 | Save the session to encrypted local storage | UC-07 | spike/sqlcipher-windows, feature/secure-store | tests/test_vault.py, tests/test_store.py, tests/test_audio_store.py (wrong key, tamper, recovery, transactional save, schema gates); timing in docs/spikes/vault-timing-mark-pc.json | in progress (built and tested locally; verified when CI is green) |
| FR-08 | Authenticate users and enforce roles | n/a | feature/auth-audit | tests/test_auth.py (lockout, idle timeout, roles, no username discovery, hash upgrade); login timing in docs/spikes/vault-timing-mark-pc.json | in progress (built and tested locally; verified when CI is green) |
| FR-09 | Tamper-evident audit log | n/a | feature/auth-audit | tests/test_audit.py (edit, forged hash, middle deletion, reorder, truncation with anchor, no free text) | in progress (built and tested locally; verified when CI is green) |
| FR-10 | SystemAdmin functions (accounts, model update, backup) | n/a | reserved | to be defined | planned |
| FR-11 | The LLM never runs before the clinician approves the transcript | UC-05 | feature/domain-controller | tests/test_controller.py | in progress (controller done) |
| FR-12 | A session cannot be finalized without a drafted note the clinician reviewed | UC-06 | feature/domain-controller | tests/test_controller.py | in progress (controller done) |
| FR-13 | Note generation is bounded and validated: hard output cap, repetition detector with retry, schema check, and a visible failure state that keeps the transcript and offers manual entry | UC-05 | feature/domain-controller, feature/llm-soap, feature/ui-dashboard | controller, cap, loop, deadline and stream-closing tests done; UI failure state pending | in progress (controller and generator done) |
| FR-14 | Model-generated diagnosis suggestions are kept separate from, and labelled apart from, the clinician's own assessment | UC-05, UC-06 | feature/domain-controller, feature/ui-dashboard | controller tests done; UI tests pending | in progress (controller done) |
| FR-15 | Required history (allergies, medications, pertinent negatives) is confirmed by the clinician before a note is finalized | UC-06 | feature/domain-controller, feature/ui-dashboard | controller tests done; UI tests pending | in progress (controller done) |
| NFR-01 | No outbound network connectivity | n/a | feature/airgap-enforcement | firewall and probe evidence | planned |
| NFR-02 | Application process opens no listening sockets; only Ollama's loopback port | n/a | feature/airgap-enforcement | socket test on launched app | planned |
| NFR-03 | End-to-end latency within a target set from measurements | n/a | eval/harness | measured on reference PC (ADR-002); target TBD | in progress (measured once) |
| NFR-04 | Peak memory within a target on a stated reference PC | n/a | spike/ollama-medgemma, feature/asr-whisper | memory table under typical load (ADR-002); clean baseline not reachable on the reference PC | in progress |
| NFR-05 | Patient data encrypted at rest | n/a | spike/sqlcipher-windows, feature/secure-store | ADR-001, ADR-003; tests/test_crypto.py, tests/test_vault.py, tests/test_audio_store.py | in progress (built and tested locally; verified when CI is green) |
| NFR-06 | Transcription accuracy (WER) reported against a target | n/a | eval/harness | WER table (target TBD) | planned |
| NFR-07 | Startup self-check warns when free memory is too low for the model | n/a | feature/airgap-enforcement | startup check test; threshold from measurements | planned |
