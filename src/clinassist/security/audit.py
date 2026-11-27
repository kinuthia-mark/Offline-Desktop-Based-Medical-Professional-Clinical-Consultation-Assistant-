"""Tamper-evident audit log (FR-09): implements the Auditor port as a SHA-256 hash chain.

Each entry stores the hash of the previous entry, and its own hash covers its fields plus that
previous hash:

    entry_hash(n) = SHA-256( prev_hash(n) | seq | ts | event | session_id | user_id )
    prev_hash(n)  = entry_hash(n-1),   prev_hash(1) = 64 zeros

Editing, deleting or reordering an entry in the middle breaks the chain, and `verify` names the
first bad entry. Deleting the LAST entries leaves a shorter chain that is still valid; that can
only be detected against a copy of the head kept elsewhere (an external anchor), so `head()` is
exposed for printing or writing down, for example at the end of each day.

Events carry names and ids only. They are checked against a strict pattern so that free text,
and with it transcript or note content, cannot be written into the log by mistake.
"""

# This file is the audit log: a record of who did what (events like logins and note saves).
# Each entry is chained to the one before by a hash, so tampering shows up when verify() runs.
# It writes into the vault database, and other parts of the app call record() to log events.
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from clinassist.security.vault import Vault

# The "previous hash" of the very first entry, since there is nothing before it.
# 64 zeros is the same length as a SHA-256 hex digest, so the first entry fits the same rules.
GENESIS = "0" * 64
# Allowed shapes: event names like "transcript_approved"; ids of letters, digits, "_" and "-".
# A sentence has spaces and capitals, so it cannot match either pattern.
_EVENT = re.compile(r"[a-z][a-z0-9_]{0,47}")
_ID = re.compile(r"[A-Za-z0-9_-]{0,64}")


# Raised when an event or id is rejected. The code is a short stable word, not free text.
class AuditError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        # Kept as an attribute so callers can check the code without parsing the message.
        self.code = code


# frozen=True makes the object read-only, so a saved head cannot be changed by accident.
@dataclass(frozen=True)
class ChainHead:
    """What to keep outside the database to detect deletion of the newest entries."""

    count: int
    entry_hash: str


@dataclass(frozen=True)
class Verification:
    ok: bool
    checked: int
    first_bad_seq: int | None = None
    problem: str = ""  # hash_mismatch | broken_link | sequence_gap | head_mismatch


# Computes one entry's hash. Used both when writing an entry and when verify re-checks it.
def entry_hash(prev: str, seq: int, ts: str, event: str, session_id: str, user_id: str | None):
    # The order of this list is part of the hash, so it must never change after release.
    fields = [prev, seq, ts, event, session_id, user_id]
    # JSON gives an unambiguous encoding: no field can bleed into the next.
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode("utf-8")).hexdigest()


# Writes and checks the audit log. It uses the vault, so the log is encrypted with the rest.
class HashChainAuditor:
    # The clock is passed in so tests can use a fixed time. UTC avoids time zone confusion.
    def __init__(self, vault: Vault, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._vault = vault
        self._clock = clock

    # Adds one entry to the end of the chain. Nothing else is allowed to write to audit_logs.
    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        # fullmatch means the whole text must fit the pattern, not just the start.
        if not _EVENT.fullmatch(event):
            raise AuditError("invalid_event_name")
        # user_id may be None (for example before anyone has logged in), so only check it when
        # given.
        if not _ID.fullmatch(session_id) or (user_id is not None and not _ID.fullmatch(user_id)):
            raise AuditError("invalid_id")
        # Timestamp as text to the millisecond. This exact text is hashed, so it is stored
        # unchanged.
        ts = self._clock().isoformat(timespec="milliseconds")
        # Opens an encrypted database connection for this one operation.
        with self._vault.connect() as conn:
            # BEGIN IMMEDIATE takes the write lock before reading the head, so two writers
            # cannot both append after the same entry.
            # Turns off Python's automatic transactions so the BEGIN IMMEDIATE below is the only
            # one.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT seq, entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                # The new entry gets the next number and points at the newest entry's hash.
                seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
                conn.execute(
                    "INSERT INTO audit_logs (seq, ts, event, session_id, user_id, prev_hash,"
                    " entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        seq,
                        ts,
                        event,
                        session_id,
                        user_id,
                        prev,
                        entry_hash(prev, seq, ts, event, session_id, user_id),
                    ),
                )
                # Save the new entry. Only reached if the insert worked.
                conn.execute("COMMIT")
            except Exception:
                # If anything failed, drop the half-written entry so the chain is not left broken.
                conn.execute("ROLLBACK")
                raise

    # Returns the count and hash of the newest entry, for the user to note down as an anchor.
    def head(self) -> ChainHead:
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT seq, entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        # An empty log has a head of count 0 and the genesis hash.
        return ChainHead(row[0], row[1]) if row else ChainHead(0, GENESIS)

    def verify(self, anchor: ChainHead | None = None) -> Verification:
        """Walk the whole chain. With an `anchor` from earlier, also detect that entries up to
        that point were removed from the end or replaced."""
        with self._vault.connect() as conn:
            rows = conn.execute(
                "SELECT seq, ts, event, session_id, user_id, prev_hash, entry_hash"
                " FROM audit_logs ORDER BY seq"
            ).fetchall()
        # Start state: the first entry must be number 1 and must point at the genesis hash.
        prev, expected_seq = GENESIS, 1
        # Remembers each entry's hash by number, so the anchor can be compared at the end.
        hashes: dict[int, str] = {}
        # Walk from the first entry to the last, checking three things at each step:
        # the numbers run 1, 2, 3 with no gaps (catches deleted entries);
        # each entry points at the hash of the one before (catches reordering and forgeries);
        # each entry's own hash matches its contents (catches edits).
        for seq, ts, event, session_id, user_id, prev_hash, stored in rows:
            if seq != expected_seq:
                # Report the number that should have been there but is missing.
                return Verification(False, len(hashes), expected_seq, "sequence_gap")
            if prev_hash != prev:
                return Verification(False, len(hashes), seq, "broken_link")
            if entry_hash(prev_hash, seq, ts, event, session_id, user_id) != stored:
                return Verification(False, len(hashes), seq, "hash_mismatch")
            # This entry passed, so keep its hash and move on to the next one.
            hashes[seq] = stored
            # The next entry must point at this hash and have the next number.
            prev, expected_seq = stored, seq + 1
        if (
            # The anchor check is optional. Without an earlier copy there is nothing to compare.
            anchor is not None
            and anchor.count > 0
            and hashes.get(anchor.count) != anchor.entry_hash
        ):
            # The entry at the anchor's position is not the one noted earlier, so history was
            # replaced.
            return Verification(False, len(hashes), anchor.count, "head_mismatch")
        # Every check passed. len(hashes) is the number of entries verified.
        return Verification(True, len(hashes))

    # limit stops the admin screen loading a huge log at once.
    def events(self, limit: int = 200) -> list[tuple[int, str, str, str, str | None]]:
        """Newest first: (seq, ts, event, session_id, user_id). For the admin view."""
        with self._vault.connect() as conn:
            return conn.execute(
                "SELECT seq, ts, event, session_id, user_id FROM audit_logs"
                " ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
