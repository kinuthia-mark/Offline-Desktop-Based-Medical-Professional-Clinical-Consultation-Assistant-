"""Interfaces the controller depends on. Adapters (audio, Whisper, Ollama, SQLCipher) implement
these in later branches, and tests supply fakes."""

from __future__ import annotations

from typing import Protocol

from clinassist.domain import Draft, GuardVerdict, SessionRecord

# Each class below is a contract: "anything with these methods can be plugged in here". The
# controller only knows these contracts, never the real microphone, model or database. A
# Protocol has no code of its own; the real parts live in the adapters and security folders.


class Recorder(Protocol):
    # The microphone: start capturing, then stop and hand back the recorded audio.
    def start(self) -> None: ...
    def stop(self) -> bytes: ...


class Transcriber(Protocol):
    # Speech-to-text: audio in, text out.
    def transcribe(self, audio: bytes) -> str: ...


class InputGuard(Protocol):
    # Screens approved text before the model sees it.
    def check(self, text: str) -> GuardVerdict: ...


class NoteGenerator(Protocol):
    def generate(self, text: str, attempt: int) -> Draft:
        """Return a draft or raise GenerationFailed. `attempt` is 1 for the first try, so an
        implementation can change its settings on a retry (for example a repetition penalty)."""
        ...


class SessionStore(Protocol):
    # Saves a finished consultation. Must raise an error, not return quietly, if saving fails.
    def save(self, record: SessionRecord) -> None: ...


class Auditor(Protocol):
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        """Events carry names and ids only, never transcript or note text."""
        ...


class NullAuditor:
    # Does nothing. Used when no audit log is supplied, for example in some tests.
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        return None
