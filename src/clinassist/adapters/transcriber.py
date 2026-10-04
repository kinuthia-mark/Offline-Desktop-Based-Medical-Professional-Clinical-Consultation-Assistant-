"""Speech-to-text with Faster-Whisper (FR-02, UC-02, ADR-007): implements the Transcriber port.

The model is loaded from a folder on this PC, never by name, so the library never reaches for
the internet: Hugging Face's offline switch is set before the library is imported, and the
folder must already contain the model. It runs on the CPU with 8-bit weights (int8), which is
what an 8 GB laptop without a graphics card can afford.

The language model and the speech model should not sit in memory together on an 8 GB PC, so the
model is loaded on first use and `unload()` frees it (NFR-04, AMD-07).

`last_info.confidence` is the average probability the model gave its own words, weighted by how
long each piece of speech lasts. It is not accuracy: a clear, confident wrong word scores high.
It is shown as a hint, the way the wireframe's "ASR Conf" label intended (AMD-28).
"""

from __future__ import annotations

import gc
import io
import math
import os
import time
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16_000


class TranscriptionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TranscriptionInfo:
    audio_seconds: float
    processing_seconds: float
    real_time_factor: float  # processing time / audio length; below 1.0 is faster than real time
    language: str
    language_probability: float
    confidence: float  # see the module docstring: a hint, not accuracy
    segments: int


def _real_model(model_dir: str, compute_type: str, cpu_threads: int):
    # Offline switches go on before the library is imported, so nothing tries to download.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_dir,
        device="cpu",
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        local_files_only=True,
    )


def wav_to_samples(audio: bytes):
    """WAV bytes from the recorder -> float samples between -1 and 1, as Whisper expects."""
    import numpy as np

    try:
        with wave.open(io.BytesIO(audio)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                raise TranscriptionError("unsupported_audio_format")
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        raise TranscriptionError("unreadable_audio") from None
    return np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0


class WhisperTranscriber:
    """`model_factory(model_dir, compute_type, cpu_threads)` builds the model; tests pass a fake."""

    def __init__(
        self,
        model_dir: str | Path,
        language: str | None = "en",
        compute_type: str = "int8",
        cpu_threads: int = 0,  # 0 lets the library choose (one per physical core)
        beam_size: int = 5,
        vad_filter: bool = True,  # skip long silences, which also stops Whisper inventing text
        model_factory=_real_model,
    ) -> None:
        self._dir = Path(model_dir)
        self._language = language
        self._compute_type = compute_type
        self._threads = cpu_threads
        self._beam_size = beam_size
        self._vad = vad_filter
        self._factory = model_factory
        self._model = None
        self.last_info: TranscriptionInfo | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> float:
        """Load the model now (for example while the clinician is still talking). Returns the
        seconds it took. Raises asr_model_missing if the folder does not hold a model."""
        if self._model is not None:
            return 0.0
        if not (self._dir / "model.bin").is_file():
            raise TranscriptionError("asr_model_missing")
        start = time.perf_counter()
        try:
            self._model = self._factory(str(self._dir), self._compute_type, self._threads)
        except Exception:
            raise TranscriptionError("asr_model_failed_to_load") from None
        return time.perf_counter() - start

    def unload(self) -> None:
        """Free the model's memory before the language model runs."""
        self._model = None
        gc.collect()

    def transcribe(self, audio: bytes) -> str:
        samples = wav_to_samples(audio)
        audio_seconds = len(samples) / SAMPLE_RATE
        self.load()
        start = time.perf_counter()
        try:
            segments, info = self._model.transcribe(
                samples,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=self._vad,
                condition_on_previous_text=False,  # stops one mistake repeating down the text
            )
            # The library produces segments lazily; reading them is where the work happens.
            pieces = [(s.text.strip(), s.end - s.start, s.avg_logprob) for s in segments]
        except TranscriptionError:
            raise
        except Exception:
            raise TranscriptionError("asr_failed") from None
        elapsed = time.perf_counter() - start

        spoken = sum(d for _, d, _ in pieces)
        confidence = sum(d * math.exp(lp) for _, d, lp in pieces) / spoken if spoken > 0 else 0.0
        self.last_info = TranscriptionInfo(
            audio_seconds=round(audio_seconds, 2),
            processing_seconds=round(elapsed, 2),
            real_time_factor=round(elapsed / audio_seconds, 3) if audio_seconds else 0.0,
            language=info.language,
            language_probability=round(float(info.language_probability), 3),
            confidence=round(confidence, 3),
            segments=len(pieces),
        )
        return " ".join(text for text, _, _ in pieces if text)
