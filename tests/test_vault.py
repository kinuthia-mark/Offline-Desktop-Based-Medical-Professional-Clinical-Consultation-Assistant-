"""The vault (FR-07, NFR-05, ADR-003): create, unlock, wrong passphrase, recovery, tampering."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from sqlcipher3 import dbapi2  # noqa: E402

from clinassist.security import schema  # noqa: E402
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import DATABASE, KEYRING, Vault, VaultError  # noqa: E402

PASS = "a long synthetic passphrase 42"
NEW_PASS = "another synthetic passphrase 77"
MARKER = "SYNTHETIC-PHI-MARKER-9081"


@pytest.fixture
def made(tmp_path):
    vault, code = Vault.create(tmp_path / "v", PASS, kdf=TEST_KDF)
    with vault.connect() as conn, conn:
        conn.execute("CREATE TABLE probe (body TEXT)")
        conn.execute("INSERT INTO probe VALUES (?)", (MARKER,))
    return tmp_path / "v", code


def _probe(vault: Vault) -> str:
    with vault.connect() as conn:
        return conn.execute("SELECT body FROM probe").fetchone()[0]


def test_create_runs_migrations_and_stores_the_kdf_settings(tmp_path):
    vault, code = Vault.create(tmp_path / "v", PASS, kdf=TEST_KDF)
    with vault.connect() as conn:
        assert schema.current_version(conn) == schema.LATEST
    assert vault.kdf == TEST_KDF
    keyring = json.loads((tmp_path / "v" / KEYRING).read_text(encoding="utf-8"))
    assert keyring["kdf"] == TEST_KDF.to_dict()
    assert code.count("-") == 7


def test_unlock_with_the_correct_passphrase_reads_the_data(made):
    directory, _ = made
    assert _probe(Vault.unlock(directory, PASS)) == MARKER


def test_wrong_passphrase_is_reported_as_such_not_as_a_sqlite_error(made):
    directory, _ = made
    with pytest.raises(VaultError) as info:
        Vault.unlock(directory, "wrong passphrase entirely")
    assert info.value.code == "incorrect_passphrase"
    assert "database" not in str(info.value)


def test_files_reveal_neither_data_nor_key(made):
    directory, code = made
    raw = (directory / DATABASE).read_bytes()
    assert MARKER.encode() not in raw
    assert not raw.startswith(b"SQLite format 3")
    keyring_text = (directory / KEYRING).read_text(encoding="utf-8")
    assert PASS not in keyring_text
    assert code not in keyring_text and code.replace("-", "") not in keyring_text


def test_standard_sqlite_cannot_open_the_database(made):
    directory, _ = made
    with pytest.raises(sqlite3.DatabaseError), closing(sqlite3.connect(directory / DATABASE)) as c:
        c.execute("SELECT * FROM sqlite_master").fetchall()


def test_create_refuses_to_overwrite_an_existing_vault(made):
    directory, _ = made
    with pytest.raises(VaultError) as info:
        Vault.create(directory, PASS, kdf=TEST_KDF)
    assert info.value.code == "vault_exists"
    assert _probe(Vault.unlock(directory, PASS)) == MARKER


def test_missing_vault(tmp_path):
    with pytest.raises(VaultError) as info:
        Vault.unlock(tmp_path / "nothing-here", PASS)
    assert info.value.code == "vault_not_found"


def test_recovery_code_sets_a_new_passphrase_and_old_one_stops_working(made):
    directory, code = made
    vault = Vault.recover(directory, code.lower().replace("-", " "), NEW_PASS)
    assert _probe(vault) == MARKER
    assert _probe(Vault.unlock(directory, NEW_PASS)) == MARKER
    with pytest.raises(VaultError, match="^incorrect_passphrase$"):
        Vault.unlock(directory, PASS)
    # the recovery code keeps working after use
    assert _probe(Vault.recover(directory, code, PASS)) == MARKER


def test_wrong_recovery_code_is_rejected(made):
    directory, _ = made
    with pytest.raises(VaultError) as info:
        Vault.recover(directory, "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH", NEW_PASS)
    assert info.value.code == "incorrect_recovery_code"
    assert _probe(Vault.unlock(directory, PASS)) == MARKER


def test_passphrase_cannot_unlock_the_recovery_slot(made):
    """Slots are bound to their label, so swapping wrapped blobs in the keyring fails."""
    directory, _ = made
    path = directory / KEYRING
    keyring = json.loads(path.read_text(encoding="utf-8"))
    keyring["recovery"], keyring["passphrase"] = keyring["passphrase"], keyring["recovery"]
    path.write_text(json.dumps(keyring), encoding="utf-8")
    with pytest.raises(VaultError, match="^incorrect_passphrase$"):
        Vault.unlock(directory, PASS)


def test_change_passphrase_requires_the_current_one(made):
    directory, _ = made
    vault = Vault.unlock(directory, PASS)
    with pytest.raises(VaultError, match="^incorrect_passphrase$"):
        vault.change_passphrase("not the current one", NEW_PASS)
    vault.change_passphrase(PASS, NEW_PASS)
    assert _probe(Vault.unlock(directory, NEW_PASS)) == MARKER
    with pytest.raises(VaultError, match="^incorrect_passphrase$"):
        Vault.unlock(directory, PASS)


def test_changing_the_passphrase_does_not_re_encrypt_the_database(made):
    """Envelope design: only the keyring changes."""
    directory, _ = made
    before = (directory / DATABASE).read_bytes()
    Vault.unlock(directory, PASS).change_passphrase(PASS, NEW_PASS)
    assert (directory / DATABASE).read_bytes() == before


def test_tampered_database_is_reported_as_corrupt_not_wrong_passphrase(made):
    directory, _ = made
    path = directory / DATABASE
    data = bytearray(path.read_bytes())
    data[100] ^= 0x01  # inside page 1, which SQLCipher reads on open
    path.write_bytes(bytes(data))
    with pytest.raises(VaultError) as info:
        Vault.unlock(directory, PASS)
    assert info.value.code == "vault_corrupt"


@pytest.mark.parametrize("content", ["not json", '{"format": 99}', '{"format": 1}'])
def test_damaged_keyring_is_reported_as_corrupt(made, content):
    directory, _ = made
    (directory / KEYRING).write_text(content, encoding="utf-8")
    with pytest.raises(VaultError, match="^vault_corrupt$"):
        Vault.unlock(directory, PASS)


def test_database_newer_than_the_program_is_refused(made):
    directory, _ = made
    vault = Vault.unlock(directory, PASS)
    with vault.connect() as conn:
        conn.execute(f"PRAGMA user_version = {schema.LATEST + 1}")
    with pytest.raises(VaultError, match="^schema_newer_than_program$"):
        Vault.unlock(directory, PASS)


def test_locked_vault_refuses_access(made):
    directory, _ = made
    vault = Vault.unlock(directory, PASS)
    vault.lock()
    assert vault.locked
    with pytest.raises(VaultError, match="^vault_locked$"), vault.connect():
        pass
    with pytest.raises(VaultError, match="^vault_locked$"):
        _ = vault.audio_key


def test_failed_create_leaves_nothing_behind(tmp_path, monkeypatch):
    def boom(conn):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(schema, "migrate", boom)
    with pytest.raises(RuntimeError):
        Vault.create(tmp_path / "v", PASS, kdf=TEST_KDF)
    assert not (tmp_path / "v" / DATABASE).exists()
    assert not (tmp_path / "v" / KEYRING).exists()


def test_every_connection_is_closed_so_windows_can_delete_the_folder(made):
    """Windows cannot delete a file with an open handle. Remove the whole vault after use,
    including after a failed statement, with the cyclic garbage collector off."""
    import gc
    import shutil

    directory, _ = made
    gc.disable()
    try:
        vault = Vault.unlock(directory, PASS)
        _probe(vault)
        with pytest.raises(dbapi2.OperationalError), vault.connect() as conn:
            conn.execute("SELECT * FROM no_such_table")
        shutil.rmtree(directory)  # raises PermissionError on Windows if a handle leaked
    finally:
        gc.enable()
    assert not directory.exists()


# ----- passphrase policy (ADR-003) -----
@pytest.mark.parametrize(
    "weak",
    [
        "",
        "short",
        "elevenchars",  # 11
        "   elevenchars   ",  # spaces around do not count
        "aaaaaaaaaaaaaaaa",
        "Password1234",
        "CLINASSIST123",
        "x" * 257,
    ],
    ids=["empty", "short", "eleven", "padded", "repeated", "common", "common_upper", "too_long"],
)
def test_weak_passphrases_are_refused(tmp_path, weak):
    with pytest.raises(VaultError, match="^weak_passphrase$"):
        Vault.create(tmp_path / "v", weak, kdf=TEST_KDF)
    assert not (tmp_path / "v" / KEYRING).exists()


@pytest.mark.parametrize(
    "ok", ["twelve chars", "correct horse battery staple", "Kibera-clinic-2026!"]
)
def test_reasonable_passphrases_are_accepted(tmp_path, ok):
    Vault.create(tmp_path / "v", ok, kdf=TEST_KDF)


def test_policy_also_applies_to_change_and_recovery(made):
    directory, code = made
    vault = Vault.unlock(directory, PASS)
    with pytest.raises(VaultError, match="^weak_passphrase$"):
        vault.change_passphrase(PASS, "short")
    with pytest.raises(VaultError, match="^weak_passphrase$"):
        Vault.recover(directory, code, "short")
    assert _probe(Vault.unlock(directory, PASS)) == MARKER  # nothing changed
