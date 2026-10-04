"""Orchestration: audio -> transcript -> guardrails -> local LLM -> validated SOAP JSON."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from .audio import AudioError, validate_wav
from .guardrails import URL_RE, GuardrailReport, sanitize, wrap_untrusted
from .llm import LLMClient, LLMError
from .soap import REPAIR_SUFFIX, SOAPValidationError, build_system_prompt, parse_soap_json
from .transcribe import Transcriber

SCHEMA_VERSION = "1.0"
DISCLAIMER = "AI-generated draft. Must be reviewed and signed off by a licensed clinician."


@dataclass
class PipelineResult:
    status: str  # "ok" | "quarantined" | "failed"
    source: str
    model: str
    guardrails: dict = field(default_factory=dict)
    note: dict | None = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "source": self.source,
            "created_at": self.created_at,
            "model": self.model,
            "disclaimer": DISCLAIMER,
            "guardrails": self.guardrails,
            "note": self.note,
            "error": self.error,
        }


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        transcriber: Transcriber | None = None,
        injection_policy: str = "quarantine",
        max_audio_seconds: int = 3600,
        max_attempts: int = 2,
        extra_input_check: Callable[[str], bool] | None = None,
    ) -> None:
        self.llm = llm
        self.transcriber = transcriber
        self.injection_policy = injection_policy
        self.max_audio_seconds = max_audio_seconds
        self.max_attempts = max_attempts
        self.extra_input_check = extra_input_check

    def _result(self, status: str, source: str, report: GuardrailReport, **kw) -> PipelineResult:
        return PipelineResult(
            status=status, source=source, model=self.llm.model, guardrails=report.to_dict(), **kw
        )

    def process_audio(self, path: Path) -> PipelineResult:
        source = path.name
        if self.transcriber is None:
            raise RuntimeError("no transcriber configured")
        try:
            validate_wav(path, self.max_audio_seconds)
        except AudioError as exc:
            return self._result("failed", source, GuardrailReport(), error=str(exc))
        return self.process_text(self.transcriber.transcribe(path), source)

    def process_text(self, text: str, source: str = "text") -> PipelineResult:
        if not text.strip():
            return self._result("failed", source, GuardrailReport(), error="empty_transcript")

        clean, report = sanitize(text, self.injection_policy)
        if not report.quarantined and self.extra_input_check and not self.extra_input_check(clean):
            report = replace(report, quarantined=True, reason="nemo_input_rail")
        if report.quarantined:
            return self._result("quarantined", source, report, error=report.reason)

        canary = f"AEGIS-CANARY-{secrets.token_hex(8)}"
        system = build_system_prompt(canary)
        user = wrap_untrusted(clean)

        last_error = "invalid_json"
        for attempt in range(self.max_attempts):
            try:
                raw = self.llm.generate(system, user if attempt == 0 else user + REPAIR_SUFFIX)
            except LLMError as exc:
                return self._result("failed", source, report, error=str(exc))

            # Output guardrails: block prompt leakage and outbound-link smuggling.
            if canary in raw:
                q = replace(report, quarantined=True, reason="output_canary_leak")
                return self._result("quarantined", source, q, error=q.reason)
            if URL_RE.search(raw):
                q = replace(report, quarantined=True, reason="output_contains_url")
                return self._result("quarantined", source, q, error=q.reason)

            try:
                note = parse_soap_json(raw)
            except SOAPValidationError as exc:
                last_error = str(exc)
                continue
            return self._result("ok", source, report, note=note.model_dump())

        return self._result("failed", source, report, error=last_error)
