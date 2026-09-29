# Requirements traceability matrix

Status values: planned, in progress, verified. A row is "verified" only when the test passes
in CI and any listed measurement is recorded. UC numbers come from the proposal; UC-03 is
assumed to be transcript review (confirm against the use case diagram).

| ID | Requirement | UC | Branch | Test / measurement | Status |
|---|---|---|---|---|---|
| FR-01 | Record consultation audio from the local microphone | UC-01 | feature/audio-recorder | fake-device tests | planned |
| FR-02 | Transcribe audio locally | UC-02 | feature/asr-whisper | WER on scripted audio | planned |
| FR-03 | Clinician reviews and edits the transcript | UC-03 | feature/ui-dashboard | UI tests | planned |
| FR-04 | Load the quantized model locally | UC-04 | spike/ollama-medgemma, feature/llm-soap | load and memory measurement | planned |
| FR-05 | Generate a structured SOAP draft with differentials | UC-05 | feature/llm-soap, feature/input-guard | schema, retry, injection tests | planned |
| FR-06 | Clinician reviews, edits and finalizes the note | UC-06 | feature/ui-dashboard | UI tests | planned |
| FR-07 | Save the session to encrypted local storage | UC-07 | feature/secure-store | wrong-key and tamper tests | planned |
| FR-08 | Authenticate users and enforce roles | n/a | feature/auth-audit | auth tests | planned |
| FR-09 | Tamper-evident audit log | n/a | feature/auth-audit | chain-break test | planned |
| FR-10 | SystemAdmin functions (accounts, model update, backup) | n/a | reserved | to be defined | planned |
| FR-11 | The LLM never runs before the clinician approves the transcript | UC-05 | feature/domain-controller | controller tests | planned |
| FR-12 | A session cannot be finalized without a drafted note the clinician reviewed | UC-06 | feature/domain-controller | controller tests | planned |
| NFR-01 | No outbound network connectivity | n/a | feature/airgap-enforcement | firewall and probe evidence | planned |
| NFR-02 | Application process opens no listening sockets; only Ollama's loopback port | n/a | feature/airgap-enforcement | socket test on launched app | planned |
| NFR-03 | End-to-end latency within a target set from measurements | n/a | eval/harness | latency table (target TBD) | planned |
| NFR-04 | Peak memory within a target on a stated reference PC | n/a | spike/ollama-medgemma | memory table (target TBD) | planned |
| NFR-05 | Patient data encrypted at rest | n/a | feature/secure-store | ADR-001 and tests | planned |
| NFR-06 | Transcription accuracy (WER) reported against a target | n/a | eval/harness | WER table (target TBD) | planned |
