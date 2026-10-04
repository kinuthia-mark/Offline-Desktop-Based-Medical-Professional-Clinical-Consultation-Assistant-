"""Hash-chained audit log (FR-09): edits, deletions and reordering are detected."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from clinassist.security.audit import (  # noqa: E402
    GENESIS,
    AuditError,
    ChainHead,
    HashChainAuditor,
)
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault  # noqa: E402

SECRET = "SECRET-PHI-4471"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def vault(tmp_path):
    v, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    return v


@pytest.fixture
def audit(vault):
    a = HashChainAuditor(vault, clock=Clock())
    for i, event in enumerate(
        ["recording_started", "transcribed", "transcript_approved", "finalized"]
    ):
        a.record(event, "sess-1", None if i == 0 else "user-1")
    return a


def _sql(vault, statement, *params):
    with vault.connect() as conn, conn:
        conn.execute(statement, params)


def test_empty_log_verifies_and_has_genesis_head(vault):
    a = HashChainAuditor(vault)
    assert a.verify().ok
    assert a.head() == ChainHead(0, GENESIS)


def test_intact_chain_verifies(audit):
    result = audit.verify()
    assert result.ok and result.checked == 4
    assert audit.head().count == 4


def test_entries_link_to_the_previous_hash(vault, audit):
    with vault.connect() as conn:
        rows = conn.execute("SELECT prev_hash, entry_hash FROM audit_logs ORDER BY seq").fetchall()
    assert rows[0][0] == GENESIS
    assert all(rows[i][0] == rows[i - 1][1] for i in range(1, len(rows)))


@pytest.mark.parametrize(
    "statement, params",
    [
        ("UPDATE audit_logs SET event = 'session_discarded' WHERE seq = 2", ()),
        ("UPDATE audit_logs SET user_id = 'someone-else' WHERE seq = 3", ()),
        ("UPDATE audit_logs SET ts = '2020-01-01T00:00:00.000+00:00' WHERE seq = 1", ()),
    ],
    ids=["event", "user", "time"],
)
def test_edited_entry_is_detected(vault, audit, statement, params):
    _sql(vault, statement, *params)
    result = audit.verify()
    assert not result.ok and result.problem == "hash_mismatch"


def test_edit_with_recomputed_hash_breaks_the_next_link(vault, audit):
    """An attacker who also rewrites the edited entry's own hash is caught at the next entry."""
    from clinassist.security.audit import entry_hash

    with vault.connect() as conn, conn:
        seq, ts, _, sid, uid, prev, _ = conn.execute(
            "SELECT * FROM audit_logs WHERE seq = 2"
        ).fetchone()
        forged = entry_hash(prev, seq, ts, "session_discarded", sid, uid)
        conn.execute(
            "UPDATE audit_logs SET event = 'session_discarded', entry_hash = ? WHERE seq = 2",
            (forged,),
        )
    result = audit.verify()
    assert not result.ok and result.first_bad_seq == 3 and result.problem == "broken_link"


def test_deleted_middle_entry_is_detected(vault, audit):
    _sql(vault, "DELETE FROM audit_logs WHERE seq = 2")
    result = audit.verify()
    assert not result.ok and result.first_bad_seq == 2 and result.problem == "sequence_gap"


def test_reordered_entries_are_detected(vault, audit):
    with vault.connect() as conn, conn:
        conn.execute("UPDATE audit_logs SET seq = 100 WHERE seq = 2")
        conn.execute("UPDATE audit_logs SET seq = 2 WHERE seq = 3")
        conn.execute("UPDATE audit_logs SET seq = 3 WHERE seq = 100")
    assert not audit.verify().ok


def test_deleting_the_newest_entries_needs_an_anchor(vault, audit):
    """Stated limit: truncation leaves a valid shorter chain. A head kept elsewhere catches it."""
    anchor = audit.head()
    _sql(vault, "DELETE FROM audit_logs WHERE seq = 4")
    assert audit.verify().ok  # undetectable without the anchor
    result = audit.verify(anchor)
    assert not result.ok and result.problem == "head_mismatch"


def test_anchor_still_matches_after_new_entries(audit):
    anchor = audit.head()
    audit.record("logout", "", "user-1")
    assert audit.verify(anchor).ok


@pytest.mark.parametrize(
    "event", ["", "Finalized", "finalized: patient had chest pain", f"note {SECRET}", "x" * 49]
)
def test_free_text_cannot_be_written_as_an_event(audit, event):
    with pytest.raises(AuditError, match="^invalid_event_name$"):
        audit.record(event, "sess-1", "user-1")


@pytest.mark.parametrize("session_id, user_id", [(SECRET + " text", None), ("s1", "dr a; drop")])
def test_ids_must_be_ids(audit, session_id, user_id):
    with pytest.raises(AuditError, match="^invalid_id$"):
        audit.record("finalized", session_id, user_id)


def test_events_newest_first(audit):
    assert [e[2] for e in audit.events(2)] == ["finalized", "transcript_approved"]


def test_controller_writes_to_the_chain(vault):
    """The real controller with the real auditor: every workflow step lands in the chain."""
    from clinassist.controller import ConsultationController
    from clinassist.domain import Draft, GuardVerdict

    class Rec:
        def start(self): ...
        def stop(self):
            return b""

    class Asr:
        def transcribe(self, audio):
            return SECRET

    class Guard:
        def check(self, text):
            return GuardVerdict(False, clean_text=text)

    class Gen:
        def generate(self, text, attempt):
            return Draft("s", "o", "p")

    class Store:
        def save(self, record): ...

    a = HashChainAuditor(vault)
    c = ConsultationController(Rec(), Asr(), Guard(), Gen(), Store(), a, id_factory=lambda: "s9")
    c.start_recording()
    c.stop_recording()
    c.approve_transcript("approved", "user-1")
    c.generate_draft()
    c.discard()
    assert [e[2] for e in reversed(a.events())] == [
        "recording_started",
        "transcribed",
        "transcript_approved",
        "draft_generated",
        "session_discarded",
    ]
    assert a.verify().ok
    with vault.connect() as conn:
        dump = " ".join(str(r) for r in conn.execute("SELECT * FROM audit_logs"))
    assert SECRET not in dump
