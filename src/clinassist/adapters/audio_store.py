"""Optional encrypted audio retention (ADR-003). OFF by default: the least data held is no audio.

When switched on, each recording is one file, AES-256-GCM encrypted with the vault's audio key
and bound to its session id as associated data, so a file renamed to another session's name fails
to decrypt. Files live outside the database because a consultation's audio is many megabytes.

File layout: MAGIC (6 bytes) | nonce (12 bytes) | ciphertext and tag.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"CAUD1\n"
NONCE_BYTES = 12
SUFFIX = ".caud"
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class AudioStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EncryptedAudioStore:
    def __init__(self, directory: Path | str, key: bytes, enabled: bool = False) -> None:
        self._dir = Path(directory)
        self._aes = AESGCM(key)
        self.enabled = enabled

    def save(self, session_id: str, audio: bytes) -> Path | None:
        """Encrypt and keep the recording, or keep nothing when retention is off."""
        if not self.enabled:
            return None
        path = self._path(session_id)
        if path.exists():
            raise AudioStoreError("audio_exists")
        nonce = secrets.token_bytes(NONCE_BYTES)
        sealed = MAGIC + nonce + self._aes.encrypt(nonce, audio, session_id.encode("ascii"))
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            fh.write(sealed)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return path

    def load(self, session_id: str) -> bytes:
        path = self._path(session_id)
        if not path.exists():
            raise AudioStoreError("audio_not_found")
        blob = path.read_bytes()
        if not blob.startswith(MAGIC):
            raise AudioStoreError("audio_corrupt")
        body = blob[len(MAGIC) :]
        try:
            return self._aes.decrypt(
                body[:NONCE_BYTES], body[NONCE_BYTES:], session_id.encode("ascii")
            )
        except (InvalidTag, ValueError):
            raise AudioStoreError("audio_corrupt") from None

    def delete(self, session_id: str) -> bool:
        """Remove the file. Returns False if there was none. An ordinary file delete: the
        ciphertext may remain on disk until overwritten, but without the key it is unreadable."""
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, session_id: str) -> Path:
        if not _SAFE_ID.fullmatch(session_id):
            raise AudioStoreError("invalid_session_id")  # also blocks path traversal
        return self._dir / f"{session_id}{SUFFIX}"
