"""Key handling (ADR-003): Argon2id, envelope wrapping, HKDF sub-keys, recovery codes."""

from __future__ import annotations

import pytest

pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from clinassist.security import crypto  # noqa: E402
from clinassist.security.crypto import TEST_KDF, CryptoError, KdfParams  # noqa: E402

LABEL = b"clinassist/keyring/v1/passphrase"


def test_default_kdf_matches_the_measured_setting():
    """ADR-001 measured t=3, 128 MiB, p=2 at 0.174 s on the reference PC. If the default
    changes, the ADR's timing no longer describes it and must be re-measured."""
    assert KdfParams() == KdfParams(time_cost=3, memory_cost_kib=131072, parallelism=2)


def test_kdf_params_round_trip_through_a_dict():
    params = KdfParams(4, 65536, 1)
    assert KdfParams.from_dict(params.to_dict()) == params


def test_kek_depends_on_secret_salt_and_settings():
    salt = crypto.new_salt()
    base = crypto.derive_kek("correct horse", salt, TEST_KDF)
    assert len(base) == 32
    assert base == crypto.derive_kek("correct horse", salt, TEST_KDF)
    assert base != crypto.derive_kek("correct horsf", salt, TEST_KDF)
    assert base != crypto.derive_kek("correct horse", crypto.new_salt(), TEST_KDF)
    assert base != crypto.derive_kek("correct horse", salt, KdfParams(2, 8192, 1))


def test_wrap_round_trip():
    kek, master = crypto.new_master_key(), crypto.new_master_key()
    assert crypto.unwrap(kek, crypto.wrap(kek, master, LABEL), LABEL) == master


def test_wrap_uses_a_fresh_nonce_each_time():
    kek, master = crypto.new_master_key(), crypto.new_master_key()
    assert crypto.wrap(kek, master, LABEL) != crypto.wrap(kek, master, LABEL)


@pytest.mark.parametrize("change", ["wrong_kek", "wrong_label", "flipped_bit", "truncated"])
def test_unwrap_rejects_anything_altered(change):
    kek, master, label = crypto.new_master_key(), crypto.new_master_key(), LABEL
    blob = crypto.wrap(kek, master, LABEL)
    if change == "wrong_kek":
        kek = crypto.new_master_key()
    elif change == "wrong_label":
        label = b"clinassist/keyring/v1/recovery"
    elif change == "flipped_bit":
        blob = blob[:20] + bytes([blob[20] ^ 1]) + blob[21:]
    else:
        blob = blob[:5]
    with pytest.raises(CryptoError, match="^unwrap_failed$"):
        crypto.unwrap(kek, blob, label)


def test_subkeys_differ_by_purpose_and_from_the_master():
    master = crypto.new_master_key()
    db, audio = crypto.subkey(master, "db"), crypto.subkey(master, "audio")
    assert len(db) == len(audio) == 32
    assert len({db, audio, master}) == 3
    assert db == crypto.subkey(master, "db")


def test_recovery_code_format_and_entropy():
    code = crypto.new_recovery_code()
    groups = code.split("-")
    assert len(groups) == 8 and all(len(g) == 4 for g in groups)
    assert len(crypto.normalize_recovery_code(code)) == 32  # 160 bits in base32
    assert crypto.new_recovery_code() != code


def test_recovery_code_accepts_casual_typing():
    code = crypto.new_recovery_code()
    typed = " " + code.lower().replace("-", " ") + "\n"
    assert crypto.normalize_recovery_code(typed) == crypto.normalize_recovery_code(code)
