"""Session store and schema (FR-07, FR-12, FR-14, FR-15): transactional saves, round trip,
database-level gates, and no PHI in errors."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from sqlcipher3 import dbapi2  # noqa: E402

from clinassist.adapters.store import StoreError, VaultSessionStore  # noqa: E402
from clinassist.controller import ConsultationController, State  # noqa: E402
from clinassist.domain import (  # noqa: E402
    AiSuggestion,
    Draft,
    GuardVerdict,
    HistoryChecklist,
    SessionRecord,
    SoapNote,
)
from clinassist.security import schema  # noqa: E402
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault, VaultError  # noqa: E402

SECRET = "SECRET-PHI-4471"
FULL = HistoryChecklist(True, True, True)


def _record(session_id: str = "s1", **changes) -> SessionRecord:
    draft = Draft(
        subjective="Cough for 3 days.",
        objective="T 38.1",
        plan="Fluids.",
        ai_assessment="Possible viral URTI.",
        suggestions=(
            AiSuggestion("Viral URTI", "fever, cough", "supportive", 1),
            AiSuggestion("Early pneumonia", "fever", "review in 48 h", 2),
        ),
        flags=("number_mismatch",),
    )
    base = SessionRecord(
        session_id=session_id,
        transcript=f"Patient reports cough. {SECRET}",
        transcript_approved_by="dr-a",
        finalized_by="dr-a",
        draft=draft,
        final_note=SoapNote("Cough 3 days.", "T 38.1", "Viral URTI, clinician view.", "Fluids."),
        accepted_suggestions=(0,),
        assessment_origin="clinician_edited",
        checklist=FULL,
        generation_attempts=1,
    )
    return replace(base, **changes)


@pytest.fixture
def vault(tmp_path):
    v, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    return v


@pytest.fixture
def store(vault):
    return VaultSessionStore(vault)


def _count(vault: Vault, table: str) -> int:
    with vault.connect() as conn:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_round_trip_keeps_every_field(store):
    record = _record()
    store.save(record)
    assert store.load("s1") == record


def test_round_trip_of_a_manual_note_without_suggestions(store):
    record = _record(
        draft=Draft(source="manual"),
        accepted_suggestions=(),
        assessment_origin="clinician_manual",
        generation_attempts=2,
    )
    store.save(record)
    assert store.load("s1") == record


def test_model_draft_and_clinician_note_are_stored_apart(vault, store):
    """AMD-19: the model's assessment never overwrites the clinician's."""
    store.save(_record())
    with vault.connect() as conn:
        rows = dict(conn.execute("SELECT kind, assessment FROM notes WHERE session_id = 's1'"))
    assert rows == {
        "model_draft": "Possible viral URTI.",
        "clinician_final": "Viral URTI, clinician view.",
    }


def test_data_survives_lock_and_unlock(tmp_path, vault, store):
    store.save(_record())
    vault.lock()
    reopened = Vault.unlock(vault.directory, "a long synthetic passphrase 42")
    assert VaultSessionStore(reopened).load("s1") == _record()


def test_duplicate_session_is_rejected_and_the_first_is_kept(vault, store):
    store.save(_record())
    with pytest.raises(StoreError) as info:
        store.save(_record(transcript="something else"))
    assert info.value.code == "duplicate_session"
    assert store.load("s1") == _record()
    assert _count(vault, "notes") == 2


def test_failed_save_writes_nothing(vault, store):
    """One transaction: an error on the last insert must undo the session row too."""
    broken = AiSuggestion(None, "r", "m", 1)  # type: ignore[arg-type]  # NOT NULL fails
    bad = _record(draft=replace(_record().draft, suggestions=(broken,)))
    with pytest.raises(StoreError, match="^rejected_by_schema$"):
        store.save(bad)
    for table in ("sessions", "notes", "suggestions"):
        assert _count(vault, table) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"checklist": HistoryChecklist(True, True, False)},  # FR-15
        {"checklist": HistoryChecklist(False, True, True)},
        {"final_note": SoapNote("s", "o", "   ", "p")},  # FR-14: clinician must write it
        {"assessment_origin": "model_decided"},
        {"transcript": "  "},
        {"finalized_by": ""},
    ],
    ids=["negatives", "allergies", "blank_assessment", "bad_origin", "blank_transcript", "no_user"],
)
def test_database_rejects_records_the_controller_would_never_produce(vault, store, changes):
    """Defence in depth: break a gate on purpose and the schema still refuses the row."""
    with pytest.raises(StoreError) as info:
        store.save(_record(**changes))
    assert info.value.code == "rejected_by_schema"
    assert _count(vault, "sessions") == 0


def test_errors_never_carry_patient_text(store):
    store.save(_record())
    for attempt in (
        lambda: store.save(_record()),
        lambda: store.save(_record("s2", checklist=HistoryChecklist())),
        lambda: store.load("missing"),
    ):
        with pytest.raises(StoreError) as info:
            attempt()
        assert SECRET not in str(info.value)
        # no chained database error whose text could quote a row
        assert info.value.__cause__ is None
        assert info.value.__context__ is None or info.value.__suppress_context__


def test_session_ids_lists_in_save_order(store):
    for sid in ("b", "a", "c"):
        store.save(_record(sid))
    assert store.session_ids() == ["b", "a", "c"]


def test_migration_is_atomic(vault, monkeypatch):
    """A failing migration leaves the version and tables as they were."""
    monkeypatch.setattr(
        schema, "MIGRATIONS", schema.MIGRATIONS + ("CREATE TABLE extra (x); SELECT broken(;",)
    )
    monkeypatch.setattr(schema, "LATEST", len(schema.MIGRATIONS))
    with vault.connect() as conn:
        with pytest.raises(dbapi2.OperationalError):
            schema.migrate(conn)
        assert schema.current_version(conn) == schema.LATEST - 1
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "extra" not in tables


# ----- with the real controller -----
class _Recorder:
    def start(self) -> None: ...

    def stop(self) -> bytes:
        return b"pcm"


class _ASR:
    def transcribe(self, audio: bytes) -> str:
        return f"raw transcript {SECRET}"


class _Guard:
    def check(self, text: str) -> GuardVerdict:
        return GuardVerdict(False, clean_text=text)


class _Generator:
    def generate(self, text: str, attempt: int) -> Draft:
        return Draft("s", "o", "p", ai_assessment="Possible viral illness.")


def _controller(store) -> ConsultationController:
    c = ConsultationController(
        _Recorder(), _ASR(), _Guard(), _Generator(), store, id_factory=lambda: "sess-1"
    )
    c.start_recording()
    c.stop_recording()
    c.approve_transcript("approved text", "dr-a")
    c.generate_draft()
    return c


def test_controller_finalize_stores_the_session(store):
    c = _controller(store)
    record = c.finalize(SoapNote("s", "o", "My assessment", "p"), "dr-a", FULL)
    assert c.state is State.FINALIZED
    assert store.load("sess-1") == record


def test_storage_failure_keeps_the_session_editable(vault, store):
    """FR-07 with FR-12: if the save fails, the clinician's work is not lost."""
    c = _controller(store)
    vault.lock()  # every save now fails
    with pytest.raises(VaultError):
        c.finalize(SoapNote("s", "o", "My assessment", "p"), "dr-a", FULL)
    assert c.state is State.DRAFTED
