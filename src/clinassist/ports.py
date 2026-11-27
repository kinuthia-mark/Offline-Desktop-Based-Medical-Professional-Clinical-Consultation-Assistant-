"""Interfaces the controller depends on. Adapters (audio, Whisper, Ollama, SQLCipher) implement
these in later branches, and tests supply fakes."""

# This file lists, as Protocols, what the controller needs from the outside world: a microphone,
# a speech-to-text part, an input guard, a note generator, a store and an auditor. The real
# versions live in other folders and the tests use simple fakes. Because the controller depends
# only on these shapes, any part can be swapped without changing the controller.
# Lets the type hints refer to classes defined later in the file, without quotes.
from __future__ import annotations

# Protocol describes a shape: any class with matching methods fits, no inheritance needed.
from typing import Protocol

from clinassist.domain import Draft, GuardVerdict, SessionRecord

# Each class below is a contract: "anything with these methods can be plugged in here". The
# controller only knows these contracts, never the real microphone, model or database. A
# Protocol has no code of its own; the real parts live in the adapters and security folders.


# The microphone part.
class Recorder(Protocol):
    # The microphone: start capturing, then stop and hand back the recorded audio.
    def start(self) -> None: ...  # the `...` body means no code here, only the shape of the method
    def stop(self) -> bytes: ...  # returns the recorded audio as raw bytes


# The speech-to-text part (Whisper in the real app).
class Transcriber(Protocol):
    # Speech-to-text: audio in, text out.
    def transcribe(self, audio: bytes) -> str: ...


# The part that screens text before the model sees it.
class InputGuard(Protocol):
    # Screens approved text before the model sees it.
    def check(self, text: str) -> GuardVerdict: ...


# The part that turns approved text into a draft note (the Ollama model in the real app).
class NoteGenerator(Protocol):
    def generate(self, text: str, attempt: int) -> Draft:
        """Return a draft or raise GenerationFailed. `attempt` is 1 for the first try, so an
        implementation can change its settings on a retry (for example a repetition penalty)."""
        ...


# The part that saves a finished consultation (the encrypted vault in the real app).
class SessionStore(Protocol):
    # Saves a finished consultation. Must raise an error, not return quietly, if saving fails.
    def save(self, record: SessionRecord) -> None: ...


# The part that writes the audit log (the hash-chained log in the real app).
class Auditor(Protocol):
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        """Events carry names and ids only, never transcript or note text."""
        ...


# A stand-in auditor that records nothing, so the controller works without a real log.
class NullAuditor:
    # Does nothing. Used when no audit log is supplied, for example in some tests.
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        return None
