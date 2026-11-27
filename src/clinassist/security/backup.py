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

# This file lets the clinician save the whole vault to one file and bring it back later,
# for example after a PC failure. Backups are copies of the already encrypted files.
# It is used from the admin screens and relies on vault.py (open) and audit.py (verify).
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

# File extension for backups. A .clinbak file is just a zip with a known layout.
SUFFIX = ".clinbak"
FORMAT = 1
MANIFEST = "manifest.json"
# The only two files in a backup, plus the manifest.
FILES = (KEYRING, DATABASE)
NO_SESSION = ""  # audit entries that belong to no consultation, as in auth.py


# One error type for backup problems, with a stable code such as backup_damaged.
class BackupError(RuntimeError):
    """Raised with a stable code, never with paths, keys or patient data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
# Summary of a backup, shown to the user before they restore.
class BackupInfo:
    created_at: str
    schema_version: int
    audit_entries: int  # how many audit entries the vault had when the backup was made
    sessions: int = -1  # filled in once the backup has been opened and checked


# Suggested file name with the date and time, so backups do not overwrite each other.
def default_name(now: datetime | None = None) -> str:
    """For example ClinAssist-backup-2026-10-05-1430.clinbak."""
    # Local time here because the name is for the person reading it.
    now = now or datetime.now()
    return f"ClinAssist-backup-{now:%Y-%m-%d-%H%M}{SUFFIX}"


# Called when an admin chooses to back up. Returns the details of the backup made.
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
        # Add the extension if the user did not type it.
        target = target.with_name(target.name + SUFFIX)
    # Record the backup first, so the backup itself contains the entry saying it was made.
    if auditor is not None:
        auditor.record("backup_created", NO_SESSION, user_id)
    # Build the file under a temporary name, so a failed backup never looks like a good one.
    tmp = target.with_name(target.name + ".part")
    try:
        with vault.connect() as conn:
            # BEGIN IMMEDIATE takes the database's write lock: nothing can be saved while the
            # files are copied, so the copy is never caught halfway through a save.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                # The database version is saved, so a restore knows what shape the data has.
                version = schema.current_version(conn)
                # Highest audit entry number, or 0 if the log is empty.
                head = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM audit_logs").fetchone()[0]
                info = BackupInfo(clock().isoformat(timespec="seconds"), version, int(head))
                manifest = {
                    "format": FORMAT,
                    "created_at": info.created_at,
                    "schema_version": version,
                    "audit_entries": info.audit_entries,
                    # Size and SHA-256 of each file, so later damage or changes to the backup can be
                    # detected.
                    "files": {name: _describe(vault.directory / name) for name in FILES},
                }
                # Encrypted data does not compress, so the files are stored as they are.
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                    # Write the manifest text straight into the zip.
                    zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
                    for name in FILES:
                        # Copy the file from disk into the zip under its plain name.
                        zf.write(vault.directory / name, name)
            finally:
                # Nothing was changed, so just release the write lock.
                conn.execute("ROLLBACK")
        # Read the finished file back before calling it a backup.
        # Fails now, not at restore time, if the new file is not a good backup.
        read_backup(tmp)
        # Rename in one step, so the target is either the old file or the finished backup.
        os.replace(tmp, target)
    # Our own error: clean up the temporary file and pass it on.
    except BackupError:
        tmp.unlink(missing_ok=True)
        raise
    # A disk problem such as no space or a locked file. Reported with a stable code.
    except OSError:
        tmp.unlink(missing_ok=True)
        raise BackupError("backup_write_failed") from None
    return info


# The first check on a backup. It needs no password because it only checks the sizes and hashes.
def read_backup(path: Path | str) -> BackupInfo:
    """Check the file is a complete, unchanged backup. Does not need the passphrase."""
    try:
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read(MANIFEST))
            # The zip opened but is not one of ours.
            if not isinstance(manifest, dict) or "files" not in manifest:
                raise BackupError("not_a_backup")
            # A backup from a layout this program does not know.
            if manifest.get("format") != FORMAT:
                raise BackupError("backup_format_unknown")
            for name in FILES:
                expected = manifest["files"][name]
                data = zf.read(name)
                # A different size or hash means the file was damaged or changed after it was made.
                if len(data) != expected["size"] or _sha256(data) != expected["sha256"]:
                    raise BackupError("backup_damaged")
    except BackupError:
        raise
    # Anything wrong with the zip or the manifest means it is not a usable backup.
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError):
        raise BackupError("not_a_backup") from None
    except OSError:
        raise BackupError("backup_unreadable") from None
    return BackupInfo(
        str(manifest["created_at"]), int(manifest["schema_version"]), manifest["audit_entries"]
    )


# Lets the user test a backup safely before they rely on it.
def check_backup(path: Path | str, secret: str) -> BackupInfo:
    """Read the backup, open it with `secret` (its passphrase or the recovery code), and verify
    its audit chain, all in a temporary folder. The current vault is not touched."""
    # A throwaway folder that is deleted when the block ends.
    with tempfile.TemporaryDirectory(prefix="clinassist-check-") as tmp:
        vault = _unpack_and_open(Path(path), Path(tmp), secret)
        try:
            return _verified(vault, read_backup(path))
        finally:
            # Always lock again, so the key is dropped even if the check failed.
            vault.lock()


# The riskiest action, so it checks everything before changing the real vault.
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
    # Time stamp in folder names, so a second restore does not clash with the first.
    stamp = clock().strftime("%Y%m%d-%H%M%S")
    # A side folder where the backup is unpacked and tested first.
    staging = vault_dir.with_name(f"vault-restoring-{stamp}")
    # Where the current vault goes, so nothing is ever deleted.
    previous = vault_dir.with_name(f"vault-before-restore-{stamp}")
    staging.mkdir(parents=True)
    try:
        restored = _unpack_and_open(Path(path), staging, secret)
        _verified(restored, read_backup(path))
    except Exception:
        # Remove the unfinished staging folder after a failure.
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # The old vault records that it was replaced; that entry stays with the old folder.
    if current_auditor is not None:
        current_auditor.record("vault_replaced_by_restore", NO_SESSION, user_id)
    try:
        if vault_dir.exists():
            # Step 1 of the swap: the old vault moves to its safe folder.
            os.replace(vault_dir, previous)  # moved aside, never deleted
        # Step 2 of the swap: the checked backup becomes the live vault.
        os.replace(staging, vault_dir)
    except OSError:
        # Put the old vault back if it was already moved.
        if previous.exists() and not vault_dir.exists():
            os.replace(previous, vault_dir)
        shutil.rmtree(staging, ignore_errors=True)
        raise BackupError("restore_failed") from None
    # The restored vault records that it was restored, continuing its own audit chain.
    # Imported here, not at the top, because audit.py imports the vault module too.
    from clinassist.security.audit import HashChainAuditor

    restored.lock()
    # Re-open from the final location, because the staging folder has moved.
    restored = _open(vault_dir, secret)
    HashChainAuditor(restored).record("vault_restored", NO_SESSION, user_id)
    restored.lock()
    # Tells the caller where the old vault is, so it can be shown to the user.
    return previous


# ----- internals -----
# Unzips the two files into a folder and opens them as a vault.
def _unpack_and_open(path: Path, folder: Path, secret: str) -> Vault:
    read_backup(path)
    with zipfile.ZipFile(path) as zf:
        for name in FILES:  # only the two known names: nothing else is ever written out
            (folder / name).write_bytes(zf.read(name))
    return _open(folder, secret)


# The user types one secret, so try it as the passphrase first, then as the recovery code.
def _open(folder: Path, secret: str) -> Vault:
    """Open with the passphrase, or failing that with the recovery code."""
    try:
        return Vault.unlock(folder, secret)
    except VaultError as exc:
        # Any other problem (such as a corrupt vault) is a real error, not just a wrong secret.
        if exc.code != "incorrect_passphrase":
            raise
    try:
        return Vault.open_with_recovery_code(folder, secret)
    except VaultError as exc:
        if exc.code == "incorrect_recovery_code":
            raise BackupError("backup_secret_incorrect") from None
        raise


# Checks the audit chain is intact and counts the sessions, so the user sees what is inside.
def _verified(vault: Vault, info: BackupInfo) -> BackupInfo:
    from clinassist.security.audit import HashChainAuditor

    # Walks the full hash chain. A broken chain means the backup was tampered with.
    result = HashChainAuditor(vault).verify()
    if not result.ok:
        raise BackupError("backup_audit_broken")
    with vault.connect() as conn:
        sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    return BackupInfo(info.created_at, info.schema_version, info.audit_entries, int(sessions))


# Size and hash of one file, for the manifest.
def _describe(path: Path) -> dict:
    data = path.read_bytes()
    return {"size": len(data), "sha256": _sha256(data)}


# hexdigest gives the hash as readable text.
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
