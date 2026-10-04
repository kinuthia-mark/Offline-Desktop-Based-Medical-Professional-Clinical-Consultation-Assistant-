"""Speech-to-text (FR-02, ADR-007): the adapter with a fake model, the WER calculator, and an
optional run of the real model when it is present in models/."""

from __future__ import annotations

import math
import os
from array import array
from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from clinassist.adapters.recorder import to_wav  # noqa: E402
from clinassist.adapters.transcriber import (  # noqa: E402
    TranscriptionError,
    WhisperTranscriber,
    wav_to_samples,
)
from clinassist.metrics import normalize, word_error_rate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ----- a fake Whisper model -----
@dataclass
class Seg:
    text: str
    start: float
    end: float
    avg_logprob: float


@dataclass
class Info:
    language: str = "en"
    language_probability: float = 0.99


class FakeModel:
    def __init__(self, segments=None, error=None) -> None:
        self.segments = (
            segments if segments is not None else [Seg(" Hello doctor.", 0.0, 2.0, -0.1)]
        )
        self.error = error
        self.calls: list[dict] = []

    def transcribe(self, samples, **kwargs):
        self.calls.append({"samples": samples, **kwargs})
        if self.error:
            raise self.error
        return iter(self.segments), Info()


def model_dir(tmp_path: Path) -> Path:
    (tmp_path / "model.bin").write_bytes(b"fake weights")
    return tmp_path


def make(tmp_path, model=None, **kwargs):
    model = model or FakeModel()
    built = []

    def factory(path, compute_type, threads):
        built.append((path, compute_type, threads))
        return model

    return WhisperTranscriber(model_dir(tmp_path), model_factory=factory, **kwargs), model, built


def speech(seconds: float) -> bytes:
    n = int(16000 * seconds)
    return to_wav(array("h", [1000 if i % 2 else -1000 for i in range(n)]).tobytes())


# ----- adapter -----
def test_segments_are_joined_into_one_transcript(tmp_path):
    model = FakeModel([Seg(" Good morning.", 0, 1, -0.1), Seg(" I have a cough. ", 1, 3, -0.2)])
    t, _, _ = make(tmp_path, model)
    assert t.transcribe(speech(3)) == "Good morning. I have a cough."


def test_settings_passed_to_the_model(tmp_path):
    t, model, built = make(tmp_path)
    t.transcribe(speech(1))
    assert built == [(str(tmp_path), "int8", 0)]
    call = model.calls[0]
    assert call["language"] == "en" and call["beam_size"] == 5
    assert call["vad_filter"] is True and call["condition_on_previous_text"] is False


def test_audio_reaches_the_model_as_float_samples(tmp_path):
    t, model, _ = make(tmp_path)
    t.transcribe(speech(1))
    samples = model.calls[0]["samples"]
    assert str(samples.dtype) == "float32" and len(samples) == 16000
    assert float(abs(samples).max()) == pytest.approx(1000 / 32768)


def test_info_reports_timing_language_and_confidence(tmp_path):
    model = FakeModel([Seg("a", 0, 1, math.log(0.9)), Seg("b", 1, 4, math.log(0.5))])
    t, _, _ = make(tmp_path, model)
    t.transcribe(speech(4))
    info = t.last_info
    assert info.audio_seconds == 4.0 and info.segments == 2
    assert info.language == "en" and info.language_probability == 0.99
    # weighted by duration: (1 x 0.9 + 3 x 0.5) / 4
    assert info.confidence == pytest.approx(0.6)
    assert info.real_time_factor >= 0


def test_silence_gives_empty_text_and_zero_confidence(tmp_path):
    t, _, _ = make(tmp_path, FakeModel(segments=[]))
    assert t.transcribe(speech(1)) == ""
    assert t.last_info.confidence == 0.0


def test_model_loads_once_and_unload_frees_it(tmp_path):
    t, _, built = make(tmp_path)
    assert not t.loaded
    t.transcribe(speech(1))
    t.transcribe(speech(1))
    assert len(built) == 1 and t.loaded
    t.unload()
    assert not t.loaded
    t.transcribe(speech(1))
    assert len(built) == 2


