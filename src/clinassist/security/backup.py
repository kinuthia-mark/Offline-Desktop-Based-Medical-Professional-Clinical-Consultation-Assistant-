"""Backup and restore of the encrypted vault (FR-10c, ADR-014).

A backup is one file (`.clinbak`, a zip archive) holding:

    manifest.json   format, time made, schema version, size and SHA-256 of each file below,
                    and the audit chain's newest entry at the time of the backup
    keyring.json    the vault's keyring, exactly as on disk (the master key only in wrapped form)
    vault.db        the SQLCipher database, exactly as on disk (encrypted)

Nothing is decrypted to make a backup, so the file is as safe to carry on a USB drive as the
vault itself: without the passphrase or the recovery code it reveals nothing.

Restoring checks the backup completely before touching the current vault:
  1. it is a backup of a format this program knows, and every file matches its SHA-256;
  2. it opens with the passphrase it had when it was made, or with the recovery code;
  3. its audit chain verifies from the first entry to the last.
Only then is the current vault folder moved aside (never deleted) and the backup put in place.

Limit: optional audio recordings (off by default, ADR-003) are not included.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from clinassist.security import schema
from clinassist.security.vault import DATABASE, KEYRING, Vault, VaultError

SUFFIX = ".clinbak"
FORMAT = 1
MANIFEST = "manifest.json"
FILES = (KEYRING, DATABASE)
NO_SESSION = ""  # audit entries that belong to no consultation, as in auth.py


class BackupError(RuntimeError):
    """Raised with a stable code, never with paths, keys or patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BackupInfo:
    created_at: str
    schema_version: int
    audit_entries: int  # how many audit entries the vault had when the backup was made
    sessions: int = -1  # filled in once the backup has been opened and checked


def default_name(now: datetime | None = None) -> str:
    """For example ClinAssist-backup-2026-10-05-1430.clinbak."""
    now = now or datetime.now()
    return f"ClinAssist-backup-{now:%Y-%m-%d-%H%M}{SUFFIX}"


def make_backup(
    vault: Vault,
    target: Path | str,
    user_id: str,
    auditor=None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> BackupInfo:
    """Write a backup of `vault` to `target`. The vault must be unlocked."""
    target = Path(target)
    if target.suffix.lower() != SUFFIX:
        target = target.with_name(target.name + SUFFIX)
    # Record the backup first, so the backup itself contains the entry saying it was made.
    if auditor is not None:
        auditor.record("backup_created", NO_SESSION, user_id)
    tmp = target.with_name(target.name + ".part")
    try:
        with vault.connect() as conn:
            # BEGIN IMMEDIATE takes the database's write lock: nothing can be saved while the
            # files are copied, so the copy is never caught halfway through a save.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = schema.current_version(conn)
                head = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM audit_logs").fetchone()[0]
                info = BackupInfo(clock().isoformat(timespec="seconds"), version, int(head))
                manifest = {
                    "format": FORMAT,
                    "created_at": info.created_at,
                    "schema_version": version,
                    "audit_entries": info.audit_entries,
                    "files": {name: _describe(vault.directory / name) for name in FILES},
                }
                # Encrypted data does not compress, so the files are stored as they are.
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                    zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
                    for name in FILES:
                        zf.write(vault.directory / name, name)
            finally:
                conn.execute("ROLLBACK")
        # Read the finished file back before calling it a backup.
        read_backup(tmp)
        os.replace(tmp, target)
    except BackupError:
        tmp.unlink(missing_ok=True)
        raise
    except OSError:
        tmp.unlink(missing_ok=True)
        raise BackupError("backup_write_failed") from None
    return info


def read_backup(path: Path | str) -> BackupInfo:
    """Check the file is a complete, unchanged backup. Does not need the passphrase."""
    try:
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read(MANIFEST))
            if not isinstance(manifest, dict) or "files" not in manifest:
                raise BackupError("not_a_backup")
            if manifest.get("format") != FORMAT:
                raise BackupError("backup_format_unknown")
            for name in FILES:
                expected = manifest["files"][name]
                data = zf.read(name)
                if len(data) != expected["size"] or _sha256(data) != expected["sha256"]:
                    raise BackupError("backup_damaged")
    except BackupError:
        raise
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError):
        raise BackupError("not_a_backup") from None
    except OSError:
        raise BackupError("backup_unreadable") from None
    return BackupInfo(
        str(manifest["created_at"]), int(manifest["schema_version"]), manifest["audit_entries"]
    )


