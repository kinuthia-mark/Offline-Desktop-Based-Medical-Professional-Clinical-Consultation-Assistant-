# Proposal cross-check

Checked on 2026-10-02 against `PROPOSAL.md` (the approved proposal) and the implementation as it
stood after `feature/secure-store`. Purpose: make sure nothing in the proposal is lost, and record
where the implementation differs and why. Every difference has an amendment in `../AMENDMENTS.md`.

## Update, 2026-10-16
The tables in sections 3, 4 and 6 now describe the build as it is today: all 29 requirements are
built and 25 are verified (`../traceability.md`). The original check of 2026-10-02 is kept in
sections 0, 1, 2 and 5. Gaps that remain are marked **open** below.

## 0. How this was checked, and what was not
- Read: every chapter, the references, the abbreviations, the abstract.
- Looked at as images: Figure 3.2 (architecture), 4.1 (use cases), 4.2 (class diagram), 4.3
  (sequence), 4.5 (architecture), 4.7 (schema), 4.8 (wireframe), and the Gantt chart.
- **Not looked at as images** (their text descriptions were read): Figure 2.1 (conceptual), 3.1
  (V-model), 4.4 (system sequence), 4.6 (entity-relationship diagram).
- Not verified: the literature claims and citations against the actual papers (only the mismatches
  visible inside the proposal were recorded), the clinical plausibility of any note, and anything
  outside the proposal text and figures.

## 1. Corrections to the amendment log's section references
The first version of the log cited some sections from memory. These were checked against the text.

| Entry | Was | Now | Why |
|---|---|---|---|
| AMD-01 | 1.6, 1.7.1, 3.5, 3.7, 4.6 | 1.6, 1.7.1 | "2B" appears only in 1.6 and 1.7.1. Sections 3.5 and 4.6 already say MedGemma 4B-IT. |
| AMD-02 | Abstract, 1.1, 1.5 | Abstract, 1.1, 1.2, 1.5 | "zero-trust" is also in 1.2; "autonomous diagnostic companion" is in 1.1. |
| AMD-03 | 1.1, 1.5, 1.7.2, 2.3.3 | 1.1, 1.5, 1.7.2, 2.1, 2.3.3, 2.4.2, 2.5, List of Abbreviations | QLoRA, NF4, Double Quantization or Paged Optimizers also appear in 2.1, 2.4.2, 2.5 and the abbreviations list. |
| AMD-04 | 2.2.1, 3.7 | Abstract, 1.1, 2.2.1 | "zero-latency" is in 2.2.1, "near parity" in 1.1, "low latency" in the Abstract. 3.7 has neither. |
| AMD-05 | 1.5, 2.2.2 | Abstract, 1.5, 2.2.2 | The compliance claims are in these three. |
| AMD-06 | 1.3.2, 3.2.1, 3.6 | 1.3.2, 1.7.2, 3.2.1, 3.2.5, 3.3, 3.6 | 1.7.2 allows public benchmark datasets; 3.2.5 and 3.6 say synthetic scripts only; 3.2.1 names PubMedQA; 3.3 sets hardware benchmarking. |
| AMD-08 | 3.1.2, 3.2.5 | 3.1, 3.1.2, 3.2, 3.2.5 | The V-Model is described in all four. |
| AMD-10 | 3.6, 4.6 | 3.4, 3.6, 4.6 | 3.4 also states the air-gap model. |
| AMD-22 | 4.8, 4.9 | 4.3, 4.8 | 4.9 is the wireframe. Key handling belongs with EncryptedDatabaseManager (4.3) and the schema text (4.8). |

## 2. Use cases (Figure 4.1 and section 4.2.1)
Numbered in the text: UC-01 Initiate Audio Recording, UC-02 Transcribe Speech to Text, UC-04 Load
Quantized LLM Model, UC-05 Generate SOAP Notes & Diagnostics, UC-06 View & Finalize Consultation,
UC-07 Save to Local Encrypted Storage. **UC-03 is never mentioned in the text.** The diagram's only
other clinician use case is Review / Edit Transcription, so UC-03 is taken to be that (inferred).
Not numbered: Authenticate / Log In, and four administrator use cases.

