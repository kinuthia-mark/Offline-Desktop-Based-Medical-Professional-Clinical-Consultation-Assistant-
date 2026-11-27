"""Startup checks (NFR-07, AMD-21): what works on this PC right now, before a consultation starts.

Each check returns ok, warn or fail with a short code. "fail" is kept for problems that make the
app unusable for its main job; anything that only removes one feature is a warning, because the
clinician can still record, review and write the note by hand.

    python -m clinassist.startup             # prints the checks for this PC
"""

# This file runs the checks shown when the app starts: Python, data folder, speech model,
# language model, memory, microphone and network. The window decides from the results
# whether the app can start. The same checks can be run from the command line.
from __future__ import annotations

import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clinassist.config import AppConfig


# The result of one check: its name, a status, a short code and how long it took.
@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | warn | fail
    code: str  # short code for the interface; never contains patient data
    seconds: float = 0.0


# Runs one check, times it, and turns a crash into a "fail" result instead of an error.
def _timed(name: str, fn: Callable[[], tuple[str, str]]) -> Check:
    start = time.perf_counter()
    try:
        status, code = fn()
    except Exception:  # a check must never stop the others from running
        status, code = "fail", "check_crashed"
    return Check(name, status, code, round(time.perf_counter() - start, 3))


# The app needs Python 3.11 or newer.
def check_python() -> tuple[str, str]:
    return ("ok", "python_ok") if sys.version_info >= (3, 11) else ("fail", "python_too_old")


# Is the speech model on disk and complete? verify() returns "ok" or the reason it is not.
def check_whisper(config: AppConfig) -> tuple[str, str]:
    from clinassist.model_files import verify

    result = verify(Path(config.models_dir), config.whisper_model)
    # Without speech-to-text the clinician can still type the transcript, but the main
    # workflow (UC-01, UC-02) is gone, so this is a failure.
    return ("ok", "whisper_ok") if result == "ok" else ("fail", f"whisper_{result}")


# Asks Ollama (on this PC) which models it has.
def check_llm(config: AppConfig, list_models=None) -> tuple[str, str]:
    """Is Ollama running on this PC, with the model installed? A warning only: without it the
    clinician writes the note by hand (FR-13)."""
    from clinassist.adapters.ollama_client import OllamaClient
    from clinassist.domain import GenerationFailed

    try:
        # list_models can be replaced in tests; otherwise a real Ollama client is used.
        installed = (list_models or OllamaClient(config.ollama_host).list_models)()
    # Ollama is not running or cannot be reached.
    except GenerationFailed:
        return "warn", "ollama_not_running"
    return ("ok", "llm_ok") if config.llm_model in installed else ("warn", "llm_model_missing")


# Looks at free RAM, because the models are slow to load when memory is short.
def check_memory(config: AppConfig, available_gb: Callable[[], float] | None = None):
    """Thresholds come from measured cold-load times (ADR-002); see AppConfig."""
    if available_gb is None:
        import psutil

        # Free memory in GB: psutil gives bytes, and 2**30 bytes make one GB.
        def available_gb() -> float:
            return psutil.virtual_memory().available / 2**30

    free = available_gb()
    if free < config.low_free_ram_gb:
        return "warn", "free_ram_very_low"  # notes will be slow; closing other programs helps
    if free < config.warn_free_ram_gb:
        return "warn", "free_ram_low"
    return "ok", "free_ram_ok"


# Is there an input device, and does the one chosen in settings still exist?
def check_microphone(config: AppConfig, list_devices=None) -> tuple[str, str]:
    try:
        if list_devices is None:
            # Imported only when no fake was passed in.
            from clinassist.adapters.recorder import list_input_devices as list_devices
        devices = list_devices()
    except Exception:
        return "warn", "microphone_check_failed"
    if not devices:
        return "warn", "no_microphone"
    # Only a chosen device number needs checking; None means the default.
    if config.microphone is not None and config.microphone not in {d.index for d in devices}:
        return "warn", "chosen_microphone_missing"
    return "ok", "microphone_ok"


# Judges the network state with the passive checks in airgap.py.
def check_network(snapshot=None) -> tuple[str, str]:
    """The air-gap checks (NFR-01, NFR-02, ADR-010). Passive: nothing is sent anywhere."""
    from clinassist.airgap import assess, take_snapshot

    # A test can pass a made-up snapshot; otherwise the live system is read.
    result = assess(snapshot or take_snapshot())
    return result.status, result.code


# Proves the vault folder can be written by creating and deleting a temporary file.
def check_data_folder(config: AppConfig) -> tuple[str, str]:
    """The vault folder must exist (or be creatable) and accept a file."""
    folder = Path(config.data_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        # delete=True removes the file when the block ends, so nothing is left behind.
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".write-test-", delete=True):
            pass
    except OSError:
        return "fail", "data_folder_not_writable"
    return "ok", "data_folder_ok"


# Runs every check. lambda delays each call so _timed can time it and catch a crash.
def run_checks(config: AppConfig, **overrides) -> list[Check]:
    """All checks, in the order the interface shows them. `overrides` replaces a check's
    outside dependency in tests (list_models, available_gb, list_devices, network_snapshot)."""
    return [
        _timed("python", check_python),
        _timed("data_folder", lambda: check_data_folder(config)),
        _timed("speech_model", lambda: check_whisper(config)),
        _timed("language_model", lambda: check_llm(config, overrides.get("list_models"))),
        _timed("memory", lambda: check_memory(config, overrides.get("available_gb"))),
        _timed("microphone", lambda: check_microphone(config, overrides.get("list_devices"))),
        _timed("network", lambda: check_network(overrides.get("network_snapshot"))),
    ]


# Only "fail" blocks start-up; warnings do not.
def can_start(checks: list[Check]) -> bool:
    return not any(c.status == "fail" for c in checks)


# Command-line entry point: prints each check, then a ready or not-ready line.
def main() -> int:
    from clinassist.airgap import install_network_guard

    # The command-line tool also switches on the offline guard, like the real app.
    install_network_guard()
    config = AppConfig.load(Path(AppConfig().data_dir) / "settings.json")
    checks = run_checks(config)
    for c in checks:
        print(f"{c.status.upper():<5} {c.name:<15} {c.code:<28} {c.seconds:.2f} s")
    print("\nReady." if can_start(checks) else "\nNot ready: see the failures above.")
    return 0 if can_start(checks) else 1


if __name__ == "__main__":
    # Runs main() only when started directly, not when imported. The number is the exit code.
    raise SystemExit(main())
