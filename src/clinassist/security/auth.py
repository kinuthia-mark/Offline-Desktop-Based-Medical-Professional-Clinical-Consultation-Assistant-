"""User accounts and login (FR-08): Argon2id password hashes, roles, lockout and idle timeout.

Two layers of access, in this order:
  1. The vault passphrase unlocks the encrypted database on this PC (ADR-003).
  2. Each person then logs in with their own account, so every audit entry names a person.

Login failures all report `invalid_credentials`, whether the username exists or not, and an
unknown username still costs one hash check, so neither the message nor the timing reveals which
usernames exist. Audit events record user ids only, never the username or password typed.
"""

# This file handles the people who use the app: creating accounts, logging in, locking an account
# after too many wrong passwords, ending idle sessions and checking roles (clinician or admin).
# Accounts live in the encrypted vault. Events are sent to the audit log through the Auditor.
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from clinassist.domain import ADMIN, ROLES
from clinassist.ports import Auditor, NullAuditor
from clinassist.security.vault import Vault, VaultError, check_passphrase

# Limits for the lockout rule: 5 wrong passwords lock the account for 15 minutes.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
# A session with no activity for 10 minutes ends, so a walk-away does not leave it open.
IDLE_TIMEOUT = timedelta(minutes=10)
NO_SESSION = ""  # audit events about accounts are not tied to a consultation

# Same Argon2id cost as the vault (ADR-003). argon2-cffi stores the settings in each hash.
DEFAULT_HASHER = PasswordHasher(time_cost=3, memory_cost=131072, parallelism=2)


# Raised for any login or account problem. The code is a stable word the screens can show.
class AuthError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Plain data holder for the logged-in person. It is created at login and passed to every action.
@dataclass
class UserSession:
    """A logged-in person. `touch` on every action; `expired` after IDLE_TIMEOUT of inactivity."""

    user_id: str
    username: str
    display_name: str
    role: str
    # Time of the last action. The idle timeout is measured from this.
    last_active: datetime
    ended: bool = field(default=False)
    # Set after an administrator reset the password: the user must choose a new one before
    # doing anything else.
    must_change_password: bool = field(default=False)

    # True if the person logged out, or has been idle for too long.
    def expired(self, now: datetime, idle: timedelta = IDLE_TIMEOUT) -> bool:
        return self.ended or now - self.last_active >= idle