| Use case | Actor | Requirement |
|---|---|---|
| Authenticate / Log In | both | FR-08 |
| UC-01 Initiate Audio Recording | clinician | FR-01 |
| UC-02 Transcribe Speech to Text (included in UC-01) | system | FR-02 |
| UC-03 Review / Edit Transcription (inferred) | clinician | FR-03 |
| UC-04 Load Quantized LLM Model (included in UC-05) | system | FR-04 |
| UC-05 Generate SOAP Notes & Diagnostics | system | FR-05, FR-11, FR-13, FR-14 |
| UC-06 View & Finalize Consultation | clinician | FR-06, FR-12, FR-15 |
| UC-07 Save to Local Encrypted Storage (extends UC-06) | system | FR-07 |
| Manage User Accounts & Roles | administrator | FR-10a |
| Update Model Weights & Files | administrator | FR-10b |
| Backup Encrypted Database | administrator | FR-10c |
| Review Security Audit Logs | administrator | FR-10d |

## 3. Class diagram (Figure 4.2) against the implementation
| Proposal class | Members in the proposal | Implementation |
|---|---|---|
| `User` (abstract), `Clinician`, `SystemAdmin` | userId, username, pinHash, role; authenticate(pin); manageUsers, updateModelWeights, backupDatabase, viewAuditLogs | `security/auth.py`: `AuthService` and `UserSession`, roles clinician and admin, passwords instead of a PIN (AMD-26). manageUsers is `create_user`, `set_active`, `unlock_account`, `reset_password`; updateModelWeights is `model_update.py`; backupDatabase is `security/backup.py`; viewAuditLogs is the admin screen with `HashChainAuditor.verify` |
| `ConsultationSession` | sessionId, startTime, endTime, status | `SessionRecord` (domain.py) plus the controller's state. **open:** start time, end time and status are not stored |
| `AudioRecord` | recordingId, filePath, durationSeconds | `adapters/audio_store.py` (optional, off by default, ADR-003). No metadata table |
| `Transcript` | transcriptId, rawText, confidenceScore | the approved text, stored in `sessions` with `transcript_language` and `asr_confidence` (schema v4) |
| `SOAPNote` | summaryId, S, O, A, P; toDict(), validate() | `SoapNote` (the clinician's) and `Draft` (the model's); validation in `soap_generator.parse_draft` |
| `ConsultationController` | currentSession; orchestrate() | `controller.ConsultationController`: explicit steps and a state machine, no single orchestrate() |
| `AudioRecorder` | sampleRate, isRecording, audioBuffer, device; start(), stop() | `adapters/recorder.py` (16 kHz mono, in memory, ADR-006) |
| `WhisperTranscriber` | modelPath, language, quantType; transcribe(audio) | `adapters/transcriber.py` (Faster-Whisper small, int8, local files only, ADR-007) |
| `LLMInferenceEngine` | modelName, quantization, maxTokens; loadModel(), generate(prompt) | `OllamaClient`, `SoapGenerator`, `GeneratorSettings`; Ollama loads on demand, `unload()` frees it |
| `ClinicalOutputFormatter` | template, rules; formatSOAP(), validate() | `soap_generator.parse_draft`, `groundcheck`, `loopcheck` |
| `EncryptedDatabaseManager` | storagePath, encKey, algorithm; saveSession, loadSession, writeAuditLog | `security.vault.Vault`, `adapters.store.VaultSessionStore`, `security.audit.HashChainAuditor`, `security.backup` |
| `DashboardUI` | isRecording; render() | `ui/`: `MainWindow`, `ConsultationWorkspace`, `RecordsView`, `OverviewView`, `AdminView`, `DatabaseView` (ADR-009) |
| (not in the proposal) | | `PatternInputGuard` (ADR-005), loop and grounding checks, the medicine-name check (`medcheck.py`), the network guard (`airgap.py`), the offline bundle and installer (ADR-012), the composition root (`app.py`) |

