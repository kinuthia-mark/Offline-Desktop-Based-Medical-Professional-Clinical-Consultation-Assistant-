"""Key handling for the vault (ADR-003). Pure functions; no files, no logging.

Envelope design:

    passphrase    --Argon2id--> passphrase KEK --AES-GCM wrap--+
                                                               +--> master key (random, 32 bytes)
    recovery code --Argon2id--> recovery KEK   --AES-GCM wrap--+
                                                                       |
                                              HKDF-SHA256 ("db")  -----+----> database key

Changing the passphrase rewraps the master key; the data is not re-encrypted. Errors are codes.
"""

# This file holds the key maths for the vault. It turns a passphrase into a key, locks (wraps)
# the random master key with it, and makes the database key from the master key.
# It has no files or database code. vault.py calls these functions and does the storing.
from __future__ import annotations

import base64
import secrets
from dataclasses import asdict, dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_BYTES = 32  # 256-bit keys, as used by AES-256
SALT_BYTES = 16  # random value mixed into each password, so equal passwords give different keys
NONCE_BYTES = 12  # fresh random value for each encryption
RECOVERY_BYTES = 20  # 160 bits, shown as 32 base32 characters


# Raised when unwrapping fails, which almost always means the passphrase or code was wrong.
class CryptoError(RuntimeError):
    """A key could not be unwrapped or derived. The message is a stable code."""


# frozen=True means the settings cannot be changed after they are made.
@dataclass(frozen=True)
class KdfParams:
    """Argon2id settings, stored inside each keyring so they can be raised later.

    Default: t=3, 128 MiB, p=2, measured at 0.174 s median on the reference PC (ADR-001).
    Above the RFC 9106 second recommended option (t=3, 64 MiB) in memory."""

    time_cost: int = 3
    memory_cost_kib: int = 131072
    parallelism: int = 2

    # Turns the settings into a plain dict so they can be saved in keyring.json.
    def to_dict(self) -> dict:
        # asdict copies the dataclass fields into a dict.
        return asdict(self)

    # A classmethod builds a KdfParams from the saved dict, without needing an existing object.
    @classmethod
    def from_dict(cls, data: dict) -> KdfParams:
        # int() makes sure values read back from JSON are numbers. A missing key raises KeyError.
        return cls(int(data["time_cost"]), int(data["memory_cost_kib"]), int(data["parallelism"]))


# Fast settings for tests only. Never use them for a real vault.
TEST_KDF = KdfParams(time_cost=1, memory_cost_kib=8192, parallelism=1)


# KEK means key-encryption key: a key whose only job is to lock the master key.
def derive_kek(secret: str, salt: bytes, params: KdfParams) -> bytes:
    # Turn a passphrase (or the recovery code) into a key-encryption key. Argon2id is slow and
    # memory-hungry on purpose (about 0.17 s and 128 MiB here), so each guess an attacker
    # makes costs the same.
    return hash_secret_raw(
        # Argon2 works on bytes, so the text is encoded first.
        secret=secret.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_cost_kib,
        parallelism=params.parallelism,
        # Ask for a 32 byte result, the size AES-256 needs.
        hash_len=KEY_BYTES,
        # Argon2id is the variant that resists both GPU cracking and side-channel attacks.
        type=Type.ID,
    )


# The master key is random, not made from the passphrase, so changing the passphrase is cheap.
def new_master_key() -> bytes:
    # secrets uses the operating system's secure random source. The random module is not safe for
    # keys.
    return secrets.token_bytes(KEY_BYTES)


# A fresh salt for every slot, so two vaults with the same passphrase get different keys.
def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


# Wrapping means encrypting one key with another key.
def wrap(kek: bytes, master_key: bytes, label: bytes) -> bytes:
    """Encrypt the master key. `label` is bound as associated data, so a passphrase wrap
    cannot be swapped into the recovery slot."""
    # A nonce must never repeat with the same key, so a new random one is made each time.
    nonce = secrets.token_bytes(NONCE_BYTES)
    # Stored as nonce followed by the encrypted key; unwrap splits them again.
    return nonce + AESGCM(kek).encrypt(nonce, master_key, label)


# The reverse of wrap. Returns the master key, or raises CryptoError.
def unwrap(kek: bytes, blob: bytes, label: bytes) -> bytes:
    # AES-GCM refuses to decrypt if the key is wrong or a single bit was changed, so a wrong
    # passphrase is detected here, before the database is touched.
    try:
        return AESGCM(kek).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], label)
    except (InvalidTag, ValueError):
        # from None hides the original error, so nothing about the key leaks into messages.
        raise CryptoError("unwrap_failed") from None


# HKDF is a standard way to make several different keys from one master key.
def subkey(master_key: bytes, purpose: str) -> bytes:
    """A separate key per purpose (only "db" today), so one key never serves two uses."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        # No salt is needed because the master key is already random and strong.
        salt=None,
        # The purpose text changes the output, so each purpose gets a different key.
        info=b"clinassist/v1/" + purpose.encode("ascii"),
    ).derive(master_key)


# The backup way in if the passphrase is forgotten. It unlocks the same master key.
def new_recovery_code() -> str:
    """A printable code, for example 'ABCD-EFGH-...'. Shown once, at vault creation."""
    # Base32 uses only capital letters and the digits 2 to 7, so there is no 0/O or 1/l
    # confusion when the code is read off paper. Groups of four make it easier to type.
    raw = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES)).decode("ascii")
    # Cut the text into groups of 4 characters and join them with dashes.
    return "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))


# Needed so the same code always gives the same key, however the user typed it.
def normalize_recovery_code(code: str) -> str:
    """Accept the code typed with or without dashes, spaces or lower case."""
    # Keep only letters and digits, in capitals. This drops dashes and spaces.
    return "".join(ch for ch in code.upper() if ch.isalnum())


# Base64 turns bytes into plain text, so they can be stored in the JSON keyring.
def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# The reverse of b64. validate=True rejects text that is not real base64, so damage is caught.
def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
