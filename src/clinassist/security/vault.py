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

# This file is the vault: the encrypted store for all patient data (notes, users, audit log).
# It creates the vault, unlocks it with the passphrase or recovery code, and hands out
# encrypted database connections. Every other part of the app reaches data only through it.
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from clinassist.security import crypto, schema
from clinassist.security.crypto import CryptoError, KdfParams

# File names inside the vault folder.
KEYRING = "keyring.json"
DATABASE = "vault.db"
# Version of the keyring file layout. An unknown number is treated as a damaged keyring.
FORMAT = 1
# These labels are tied into each wrap, so the passphrase copy and the recovery copy cannot be
# swapped.
_PASS_LABEL = b"clinassist/keyring/v1/passphrase"
_RECOVERY_LABEL = b"clinassist/keyring/v1/recovery"


# One error type for all vault problems. The code says which, for example vault_locked.
class VaultError(RuntimeError):
    """Raised with a stable code, never with key material, paths or patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Length limits for the passphrase policy.
MIN_PASSPHRASE_CHARS = 12
MAX_PASSPHRASE_CHARS = 256  # bounds the work an Argon2id call is asked to do
# A small block list of very common passphrases that are long enough to pass the length rule.
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
    # Spaces at the start or end are ignored when counting, so "   short   " is still short.
    core = passphrase.strip()
    if not MIN_PASSPHRASE_CHARS <= len(core) <= MAX_PASSPHRASE_CHARS:
        raise VaultError("weak_passphrase")
    # Refuse well-known choices in any capitalisation, and one character repeated.
    if core.lower() in _COMMON or len(set(core)) == 1:
        raise VaultError("weak_passphrase")


# One open vault. It holds the master key in memory only until lock() is called.
class Vault:
    """An unlocked vault. Create one with `create`, `unlock` or `recover`."""

    # Use create, unlock or recover instead of calling this directly.
    def __init__(self, directory: Path, master_key: bytes, keyring: dict) -> None:
        self._dir = Path(directory)
        # None means locked. The key is kept only in memory, never saved in plain form.
        self._master: bytes | None = master_key
        self._keyring = keyring

    # ----- opening -----
    # A classmethod runs on the class itself, so no Vault object is needed yet.
    @classmethod
    def create(
        cls, directory: Path | str, passphrase: str, kdf: KdfParams | None = None
    ) -> tuple[Vault, str]:
        """Make a new vault. Returns the vault and the recovery code, which is shown once and
        never stored in readable form."""
        directory = Path(directory)
        # Refuse to overwrite an existing vault, which would destroy its data.
        if (directory / KEYRING).exists() or (directory / DATABASE).exists():
            raise VaultError("vault_exists")
        check_passphrase(passphrase)
        # Use the real settings unless tests pass the fast ones.
        kdf = kdf or KdfParams()
        # The master key is random; nobody ever types or sees it. It is stored only in wrapped
        # (encrypted) form, twice: once locked by the passphrase, once by the recovery code.
        master = crypto.new_master_key()
        recovery_code = crypto.new_recovery_code()
        keyring = {
            # The keyring records its layout version and Argon2id settings, so they can change
            # later.
            "format": FORMAT,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "kdf": kdf.to_dict(),
            "passphrase": _wrapped_slot(passphrase, master, kdf, _PASS_LABEL),
            "recovery": _wrapped_slot(
                crypto.normalize_recovery_code(recovery_code), master, kdf, _RECOVERY_LABEL
            ),
        }
        # Make the vault folder (and parents) if it is not there yet.
        directory.mkdir(parents=True, exist_ok=True)
        vault = cls(directory, master, keyring)
        try:
            with vault.connect() as conn:
                # Creates the tables in a new database, or updates an older one.
                schema.migrate(conn)
            # Save the keyring last, so a vault only counts as existing once everything else worked.
            vault._write_keyring()
        except Exception:
            # Remove a half-made vault so the next attempt does not hit vault_exists.
            for name in (DATABASE, KEYRING):
                (directory / name).unlink(missing_ok=True)
            raise
        return vault, recovery_code

    @classmethod
    # Normal login to the vault. Returns an open Vault or raises VaultError.
    def unlock(cls, directory: Path | str, passphrase: str) -> Vault:
        directory = Path(directory)
        # Read the keyring, turn the passphrase into a key, and try to unwrap the master key.
        # If that fails, the passphrase is wrong, and we know it before opening the database.
        keyring = _read_keyring(directory)
        master = _open_slot(keyring, "passphrase", passphrase, _PASS_LABEL)
        if master is None:
            raise VaultError("incorrect_passphrase")
        # Shared final step: check the database file exists and is up to date.
        return cls._opened(directory, master, keyring)

    @classmethod
    # Used for checking a backup without changing anything.
    def open_with_recovery_code(cls, directory: Path | str, recovery_code: str) -> Vault:
        """Open with the recovery code without changing the passphrase. Used to check a backup
        whose passphrase has since been changed; the recovery code never changes."""
        directory = Path(directory)
        keyring = _read_keyring(directory)
        code = crypto.normalize_recovery_code(recovery_code)
        master = _open_slot(keyring, "recovery", code, _RECOVERY_LABEL)
        if master is None:
            raise VaultError("incorrect_recovery_code")
        return cls._opened(directory, master, keyring)

    @classmethod
    # For a forgotten passphrase. Only the passphrase slot changes, the data is not re-encrypted.
    def recover(cls, directory: Path | str, recovery_code: str, new_passphrase: str) -> Vault:
        """Set a new passphrase using the printed recovery code. The old passphrase stops
        working; the recovery code stays valid."""
        directory = Path(directory)
        keyring = _read_keyring(directory)
        code = crypto.normalize_recovery_code(recovery_code)
        master = _open_slot(keyring, "recovery", code, _RECOVERY_LABEL)
        if master is None:
            raise VaultError("incorrect_recovery_code")
        # Check the new passphrase before changing anything, so a weak one cannot be saved.
        check_passphrase(new_passphrase)
        vault = cls._opened(directory, master, keyring)
        # Wrap the same master key again with a key made from the new passphrase.
        vault._set_passphrase(new_passphrase)
        return vault

    @classmethod
    # Final step after a key has been unwrapped: open the database and bring it up to date.
    def _opened(cls, directory: Path, master: bytes, keyring: dict) -> Vault:
        if not (directory / DATABASE).exists():
            raise VaultError("vault_corrupt")
        vault = cls(directory, master, keyring)
        try:
            with vault.connect() as conn:
                schema.migrate(conn)
        except schema.SchemaError as exc:
            # Pass on the stable code (schema_newer_than_program) as a vault error.
            raise VaultError(str(exc)) from None
        except Exception:
            # The master key was correct, so an unreadable database means it was damaged or
            # replaced, not a wrong passphrase.
            raise VaultError("vault_corrupt") from None
        return vault

    # ----- use -----
    @contextmanager
    # A context manager, so it is used with a with block and closes by itself.
    def connect(self) -> Iterator:
        """An open SQLCipher connection that is ALWAYS closed afterwards (Windows cannot delete
        or replace a file with an open handle)."""
        # Imported here so the rest of the file can load even where SQLCipher is not installed.
        from sqlcipher3 import dbapi2

        # The database has its own key, derived from the master key, so the master key itself
        # never serves as a database key.
        key = crypto.subkey(self._require_master(), "db")
        # The file is encrypted, so nothing can be read until the key pragma below is run.
        conn = dbapi2.connect(str(self._dir / DATABASE))
        # "PRAGMA key" hands SQLCipher the key; every page of the file is decrypted with it.
        # foreign_keys makes the database enforce links between tables (a note must belong to
        # a session).
        try:
            conn.execute(f"PRAGMA key = \"x'{key.hex()}'\"")  # hex from bytes: safe to inline
            conn.execute("PRAGMA foreign_keys = ON")
            # Hand the open connection to the caller's with block. The finally below runs
            # afterwards.
            yield conn
        finally:
            # Always close, even after an error, so Windows can later move or delete the file.
            conn.close()

    # A property is read like an attribute, without brackets.
    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def kdf(self) -> KdfParams:
        return KdfParams.from_dict(self._keyring["kdf"])

    def recovery_code_matches(self, recovery_code: str) -> bool:
        """True if `recovery_code` is this vault's recovery code. Used to let the holder of the
        code reset a forgotten login password: they could already open the whole vault with it,
        so this gives them nothing new. Costs one Argon2id derivation, like a login."""
        code = crypto.normalize_recovery_code(recovery_code)
        return _open_slot(self._keyring, "recovery", code, _RECOVERY_LABEL) is not None

    def change_passphrase(self, old: str, new: str) -> None:
        """Requires the current passphrase even though the vault is unlocked, so an unattended
        unlocked session cannot be used to take the vault over."""
        if _open_slot(self._keyring, "passphrase", old, _PASS_LABEL) is None:
            raise VaultError("incorrect_passphrase")
        check_passphrase(new)
        self._set_passphrase(new)

    # Locks the vault again, for example when the user is finished.
    def lock(self) -> None:
        # Forget the master key. Every later connect() raises vault_locked.
        # Drops the only reference to the key. Python cannot guarantee it is wiped from memory.
        self._master = None

    @property
    def locked(self) -> bool:
        return self._master is None

    # ----- internals -----
    # Returns the key, or raises vault_locked. Every use of the key goes through this check.
    def _require_master(self) -> bytes:
        if self._master is None:
            raise VaultError("vault_locked")
        return self._master

    # Replaces only the passphrase slot. The recovery slot and the data stay as they are.
    def _set_passphrase(self, passphrase: str) -> None:
        self._keyring["passphrase"] = _wrapped_slot(
            passphrase, self._require_master(), self.kdf, _PASS_LABEL
        )
        self._write_keyring()

    # Used whenever the keyring changes.
    def _write_keyring(self) -> None:
        """Write to a temporary file, then replace, so a crash never leaves half a keyring."""
        path = self._dir / KEYRING
        # Write beside the real file first, so the real file is never half written.
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self._keyring, fh, indent=2)
            fh.flush()
            # Force the data onto the disk before the replace, in case the power fails.
            os.fsync(fh.fileno())
        # Swap the files in one step. It is atomic, so there is never a half keyring.
        os.replace(tmp, path)


# Builds one keyring slot. Used for both the passphrase and the recovery code.
def _wrapped_slot(secret: str, master: bytes, kdf: KdfParams, label: bytes) -> dict:
    # One "slot" in the keyring: a fresh salt, and the master key locked with a key made from
    # the secret and that salt. Stored as base64 text so the keyring is readable JSON.
    salt = crypto.new_salt()
    kek = crypto.derive_kek(secret, salt, kdf)
    return {"salt": crypto.b64(salt), "wrapped": crypto.b64(crypto.wrap(kek, master, label))}


# Tries one slot. Slot is "passphrase" or "recovery".
def _open_slot(keyring: dict, slot: str, secret: str, label: bytes) -> bytes | None:
    # Returns the master key, or None if the secret is wrong. A keyring with missing or
    # malformed fields is reported as corrupt rather than as a wrong secret.
    try:
        entry = keyring[slot]
        kdf = KdfParams.from_dict(keyring["kdf"])
        kek = crypto.derive_kek(secret, crypto.unb64(entry["salt"]), kdf)
        return crypto.unwrap(kek, crypto.unb64(entry["wrapped"]), label)
    except CryptoError:
        return None
    except (KeyError, TypeError, ValueError):
        raise VaultError("vault_corrupt") from None


# Loads and checks keyring.json. Any problem with the file becomes a stable error code.
def _read_keyring(directory: Path) -> dict:
    path = directory / KEYRING
    if not path.exists():
        raise VaultError("vault_not_found")
    try:
        keyring = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise VaultError("vault_corrupt") from None
    # Reject a file that is not a JSON object or has an unknown layout version.
    if not isinstance(keyring, dict) or keyring.get("format") != FORMAT:
        raise VaultError("vault_corrupt")
    return keyring
