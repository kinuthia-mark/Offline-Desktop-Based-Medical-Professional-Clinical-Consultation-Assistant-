"""Backup and restore of the vault (FR-10c, ADR-014): the backup stays encrypted, and a restore
replaces nothing until the backup is proven complete, openable and untampered."""

from __future__ import annotations

import zipfile

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")

from clinassist.adapters.store import VaultSessionStore  # noqa: E402
from clinassist.security.audit import HashChainAuditor  # noqa: E402
from clinassist.security.backup import (  # noqa: E402
    BackupError,
    check_backup,
    default_name,
    make_backup,
    read_backup,
    restore_backup,
)
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault  # noqa: E402
from tests.test_store import SECRET, _record  # noqa: E402

PASS = "a long synthetic passphrase 42"


@pytest.fixture
def made(tmp_path):
    """A vault with one saved consultation and an audit entry, plus its recovery code."""
    vault, code = Vault.create(tmp_path / "data" / "vault", PASS, kdf=TEST_KDF)
    VaultSessionStore(vault).save(_record("s1"))
    HashChainAuditor(vault).record("login", "", "admin1")
    return vault, code


def _sessions(vault: Vault) -> list[str]:
    return VaultSessionStore(vault).session_ids()


def _events(vault: Vault) -> list[str]:
    return [e[2] for e in HashChainAuditor(vault).events(100)]


def _folder_bytes(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def test_backup_and_restore_round_trip(made, tmp_path):
    vault, _ = made
    auditor = HashChainAuditor(vault)
    info = make_backup(vault, tmp_path / "b.clinbak", "admin1", auditor)
    assert info.audit_entries >= 2
    VaultSessionStore(vault).save(_record("s2"))  # saved after the backup

    previous = restore_backup(tmp_path / "b.clinbak", vault.directory, PASS, "admin1", auditor)

    restored = Vault.unlock(vault.directory, PASS)
    assert _sessions(restored) == ["s1"]  # back to the moment of the backup
    assert HashChainAuditor(restored).verify().ok
    assert "backup_created" in _events(restored) and _events(restored)[0] == "vault_restored"
    old = Vault.unlock(previous, PASS)  # the replaced vault was moved aside, not deleted
    assert sorted(_sessions(old)) == ["s1", "s2"]
    assert _events(old)[0] == "vault_replaced_by_restore"
    assert not list(vault.directory.parent.glob("vault-restoring-*"))


def test_the_backup_file_is_encrypted_and_holds_only_the_vault(made, tmp_path):
    vault, _ = made
    make_backup(vault, tmp_path / "b.clinbak", "admin1")
    data = (tmp_path / "b.clinbak").read_bytes()
    assert SECRET.encode() not in data and b"Cough" not in data
    assert b"SQLite format 3" not in data
    with zipfile.ZipFile(tmp_path / "b.clinbak") as zf:
        assert sorted(zf.namelist()) == ["keyring.json", "manifest.json", "vault.db"]


def test_backup_name_gets_the_extension(made, tmp_path):
    vault, _ = made
    make_backup(vault, tmp_path / "plain", "admin1")
    assert (tmp_path / "plain.clinbak").exists() and not (tmp_path / "plain").exists()
    assert default_name().startswith("ClinAssist-backup-") and default_name().endswith(".clinbak")


def test_recovery_code_opens_a_backup_after_the_passphrase_changed(made, tmp_path):
    vault, code = made
    make_backup(vault, tmp_path / "b.clinbak", "admin1")
    vault.change_passphrase(PASS, "a different long passphrase 7")
    # The backup still has the old passphrase; the recovery code never changes.
    assert check_backup(tmp_path / "b.clinbak", PASS).sessions == 1
    assert check_backup(tmp_path / "b.clinbak", code.lower()).sessions == 1


def test_wrong_secret_changes_nothing(made, tmp_path):
    vault, _ = made
    make_backup(vault, tmp_path / "b.clinbak", "admin1")
    before = _folder_bytes(vault.directory)
    with pytest.raises(BackupError) as info:
        restore_backup(tmp_path / "b.clinbak", vault.directory, "not the passphrase 99", "a")
    assert info.value.code == "backup_secret_incorrect"
    assert _folder_bytes(vault.directory) == before
    assert sorted(p.name for p in vault.directory.parent.iterdir()) == ["vault"]


def test_a_changed_byte_is_refused_before_anything_is_replaced(made, tmp_path):
    vault, _ = made
    good = tmp_path / "b.clinbak"
    make_backup(vault, good, "admin1")
    bad = tmp_path / "bad.clinbak"
    with zipfile.ZipFile(good) as src, zipfile.ZipFile(bad, "w") as dst:
        for name in src.namelist():
            data = bytearray(src.read(name))
            if name == "vault.db":
                data[5000] ^= 0x01  # one bit
            dst.writestr(name, bytes(data))
    before = _folder_bytes(vault.directory)
    with pytest.raises(BackupError) as info:
        restore_backup(bad, vault.directory, PASS, "admin1")
    assert info.value.code == "backup_damaged"
    assert _folder_bytes(vault.directory) == before


def test_a_backup_with_an_edited_audit_log_is_refused(made, tmp_path):
    """The manifest only proves the file was not changed after the backup. A vault whose log was
    edited before the backup is caught by checking the chain itself."""
    vault, _ = made
    with vault.connect() as conn:
        conn.execute("UPDATE audit_logs SET user_id = 'someone_else' WHERE seq = 1")
        conn.commit()
    make_backup(vault, tmp_path / "b.clinbak", "admin1")
    with pytest.raises(BackupError) as info:
        check_backup(tmp_path / "b.clinbak", PASS)
    assert info.value.code == "backup_audit_broken"
    before = _folder_bytes(vault.directory)
    with pytest.raises(BackupError) as info:
        restore_backup(tmp_path / "b.clinbak", vault.directory, PASS, "admin1")
    assert info.value.code == "backup_audit_broken"
    assert _folder_bytes(vault.directory) == before


@pytest.mark.parametrize("content", [b"not a zip at all", b""])
def test_other_files_are_not_backups(tmp_path, content):
    path = tmp_path / "x.clinbak"
    path.write_bytes(content)
    with pytest.raises(BackupError) as info:
        read_backup(path)
    assert info.value.code == "not_a_backup"


def test_errors_never_carry_paths_or_patient_text(made, tmp_path):
    vault, _ = made
    make_backup(vault, tmp_path / "b.clinbak", "admin1")
    with pytest.raises(BackupError) as info:
        check_backup(tmp_path / "b.clinbak", SECRET)
    assert str(info.value) == "backup_secret_incorrect"
