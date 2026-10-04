"""Accounts and login (FR-08): roles, lockout, idle timeout, no username enumeration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from argon2 import PasswordHasher  # noqa: E402

from clinassist.security.audit import HashChainAuditor  # noqa: E402
from clinassist.security.auth import (  # noqa: E402
    IDLE_TIMEOUT,
    LOCKOUT,
    MAX_FAILED_ATTEMPTS,
    AuthError,
    AuthService,
)
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault  # noqa: E402

FAST = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
ADMIN_PW = "admin synthetic password 1"
DOC_PW = "doctor synthetic password 2"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def rig(tmp_path):
    vault, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    clock = Clock()
    audit = HashChainAuditor(vault, clock=clock)
    auth = AuthService(vault, audit, clock=clock, hasher=FAST)
    auth.create_first_admin("admin", ADMIN_PW, "Synthetic Admin")
    admin = auth.login("admin", ADMIN_PW)
    doc_id = auth.create_user(admin, "dr.wanjiru", DOC_PW, "Dr Synthetic", "clinician")
    return auth, admin, doc_id, clock, audit, vault


def _events(audit) -> list[str]:
    return [e[2] for e in reversed(audit.events())]


def test_first_admin_only_once(rig):
    auth = rig[0]
    with pytest.raises(AuthError, match="^setup_already_done$"):
        auth.create_first_admin("second", ADMIN_PW, "x")


def test_login_returns_a_session_with_role(rig):
    auth, *_ = rig
    s = auth.login("dr.wanjiru", DOC_PW)
    assert (s.username, s.role) == ("dr.wanjiru", "clinician")


def test_username_is_case_insensitive_and_unique(rig):
    auth, admin, *_ = rig
    assert auth.login("DR.WANJIRU", DOC_PW).username == "dr.wanjiru"
    with pytest.raises(AuthError, match="^username_taken$"):
        auth.create_user(admin, "Dr.Wanjiru", DOC_PW, "dup", "clinician")


def test_passwords_are_stored_as_argon2id_hashes(rig):
    *_, vault = rig
    with vault.connect() as conn:
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM users")]
    assert all(h.startswith("$argon2id$") for h in hashes)
    assert not any(DOC_PW in h or ADMIN_PW in h for h in hashes)


def test_wrong_password_and_unknown_user_look_the_same(rig):
    auth, *_ = rig
    with pytest.raises(AuthError) as wrong:
        auth.login("dr.wanjiru", "not the right password")
    with pytest.raises(AuthError) as unknown:
        auth.login("nobody.here", "not the right password")
    assert wrong.value.code == unknown.value.code == "invalid_credentials"


def test_lockout_after_repeated_failures_then_expiry(rig):
    auth, _, _, clock, audit, _ = rig
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(AuthError, match="^invalid_credentials$"):
            auth.login("dr.wanjiru", "wrong password attempt")
    with pytest.raises(AuthError, match="^account_locked$"):
        auth.login("dr.wanjiru", "wrong password attempt")
    # even the right password is refused while locked
    with pytest.raises(AuthError, match="^account_locked$"):
        auth.login("dr.wanjiru", DOC_PW)
    clock.advance(LOCKOUT)
    assert auth.login("dr.wanjiru", DOC_PW).role == "clinician"
    assert "account_locked" in _events(audit) and "login_refused_locked" in _events(audit)


def test_successful_login_resets_the_failure_count(rig):
    auth, *_ = rig
    for _ in range(MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(AuthError):
            auth.login("dr.wanjiru", "wrong password attempt")
    auth.login("dr.wanjiru", DOC_PW)
    with pytest.raises(AuthError, match="^invalid_credentials$"):
        auth.login("dr.wanjiru", "wrong password attempt")  # counter started again


def test_admin_can_unlock_an_account(rig):
    auth, admin, doc_id, *_ = rig
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthError):
            auth.login("dr.wanjiru", "wrong password attempt")
    auth.unlock_account(admin, doc_id)
    assert auth.login("dr.wanjiru", DOC_PW)


def test_idle_session_expires(rig):
    auth, _, _, clock, audit, _ = rig
    s = auth.login("dr.wanjiru", DOC_PW)
    clock.advance(IDLE_TIMEOUT - timedelta(seconds=1))
    auth.require(s)  # activity refreshes the timer
    clock.advance(IDLE_TIMEOUT - timedelta(seconds=1))
    auth.require(s)
    clock.advance(IDLE_TIMEOUT)
    with pytest.raises(AuthError, match="^session_expired$"):
        auth.require(s)
    with pytest.raises(AuthError, match="^session_expired$"):
        auth.require(s)  # stays expired
    assert _events(audit).count("session_timed_out") == 1


def test_logout_ends_the_session(rig):
    auth, *_ = rig
    s = auth.login("dr.wanjiru", DOC_PW)
    auth.logout(s)
    with pytest.raises(AuthError, match="^session_expired$"):
        auth.require(s)


def test_clinician_cannot_do_admin_actions(rig):
    auth, _, _, _, audit, _ = rig
    doc = auth.login("dr.wanjiru", DOC_PW)
    with pytest.raises(AuthError, match="^forbidden$"):
        auth.create_user(doc, "intruder", DOC_PW, "x", "admin")
    assert "access_denied" in _events(audit)


def test_deactivated_user_cannot_log_in(rig):
    auth, admin, doc_id, *_ = rig
    auth.set_active(admin, doc_id, False)
    with pytest.raises(AuthError, match="^account_inactive$"):
        auth.login("dr.wanjiru", DOC_PW)
    with pytest.raises(AuthError, match="^invalid_credentials$"):
        auth.login("dr.wanjiru", "wrong password attempt")  # not revealed to a guesser
    auth.set_active(admin, doc_id, True)
    assert auth.login("dr.wanjiru", DOC_PW)


def test_admin_cannot_deactivate_themselves(rig):
    auth, admin, *_ = rig
    with pytest.raises(AuthError, match="^cannot_deactivate_self$"):
        auth.set_active(admin, admin.user_id, False)


@pytest.mark.parametrize(
    "username, password, role, code",
    [
        ("ok.user", "short", "clinician", "weak_password"),
        ("long.username.x", "long.username.x", "clinician", "weak_password"),
        ("a b", DOC_PW, "clinician", "invalid_username"),
        ("ab", DOC_PW, "clinician", "invalid_username"),
        ("ok.user", DOC_PW, "superuser", "invalid_role"),
    ],
)
def test_account_rules(rig, username, password, role, code):
    auth, admin, *_ = rig
    with pytest.raises(AuthError) as info:
        auth.create_user(admin, username, password, "x", role)
    assert info.value.code == code


def test_change_password(rig):
    auth, *_ = rig
    s = auth.login("dr.wanjiru", DOC_PW)
    with pytest.raises(AuthError, match="^invalid_credentials$"):
        auth.change_password(s, "not the old one at all", "a brand new password 3")
    auth.change_password(s, DOC_PW, "a brand new password 3")
    assert auth.login("dr.wanjiru", "a brand new password 3")
    with pytest.raises(AuthError):
        auth.login("dr.wanjiru", DOC_PW)


def test_weaker_old_hash_is_upgraded_on_login(tmp_path):
    vault, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    weak = AuthService(vault, hasher=FAST)
    weak.create_first_admin("admin", ADMIN_PW, "x")
    stronger = PasswordHasher(time_cost=2, memory_cost=8192, parallelism=1)
    AuthService(vault, hasher=stronger).login("admin", ADMIN_PW)
    with vault.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "t=2" in stored


def test_audit_never_records_typed_usernames_or_passwords(rig):
    auth, *_, audit, vault = rig
    with pytest.raises(AuthError):
        auth.login("SECRET-NAME-77", "SECRET-PASSWORD-77")
    with vault.connect() as conn:
        dump = " ".join(str(r) for r in conn.execute("SELECT * FROM audit_logs"))
    assert "SECRET-NAME-77" not in dump and "SECRET-PASSWORD-77" not in dump
    assert audit.verify().ok


def test_v1_vault_upgrades_to_v2_keeping_sessions(tmp_path, monkeypatch):
    """A vault made before this branch gains the new tables and keeps its data."""
    from clinassist.security import schema

    monkeypatch.setattr(schema, "LATEST", 1)
    vault, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    with vault.connect() as conn:
        assert schema.current_version(conn) == 1
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "users" not in tables
    monkeypatch.setattr(schema, "LATEST", len(schema.MIGRATIONS))
    reopened = Vault.unlock(tmp_path / "v", "a long synthetic passphrase 42")
    with reopened.connect() as conn:
        assert schema.current_version(conn) == 2
    assert not AuthService(reopened, hasher=FAST).has_users()


def test_admin_can_list_accounts_without_password_hashes(rig):
    auth, admin, doc_id, *_ = rig
    users = auth.list_users(admin)
    assert [u["username"] for u in users] == ["admin", "dr.wanjiru"]
    assert all("password" not in str(u) and "argon2" not in str(u) for u in users)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthError):
            auth.login("dr.wanjiru", "wrong password attempt")
    doctor = next(u for u in auth.list_users(admin) if u["user_id"] == doc_id)
    assert doctor["locked"] and doctor["active"] and doctor["role"] == "clinician"


def test_clinician_cannot_list_accounts(rig):
    auth, *_ = rig
    with pytest.raises(AuthError, match="^forbidden$"):
        auth.list_users(auth.login("dr.wanjiru", DOC_PW))
