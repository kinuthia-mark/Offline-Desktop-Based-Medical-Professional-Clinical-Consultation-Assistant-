"""Composition root, memory plan, settings and startup checks (NFR-04, NFR-07, AMD-07, AMD-21)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")

from fake_ollama import FakeOllama, Script, stream_text  # noqa: E402
from model_outputs import GOOD_SHORT  # noqa: E402

from clinassist.app import SequentialModels, WavFileRecorder, build  # noqa: E402
from clinassist.config import AppConfig, ConfigError  # noqa: E402
from clinassist.controller import State  # noqa: E402
from clinassist.domain import HistoryChecklist, SoapNote  # noqa: E402
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault  # noqa: E402
from clinassist.startup import (  # noqa: E402
    can_start,
    check_data_folder,
    check_llm,
    check_memory,
    check_microphone,
    check_whisper,
    run_checks,
)


# ----- fakes -----
class FakeTranscriber:
    def __init__(self, log: list[str], fail: bool = False) -> None:
        self.log, self.fail, self.loaded = log, fail, False

    def load(self) -> float:
        self.loaded = True
        self.log.append("whisper.load")
        return 0.0

    def unload(self) -> None:
        self.loaded = False
        self.log.append("whisper.unload")

    def transcribe(self, audio: bytes) -> str:
        self.log.append(f"whisper.transcribe(loaded={self.loaded})")
        if self.fail:
            raise RuntimeError("asr_failed")
        return "Doctor: What brings you in? Patient: A cough for three days."


class FakeGenerator:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def unload(self) -> None:
        self.log.append("llm.unload")


class FakeRecorder:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def start(self) -> None:
        self.log.append("mic.start")

    def stop(self) -> bytes:
        self.log.append("mic.stop")
        return b"wav"


# ----- the memory plan -----
def test_models_are_never_loaded_together():
    log: list[str] = []
    asr, llm = FakeTranscriber(log), FakeGenerator(log)
    plan = SequentialModels(asr, llm)
    plan.before_recording()
    plan.transcribe(b"wav")
    # the language model is freed before Whisper loads, and Whisper is freed after use
    assert log == [
        "llm.unload",
        "whisper.load",
        "whisper.transcribe(loaded=True)",
        "whisper.unload",
    ]
    assert not asr.loaded


def test_whisper_is_freed_even_when_transcription_fails():
    log: list[str] = []
    plan = SequentialModels(FakeTranscriber(log, fail=True), FakeGenerator(log))
    plan.before_recording()
    with pytest.raises(RuntimeError):
        plan.transcribe(b"wav")
    assert log[-1] == "whisper.unload"


def test_a_failed_preload_is_reported_when_transcribing():
    log: list[str] = []

    class Missing(FakeTranscriber):
        def load(self) -> float:
            raise RuntimeError("asr_model_missing")

        def transcribe(self, audio: bytes) -> str:
            self.load()  # the real transcriber loads on use and raises the real error
            return ""

    plan = SequentialModels(Missing(log), FakeGenerator(log))
    plan.before_recording()
    with pytest.raises(RuntimeError, match="asr_model_missing"):
        plan.transcribe(b"wav")
    assert "whisper_preload_failed" in plan.log


# ----- the whole app with fake models -----
@pytest.fixture
def vault(tmp_path):
    v, _ = Vault.create(tmp_path / "vault", "a long synthetic passphrase 42", kdf=TEST_KDF)
    return v


@pytest.fixture
def fake_ollama():
    fake = FakeOllama(lambda r: Script(pieces=stream_text(GOOD_SHORT)))
    yield fake
    fake.stop()


def test_a_whole_consultation_runs_through_the_real_parts(tmp_path, vault, fake_ollama):
    """Real guard, generator (against a fake Ollama), store, auditor and memory plan; only the
    microphone and Whisper are fakes."""
    log: list[str] = []
    config = AppConfig(data_dir=str(tmp_path), ollama_host=fake_ollama.url)
    services = build(config, vault, recorder=FakeRecorder(log), transcriber=FakeTranscriber(log))
    c = services.new_controller()
    c.start_recording()
    text = c.stop_recording()
    c.approve_transcript(text, "dr-a")
    draft = c.generate_draft()
    record = c.finalize(SoapNote(draft.subjective, draft.objective, "Viral URTI", draft.plan),
                        "dr-a", HistoryChecklist(True, True, True))  # fmt: skip
    assert c.state is State.FINALIZED
    assert services.store.load(record.session_id) == record
    assert services.auditor.verify().ok
    assert [e[2] for e in reversed(services.auditor.events())] == [
        "recording_started", "transcribed", "transcript_approved", "draft_generated", "finalized",
    ]  # fmt: skip
    # memory plan: Ollama was told to free MedGemma, Whisper was loaded when used, then freed
    assert fake_ollama.generate_requests[0] == {"model": "medgemma:4b", "keep_alive": 0}
    assert "whisper.transcribe(loaded=True)" in log
    assert log.index("whisper.unload") > log.index("whisper.transcribe(loaded=True)")
    assert not services.plan._transcriber.loaded


def test_the_generator_is_told_to_free_memory_before_recording(tmp_path, vault, fake_ollama):
    config = AppConfig(data_dir=str(tmp_path), ollama_host=fake_ollama.url)
    services = build(config, vault, recorder=FakeRecorder([]), transcriber=FakeTranscriber([]))
    services.new_controller().start_recording()
    assert fake_ollama.generate_requests == [{"model": "medgemma:4b", "keep_alive": 0}]


def test_wav_file_recorder_returns_the_file(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"RIFF....")
    rec = WavFileRecorder(tmp_path / "a.wav")
    rec.start()
    assert rec.stop() == b"RIFF...."


# ----- settings -----
def test_missing_settings_file_means_defaults(tmp_path):
    config = AppConfig.load(tmp_path / "settings.json")
    assert config == AppConfig()
    assert config.whisper_model == "small" and config.keep_audio is False


def test_settings_file_overrides_and_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"whisper_model": "base", "microphone": 1, "warn_free_ram_gb": 3}))
    config = AppConfig.load(path)
    assert (config.whisper_model, config.microphone, config.warn_free_ram_gb) == ("base", 1, 3)
    config.save(path)
    assert AppConfig.load(path) == config


@pytest.mark.parametrize(
    "content, code",
    [
        ("not json", "settings_unreadable"),
        ("[1, 2]", "settings_unreadable"),
        ('{"keep_audios": true}', "unknown_setting:keep_audios"),  # a typo must not be ignored
        ('{"keep_audio": "no"}', "wrong_type:keep_audio"),  # "no" is not False
        ('{"keep_audio": 0}', "wrong_type:keep_audio"),
        ('{"microphone": "1"}', "wrong_type:microphone"),
        ('{"whisper_model": "large"}', "unknown_whisper_model"),
    ],
)
def test_bad_settings_are_refused_with_a_code(tmp_path, content, code):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        AppConfig.load(path)
    assert info.value.code == code


# ----- startup checks -----
def test_llm_check(fake_ollama):
    config = AppConfig(ollama_host=fake_ollama.url)
    assert check_llm(config) == ("ok", "llm_ok")
    fake_ollama.installed = ["llama3:8b"]
    assert check_llm(config) == ("warn", "llm_model_missing")


def test_llm_check_when_ollama_is_not_running():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert check_llm(AppConfig(ollama_host=f"http://127.0.0.1:{port}")) == (
        "warn",
        "ollama_not_running",
    )


@pytest.mark.parametrize(
    "free, expected",
    [
        (3.5, ("ok", "free_ram_ok")),
        (1.5, ("warn", "free_ram_low")),
        (0.7, ("warn", "free_ram_very_low")),
    ],
)
def test_memory_check_thresholds(free, expected):
    assert check_memory(AppConfig(), lambda: free) == expected


@dataclass
class Dev:
    index: int


def test_microphone_check():
    config = AppConfig()
    assert check_microphone(config, lambda: [Dev(0), Dev(1)]) == ("ok", "microphone_ok")
    assert check_microphone(config, lambda: []) == ("warn", "no_microphone")
    assert check_microphone(AppConfig(microphone=7), lambda: [Dev(0)]) == (
        "warn",
        "chosen_microphone_missing",
    )


def test_whisper_check_fails_without_the_model(tmp_path):
    assert check_whisper(AppConfig(models_dir=str(tmp_path))) == ("fail", "whisper_missing_files")


def test_data_folder_check(tmp_path):
    assert check_data_folder(AppConfig(data_dir=str(tmp_path / "new"))) == ("ok", "data_folder_ok")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert check_data_folder(AppConfig(data_dir=str(blocker))) == (
        "fail",
        "data_folder_not_writable",
    )


def test_warnings_allow_start_but_failures_do_not(tmp_path):
    config = AppConfig(data_dir=str(tmp_path), models_dir=str(tmp_path / "none"))
    checks = run_checks(
        config, list_models=lambda: [], available_gb=lambda: 0.5, list_devices=lambda: [Dev(0)]
    )
    by_name = {c.name: (c.status, c.code) for c in checks}
    assert by_name["speech_model"] == ("fail", "whisper_missing_files")
    assert by_name["language_model"] == ("warn", "llm_model_missing")
    assert by_name["memory"] == ("warn", "free_ram_very_low")
    assert not can_start(checks)


def test_a_crashing_check_does_not_stop_the_others(tmp_path):
    def boom():
        raise RuntimeError("unexpected")

    checks = run_checks(AppConfig(data_dir=str(tmp_path)), available_gb=boom)
    memory = next(c for c in checks if c.name == "memory")
    assert (memory.status, memory.code) == ("fail", "check_crashed")
    assert len(checks) == 7  # including the network check (ADR-010)
