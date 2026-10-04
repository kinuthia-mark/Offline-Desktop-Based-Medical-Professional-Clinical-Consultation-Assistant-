"""Microphone recorder (FR-01, UC-01): implements the controller's Recorder port.

Audio is captured at 16 kHz, mono, 16-bit, which is what Whisper works with, and kept in memory
only. Nothing is written to disk here; keeping a recording is a separate, optional step that is
off by default (adapters/audio_store.py, ADR-003). `stop()` returns the recording as WAV bytes,
so the next step can read the format from the data itself.

Errors are short codes for the interface to explain:

    no_microphone              Windows reports no input device at all
    microphone_unavailable     the device could not be opened (in use, unplugged, blocked)
    sample_rate_not_supported  the device cannot record at 16 kHz
    already_recording / not_recording   start and stop called out of order

On Windows, a microphone blocked in the privacy settings often records silence instead of
failing. So every recording is measured, and `last_info.silent` is True when nothing was heard.
"""

from __future__ import annotations

import io
import threading
import time
import wave
from array import array
from dataclasses import dataclass

SAMPLE_RATE = 16_000  # samples per second; Whisper's native rate
CHANNELS = 1  # mono: one microphone, and half the memory of stereo
SAMPLE_WIDTH = 2  # bytes per sample (16-bit)
BLOCK_SECONDS = 0.1  # the audio arrives in blocks of a tenth of a second
DEFAULT_MAX_SECONDS = 45 * 60  # longest consultation kept: 45 minutes, about 86 MB in memory
# Below this peak level (out of 1.0) a recording counts as silent. A quiet room still gives
# about 0.001 to 0.01 from background noise, so true digital silence is well below it.
SILENCE_PEAK = 0.0005

# Inputs that record what the computer is playing rather than what the microphone hears. They
# are never offered as a microphone.
_LOOPBACK_WORDS = ("stereo mix", "what u hear", "wave out", "loopback", "mixage stéréo")


class RecorderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    default_sample_rate: float


@dataclass(frozen=True)
class RecordingInfo:
    """Facts about the last recording, for the interface and the logs. No audio content."""

    seconds: float
    peak: float  # loudest sample, 0.0 to 1.0
    rms: float  # average loudness, 0.0 to 1.0
    silent: bool
    limit_reached: bool  # recording stopped itself at max_seconds
    overflows: int  # blocks where the computer was too busy and audio was lost


def _block_stats(pcm: bytes) -> tuple[int, int, int]:
    """Loudest sample, sum of squares and sample count of one block of 16-bit audio. Kept as
    running totals while recording, so the level of a 45-minute recording is known at once."""
    samples = array("h", pcm)
    if not samples:
        return 0, 0, 0
    return max(max(samples), -min(samples)), sum(s * s for s in samples), len(samples)


def to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw 16-bit mono samples in a WAV header, in memory."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _sounddevice():
    import sounddevice  # loaded on first use, so the rest of the app works without it

    return sounddevice


def list_input_devices(sd=None) -> list[InputDevice]:
    """Microphones the clinician can choose from, each listed once.

    Windows lists the same microphone once per audio system (MME, DirectSound, WASAPI, WDM-KS).
    Only devices on the same audio system as the Windows default input are listed, and inputs
    that record the computer's own sound output ("Stereo Mix") are left out."""
    sd = sd or _sounddevice()
    default_index = sd.default.device[0]
    if default_index is None or default_index < 0:
        return []
    devices = sd.query_devices()
    default_api = devices[default_index]["hostapi"]
    found = []
    for index, info in enumerate(devices):
        name = str(info["name"]).strip()
        if (
            info["max_input_channels"] > 0
            and info["hostapi"] == default_api
            and not any(word in name.lower() for word in _LOOPBACK_WORDS)
        ):
            found.append(InputDevice(index, name, float(info["default_samplerate"])))
    return found


