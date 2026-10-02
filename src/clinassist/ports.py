"""Interfaces the controller depends on. Adapters (audio, Whisper, Ollama, SQLCipher) implement
these in later branches, and tests supply fakes."""

from __future__ import annotations

from typing import Protocol

from clinassist.domain import Draft, GuardVerdict, SessionRecord


class Recorder(Protocol):
    def start(self) -> None: ...
    def stop(self) -> bytes: ...


class Transcriber(Protocol):
    def transcribe(self, audio: bytes) -> str: ...


class InputGuard(Protocol):
    def check(self, text: str) -> GuardVerdict: ...


class NoteGenerator(Protocol):
    def generate(self, text: str, attempt: int) -> Draft:
        """Return a draft or raise GenerationFailed. `attempt` is 1 for the first try, so an
        implementation can change its settings on a retry (for example a repetition penalty)."""
        ...


class SessionStore(Protocol):
    def save(self, record: SessionRecord) -> None: ...


class Auditor(Protocol):
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        """Events carry names and ids only, never transcript or note text."""
        ...


class NullAuditor:
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        return None