def test_missing_model_folder_is_reported(tmp_path):
    t = WhisperTranscriber(tmp_path / "nothing", model_factory=lambda *a: FakeModel())
    with pytest.raises(TranscriptionError, match="^asr_model_missing$"):
        t.transcribe(speech(1))


def test_model_that_fails_to_load_is_reported(tmp_path):
    def broken(*args):
        raise RuntimeError("corrupt file with SECRET path")

    t = WhisperTranscriber(model_dir(tmp_path), model_factory=broken)
    with pytest.raises(TranscriptionError) as info:
        t.load()
    assert info.value.code == "asr_model_failed_to_load" and "SECRET" not in str(info.value)


def test_failure_while_transcribing_is_a_code(tmp_path):
    t, _, _ = make(tmp_path, FakeModel(error=RuntimeError("SECRET details")))
    with pytest.raises(TranscriptionError) as info:
        t.transcribe(speech(1))
    assert info.value.code == "asr_failed" and info.value.__cause__ is None


@pytest.mark.parametrize(
    "audio, code",
    [
        (b"not a wav file", "unreadable_audio"),
        (to_wav(b"\x00\x00" * 100, sample_rate=44100), "unsupported_audio_format"),
    ],
)
def test_bad_audio_is_refused(tmp_path, audio, code):
    t, _, _ = make(tmp_path)
    with pytest.raises(TranscriptionError, match=f"^{code}$"):
        t.transcribe(audio)


def test_the_real_loader_switches_hugging_face_offline(tmp_path, monkeypatch):
    """The real factory must set the offline switches before importing the library."""
    pytest.importorskip("faster_whisper")
    import faster_whisper

    from clinassist.adapters import transcriber

    seen = {}

    class Spy:
        def __init__(self, path, **kwargs):
            seen.update(kwargs, path=path, offline=os.environ.get("HF_HUB_OFFLINE"))

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(faster_whisper, "WhisperModel", Spy)
    transcriber._real_model(str(tmp_path), "int8", 0)
    assert seen["offline"] == "1" and seen["local_files_only"] is True
    assert seen["device"] == "cpu" and seen["path"] == str(tmp_path)


def test_wav_to_samples_round_trip():
    samples = wav_to_samples(to_wav(array("h", [0, 16384, -16384, 32767]).tobytes()))
    assert [round(float(s), 4) for s in samples] == [0.0, 0.5, -0.5, 1.0]


# ----- word error rate -----
def test_identical_text_has_zero_error():
    assert word_error_rate("Patient: I have a cough.", "i have a cough").wer == 0.0


def test_each_kind_of_error_is_counted():
    r = word_error_rate("the patient has a dry cough", "the patient had dry cough today")
    assert (r.substitutions, r.deletions, r.insertions) == (1, 1, 1)
    assert r.reference_words == 6 and r.wer == pytest.approx(3 / 6, abs=1e-4)


def test_labels_comments_hyphens_and_punctuation_are_ignored():
    ref = "# SYNTHETIC\nDoctor: Any long-term illness?\nPatient: No, none."
    assert normalize(ref) == ["any", "long", "term", "illness", "no", "none"]


def test_numbers_can_be_compared_as_digits():
    ref = "Fever for three days, BP one fifty two over ninety four, twenty two years"
    hyp = "fever for 3 days bp 152 over 94 22 years"
    assert word_error_rate(ref, hyp).wer > 0.3
    assert word_error_rate(ref, hyp, numbers_as_digits=True).wer == 0.0


def test_empty_reference():
    assert word_error_rate("", "").wer == 0.0
    assert word_error_rate("", "extra").wer == 1.0


# ----- the real model, when downloaded -----
MODELS = ROOT / "models"
AUDIO = ROOT / "spikes" / "audio" / "consult_01.wav"