class SoundDeviceRecorder:
    """Records from one microphone into memory. `sd` is the sounddevice module; tests pass a
    fake one so no hardware is needed."""

    def __init__(
        self,
        device: int | None = None,
        max_seconds: float = DEFAULT_MAX_SECONDS,
        sd=None,
    ) -> None:
        self._sd = sd
        self._device = device  # None means the Windows default microphone
        self._max_bytes = int(max_seconds * SAMPLE_RATE) * SAMPLE_WIDTH
        self._lock = threading.Lock()  # the audio arrives on another thread
        self._stream = None
        self._buffer = bytearray()
        self._level = 0.0
        self._peak, self._sum_squares, self._count = 0, 0, 0
        self._limit_reached = False
        self._overflows = 0
        self._started_at = 0.0
        self.last_info: RecordingInfo | None = None

    # ----- the Recorder port -----
    def start(self) -> None:
        if self._stream is not None:
            raise RecorderError("already_recording")
        sd = self._sd or _sounddevice()
        self._sd = sd
        if self._device is None and (sd.default.device[0] is None or sd.default.device[0] < 0):
            raise RecorderError("no_microphone")
        with self._lock:
            self._buffer = bytearray()
            self._level, self._limit_reached, self._overflows = 0.0, False, 0
            self._peak, self._sum_squares, self._count = 0, 0, 0
        try:
            stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=int(SAMPLE_RATE * BLOCK_SECONDS),
                device=self._device,
                callback=self._on_audio,
            )
            stream.start()
        except sd.PortAudioError as exc:
            raise RecorderError(_error_code(str(exc))) from None
        self._stream = stream
        self._started_at = time.monotonic()

    def stop(self) -> bytes:
        """Stop and return the recording as WAV bytes. Always releases the microphone."""
        if self._stream is None:
            raise RecorderError("not_recording")
        stream, self._stream = self._stream, None
        try:
            stream.stop()
        finally:
            stream.close()  # release the device even if stopping failed
        with self._lock:
            pcm = bytes(self._buffer)
            self._buffer = bytearray()  # do not keep a second copy of the consultation
            limit, overflows = self._limit_reached, self._overflows
            peak = min(self._peak / 32768, 1.0)
            rms = (self._sum_squares / self._count) ** 0.5 / 32768 if self._count else 0.0
        self.last_info = RecordingInfo(
            seconds=len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH),
            peak=round(peak, 5),
            rms=round(rms, 5),
            silent=peak < SILENCE_PEAK,
            limit_reached=limit,
            overflows=overflows,
        )
        return to_wav(pcm)

    # ----- for the interface while recording -----
    @property
    def recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """Loudness of the latest block, 0.0 to 1.0, for a level meter on screen."""
        return self._level

    @property
    def seconds(self) -> float:
        with self._lock:
            return len(self._buffer) / (SAMPLE_RATE * SAMPLE_WIDTH)

    # ----- internals -----
    def _on_audio(self, indata, frames, time_info, status) -> None:
        """Called by the audio system on its own thread for every block. Kept short: copy the
        block, note the level, and stop once the maximum length is reached."""
        block = bytes(indata)
        with self._lock:
            if status and getattr(status, "input_overflow", False):
                self._overflows += 1
            # Keep only as much of the block as fits under the maximum length.
            room = max(self._max_bytes - len(self._buffer), 0)
            kept = block[:room]
            self._buffer.extend(kept)
            peak, squares, count = _block_stats(kept)
            self._peak = max(self._peak, peak)
            self._sum_squares += squares
            self._count += count
            self._level = min(peak / 32768, 1.0)
            if len(block) >= room:
                self._limit_reached = True
        if self._limit_reached:
            raise self._sd.CallbackStop  # tells the audio system to stop calling us


def _error_code(message: str) -> str:
    """Turn a PortAudio message into one of our codes. The message is not passed on."""
    text = message.lower()
    if "sample rate" in text or "samplerate" in text:
        return "sample_rate_not_supported"
    if "no default input" in text or "device -1" in text or "no device" in text:
        return "no_microphone"
    return "microphone_unavailable"
