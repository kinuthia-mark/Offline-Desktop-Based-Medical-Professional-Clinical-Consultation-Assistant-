"""Key handling for the vault (ADR-003). Pure functions; no files, no logging.

Envelope design:

    passphrase    --Argon2id--> passphrase KEK --AES-GCM wrap--+
                                                               +--> master key (random, 32 bytes)
    recovery code --Argon2id--> recovery KEK   --AES-GCM wrap--+
                                                                       |
                                              HKDF-SHA256 ("db")  -----+----> database key
                                              HKDF-SHA256 ("audio") ---+----> audio key

Changing the passphrase rewraps the master key; the data is not re-encrypted. Errors are codes.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import asdict, dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_BYTES = 32
SALT_BYTES = 16
NONCE_BYTES = 12
RECOVERY_BYTES = 20  # 160 bits, shown as 32 base32 characters


class CryptoError(RuntimeError):
    """A key could not be unwrapped or derived. The message is a stable code."""


@dataclass(frozen=True)
class KdfParams:
    """Argon2id settings, stored inside each keyring so they can be raised later.

    Default: t=3, 128 MiB, p=2, measured at 0.174 s median on the reference PC (ADR-001).
    Above the RFC 9106 second recommended option (t=3, 64 MiB) in memory."""

    time_cost: int = 3
    memory_cost_kib: int = 131072
    parallelism: int = 2

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> KdfParams:
        return cls(int(data["time_cost"]), int(data["memory_cost_kib"]), int(data["parallelism"]))


# Fast settings for tests only. Never use them for a real vault.
TEST_KDF = KdfParams(time_cost=1, memory_cost_kib=8192, parallelism=1)


def derive_kek(secret: str, salt: bytes, params: KdfParams) -> bytes:
    return hash_secret_raw(
        secret=secret.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost_kib,
        parallelism=params.parallelism,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def new_master_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def wrap(kek: bytes, master_key: bytes, label: bytes) -> bytes:
    """Encrypt the master key. `label` is bound as associated data, so a passphrase wrap
    cannot be swapped into the recovery slot."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + AESGCM(kek).encrypt(nonce, master_key, label)


def unwrap(kek: bytes, blob: bytes, label: bytes) -> bytes:
    try:
        return AESGCM(kek).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], label)
    except (InvalidTag, ValueError):
        raise CryptoError("unwrap_failed") from None


def subkey(master_key: bytes, purpose: str) -> bytes:
    """A separate key per purpose ("db", "audio"), so one key never serves two uses."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=None,
        info=b"clinassist/v1/" + purpose.encode("ascii"),
    ).derive(master_key)


def new_recovery_code() -> str:
    """A printable code, for example 'ABCD-EFGH-...'. Shown once, at vault creation."""
    raw = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES)).decode("ascii")
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def normalize_recovery_code(code: str) -> str:
    """Accept the code typed with or without dashes, spaces or lower case."""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
