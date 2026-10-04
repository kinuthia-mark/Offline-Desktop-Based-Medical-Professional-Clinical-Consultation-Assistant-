"""Known model files and their SHA-256 fingerprints (ADR-007).

The models are not in the repository; they are downloaded once (or shipped with the installer)
into the models/ folder. Before trusting a folder, `verify` checks the large weights file
against the fingerprint published by Hugging Face, so a damaged download or a swapped file is
caught. Hashing a 480 MB file takes a second or two, so this runs at install and at startup,
not on every transcription.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelFile:
    folder: str  # inside models/
    source: str  # where it was downloaded from
    weights_bytes: int
    weights_sha256: str


WHISPER_MODELS = {
    "base": ModelFile(
        "faster-whisper-base",
        "https://huggingface.co/Systran/faster-whisper-base",
        145_217_532,
        "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
    ),
    "small": ModelFile(
        "faster-whisper-small",
        "https://huggingface.co/Systran/faster-whisper-small",
        483_546_902,
        "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
    ),
}
_REQUIRED = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def verify(models_root: Path, name: str) -> str:
    """Return "ok", or a code saying what is wrong: missing_files, wrong_size, wrong_checksum."""
    spec = WHISPER_MODELS[name]
    folder = Path(models_root) / spec.folder
    if not all((folder / f).is_file() for f in _REQUIRED):
        return "missing_files"
    weights = folder / "model.bin"
    if weights.stat().st_size != spec.weights_bytes:  # cheap check first
        return "wrong_size"
    if sha256_of(weights) != spec.weights_sha256:
        return "wrong_checksum"
    return "ok"
