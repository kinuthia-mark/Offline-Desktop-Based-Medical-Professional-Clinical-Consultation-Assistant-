"""Optional encrypted audio (ADR-003): off by default, bound to its session, tamper-evident."""

from __future__ import annotations

import secrets

import pytest

pytest.importorskip("cryptography")

from clinassist.adapters.audio_store import AudioStoreError, EncryptedAudioStore  # noqa: E402

AUDIO = b"RIFF" + secrets.token_bytes(64_000)  # random bytes standing in for a recording


@pytest.fixture
def key():
    return secrets.token_bytes(32)


def test_retention_is_off_by_default_and_keeps_nothing(tmp_path, key):
    store = EncryptedAudioStore(tmp_path / "audio", key)
    assert store.enabled is False
    assert store.save("s1", AUDIO) is None
    assert not (tmp_path / "audio").exists()


def test_round_trip_when_enabled(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    path = store.save("s1", AUDIO)
    assert path is not None and path.exists()
    assert store.load("s1") == AUDIO


def test_file_holds_no_plaintext(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    raw = store.save("s1", AUDIO).read_bytes()
    assert AUDIO[:4096] not in raw
    assert b"RIFF" not in raw


def test_file_renamed_to_another_session_fails(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    store.save("s1", AUDIO).rename(tmp_path / "s2.caud")
    with pytest.raises(AudioStoreError, match="^audio_corrupt$"):
        store.load("s2")


def test_flipped_bit_and_wrong_key_are_detected(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    path = store.save("s1", AUDIO)
    with pytest.raises(AudioStoreError, match="^audio_corrupt$"):
        EncryptedAudioStore(tmp_path, secrets.token_bytes(32)).load("s1")
    data = bytearray(path.read_bytes())
    data[-10] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(AudioStoreError, match="^audio_corrupt$"):
        store.load("s1")


def test_existing_recording_is_not_overwritten(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    store.save("s1", AUDIO)
    with pytest.raises(AudioStoreError, match="^audio_exists$"):
        store.save("s1", b"other")
    assert store.load("s1") == AUDIO


@pytest.mark.parametrize("bad", ["../escape", "a/b", "c:\\x", "", "x" * 65])
def test_session_id_cannot_escape_the_folder(tmp_path, key, bad):
    store = EncryptedAudioStore(tmp_path / "audio", key, enabled=True)
    with pytest.raises(AudioStoreError, match="^invalid_session_id$"):
        store.save(bad, AUDIO)


def test_delete(tmp_path, key):
    store = EncryptedAudioStore(tmp_path, key, enabled=True)
    store.save("s1", AUDIO)
    assert store.delete("s1") is True
    assert store.delete("s1") is False
    with pytest.raises(AudioStoreError, match="^audio_not_found$"):
        store.load("s1")


def test_uses_the_vault_audio_key(tmp_path):
    pytest.importorskip("sqlcipher3")
    pytest.importorskip("argon2")
    from clinassist.security.crypto import TEST_KDF
    from clinassist.security.vault import Vault

    vault, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    store = EncryptedAudioStore(tmp_path / "v" / "audio", vault.audio_key, enabled=True)
    store.save("s1", AUDIO)
    reopened = Vault.unlock(tmp_path / "v", "a long synthetic passphrase 42")
    assert EncryptedAudioStore(tmp_path / "v" / "audio", reopened.audio_key).load("s1") == AUDIO
