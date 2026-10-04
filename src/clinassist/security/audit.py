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

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from clinassist.security.vault import Vault

GENESIS = "0" * 64
_EVENT = re.compile(r"[a-z][a-z0-9_]{0,47}")
_ID = re.compile(r"[A-Za-z0-9_-]{0,64}")


class AuditError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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


def entry_hash(prev: str, seq: int, ts: str, event: str, session_id: str, user_id: str | None):
    fields = [prev, seq, ts, event, session_id, user_id]
    # JSON gives an unambiguous encoding: no field can bleed into the next.
    return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode("utf-8")).hexdigest()


class HashChainAuditor:
    def __init__(self, vault: Vault, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._vault = vault
        self._clock = clock

    def record(self, event: str, session_id: str, user_id: str | None) -> None:
        if not _EVENT.fullmatch(event):
            raise AuditError("invalid_event_name")
        if not _ID.fullmatch(session_id) or (user_id is not None and not _ID.fullmatch(user_id)):
            raise AuditError("invalid_id")
        ts = self._clock().isoformat(timespec="milliseconds")
        with self._vault.connect() as conn:
            # BEGIN IMMEDIATE takes the write lock before reading the head, so two writers
            # cannot both append after the same entry.
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT seq, entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1"
                ).fetchone()
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
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def head(self) -> ChainHead:
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT seq, entry_hash FROM audit_logs ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return ChainHead(row[0], row[1]) if row else ChainHead(0, GENESIS)

    def verify(self, anchor: ChainHead | None = None) -> Verification:
        """Walk the whole chain. With an `anchor` from earlier, also detect that entries up to
        that point were removed from the end or replaced."""
        with self._vault.connect() as conn:
            rows = conn.execute(
                "SELECT seq, ts, event, session_id, user_id, prev_hash, entry_hash"
                " FROM audit_logs ORDER BY seq"
            ).fetchall()
        prev, expected_seq = GENESIS, 1
        hashes: dict[int, str] = {}
        for seq, ts, event, session_id, user_id, prev_hash, stored in rows:
            if seq != expected_seq:
                return Verification(False, len(hashes), expected_seq, "sequence_gap")
            if prev_hash != prev:
                return Verification(False, len(hashes), seq, "broken_link")
            if entry_hash(prev_hash, seq, ts, event, session_id, user_id) != stored:
                return Verification(False, len(hashes), seq, "hash_mismatch")
            hashes[seq] = stored
            prev, expected_seq = stored, seq + 1
        if (
            anchor is not None
            and anchor.count > 0
            and hashes.get(anchor.count) != anchor.entry_hash
        ):
            return Verification(False, len(hashes), anchor.count, "head_mismatch")
        return Verification(True, len(hashes))

    def events(self, limit: int = 200) -> list[tuple[int, str, str, str, str | None]]:
        """Newest first: (seq, ts, event, session_id, user_id). For the admin view."""
        with self._vault.connect() as conn:
            return conn.execute(
                "SELECT seq, ts, event, session_id, user_id FROM audit_logs"
                " ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
