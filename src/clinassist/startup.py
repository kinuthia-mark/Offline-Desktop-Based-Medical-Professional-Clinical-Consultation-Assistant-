"""Startup checks (NFR-07, AMD-21): what works on this PC right now, before a consultation starts.

Each check returns ok, warn or fail with a short code. "fail" is kept for problems that make the
app unusable for its main job; anything that only removes one feature is a warning, because the
clinician can still record, review and write the note by hand.

    python -m clinassist.startup             # prints the checks for this PC
"""

from __future__ import annotations

import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clinassist.config import AppConfig


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | warn | fail
    code: str  # short code for the interface; never contains patient data
    seconds: float = 0.0


def _timed(name: str, fn: Callable[[], tuple[str, str]]) -> Check:
    start = time.perf_counter()
    try:
        status, code = fn()
    except Exception:  # a check must never stop the others from running
        status, code = "fail", "check_crashed"
    return Check(name, status, code, round(time.perf_counter() - start, 3))


def check_python() -> tuple[str, str]:
    return ("ok", "python_ok") if sys.version_info >= (3, 11) else ("fail", "python_too_old")


def check_whisper(config: AppConfig) -> tuple[str, str]:
    from clinassist.model_files import verify

    result = verify(Path(config.models_dir), config.whisper_model)
    # Without speech-to-text the clinician can still type the transcript, but the main
    # workflow (UC-01, UC-02) is gone, so this is a failure.
    return ("ok", "whisper_ok") if result == "ok" else ("fail", f"whisper_{result}")


def check_llm(config: AppConfig, list_models=None) -> tuple[str, str]:
    """Is Ollama running on this PC, with the model installed? A warning only: without it the
    clinician writes the note by hand (FR-13)."""
    from clinassist.adapters.ollama_client import OllamaClient
    from clinassist.domain import GenerationFailed

    try:
        installed = (list_models or OllamaClient(config.ollama_host).list_models)()
    except GenerationFailed:
        return "warn", "ollama_not_running"
    return ("ok", "llm_ok") if config.llm_model in installed else ("warn", "llm_model_missing")


def check_memory(config: AppConfig, available_gb: Callable[[], float] | None = None):
    """Thresholds come from measured cold-load times (ADR-002); see AppConfig."""
    if available_gb is None:
        import psutil

        def available_gb() -> float:
            return psutil.virtual_memory().available / 2**30

    free = available_gb()
    if free < config.low_free_ram_gb:
        return "warn", "free_ram_very_low"  # notes will be slow; closing other programs helps
    if free < config.warn_free_ram_gb:
        return "warn", "free_ram_low"
    return "ok", "free_ram_ok"


def check_microphone(config: AppConfig, list_devices=None) -> tuple[str, str]:
    try:
        if list_devices is None:
            from clinassist.adapters.recorder import list_input_devices as list_devices
        devices = list_devices()
    except Exception:
        return "warn", "microphone_check_failed"
    if not devices:
        return "warn", "no_microphone"
    if config.microphone is not None and config.microphone not in {d.index for d in devices}:
        return "warn", "chosen_microphone_missing"
    return "ok", "microphone_ok"


def check_data_folder(config: AppConfig) -> tuple[str, str]:
    """The vault folder must exist (or be creatable) and accept a file."""
    folder = Path(config.data_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".write-test-", delete=True):
            pass
    except OSError:
        return "fail", "data_folder_not_writable"
    return "ok", "data_folder_ok"


def run_checks(config: AppConfig, **overrides) -> list[Check]:
    """All checks, in the order the interface shows them. `overrides` replaces a check's
    outside dependency in tests (list_models, available_gb, list_devices)."""
    return [
        _timed("python", check_python),
        _timed("data_folder", lambda: check_data_folder(config)),
        _timed("speech_model", lambda: check_whisper(config)),
        _timed("language_model", lambda: check_llm(config, overrides.get("list_models"))),
        _timed("memory", lambda: check_memory(config, overrides.get("available_gb"))),
        _timed("microphone", lambda: check_microphone(config, overrides.get("list_devices"))),
    ]


def can_start(checks: list[Check]) -> bool:
    return not any(c.status == "fail" for c in checks)


def main() -> int:
    config = AppConfig.load(Path(AppConfig().data_dir) / "settings.json")
    checks = run_checks(config)
    for c in checks:
        print(f"{c.status.upper():<5} {c.name:<15} {c.code:<28} {c.seconds:.2f} s")
    print("\nReady." if can_start(checks) else "\nNot ready: see the failures above.")
    return 0 if can_start(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
