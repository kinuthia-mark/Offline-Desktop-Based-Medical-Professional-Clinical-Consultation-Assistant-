"""Microphone recorder (FR-01): format, limits, errors and device listing, using a fake audio
system so no hardware is needed. One test uses the real microphone and is skipped unless
CLINASSIST_HARDWARE=1 is set."""

from __future__ import annotations

import io
import os
import wave
from array import array

import pytest

from clinassist.adapters.recorder import (
    SAMPLE_RATE,
    RecorderError,
    SoundDeviceRecorder,
    list_input_devices,
    to_wav,
)
from clinassist.controller import ConsultationController, State


# ----- a fake sounddevice module -----
class FakePortAudioError(Exception):
    pass


class FakeCallbackStop(Exception):
    pass


class FakeStatus:
    def __init__(self, overflow: bool = False) -> None:
        self.input_overflow = overflow


def tone(samples: int, amplitude: int) -> bytes:
    """A square wave at the given amplitude (out of 32767)."""
    return array("h", [amplitude if i % 2 else -amplitude for i in range(samples)]).tobytes()


def _device(name: str, inputs: int, hostapi: int, rate: int) -> dict:
    return {
        "name": name,
        "max_input_channels": inputs,
        "hostapi": hostapi,
        "default_samplerate": rate,
    }


class FakeSD:
    PortAudioError = FakePortAudioError
    CallbackStop = FakeCallbackStop

    def __init__(self, blocks=(), default_input=1, open_error=None, devices=None, overflow_at=()):
        self.blocks = list(blocks)  # what the "microphone" hears, block by block
        self.open_error = open_error
        self.overflow_at = set(overflow_at)
        self.streams: list[FakeStream] = []
        self.default = type("Default", (), {"device": [default_input, 3]})()
        self.devices = devices or [
            _device("Sound Mapper", 2, 0, 44100),
            _device("Microphone Array", 2, 0, 44100),
            _device("Speakers", 0, 0, 44100),
            _device("Stereo Mix (Realtek)", 2, 0, 48000),  # records the PC's own sound output
            _device("Microphone Array", 2, 1, 48000),  # same microphone, another audio system
        ]

    def query_devices(self):
        return self.devices

    def RawInputStream(self, **kwargs):  # noqa: N802 - same name as the real module
        if self.open_error:
            raise FakePortAudioError(self.open_error)
        stream = FakeStream(self, kwargs)
        self.streams.append(stream)
        return stream


class FakeStream:
    def __init__(self, sd: FakeSD, kwargs: dict) -> None:
        self.sd, self.kwargs = sd, kwargs
        self.started = self.stopped = self.closed = False
        self.callback_stopped = False

    def start(self) -> None:
        self.started = True

    def deliver(self) -> None:
        """Feed every block to the recorder, as the audio thread would."""
        for i, block in enumerate(self.sd.blocks):
            status = FakeStatus(overflow=i in self.sd.overflow_at)
            try:
                self.kwargs["callback"](block, len(block) // 2, None, status)
            except FakeCallbackStop:
                self.callback_stopped = True
                return

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


BLOCK = int(SAMPLE_RATE * 0.1)  # one tenth of a second


def record(sd: FakeSD, **kwargs) -> tuple[SoundDeviceRecorder, bytes]:
    rec = SoundDeviceRecorder(sd=sd, **kwargs)
    rec.start()
    sd.streams[-1].deliver()
    return rec, rec.stop()


def read_wav(data: bytes):
    with wave.open(io.BytesIO(data)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())


# ----- format -----
def test_records_16khz_mono_16bit_wav():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)] * 10)
    rec, data = record(sd)
    rate, channels, width, frames = read_wav(data)
    assert (rate, channels, width) == (16000, 1, 2)
    assert frames == tone(BLOCK, 3000) * 10
    assert sd.streams[0].kwargs["samplerate"] == 16000
    assert sd.streams[0].kwargs["channels"] == 1 and sd.streams[0].kwargs["dtype"] == "int16"
    assert rec.last_info.seconds == pytest.approx(1.0)


def test_levels_are_measured():
    rec, _ = record(FakeSD(blocks=[tone(BLOCK, 16384)] * 5))
    assert rec.last_info.peak == pytest.approx(0.5)
    assert rec.last_info.rms == pytest.approx(0.5)
    assert not rec.last_info.silent


def test_a_silent_recording_is_reported():
    """Windows often records silence when the microphone is blocked in privacy settings."""
    rec, _ = record(FakeSD(blocks=[bytes(BLOCK * 2)] * 5))
    assert rec.last_info.silent and rec.last_info.peak == 0.0


def test_quiet_room_noise_is_not_counted_as_silence():
    """Measured on the reference PC: a quiet room peaked at about 0.0013."""
    rec, _ = record(FakeSD(blocks=[tone(BLOCK, 40)] * 5))  # 40/32768 = 0.0012
    assert not rec.last_info.silent


def test_level_meter_follows_the_latest_block():
    sd = FakeSD(blocks=[tone(BLOCK, 30000), tone(BLOCK, 3000)])
    rec = SoundDeviceRecorder(sd=sd)
    rec.start()
    sd.streams[0].deliver()
    assert rec.level == pytest.approx(3000 / 32768)
    assert rec.recording and rec.seconds == pytest.approx(0.2)
    rec.stop()
    assert not rec.recording


def test_the_recorder_does_not_keep_the_audio_after_handing_it_over():
    """Privacy: after stop() the only copy is the one returned to the caller."""
    rec, _ = record(FakeSD(blocks=[tone(BLOCK, 3000)] * 5))
    assert rec.seconds == 0.0
    assert len(rec._buffer) == 0


