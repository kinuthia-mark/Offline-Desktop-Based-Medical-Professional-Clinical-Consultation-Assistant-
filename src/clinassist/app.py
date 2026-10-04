"""Composition root: the one place where the real parts are built and connected.

Everything else in the program receives its parts from here, which is why each part can be
tested on its own with fakes. The interface asks this module for a controller and never imports
an adapter itself.

Memory plan for an 8 GB PC (NFR-04, AMD-07, ADR-007). The speech model and the language model
are never in memory together:

    recording starts  -> free the language model, then load Whisper in the background
                         (it takes 1 to 2 s and the clinician is talking anyway)
    recording stops   -> transcribe, then free Whisper at once
    draft requested   -> Ollama loads MedGemma into the memory Whisper gave back
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from clinassist.config import AppConfig
from clinassist.controller import ConsultationController
from clinassist.ports import Auditor, InputGuard, NoteGenerator, Recorder, SessionStore


class SequentialModels:
    """Wraps the recorder, transcriber and generator so the memory plan above happens without
    the controller knowing about it. `log` records the order of steps, for the tests."""

    def __init__(self, transcriber, generator) -> None:
        self._transcriber = transcriber
        self._generator = generator
        self._preload: threading.Thread | None = None
        self.log: list[str] = []

    def before_recording(self) -> None:
        self._generator.unload()  # free MedGemma first
        self.log.append("llm_unloaded")
        # Load Whisper while the clinician speaks. A failure here (for example a missing model)
        # is not lost: transcribe() calls load() again and raises the proper error then.
        self._preload = threading.Thread(target=self._safe_preload, daemon=True)
        self._preload.start()

    @property
    def last_info(self):
        """Facts about the last transcription (language, confidence hint), for the screen."""
        return getattr(self._transcriber, "last_info", None)

    def _safe_preload(self) -> None:
        try:
            self._transcriber.load()
            self.log.append("whisper_loaded")
        except Exception:
            self.log.append("whisper_preload_failed")

    def transcribe(self, audio: bytes) -> str:
        if self._preload is not None:
            self._preload.join()
            self._preload = None
        try:
            text = self._transcriber.transcribe(audio)
            self.log.append("transcribed")
            return text
        finally:
            self._transcriber.unload()  # always give the memory back, even after an error
            self.log.append("whisper_unloaded")


class _PlannedRecorder:
    """The real recorder, with the memory plan's first step run before it starts."""

    def __init__(self, recorder: Recorder, plan: SequentialModels) -> None:
        self._recorder, self._plan = recorder, plan

    def start(self) -> None:
        self._plan.before_recording()
        self._recorder.start()

    def stop(self) -> bytes:
        return self._recorder.stop()


class ProgressRelay:
    """Passes the generator's progress (a growing count of pieces received) to whoever is
    listening, usually the interface's progress bar."""

    def __init__(self) -> None:
        self.listener = None

    def __call__(self, pieces: int) -> None:
        if self.listener is not None:
            self.listener(pieces)


@dataclass
class Services:
    """Everything the interface needs, built once after the vault is unlocked."""

    config: AppConfig
    recorder: Recorder
    microphone: object  # the unwrapped recorder: level meter and elapsed time for the screen
    progress: ProgressRelay
    plan: SequentialModels
    guard: InputGuard
    generator: NoteGenerator
    store: SessionStore
    auditor: Auditor
    auth: object  # AuthService; typed loosely to keep this module free of the security imports

    def new_controller(self) -> ConsultationController:
        """A fresh controller for each consultation."""
        return ConsultationController(
            recorder=self.recorder,
            transcriber=self.plan,
            guard=self.guard,
            generator=self.generator,
            store=self.store,
            auditor=self.auditor,
        )


def build(config: AppConfig, vault, *, recorder=None, transcriber=None, generator=None):
    """Connect the real parts. The keyword arguments replace a part, for tests and for the
    scripted evaluation (for example a recorder that plays a WAV file)."""
    from clinassist.adapters.input_guard import PatternInputGuard
    from clinassist.adapters.soap_generator import GeneratorSettings, SoapGenerator
    from clinassist.adapters.store import VaultSessionStore
    from clinassist.security.audit import HashChainAuditor
    from clinassist.security.auth import AuthService

    if recorder is None:
        from clinassist.adapters.recorder import SoundDeviceRecorder

        recorder = SoundDeviceRecorder(device=config.microphone)
    if transcriber is None:
        from clinassist.adapters.transcriber import WhisperTranscriber

        transcriber = WhisperTranscriber(config.whisper_dir())
    progress = ProgressRelay()
    if generator is None:
        generator = SoapGenerator(
            GeneratorSettings(model=config.llm_model, host=config.ollama_host), progress=progress
        )

    plan = SequentialModels(transcriber, generator)
    auditor = HashChainAuditor(vault)
    return Services(
        config=config,
        recorder=_PlannedRecorder(recorder, plan),
        microphone=recorder,
        progress=progress,
        plan=plan,
        guard=PatternInputGuard(),
        generator=generator,
        store=VaultSessionStore(vault),
        auditor=auditor,
        auth=AuthService(vault, auditor),
    )


class WavFileRecorder:
    """A Recorder that "records" by returning a WAV file. Used by the scripted evaluation and
    demonstrations with synthetic audio; never by the real interface."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def start(self) -> None:
        return None

    def stop(self) -> bytes:
        return self._path.read_bytes()