Operations in the sequence diagram (Figure 4.3) and system sequence diagram (4.5):
startConsultation() / startRecording() is `start_recording()`; stopConsultation() is
`stop_recording()`, which returns the transcript for displayTranscript(); submitTranscript() /
confirmEditedTranscript() is `approve_transcript()`; generate(), then formatSOAP(), then
displaySOAPNote() is `generate_draft()`; finalizeSession() then saveSession() is `finalize()`.
Added by the implementation and absent from the diagrams: the clinician's own assessment, the
history checklist, the failure state with retry and manual entry, the input guard, reopening the
transcript, discard, and login. The diagrams must show them (AMD-11, AMD-14).

## 4. Database schema (Figure 4.7) against the implementation
| Proposal table and columns | Implementation | Difference |
|---|---|---|
| `users`: user_id, username, pin_hash, full_name, role, created_at | `users` | `display_name` for full_name; an Argon2id password hash replaces pin_hash; lockout columns and `must_change_password` added |
| `audit_logs`: log_id, user_id, action, timestamp | `audit_logs` (seq, ts, event, session_id, user_id, prev_hash, entry_hash) | hash-chain columns added (ADR-004) |
| `consultation_sessions`: session_id, clinician_id, consultation_date, start_time, end_time, status | `sessions` (session_id, created_at, finalized_by, ...) | **open:** no start_time, end_time or status; created_at stands for the date |
| `transcripts`: transcript_id, session_id, transcript_text, language, confidence_score, generated_at | the approved text inside `sessions`, with `transcript_language` and `asr_confidence` | no separate table; generated_at not stored |
| `audio_records`: recording_id, session_id, file_path (NOT NULL), sample_rate, duration_seconds, recorded_at; 1-to-1 | none | audio is not kept by default (ADR-003); the proposal makes a recording mandatory (AMD-23) |
| `soap_notes`: summary_id, session_id, S, O, A, P, model_version (NOT NULL), generated_at | `notes`, one row of kind `model_draft` and one of kind `clinician_final` | draft and final kept side by side; `sessions.model_version` and `sessions.asr_model` record the models used (empty for a note written by hand or a typed transcript, so not NOT NULL); generated_at not stored |
| `diagnosis_suggestions`: diagnosis_id, summary_id, diagnosis_text, management_strategy, confidence_rank | `suggestions` (session_id, position, rank, diagnosis, rationale, management, accepted) | rank replaces confidence_rank; rationale and accepted added |
| All keys are 36-character UUIDv4 | session ids are 32-character hex; composite keys in `notes` and `suggestions` | **open:** align or amend (AMD-34) |
| "PBKDF2 key derivation" (4.8 text) | Argon2id and an envelope key | AMD-22 |

## 5. Wireframe (Figure 4.8) as a checklist for the interface
- Header: application title, **[ Status: Air-Gapped ]**, "User: Clinician", [ Logout ].
- Navigation: Consultation Workspace, Session Records, Audit & System Logs.
- Panel 1, Session & Audio Control: Session ID (shown as `SESS-YYYYMMDD-NN`), Date, Start Recording,
  Stop Recording, Status (Ready / Standby), Duration (hh:mm:ss), Sample Rate (16 kHz), Save Session,
  Reset / New Session.
- Panel 2, ASR Transcript Editor: editable text, "Lang: English (en)", "ASR Conf: 94.8%", and
  Confirm Transcript & Run LLM.
- Panel 3, Clinical Output & Diagnostics: tabs SOAP Summary and Diagnostics; Subjective, Objective,
  Assessment, Plan; "Model: MedGemma 4B-IT (Quantized Local)"; Edit SOAP; Export / Save.
- All on one screen (section 3.2.2).
Things the wireframe needs and does not show: login, the history checklist, the clinician's own
assessment box, the failure state, progress during generation, advisory flags, a discard
confirmation, the recovery code at setup. The "Air-Gapped" label must reflect a real check
(NFR-01, NFR-02), not a fixed string. "ASR Conf" needs a stated definition. "Export / Save" is not
defined anywhere in the text.

