"""The vault: one folder holding a keyring and a SQLCipher database (FR-07, NFR-05, ADR-003).

    <vault dir>/keyring.json   salts, Argon2id settings and the two wrapped copies of the master
                               key. Not secret on its own: without the passphrase or the recovery
                               code it does not reveal the key.
    <vault dir>/vault.db       SQLCipher database, keyed with a sub-key of the master key.

Errors are VaultError with a stable code. SQLCipher's own "file is not a database" never reaches
the interface; a wrong passphrase is reported as `incorrect_passphrase`.

Limitation: while unlocked, keys and decrypted rows live in process memory. Python cannot reliably
wipe them, and SQLCipher does not protect against a memory dump. `lock()` drops the references.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from clinassist.security import crypto, schema
from clinassist.security.crypto import CryptoError, KdfParams

KEYRING = "keyring.json"
DATABASE = "vault.db"
FORMAT = 1
_PASS_LABEL = b"clinassist/keyring/v1/passphrase"
_RECOVERY_LABEL = b"clinassist/keyring/v1/recovery"


class VaultError(RuntimeError):
    """Raised with a stable code, never with key material, paths or patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


MIN_PASSPHRASE_CHARS = 12
MAX_PASSPHRASE_CHARS = 256  # bounds the work an Argon2id call is asked to do
_COMMON = frozenset(
    {
        "password1234",
        "password12345",
        "password123!",
        "passwordpassword",
        "123456789012",
        "qwertyuiop12",
        "iloveyou1234",
        "letmein12345",
        "welcome12345",
        "administrator",
        "clinassist123",
        "doctor123456",
    }
)


def check_passphrase(passphrase: str) -> None:
    """Raise VaultError("weak_passphrase") if the passphrase does not meet the policy.

    Called when a vault is created and when the passphrase is changed or reset.

    Policy (ADR-003), following NIST SP 800-63B: length over composition rules. At least 12
    characters not counting leading or trailing spaces, at most 256, not a known common choice,
    and not one character repeated. No "must contain a symbol" rule: it pushes people to
    predictable patterns and makes a memorable multi-word passphrase harder to use."""
    core = passphrase.strip()
    if not MIN_PASSPHRASE_CHARS <= len(core) <= MAX_PASSPHRASE_CHARS:
        raise VaultError("weak_passphrase")
    if core.lower() in _COMMON or len(set(core)) == 1:
        raise VaultError("weak_passphrase")


