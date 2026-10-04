"""Self-test of an installed copy (release, ADR-012): does every heavy part actually work here?

    ClinAssist-check.exe --self-test

Packaging can silently leave out a library or a data file, and the light start-up checks would
not notice. This uses each part for real: the window library, the encrypted database, the
password hashing, the dictionary, the microphone library, and the speech model with its
silence detector on a second of synthetic silence. Nothing is saved; nothing leaves the PC.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def _window() -> str:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication([])
    label = QLabel("self-test")
    label.show()
    app.processEvents()
    label.close()
    return "window library works"


def _database() -> str:
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        vault, _ = Vault.create(Path(tmp) / "v", "self test passphrase 123", kdf=TEST_KDF)
        with vault.connect() as conn:
            version = conn.execute("PRAGMA cipher_version").fetchone()[0]
        vault.lock()
    return f"encrypted database works (SQLCipher {version})"


def _passwords() -> str:
    from argon2 import PasswordHasher

    hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    assert hasher.verify(hasher.hash("self test"), "self test")
    return "password hashing works"


def _dictionary() -> str:
    from clinassist.adapters.groundcheck import merged_words

    assert merged_words("healthand", set()) == ["healthand"]
    return "dictionary for the merged-word check works"


def _microphone_library() -> str:
    from clinassist.adapters.recorder import list_input_devices

    return f"microphone library works ({len(list_input_devices())} microphone(s) found)"


def _speech() -> str:
    from clinassist.adapters.recorder import to_wav
    from clinassist.adapters.transcriber import WhisperTranscriber
    from clinassist.config import AppConfig

    folder = AppConfig().whisper_dir()
    if not (folder / "model.bin").is_file():
        return "SKIPPED speech model: not installed next to the program"
    t = WhisperTranscriber(folder)
    t.transcribe(to_wav(bytes(32000)))  # one second of silence: exercises the silence detector
    t.unload()
    return "speech model and silence detector work"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("window", _window),
    ("database", _database),
    ("passwords", _passwords),
    ("dictionary", _dictionary),
    ("microphone", _microphone_library),
    ("speech", _speech),
]


def run() -> int:
    failures = 0
    for name, check in CHECKS:
        try:
            print(f"OK    {check()}")
        except Exception as exc:  # report every failing part, not only the first
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}")
    print("Self-test passed." if not failures else f"Self-test failed: {failures} part(s).")
    return 1 if failures else 0