# All account and login rules in one place. It uses the vault for storage and the auditor for the
# log.
class AuthService:
    def __init__(
        self,
        vault: Vault,
        # Optional, so tests can run without an audit log.
        auditor: Auditor | None = None,
        # The clock is passed in so tests can fake the time (for lockout and timeout).
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        hasher: PasswordHasher = DEFAULT_HASHER,
        idle_timeout: timedelta = IDLE_TIMEOUT,
    ) -> None:
        self._vault = vault
        # NullAuditor does nothing, so the code never has to check for None.
        self._auditor = auditor or NullAuditor()
        self._clock = clock
        self._hasher = hasher
        self._idle = idle_timeout
        # Verified against when the username is unknown, so that path costs the same time.
        # A made-up hash. Checking against it takes as long as a real check.
        self._dummy_hash = hasher.hash("timing-equaliser-not-a-password")

    # ----- accounts -----
    # Used on first run to decide whether to show the create-admin screen or the login screen.
    def has_users(self) -> bool:
        with self._vault.connect() as conn:
            # Fetch one row at most. If there is any row, at least one account exists.
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    # Returns the new account's id.
    def create_first_admin(self, username: str, password: str, display_name: str) -> str:
        """The first account, a system administrator, who then creates everyone else. Only
        allowed while there are no accounts at all (first run)."""
        if self.has_users():
            raise AuthError("setup_already_done")
        # _insert checks the rules and saves the account with a hashed password.
        user_id = self._insert(username, password, display_name, ADMIN)
        self._auditor.record("first_admin_created", NO_SESSION, user_id)
        return user_id

    # Admin creates a clinician or another admin.
    def create_user(
        self, admin: UserSession, username: str, password: str, display_name: str, role: str
    ) -> str:
        # Check the caller is a logged-in admin. Raises forbidden otherwise.
        self.require(admin, ADMIN)
        user_id = self._insert(username, password, display_name, role)
        self._auditor.record("user_created", NO_SESSION, admin.user_id)
        return user_id

    # The admin's user list. The locked flag is worked out from the lock time.
    def list_users(self, admin: UserSession) -> list[dict]:
        """Accounts for the administrator's screen. Never includes password hashes."""
        self.require(admin, ADMIN)
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
                # Locked only if a lock time exists and it is still in the future.
                "locked": bool(locked_until) and now < datetime.fromisoformat(locked_until),
            }
            for user_id, username, display, role, active, locked_until in rows
        ]

    # Deactivating blocks login but keeps the account, so past audit entries still make sense.
    def set_active(self, admin: UserSession, user_id: str, active: bool) -> None:
        self.require(admin, ADMIN)
        if user_id == admin.user_id and not active:
            # Stops an admin locking themselves out of the only admin account.
            raise AuthError("cannot_deactivate_self")
        # The second conn is a transaction: it commits if the block works and rolls back if it
        # fails.
        with self._vault.connect() as conn, conn:
            # rowcount is how many rows the UPDATE changed. Zero means no such user.
            changed = conn.execute(
                "UPDATE users SET active = ? WHERE user_id = ?", (int(active), user_id)
            ).rowcount
        if not changed:
            raise AuthError("user_not_found")
        self._auditor.record(
            "user_activated" if active else "user_deactivated", NO_SESSION, admin.user_id
        )

    # Lets an admin clear a lockout without waiting 15 minutes.
    def unlock_account(self, admin: UserSession, user_id: str) -> None:
        self.require(admin, ADMIN)
        with self._vault.connect() as conn, conn:
            changed = conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
                (user_id,),
            ).rowcount
        if not changed:
            raise AuthError("user_not_found")
        self._auditor.record("account_unlocked", NO_SESSION, admin.user_id)

    # Sets must_change_password so the temporary one is replaced at next login.
    def reset_password(self, admin: UserSession, user_id: str, temporary: str) -> None:
        """For a user who forgot their password. The administrator sets a temporary password,
        which also clears any lockout; the user must replace it at their next login, so the
        administrator never knows the password actually in use. An administrator changes their
        own password with change_password, which needs the current one."""
        self.require(admin, ADMIN)
        if user_id == admin.user_id:
            # An admin must use change_password for their own account, which needs the old password.
            raise AuthError("cannot_reset_own_password")
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            raise AuthError("user_not_found")
        # The temporary password must pass the same strength rule as any other.
        self._check_policy(temporary)
        # A password equal to the username is too easy to guess.
        if temporary.strip().lower() == row[0].lower():
            raise AuthError("weak_password")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 1,"
                " failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
                (self._hasher.hash(temporary), user_id),
            )
        self._auditor.record("password_reset", NO_SESSION, admin.user_id)

    # The way back in when nobody is left who can reset the password.
    def recover_password(self, username: str, recovery_code: str, new: str) -> None:
        """ "Forgot password" on the login screen, for when no other administrator can reset it
        (for example the only administrator forgot theirs). Needs the vault's recovery code,
        printed when the vault was created. Whoever holds that code can already open the whole
        vault, so it may also set a login password. Clears any lockout; no forced change
        afterwards, since the user chose this password themselves."""
        if not self._vault.recovery_code_matches(recovery_code):
            # Log the failed try. No user id, because the code is not tied to a person.
            self._auditor.record("password_recovery_failed", NO_SESSION, None)
            raise AuthError("incorrect_recovery_code")
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username FROM users WHERE username = ?", (username.strip(),)
            ).fetchone()
        if row is None:
            raise AuthError("user_not_found")
        # Unpack the row into the id and the username.
        user_id, name = row
        self._check_policy(new)
        if new.strip().lower() == name.lower():
            raise AuthError("weak_password")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0,"
                " failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
                (self._hasher.hash(new), user_id),
            )
        self._auditor.record("password_recovered", NO_SESSION, user_id)

    # A logged-in user changes their own password. The old one is required as proof.
    def change_password(self, session: UserSession, old: str, new: str) -> None:
        self.require(session, changing_password=True)  # the one action allowed after a reset
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (session.user_id,)
            ).fetchone()
        # Same error whether the old password is wrong or the account is missing.
        if row is None or not self._verify(row[0], old):
            # The same message for unknown user and wrong password, so usernames are not revealed.
            raise AuthError("invalid_credentials")
        self._check_policy(new)
        # Reusing the old password would make the change pointless.
        if new == old:
            raise AuthError("password_unchanged")
        if new.strip().lower() == session.username.lower():
            raise AuthError("weak_password")
        with self._vault.connect() as conn, conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
                (self._hasher.hash(new), session.user_id),
            )
        # Update the live session too, so the user can carry on without logging in again.
        session.must_change_password = False
        self._auditor.record("password_changed", NO_SESSION, session.user_id)

    # Looks up a person's name from their id, since the database stores only the id.
    def display_name(self, session: UserSession, user_id: str) -> str:
        """The full name of an account, for example to print who finalized a note."""
        self.require(session)
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT display_name, username FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return "unknown account"
        # Use the display name, or the username if the display name is empty.
        return row[0] or row[1]

    # ----- login -----
    # Checks the username and password and returns a session. The order of checks matters.
    def login(self, username: str, password: str) -> UserSession:
        now = self._clock()
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, role, password_hash, failed_attempts,"
                " locked_until, active, must_change_password FROM users WHERE username = ?",
                # strip removes stray spaces typed before or after the username.
                (username.strip(),),
            ).fetchone()
        if row is None:
            # Wasted work on purpose: it makes an unknown username take as long as a known one.
            self._verify(self._dummy_hash, password)  # same cost as a real check
            self._auditor.record("login_failed", NO_SESSION, None)
            raise AuthError("invalid_credentials")

        # Unpack the database row into named values.
        user_id, name, display, role, pw_hash, failed, locked_until, active, must_change = row
        # Check 1: is the account locked? While it is, even the right password is refused.
        if locked_until and now < datetime.fromisoformat(locked_until):
            self._auditor.record("login_refused_locked", NO_SESSION, user_id)
            raise AuthError("account_locked")
        # Check 2: the password. A wrong one adds to the failure count; the fifth in a row
        # locks the account for 15 minutes and resets the count.
        if not self._verify(pw_hash, password):
            # Count this wrong password.
            failed += 1
            # True when this was the fifth wrong password in a row.
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
        # An admin turned this account off.
        if not active:
            # Checked after the password, so an inactive account is only revealed to its owner.
            self._auditor.record("login_refused_inactive", NO_SESSION, user_id)
            raise AuthError("account_inactive")

        # Success: clear the failure count. If the stored hash was made with weaker settings
        # than today's, replace it now, while we have the password in hand.
        with self._vault.connect() as conn, conn:
            # Only re-hash when needed, because hashing is slow on purpose.
            new_hash = self._hasher.hash(password) if self._needs_rehash(pw_hash) else pw_hash
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL, password_hash = ?"
                " WHERE user_id = ?",
                (new_hash, user_id),
            )
        self._auditor.record("login_succeeded", NO_SESSION, user_id)
        # Time of login is the first activity time.
        return UserSession(
            user_id, name, display, role, now, must_change_password=bool(must_change)
        )

    # Ends the session. The check makes a second logout do nothing, so it is logged once.
    def logout(self, session: UserSession) -> None:
        if not session.ended:
            session.ended = True
            self._auditor.record("logout", NO_SESSION, session.user_id)

    # The gate every protected action passes through, so no screen can skip these checks.
    def require(
        self, session: UserSession, role: str | None = None, changing_password: bool = False
    ) -> None:
        """Call before every protected action. Ends an idle session; refuses everything until a
        reset password is replaced; checks the role; refreshes the activity time."""
        now = self._clock()
        # Idle too long, or already logged out.
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
        # The action is allowed, so the idle timer starts again.
        session.last_active = now

    # ----- internals -----
    # Shared by create_first_admin and create_user. Checks the rules, then saves the account.
    def _insert(self, username: str, password: str, display_name: str, role: str) -> str:
        # Imported here to use its IntegrityError, raised when the username already exists.
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
        # A random id. Audit entries use this id, not the name.
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
                        # Only the Argon2id hash is stored, never the password itself.
                        self._hasher.hash(password),
                        self._clock().isoformat(timespec="seconds"),
                    ),
                )
        # The username column is UNIQUE, so the database itself rejects a duplicate.
        except dbapi2.IntegrityError:
            raise AuthError("username_taken") from None
        return user_id

    # Needs no self, because it only checks the password text.
    @staticmethod
    # Reuses the vault passphrase rule and turns its error into an auth error.
    def _check_policy(password: str) -> None:
        try:
            check_passphrase(password)  # same rule as the vault passphrase (ADR-003)
        except VaultError:
            raise AuthError("weak_password") from None

    # Wrapper around the Argon2 check that returns True or False instead of raising.
    def _verify(self, stored: str, password: str) -> bool:
        # True only for the right password. Any problem with the stored hash counts as a wrong
        # password, never as a crash.
        try:
            return self._hasher.verify(stored, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # True if the stored hash used older, weaker settings than the current ones.
    def _needs_rehash(self, stored: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(stored)
        except InvalidHashError:
            # A hash that cannot be read is replaced at the next successful login.
            return True
