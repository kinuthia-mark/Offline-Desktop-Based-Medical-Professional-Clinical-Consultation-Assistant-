# Threat Model

**Asset:** doctor–patient audio, transcripts, and generated SOAP notes (PHI).
**Trust boundary:** the host running the container. Everything that enters the pipeline
(audio, and therefore the transcript) is **untrusted input**.

| # | Threat | Mitigation in this repo | Residual risk |
|---|--------|-------------------------|---------------|
| T1 | **Prompt injection** via speech or a crafted audio file ("ignore previous instructions…") | Unicode normalisation; regex screening (`guardrails.py`); default policy **quarantines** flagged input *before* inference; transcript wrapped in `<transcript>` tags with delimiters escaped; system prompt tells the model to treat it as data; strict JSON schema with `extra="forbid"`; optional NeMo input rail | Heuristics are bypassable (paraphrase, other languages, indirect phrasing). The model may still be swayed by novel attacks. Treat output as a draft requiring clinician review. |
| T2 | **Context / prompt leakage** in model output | Per-request **canary** token in the system prompt; output containing it is quarantined; output containing URLs is quarantined | Detects verbatim leakage only, not paraphrased leakage. |
| T3 | **Network egress / exfiltration** by a compromised dependency or model runtime | `network_mode: none`; runtime `enforce_airgap()` probe refuses to start if a public IP is reachable; LLM client only accepts loopback URLs and ignores proxy env vars; `HF_HUB_OFFLINE`, `local_files_only`, telemetry env flags | Does not defend against a compromised *host* or container-runtime escape. Weight files must be verified at staging time (see supply chain). |
| T4 | **Resource exhaustion** (huge or endless audio, runaway inference) | cgroup CPU/memory/PID limits; `max_audio_seconds`; transcript length cap; LLM request timeout | A tight limit can also make legitimate long recordings fail. |
| T5 | **PHI at rest / in logs** | Outputs written `0600` in a single writable mount; no transcript or note text is ever logged (errors are coarse codes); no swap (`memswap_limit == mem_limit`); read-only root FS; `tmpfs` for scratch | Outputs are **not encrypted at rest** by this repo — use full-disk/volume encryption. Filenames are copied into `source`: use opaque IDs, not patient names. |
| T6 | **PII exposure to the model** | Regex redaction (SSN, phone, email, MRN, labelled DOB, URLs, IPs) before inference | Regex cannot find free-text names or addresses, or PII *spoken as words* ("five five five…"). Add an NER-based redactor (e.g. Presidio) for production. |
| T7 | **Supply chain** (base image, PyPI packages, model weights) | Weights baked in offline; read-only mounts; minimal deps | Base image is `latest` by default — pin a digest. Pin and hash Python deps. Verify weight checksums on the staging machine. |
| T8 | **Container hardening** | non-root UID, `cap_drop: ALL`, `no-new-privileges`, read-only rootfs | `/tmp` is mounted `exec` for Ollama's runner; drop that if your build doesn't need it. |

## Out of scope
Physical access, host OS compromise, insider misuse, EMR-side security, user authentication
and audit logging, and the clinical safety/accuracy of generated notes.