# ----- limits -----
def test_recording_stops_itself_at_the_maximum_length():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)] * 50)  # 5 seconds offered
    rec, data = record(sd, max_seconds=2.0)
    assert rec.last_info.limit_reached
    assert rec.last_info.seconds == pytest.approx(2.0)
    assert len(read_wav(data)[3]) == 2 * SAMPLE_RATE * 2
    assert sd.streams[0].callback_stopped


def test_lost_audio_is_counted():
    rec, _ = record(FakeSD(blocks=[tone(BLOCK, 3000)] * 5, overflow_at={1, 3}))
    assert rec.last_info.overflows == 2


# ----- order and cleanup -----
def test_microphone_is_released_after_stop():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)])
    record(sd)
    assert sd.streams[0].stopped and sd.streams[0].closed


def test_microphone_is_released_even_if_stopping_fails():
    sd = FakeSD()
    rec = SoundDeviceRecorder(sd=sd)
    rec.start()

    def broken_stop():
        raise FakePortAudioError("device lost")

    sd.streams[0].stop = broken_stop
    with pytest.raises(FakePortAudioError):
        rec.stop()
    assert sd.streams[0].closed and not rec.recording


def test_start_twice_and_stop_without_start_are_refused():
    rec = SoundDeviceRecorder(sd=FakeSD())
    with pytest.raises(RecorderError, match="^not_recording$"):
        rec.stop()
    rec.start()
    with pytest.raises(RecorderError, match="^already_recording$"):
        rec.start()


def test_a_second_recording_starts_empty():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)] * 3)
    rec, _ = record(sd)
    sd.blocks = [tone(BLOCK, 1000)]
    rec.start()
    sd.streams[-1].deliver()
    assert rec.stop() == to_wav(tone(BLOCK, 1000))


# ----- errors -----
def test_no_microphone_at_all():
    with pytest.raises(RecorderError, match="^no_microphone$"):
        SoundDeviceRecorder(sd=FakeSD(default_input=-1)).start()


@pytest.mark.parametrize(
    "message, code",
    [
        ("Invalid sample rate [PaErrorCode -9997]", "sample_rate_not_supported"),
        ("Error querying device -1", "no_microphone"),
        ("Unanticipated host error [PaErrorCode -9999]", "microphone_unavailable"),
        ("Device unavailable [PaErrorCode -9985]", "microphone_unavailable"),
    ],
)
def test_audio_system_errors_become_codes(message, code):
    with pytest.raises(RecorderError) as info:
        SoundDeviceRecorder(sd=FakeSD(open_error=message)).start()
    assert info.value.code == code
    assert "PaErrorCode" not in str(info.value)


def test_a_failed_start_leaves_the_recorder_usable():
    sd = FakeSD(open_error="Device unavailable")
    rec = SoundDeviceRecorder(sd=sd)
    with pytest.raises(RecorderError):
        rec.start()
    sd.open_error = None
    rec.start()
    assert rec.recording


# ----- device list -----
def test_device_list_has_each_microphone_once_and_no_loopback_inputs():
    devices = list_input_devices(FakeSD())
    assert [(d.index, d.name) for d in devices] == [(0, "Sound Mapper"), (1, "Microphone Array")]


def test_device_list_is_empty_without_a_default_microphone():
    assert list_input_devices(FakeSD(default_input=-1)) == []


def test_a_chosen_device_is_used():
    sd = FakeSD()
    rec = SoundDeviceRecorder(device=1, sd=sd)
    rec.start()
    assert sd.streams[0].kwargs["device"] == 1


# ----- with the controller -----
class _Asr:
    def __init__(self) -> None:
        self.audio = b""

    def transcribe(self, audio: bytes) -> str:
        self.audio = audio
        return "transcript"


class _Unused:
    def check(self, text):  # pragma: no cover - not reached
        raise AssertionError

    def generate(self, text, attempt):  # pragma: no cover
        raise AssertionError

    def save(self, record):  # pragma: no cover
        raise AssertionError


def test_controller_hands_the_wav_to_speech_to_text():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)] * 3)
    asr = _Asr()
    c = ConsultationController(SoundDeviceRecorder(sd=sd), asr, _Unused(), _Unused(), _Unused())
    c.start_recording()
    sd.streams[0].deliver()
    c.stop_recording()
    assert read_wav(asr.audio)[3] == tone(BLOCK, 3000) * 3
    assert c.state is State.TRANSCRIBED


def test_discard_while_recording_releases_the_microphone():
    sd = FakeSD(blocks=[tone(BLOCK, 3000)])
    c = ConsultationController(SoundDeviceRecorder(sd=sd), _Asr(), _Unused(), _Unused(), _Unused())
    c.start_recording()
    c.discard()
    assert sd.streams[0].closed and c.state is State.IDLE


# ----- the real microphone (opt-in) -----
@pytest.mark.hardware
@pytest.mark.skipif(
    os.environ.get("CLINASSIST_HARDWARE") != "1", reason="set CLINASSIST_HARDWARE=1 to use the mic"
)
def test_real_microphone_records_two_seconds():
    import time

    pytest.importorskip("sounddevice")
    rec = SoundDeviceRecorder()
    rec.start()
    time.sleep(2.0)
    rate, channels, width, frames = read_wav(rec.stop())
    assert (rate, channels, width) == (16000, 1, 2)
    assert 1.5 <= rec.last_info.seconds <= 2.2
    assert not rec.last_info.silent, "silent: check Windows microphone privacy settings"
