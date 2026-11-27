"""Application settings, with the reason for each default.

Settings live in a small JSON file (`settings.json` in the data folder). Anything not in the file
keeps its default. Unknown names and wrong types are refused with a code, so a typing mistake in
the file cannot silently switch a safety setting off.
"""

# This file holds the settings (which models, where the data lives, memory limits).
# Everything else reads them from one AppConfig object, so a default is changed in
# one place only. It is read at start-up from settings.json.
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from clinassist.adapters.ollama_client import DEFAULT_HOST


def app_folder() -> Path:
    """Where the program's own files are: next to ClinAssist.exe once installed, or the project
    folder when running from source. Models are looked up here, never relative to wherever the
    program happened to be started from."""
    # "frozen" is set when the app is packaged into an .exe; then files sit beside the .exe.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # From source, parents[2] is the project root (two folders above this file).
    return Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    # %LOCALAPPDATA% is per Windows user and is not synced to OneDrive, unlike Documents.
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "ClinAssist"


# A settings problem. Only a short code is kept, so the screen can show a clear message.
class ConfigError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# frozen=True: settings cannot be changed after loading. A change makes a new object.
@dataclass(frozen=True)
class AppConfig:
    # Where the encrypted vault lives. Created on first run.
    data_dir: str = str(default_data_dir())
    # Where the Whisper models are, next to the program (shipped by the installer).
    models_dir: str = str(app_folder() / "models")
    # small: right on 9 of 11 medicine names, against 6 of 11 for base (ADR-007).
    whisper_model: str = "small"
    # MedGemma 4B, Q4_K_M, run by Ollama on this PC only (ADR-002).
    llm_model: str = "medgemma:4b"
    # The ranked list of possible diagnoses with management (the proposal's core output, AMD-32),
    # shown apart from the note and labelled AI-generated. Adds about 20 s per note (ADR-013).
    ai_suggestions: bool = True
    ollama_host: str = DEFAULT_HOST
    # None: the Windows default microphone.
    microphone: int | None = None
    # Free memory below which the startup check warns. Cold model loads took 7.7 to 10.8 s with
    # 2 GB or more free, 10.6 to 14.5 s with 1.0 to 1.4 GB, and 20.1 s with 0.67 GB (ADR-002).
    warn_free_ram_gb: float = 2.0
    low_free_ram_gb: float = 1.0

    # Folder of the chosen speech model inside models_dir.
    def whisper_dir(self) -> Path:
        from clinassist.model_files import WHISPER_MODELS

        return Path(self.models_dir) / WHISPER_MODELS[self.whisper_model].folder

    # classmethod: called as AppConfig.load(path) and returns a new AppConfig.
    @classmethod
    def load(cls, path: Path | str) -> AppConfig:
        """Defaults, overridden by whatever the JSON file sets. A missing file means defaults."""
        path = Path(path)
        # No settings file yet (first run) means all defaults.
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # "from None" hides the original error, which could include file text.
            raise ConfigError("settings_unreadable") from None
        if not isinstance(data, dict):
            raise ConfigError("settings_unreadable")
        # Map of setting name to field, used to spot names that do not exist.
        known = {f.name: f for f in fields(cls)}
        for name, value in data.items():
            if name not in known:
                raise ConfigError(f"unknown_setting:{name}")
            default = getattr(cls(), name)
            # The value must have the same kind as the default (a number where a number goes).
            ok = (
                # microphone may be None (use the default) or a device number.
                (name == "microphone" and (value is None or type(value) is int))
                # "type(value) is bool", not isinstance, because True is also an int in Python.
                or (isinstance(default, bool) and type(value) is bool)
                # A whole number is accepted where a decimal is expected.
                or (type(default) is float and type(value) in (int, float))
                or (type(default) is str and type(value) is str)
            )
            if not ok:
                raise ConfigError(f"wrong_type:{name}")
        # replace() copies the defaults with the file's values applied on top.
        config = replace(cls(), **data)
        from clinassist.model_files import WHISPER_MODELS

        if config.whisper_model not in WHISPER_MODELS:
            raise ConfigError("unknown_whisper_model")
        return config

    # Writes the settings back as readable JSON (indent=2), so they can be edited by hand.
    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
