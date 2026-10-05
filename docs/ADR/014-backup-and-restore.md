# ADR-014: Backup and restore of the encrypted vault

- Status: accepted
- Date: 2026-10-05
- Requirement IDs: FR-10c (use case "Backup Encrypted Database", Figure 4.1)
- Evidence: `src/clinassist/security/backup.py`, `tests/test_backup.py`, the backup tests in
  `tests/test_ui.py`

## Context
All records live in one encrypted vault folder on one PC (ADR-001, ADR-003). A failed disk, a
stolen laptop or a damaged file would lose every consultation. The proposal lists backing up the
encrypted database as an administrator use case but does not say how.

Two risks shape the design. A backup must not become the weak copy: it travels on a USB drive, so
it must be as unreadable as the vault. And a restore replaces the clinic's records, so a wrong,
damaged or tampered backup must never be put in place, and the records it replaces must not be
lost.

## Options considered
1. **Copy the vault folder by hand.** No tools needed, but a copy made during a save can be
   half-written, nothing checks it, and staff must know where the folder is.
2. **Export the records decrypted** (for example to CSV) and re-import them. Readable by anyone
   who finds the drive. Rejected.
3. **One file with the vault's two files exactly as they are, plus fingerprints**, made and
   restored from the admin screen. Chosen.

## Decision
- **Making a backup** (admin only): the program takes the database's write lock, so nothing is
  saved during the copy. It then writes one `.clinbak` file (a zip archive) holding `keyring.json`,
  `vault.db` and a manifest with each file's size and SHA-256, the schema version, and the number
  of audit entries. Nothing is decrypted. The file is read back and checked before it is called a
  backup. The audit log records `backup_created`, and the backup itself contains that entry.
- **Restoring** (admin only) checks everything before changing anything:
  1. every file matches its SHA-256 in the manifest;
  2. the backup opens with the passphrase it had when it was made, or with the recovery code
     (which never changes, so it still works after the passphrase has been changed);
  3. its audit chain verifies from the first entry to the last.

  The admin then sees the backup's date and how many consultations it holds, and confirms. The
  current vault records `vault_replaced_by_restore` and is moved to `vault-before-restore-<time>`,
  never deleted. The backup is put in place, and records `vault_restored` in its own chain. The
  program then closes, because the vault it has open no longer matches the files.
- Backup and restore are reached through `app.Backups`, so the screens still never import the
  security package (a rule checked by `tests/test_ui.py`).

## Evidence
`tests/test_backup.py` covers:
- the round trip: a consultation saved after the backup is gone after the restore and is still
  in the moved-aside vault, and both audit chains verify;
- the backup file contains no readable text, no SQLite header, and only the three expected files;
- the recovery code opens a backup after the passphrase has been changed;
- a wrong passphrase, one flipped bit in the database, and an audit log edited before the backup
  are each refused with the current vault byte-for-byte unchanged;
- a file that is not a backup is refused;
- error messages carry codes only.

Removing the audit-chain check from the restore makes a test fail.

The UI tests cover backing up and restoring from the admin screen, cancelling at the
confirmation, a wrong passphrase, and a clinician being refused.

## Limits
- Backups are made when the administrator chooses; there is no schedule. A clinic should make one
  at the end of each day and keep it away from the PC.
- A backup restores the vault as it was. Consultations saved after it are only in the
  moved-aside folder; merging the two is not supported.
- Optional audio recordings (off by default, ADR-003) are not included.
- The manifest proves the file did not change after it was made. It does not prove who made it.
  Anyone with the passphrase could make a vault and a matching backup; the audit chain and the
  admin's own record of chain fingerprints (FR-10d) are the check on that.