How the build meets it today: the same three panels and the SOAP and Diagnostics tabs (ADR-009,
AMD-42); the header shows what the network check found; navigation depends on the role (AMD-41);
the session id is shown as its first 8 characters, not `SESS-YYYYMMDD-NN`; the speech confidence
is defined and labelled as a hint (AMD-28); "Export / Save" is a PDF export of one finalized note
(AMD-36); finalizing saves the session; the panel shows "Model: medgemma:4b (quantized, runs on this computer)".

## 6. Findings not recorded before this cross-check
| # | Where in the proposal | What it says | What we found | Status today |
|---|---|---|---|---|
| F1 | 1.3.1, 1.6, 2.6, UC-05, Diagnostics tab | The core output is a list of probable diseases with management strategies | suggestions were off by default for latency | on by default, measured (ADR-013, AMD-32); clinician scoring open |
| F2 | Figure 4.1, 4.3 | Four administrator functions | only "reserved" at the time | all four built (FR-10a to FR-10d, AMD-25) |
| F3 | Figure 3.2, 4.3, 4.8 | Login by "Local PIN" and `pin_hash` | a short PIN is brute-forceable | password with Argon2id and lockout (AMD-26) |
| F4 | UC-06 | Unparseable output goes to a fallback viewer | a failure state with retry or manual entry | kept: no raw-output viewer (AMD-27) |
| F5 | UC-05, wireframe | "low confidence" segments highlighted; "ASR Conf" shown | an LLM has no calibrated confidence | advisory flags, and a defined speech confidence labelled as a hint (AMD-28) |
| F6 | UC-01, 2.6, Figure 3.2 | Audio in memory (UC-01) but also a temporary WAV file (2.6, Figure 3.2) | the proposal contradicts itself | memory only (AMD-23) |
| F7 | 3.6, 3.3, 3.2.5 | Synthetic audio validated by professionals; a rubric made with experts; clinician interviews; representative machines | none of these existed | synthetic audio and a scoring sheet made (ADR-011); **open:** clinician scoring, real voices, a second PC (AMD-30) |
| F8 | 3.2.5 | Deliverables include System Design and Test Cases documentation | no test-case document planned | **open:** at the final update (AMD-31, NFR-08) |
| F9 | Appendix 1 | Gantt: implementation to about week 19, submission end of week 24 | re-plan needed | implementation complete by about week 16 (AMD-31) |
| F10 | 3.7 | "a minimum of 4 to 6 GB of RAM" | model uses 2.68 GB on an 8 GB PC | measured (AMD-33) |
| F11 | Figure 4.5 | The LLM engine sits inside the application boundary | Ollama is a separate process on 127.0.0.1:11434 | firewall rules cover it (AMD-10, ADR-010) |
| F12 | wireframe | "Lang: English (en)" | Swahili and mixed speech not covered | **open:** untested (AMD-35) |
| F13 | wireframe | "Export / Save" | writing outside the vault leaves the encryption | one finalized note as a PDF, audited (AMD-36) |
| F14 | UC-06, Figure 4.3 | Saving is optional | finalizing saves; not saving means discarding | **open:** confirm in the text (AMD-24) |
| F15 | 3.5, Figure 4.5 | GUI "Tkinter or PyQt6" | | PySide6 (AMD-09) |
| F16 | 2.4.2 | local models run on laptops "with 16 GB of RAM" | reference PC has 8 GB | measured on 8 GB (AMD-33) |
| F17 | References | Missing and duplicated references | | **open:** at the final update (AMD-13) |

## 7. Timeline (Appendix 1) against today
24 weeks, July to December 2026. Phase 4 implementation roughly weeks 11 to 19, Phase 5
verification weeks 18 to 22, deliverables weeks 21 to 24, submission at the end of week 24. On
16 October 2026 (about week 16) implementation is complete; verification with people (clinician scoring,
real voices, a second PC) and the deliverable documents remain. The defence date is not stated in
the proposal; confirm it with the supervisor.