def check_backup(path: Path | str, secret: str) -> BackupInfo:
    """Read the backup, open it with `secret` (its passphrase or the recovery code), and verify
    its audit chain, all in a temporary folder. The current vault is not touched."""
    with tempfile.TemporaryDirectory(prefix="clinassist-check-") as tmp:
        vault = _unpack_and_open(Path(path), Path(tmp), secret)
        try:
            return _verified(vault, read_backup(path))
        finally:
            vault.lock()


def restore_backup(
    path: Path | str,
    vault_dir: Path | str,
    secret: str,
    user_id: str,
    current_auditor=None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Path:
    """Replace the vault in `vault_dir` with the backup. Returns where the previous vault was
    moved. The program must stop using its open vault afterwards (the files have changed)."""
    vault_dir = Path(vault_dir)
    stamp = clock().strftime("%Y%m%d-%H%M%S")
    staging = vault_dir.with_name(f"vault-restoring-{stamp}")
    previous = vault_dir.with_name(f"vault-before-restore-{stamp}")
    staging.mkdir(parents=True)
    try:
        restored = _unpack_and_open(Path(path), staging, secret)
        _verified(restored, read_backup(path))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # The old vault records that it was replaced; that entry stays with the old folder.
    if current_auditor is not None:
        current_auditor.record("vault_replaced_by_restore", NO_SESSION, user_id)
    try:
        if vault_dir.exists():
            os.replace(vault_dir, previous)  # moved aside, never deleted
        os.replace(staging, vault_dir)
    except OSError:
        # Put the old vault back if it was already moved.
        if previous.exists() and not vault_dir.exists():
            os.replace(previous, vault_dir)
        shutil.rmtree(staging, ignore_errors=True)
        raise BackupError("restore_failed") from None
    # The restored vault records that it was restored, continuing its own audit chain.
    from clinassist.security.audit import HashChainAuditor

    restored.lock()
    restored = _open(vault_dir, secret)
    HashChainAuditor(restored).record("vault_restored", NO_SESSION, user_id)
    restored.lock()
    return previous


# ----- internals -----
def _unpack_and_open(path: Path, folder: Path, secret: str) -> Vault:
    read_backup(path)
    with zipfile.ZipFile(path) as zf:
        for name in FILES:  # only the two known names: nothing else is ever written out
            (folder / name).write_bytes(zf.read(name))
    return _open(folder, secret)


def _open(folder: Path, secret: str) -> Vault:
    """Open with the passphrase, or failing that with the recovery code."""
    try:
        return Vault.unlock(folder, secret)
    except VaultError as exc:
        if exc.code != "incorrect_passphrase":
            raise
    try:
        return Vault.open_with_recovery_code(folder, secret)
    except VaultError as exc:
        if exc.code == "incorrect_recovery_code":
            raise BackupError("backup_secret_incorrect") from None
        raise


def _verified(vault: Vault, info: BackupInfo) -> BackupInfo:
    from clinassist.security.audit import HashChainAuditor

    result = HashChainAuditor(vault).verify()
    if not result.ok:
        raise BackupError("backup_audit_broken")
    with vault.connect() as conn:
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    return BackupInfo(info.created_at, info.schema_version, info.audit_entries, int(sessions))


def _describe(path: Path) -> dict:
    data = path.read_bytes()
    return {"size": len(data), "sha256": _sha256(data)}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
