"""User accounts and login (FR-08): Argon2id password hashes, roles, lockout and idle timeout.

Two layers of access, in this order:
  1. The vault passphrase unlocks the encrypted database on this PC (ADR-003).
  2. Each person then logs in with their own account, so every audit entry names a person.

Login failures all report `invalid_credentials`, whether the username exists or not, and an
unknown username still costs one hash check, so neither the message nor the timing reveals which
usernames exist. Audit events record user ids only, never the username or password typed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from clinassist.ports import Auditor, NullAuditor
from clinassist.security.vault import Vault, VaultError, check_passphrase

ROLES = ("clinician", "admin")
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
IDLE_TIMEOUT = timedelta(minutes=10)
NO_SESSION = ""  # audit events about accounts are not tied to a consultation

# Same Argon2id cost as the vault (ADR-003). argon2-cffi stores the settings in each hash.
DEFAULT_HASHER = PasswordHasher(time_cost=3, memory_cost=131072, parallelism=2)


class AuthError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class UserSession:
    """A logged-in person. `touch` on every action; `expired` after IDLE_TIMEOUT of inactivity."""

    user_id: str
    username: str
    display_name: str
    role: str
    last_active: datetime
    ended: bool = field(default=False)
    # Set after an administrator reset the password: the user must choose a new one before
    # doing anything else.
    must_change_password: bool = field(default=False)

    def expired(self, now: datetime, idle: timedelta = IDLE_TIMEOUT) -> bool:
        return self.ended or now - self.last_active >= idle


class AuthService:
    def __init__(
        self,
        vault: Vault,
        auditor: Auditor | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        hasher: PasswordHasher = DEFAULT_HASHER,
        idle_timeout: timedelta = IDLE_TIMEOUT,
    ) -> None:
        self._vault = vault
        self._auditor = auditor or NullAuditor()
        self._clock = clock
        self._hasher = hasher
        self._idle = idle_timeout
        # Verified against when the username is unknown, so that path costs the same time.
        self._dummy_hash = hasher.hash("timing-equaliser-not-a-password")

    # ----- accounts -----
    def has_users(self) -> bool:
        with self._vault.connect() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create_first_admin(self, username: str, password: str, display_name: str) -> str:
        """Only allowed while there are no accounts at all (first run)."""
        if self.has_users():
            raise AuthError("setup_already_done")
        user_id = self._insert(username, password, display_name, "admin")
        self._auditor.record("first_admin_created", NO_SESSION, user_id)
        return user_id

    def create_user(
        self, admin: UserSession, username: str, password: str, display_name: str, role: str
    ) -> str:
        self.require(admin, "admin")
        user_id = self._insert(username, password, display_name, role)
        self._auditor.record("user_created", NO_SESSION, admin.user_id)
        return user_id

    def list_users(self, admin: UserSession) -> list[dict]:
        """Accounts for the administrator's screen. Never includes password hashes."""
        self.require(admin, "admin")
        now = self._clock()
        with self._vault.connect() as conn:
            rows = conn.execute(
                "SELECT user_id, username, display_name, role, active, locked_until"
                " FROM users ORDER BY username"
            ).fetchall()
        return [
            {
                "user_id": user_id,
                "username": username,
                "display_name": display,
                "role": role,
                "active": bool(active),
                "locked": bool(locked_until) and now < datetime.fromisoformat(locked_until),
            }
            for user_id, username, display, role, active, locked_until in rows
        ]

    def set_active(self, admin: UserSession, user_id: str, active: bool) -> None:
        self.require(admin, "admin")
        if user_id == admin.user_id and not active:
            raise AuthError("cannot_deactivate_self")
        with self._vault.connect() as conn, conn:
            changed = conn.execute(
                "UPDATE users SET active = ? WHERE user_id = ?", (int(active), user_id)
            ).rowcount
        if not changed:
            raise AuthError("user_not_found")
        self._auditor.record(
            "user_activated" if active else "user_deactivated", NO_SESSION, admin.user_id
        )

    def unlock_account(self, admin: UserSession, user_id: str) -> None:
        self.require(admin, "admin")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
                (user_id,),
            )
        self._auditor.record("account_unlocked", NO_SESSION, admin.user_id)

    def reset_password(self, admin: UserSession, user_id: str, temporary: str) -> None:
        """For a user who forgot their password. The administrator sets a temporary password,
        which also clears any lockout; the user must replace it at their next login, so the
        administrator never knows the password actually in use. An administrator changes their
        own password with change_password, which needs the current one."""
        self.require(admin, "admin")
        if user_id == admin.user_id:
            raise AuthError("cannot_reset_own_password")
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            raise AuthError("user_not_found")
        self._check_policy(temporary)
        if temporary.strip().lower() == row[0].lower():
            raise AuthError("weak_password")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1,"
                " failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
                (self._hasher.hash(temporary), user_id),
            )
        self._auditor.record("password_reset", NO_SESSION, admin.user_id)

    def change_password(self, session: UserSession, old: str, new: str) -> None:
        self.require(session, changing_password=True)  # the one action allowed after a reset
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (session.user_id,)
            ).fetchone()
        if row is None or not self._verify(row[0], old):
            raise AuthError("invalid_credentials")
        self._check_policy(new)
        if new == old:
            raise AuthError("password_unchanged")
        if new.strip().lower() == session.username.lower():
            raise AuthError("weak_password")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                (self._hasher.hash(new), session.user_id),
            )
        session.must_change_password = False
        self._auditor.record("password_changed", NO_SESSION, session.user_id)

    # ----- login -----
    def login(self, username: str, password: str) -> UserSession:
        now = self._clock()
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, role, password_hash, failed_attempts,"
                " locked_until, active, must_change_password FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if row is None:
            self._verify(self._dummy_hash, password)  # same cost as a real check
            self._auditor.record("login_failed", NO_SESSION, None)
            raise AuthError("invalid_credentials")

        user_id, name, display, role, pw_hash, failed, locked_until, active, must_change = row
        # Check 1: is the account locked? While it is, even the right password is refused.
        if locked_until and now < datetime.fromisoformat(locked_until):
            self._auditor.record("login_refused_locked", NO_SESSION, user_id)
            raise AuthError("account_locked")
        # Check 2: the password. A wrong one adds to the failure count; the fifth in a row
        # locks the account for 15 minutes and resets the count.
        if not self._verify(pw_hash, password):
            failed += 1
            lock = failed >= MAX_FAILED_ATTEMPTS
            with self._vault.connect() as conn, conn:
                conn.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE user_id = ?",
                    (
                        0 if lock else failed,
                        (now + LOCKOUT).isoformat() if lock else None,
                        user_id,
                    ),
                )
            self._auditor.record("account_locked" if lock else "login_failed", NO_SESSION, user_id)
            raise AuthError("account_locked" if lock else "invalid_credentials")
        if not active:
            # Checked after the password, so an inactive account is only revealed to its owner.
            self._auditor.record("login_refused_inactive", NO_SESSION, user_id)
            raise AuthError("account_inactive")

        # Success: clear the failure count. If the stored hash was made with weaker settings
        # than today's, replace it now, while we have the password in hand.
        with self._vault.connect() as conn, conn:
            new_hash = self._hasher.hash(password) if self._needs_rehash(pw_hash) else pw_hash
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, password_hash = ?"
                " WHERE user_id = ?",
                (new_hash, user_id),
            )
        self._auditor.record("login_succeeded", NO_SESSION, user_id)
        return UserSession(
            user_id, name, display, role, now, must_change_password=bool(must_change)
        )

    def logout(self, session: UserSession) -> None:
        if not session.ended:
            session.ended = True
            self._auditor.record("logout", NO_SESSION, session.user_id)

    def require(
        self, session: UserSession, role: str | None = None, changing_password: bool = False
    ) -> None:
        """Call before every protected action. Ends an idle session; refuses everything until a
        reset password is replaced; checks the role; refreshes the activity time."""
        now = self._clock()
        if session.expired(now, self._idle):
            if not session.ended:
                session.ended = True
                self._auditor.record("session_timed_out", NO_SESSION, session.user_id)
            raise AuthError("session_expired")
        if session.must_change_password and not changing_password:
            raise AuthError("password_change_required")
        if role is not None and session.role != role:
            self._auditor.record("access_denied", NO_SESSION, session.user_id)
            raise AuthError("forbidden")
        session.last_active = now

    # ----- internals -----
    def _insert(self, username: str, password: str, display_name: str, role: str) -> str:
        from sqlcipher3 import dbapi2

        # Rules for a new account: a known role; a username of 3 to 64 characters with no
        # spaces; a password that passes the same policy as the vault and is not the username.
        username = username.strip()
        if role not in ROLES:
            raise AuthError("invalid_role")
        if not 3 <= len(username) <= 64 or any(ch.isspace() for ch in username):
            raise AuthError("invalid_username")
        self._check_policy(password)
        if password.strip().lower() == username.lower():
            raise AuthError("weak_password")
        user_id = uuid.uuid4().hex
        try:
            with self._vault.connect() as conn, conn:
                conn.execute(
                    "INSERT INTO users (user_id, username, display_name, role, password_hash,"
                    " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        username,
                        display_name.strip(),
                        role,
                        self._hasher.hash(password),
                        self._clock().isoformat(timespec="seconds"),
                    ),
                )
        except dbapi2.IntegrityError:
            raise AuthError("username_taken") from None
        return user_id

    @staticmethod
    def _check_policy(password: str) -> None:
        try:
            check_passphrase(password)  # same rule as the vault passphrase (ADR-003)
        except VaultError:
            raise AuthError("weak_password") from None

    def _verify(self, stored: str, password: str) -> bool:
        # True only for the right password. Any problem with the stored hash counts as a wrong
        # password, never as a crash.
        try:
            return self._hasher.verify(stored, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def _needs_rehash(self, stored: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(stored)
        except InvalidHashError:
            return True