@pytest.mark.parametrize("name", ["base", "small"])
def test_real_model_transcribes_the_synthetic_consultation(name):
    from clinassist import model_files

    if not AUDIO.is_file() or model_files.verify(MODELS, name) != "ok":
        pytest.skip("model or audio not present on this machine")
    pytest.importorskip("faster_whisper")
    t = WhisperTranscriber(MODELS / model_files.WHISPER_MODELS[name].folder)
    text = t.transcribe(AUDIO.read_bytes())
    t.unload()
    reference = (ROOT / "spikes" / "transcripts" / "synthetic_consult_01.txt").read_text("utf-8")
    assert word_error_rate(reference, text, numbers_as_digits=True).wer < 0.15


# ----- model file check -----
def _fake_model_folder(root: Path, weights: bytes) -> None:
    folder = root / "faster-whisper-base"
    folder.mkdir(parents=True)
    for name in ("config.json", "tokenizer.json", "vocabulary.txt"):
        (folder / name).write_text("{}", encoding="utf-8")
    (folder / "model.bin").write_bytes(weights)


def test_model_check_reports_missing_wrong_size_and_wrong_checksum(tmp_path, monkeypatch):
    import hashlib

    from clinassist import model_files

    weights = b"pretend weights"
    good = model_files.ModelFile(
        "faster-whisper-base", "test", len(weights), hashlib.sha256(weights).hexdigest()
    )
    monkeypatch.setitem(model_files.WHISPER_MODELS, "base", good)
    assert model_files.verify(tmp_path, "base") == "missing_files"
    _fake_model_folder(tmp_path, weights)
    assert model_files.verify(tmp_path, "base") == "ok"
    (tmp_path / "faster-whisper-base" / "model.bin").write_bytes(b"pretend weightz")  # same size
    assert model_files.verify(tmp_path, "base") == "wrong_checksum"
    (tmp_path / "faster-whisper-base" / "model.bin").write_bytes(b"short")
    assert model_files.verify(tmp_path, "base") == "wrong_size"


@pytest.mark.parametrize("name", ["base", "small"])
def test_downloaded_models_match_their_published_checksums(name):
    from clinassist import model_files

    if not (MODELS / model_files.WHISPER_MODELS[name].folder / "model.bin").is_file():
        pytest.skip("model not present on this machine")
    assert model_files.verify(MODELS, name) == "ok"


def test_blood_pressure_said_without_hundred_becomes_one_number():
    assert normalize("one fifty two over ninety four", numbers_as_digits=True) == [
        "152",
        "over",
        "94",
    ]
    assert normalize("one twelve over seventy", numbers_as_digits=True) == ["112", "over", "70"]
    assert normalize("one fifty", numbers_as_digits=True) == ["150"]


def test_spelling_and_unit_variants_can_count_as_the_same_word():
    ref = "Haemoglobin 11 litres, 500 milligrams, alright"
    hyp = "hemoglobin 11 liters 500 mg all right"
    assert word_error_rate(ref, hyp).wer > 0.4
    assert word_error_rate(ref, hyp, standard_spelling=True).wer == 0.0


def test_term_recall_counts_each_mention():
    from clinassist.metrics import term_recall

    ref = "amlodipine in the morning, amlodipine at night, paracetamol, amlodipine"
    hyp = "amlotyping in the morning, amlodipine at night, paracetamol, amlotyping"
    assert term_recall(ref, hyp, ["amlodipine", "paracetamol"]) == (2, 4)
    assert term_recall("no drugs", "no drugs", ["amlodipine"]) == (0, 0)


def test_hundreds_are_read_as_one_number():
    assert normalize("one hundred and four", numbers_as_digits=True) == ["104"]
    assert normalize("two hundred and fifty", numbers_as_digits=True) == ["250"]
    assert normalize("one hundred and forty-four", numbers_as_digits=True) == ["144"]
    assert normalize("three hundred milligrams", numbers_as_digits=True) == ["300", "milligrams"]