class Vault:
    """An unlocked vault. Create one with `create`, `unlock` or `recover`."""

    def __init__(self, directory: Path, master_key: bytes, keyring: dict) -> None:
        self._dir = Path(directory)
        self._master: bytes | None = master_key
        self._keyring = keyring

    # ----- opening -----
    @classmethod
    def create(
        cls, directory: Path | str, passphrase: str, kdf: KdfParams | None = None
    ) -> tuple[Vault, str]:
        """Make a new vault. Returns the vault and the recovery code, which is shown once and
        never stored in readable form."""
        directory = Path(directory)
        if (directory / KEYRING).exists() or (directory / DATABASE).exists():
            raise VaultError("vault_exists")
        check_passphrase(passphrase)
        kdf = kdf or KdfParams()
        master = crypto.new_master_key()
        recovery_code = crypto.new_recovery_code()
        keyring = {
            "format": FORMAT,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "kdf": kdf.to_dict(),
            "passphrase": _wrapped_slot(passphrase, master, kdf, _PASS_LABEL),
            "recovery": _wrapped_slot(
                crypto.normalize_recovery_code(recovery_code), master, kdf, _RECOVERY_LABEL
            ),
        }
        directory.mkdir(parents=True, exist_ok=True)
        vault = cls(directory, master, keyring)
        try:
            with vault.connect() as conn:
                schema.migrate(conn)
            vault._write_keyring()
        except Exception:
            # Remove a half-made vault so the next attempt does not hit vault_exists.
            for name in (DATABASE, KEYRING):
                (directory / name).unlink(missing_ok=True)
            raise
        return vault, recovery_code

    @classmethod
    def unlock(cls, directory: Path | str, passphrase: str) -> Vault:
        directory = Path(directory)
        keyring = _read_keyring(directory)
        master = _open_slot(keyring, "passphrase", passphrase, _PASS_LABEL)
        if master is None:
            raise VaultError("incorrect_passphrase")
        return cls._opened(directory, master, keyring)

    @classmethod
    def recover(cls, directory: Path | str, recovery_code: str, new_passphrase: str) -> Vault:
        """Set a new passphrase using the printed recovery code. The old passphrase stops
        working; the recovery code stays valid."""
        directory = Path(directory)
        keyring = _read_keyring(directory)
        code = crypto.normalize_recovery_code(recovery_code)
        master = _open_slot(keyring, "recovery", code, _RECOVERY_LABEL)
        if master is None:
            raise VaultError("incorrect_recovery_code")
        check_passphrase(new_passphrase)
        vault = cls._opened(directory, master, keyring)
        vault._set_passphrase(new_passphrase)
        return vault

    @classmethod
    def _opened(cls, directory: Path, master: bytes, keyring: dict) -> Vault:
        if not (directory / DATABASE).exists():
            raise VaultError("vault_corrupt")
        vault = cls(directory, master, keyring)
        try:
            with vault.connect() as conn:
                schema.migrate(conn)
        except schema.SchemaError as exc:
            raise VaultError(str(exc)) from None
        except Exception:
            # The master key was correct, so an unreadable database means it was damaged or
            # replaced, not a wrong passphrase.
            raise VaultError("vault_corrupt") from None
        return vault

    # ----- use -----
    @contextmanager
    def connect(self) -> Iterator:
        """An open SQLCipher connection that is ALWAYS closed afterwards (Windows cannot delete
        or replace a file with an open handle)."""
        from sqlcipher3 import dbapi2

        key = crypto.subkey(self._require_master(), "db")
        conn = dbapi2.connect(str(self._dir / DATABASE))
        try:
            conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")  # hex from bytes: safe to inline
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    @property
    def audio_key(self) -> bytes:
        return crypto.subkey(self._require_master(), "audio")

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def kdf(self) -> KdfParams:
        return KdfParams.from_dict(self._keyring["kdf"])

    def change_passphrase(self, old: str, new: str) -> None:
        """Requires the current passphrase even though the vault is unlocked, so an unattended
        unlocked session cannot be used to take the vault over."""
        if _open_slot(self._keyring, "passphrase", old, _PASS_LABEL) is None:
            raise VaultError("incorrect_passphrase")
        check_passphrase(new)
        self._set_passphrase(new)

    def lock(self) -> None:
        self._master = None

    @property
    def locked(self) -> bool:
        return self._master is None

    # ----- internals -----
    def _require_master(self) -> bytes:
        if self._master is None:
            raise VaultError("vault_locked")
        return self._master

    def _set_passphrase(self, passphrase: str) -> None:
        self._keyring["passphrase"] = _wrapped_slot(
            passphrase, self._require_master(), self.kdf, _PASS_LABEL
        )
        self._write_keyring()

    def _write_keyring(self) -> None:
        """Write to a temporary file, then replace, so a crash never leaves half a keyring."""
        path = self._dir / KEYRING
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self._keyring, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)


def _wrapped_slot(secret: str, master: bytes, kdf: KdfParams, label: bytes) -> dict:
    salt = crypto.new_salt()
    kek = crypto.derive_kek(secret, salt, kdf)
    return {"salt": crypto.b64(salt), "wrapped": crypto.b64(crypto.wrap(kek, master, label))}


def _open_slot(keyring: dict, slot: str, secret: str, label: bytes) -> bytes | None:
    try:
        entry = keyring[slot]
        kdf = KdfParams.from_dict(keyring["kdf"])
        kek = crypto.derive_kek(secret, crypto.unb64(entry["salt"]), kdf)
        return crypto.unwrap(kek, crypto.unb64(entry["wrapped"]), label)
    except CryptoError:
        return None
    except (KeyError, TypeError, ValueError):
        raise VaultError("vault_corrupt") from None


def _read_keyring(directory: Path) -> dict:
    path = directory / KEYRING
    if not path.exists():
        raise VaultError("vault_not_found")
    try:
        keyring = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise VaultError("vault_corrupt") from None
    if not isinstance(keyring, dict) or keyring.get("format") != FORMAT:
        raise VaultError("vault_corrupt")
    return keyring
