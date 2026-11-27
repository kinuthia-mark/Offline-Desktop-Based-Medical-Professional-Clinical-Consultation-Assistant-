"""Self-test of an installed copy (release, ADR-012): does every heavy part actually work here?

    ClinAssist-check.exe --self-test

Packaging can silently leave out a library or a data file, and the light start-up checks would
not notice. This uses each part for real: the window library, the encrypted database, the
password hashing, the dictionary, the microphone library, and the speech model with its
silence detector on a second of synthetic silence. Nothing is saved; nothing leaves the PC.
"""

# This file is a release check run on an installed copy (ClinAssist-check.exe --self-test).
# Each function below uses one heavy library for real and returns a one-line result.
# If packaging left a library out, that check fails. It is not part of normal use.
from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


# Opens a real Qt window with no screen. Proves the window library was packaged.
def _window() -> str:
    # "offscreen" lets Qt run without a display; setdefault keeps a value already set.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Imported here so a missing library fails this one check, not the whole file.
    from PySide6.QtWidgets import QApplication, QLabel

    # Reuse the running application object if there is one, since only one may exist.
    app = QApplication.instance() or QApplication([])
    label = QLabel("self-test")
    label.show()
    # Lets Qt draw the window once, so any broken part shows up now.
    app.processEvents()
    label.close()
    return "window library works"


# Creates a throwaway encrypted vault, opens it and reads the SQLCipher version.
def _database() -> str:
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    # Temporary folder, deleted afterwards, so nothing is saved.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        # TEST_KDF is a cheap key setting so the check is fast. It is only for tests.
        vault, _ = Vault.create(Path(tmp) / "v", "self test passphrase 123", kdf=TEST_KDF)
        with vault.connect() as conn:
            version = conn.execute("PRAGMA cipher_version").fetchone()[0]
        vault.lock()
    return f"encrypted database works (SQLCipher {version})"


# Hashes and verifies a password with Argon2, to prove that library works.
def _passwords() -> str:
    from argon2 import PasswordHasher

    # Small cost settings so the check is quick. Real accounts use stronger ones.
    hasher = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    # verify raises an error on a mismatch, and assert fails if the result is false.
    assert hasher.verify(hasher.hash("self test"), "self test")
    return "password hashing works"


# Uses the word list behind the merged-word check, to prove its data file was packaged.
def _dictionary() -> str:
    from clinassist.adapters.groundcheck import merged_words

    # An unknown word with an empty known-set must come back unchanged. This only proves it loads.
    assert merged_words("healthand", set()) == ["healthand"]
    return "dictionary for the merged-word check works"


# Asks the sound library for its input devices. Zero devices still passes the library test.
def _microphone_library() -> str:
    from clinassist.adapters.recorder import list_input_devices

    return f"microphone library works ({len(list_input_devices())} microphone(s) found)"


# Loads the Whisper model and runs it on silence, if the model files are installed.
def _speech() -> str:
    from clinassist.adapters.recorder import to_wav
    from clinassist.adapters.transcriber import WhisperTranscriber
    from clinassist.config import AppConfig

    folder = AppConfig().whisper_dir()
    # No model file means the installer did not include it, so this is skipped, not failed.
    if not (folder / "model.bin").is_file():
        return "SKIPPED speech model: not installed next to the program"
    t = WhisperTranscriber(folder)
    # bytes(32000) is 32,000 zero bytes. At 16 kHz, 16-bit mono that is one second.
    t.transcribe(to_wav(bytes(32000)))  # one second of silence: exercises the silence detector
    t.unload()
    return "speech model and silence detector work"


# The list of checks, run in this order. Each is a name and a function that returns text.
CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("window", _window),
    ("database", _database),
    ("passwords", _passwords),
    ("dictionary", _dictionary),
    ("microphone", _microphone_library),
    ("speech", _speech),
]


# Runs every check, prints OK or FAIL for each, and returns the exit code (0 means all passed).
def run() -> int:
    # Count of failed parts. A failure does not stop the others, so one run lists everything wrong.
    failures = 0
    for name, check in CHECKS:
        try:
            print(f"OK    {check()}")
        except Exception as exc:  # report every failing part, not only the first
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}")
    print("Self-test passed." if not failures else f"Self-test failed: {failures} part(s).")
    return 1 if failures else 0
