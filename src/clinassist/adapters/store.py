"""SessionStore backed by the encrypted vault (FR-07, NFR-05).

`save` writes one session in a single transaction: either every row is stored or none is. On
failure it raises StoreError with a code, and the controller stays in DRAFTED, so the clinician
loses nothing (see ConsultationController.finalize).
"""

# This file saves a finished consultation into the encrypted vault and reads it back.
# The controller calls it when the clinician finalises a note, and the history screen uses it.
# All SQL lives here, so no other file needs to know the table layout.
from __future__ import annotations

import json
from datetime import UTC, datetime

from clinassist.domain import AiSuggestion, Draft, HistoryChecklist, SessionRecord, SoapNote
from clinassist.security.vault import Vault


class StoreError(RuntimeError):
    """Raised with a stable code. Never carries transcript or note text."""

    # Only the short code is kept, so an error message can never leak patient text.
    def __init__(self, code: str) -> None:
        super().__init__(code)
        # Callers read this code to decide what to tell the clinician.
        self.code = code


# The one class that talks to the database for sessions. The Vault gives it a connection.


class VaultSessionStore:
    # The vault gives the encrypted connection. The clock is a parameter so tests can fix the time.
    def __init__(self, vault: Vault, clock=lambda: datetime.now(UTC)) -> None:
        self._vault = vault
        self._clock = clock

    def save(self, record: SessionRecord) -> None:
        # Imported here (not at the top) so the module loads even where SQLCipher is not installed.
        from sqlcipher3 import dbapi2

        # Short names for the three parts of the record that are used many times below.
        draft, note, ticks = record.draft, record.final_note, record.checklist
        # A set makes the "was this suggestion accepted" check fast.
        accepted = set(record.accepted_suggestions)
        # One consultation is written to three tables: the session itself, the two notes
        # (model draft and clinician's final), and the model's suggestions. The "?" marks are
        # placeholders the database fills in safely, so text from a note can never be read as
        # a database command.
        try:
            with self._vault.connect() as conn:
                with conn:  # one transaction: commit on success, roll back on any error
                    conn.execute(
                        "INSERT INTO sessions (session_id, created_at, transcript,"
                        " transcript_approved_by, finalized_by, draft_source, assessment_origin,"
                        " allergies_confirmed, medications_confirmed, negatives_confirmed,"
                        " generation_attempts, guardrail_flags, asr_model, model_version,"
                        " transcript_language, asr_confidence)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            record.session_id,
                            # Time is set by the store, not the
                            # caller, and trimmed to whole seconds.
                            self._clock().isoformat(timespec="seconds"),
                            record.transcript,
                            record.transcript_approved_by,
                            record.finalized_by,
                            draft.source,
                            record.assessment_origin,
                            # Tick boxes are stored as 0 or 1
                            # because the database has no true/false
                            # type.
                            int(ticks.allergies),
                            int(ticks.medications),
                            int(ticks.pertinent_negatives),
                            record.generation_attempts,
                            # The flags list is stored as one JSON text value.
                            json.dumps(list(draft.flags)),
                            # Empty text becomes NULL (nothing stored) instead of an empty string.
                            record.asr_model or None,
                            record.model_version or None,
                            record.transcript_language or None,
                            record.asr_confidence,
                        ),
                    )
                    conn.executemany(
                        "INSERT INTO notes (session_id, kind, subjective, objective, assessment,"
                        " plan) VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            (
                                record.session_id,
                                "model_draft",
                                draft.subjective,
                                draft.objective,
                                draft.ai_assessment,
                                draft.plan,
                            ),
                            (
                                record.session_id,
                                "clinician_final",
                                note.subjective,
                                note.objective,
                                note.assessment,
                                note.plan,
                            ),
                        ],
                    )
                    conn.executemany(
                        "INSERT INTO suggestions (session_id, position, rank, diagnosis,"
                        " rationale, management, accepted) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                record.session_id,
                                i,
                                s.rank,
                                s.diagnosis,
                                s.rationale,
                                s.management,
                                # 1 if this suggestion's
                                # position was accepted by the
                                # clinician, else 0.
                                int(i in accepted),
                            )
                            for i, s in enumerate(draft.suggestions)
                        ],
                    )
        # The database refused the record. Either the session was already saved, or a rule in the
        # schema was broken (for example a history box not ticked). The original database message
        # is dropped ("from None") because it could quote part of the note.
        except dbapi2.IntegrityError as exc:
            # Both a duplicate and a broken rule are IntegrityErrors, so the message
            # text tells them apart.
            duplicate = "UNIQUE" in str(exc) and "sessions.session_id" in str(exc)
            raise StoreError("duplicate_session" if duplicate else "rejected_by_schema") from None
        # Any other database failure (disk, key, locked file).
        except dbapi2.DatabaseError:
            raise StoreError("storage_failed") from None

    def load(self, session_id: str) -> SessionRecord:
        """Read a stored session back. Used by history views and by the round-trip tests."""
        with self._vault.connect() as conn:
            # The sessions row holds the main fields. Column order here matches the
            # row[n] numbers below.
            row = conn.execute(
                "SELECT transcript, transcript_approved_by, finalized_by, draft_source,"
                " assessment_origin, allergies_confirmed, medications_confirmed,"
                " negatives_confirmed, generation_attempts, guardrail_flags, asr_model,"
                " model_version, transcript_language, asr_confidence"
                " FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise StoreError("session_not_found")
            # Gather both notes into a dictionary keyed by kind, so each can be looked up by name.
            notes = {
                kind: (s, o, a, p)
                for kind, s, o, a, p in conn.execute(
                    "SELECT kind, subjective, objective, assessment, plan FROM notes"
                    " WHERE session_id = ?",
                    (session_id,),
                )
            }
            # Suggestions come back in their saved order (position).
            suggestion_rows = conn.execute(
                "SELECT position, rank, diagnosis, rationale, management, accepted"
                " FROM suggestions WHERE session_id = ? ORDER BY position",
                (session_id,),
            ).fetchall()

        # Rebuild the same objects that were saved, so a stored session reads back exactly as it
        # was finalized (the round-trip tests check this field by field).
        ds, do, da, dp = notes["model_draft"]
        draft = Draft(
            subjective=ds,
            objective=do,
            plan=dp,
            ai_assessment=da,
            suggestions=tuple(
                # Rows are (position, rank, diagnosis, rationale, management,
                # accepted), so this picks the middle four.
                AiSuggestion(d, r, m, rank)
                for _, rank, d, r, m, _ in suggestion_rows
            ),
            source=row[3],
            # Flags were saved as JSON text, so turn them back into a tuple.
            flags=tuple(json.loads(row[9])),
        )
        return SessionRecord(
            session_id=session_id,
            transcript=row[0],
            transcript_approved_by=row[1],
            finalized_by=row[2],
            draft=draft,
            final_note=SoapNote(*notes["clinician_final"]),
            # Positions of the suggestions whose accepted column is 1.
            accepted_suggestions=tuple(pos for pos, *_, acc in suggestion_rows if acc),
            assessment_origin=row[4],
            checklist=HistoryChecklist(bool(row[5]), bool(row[6]), bool(row[7])),
            generation_attempts=row[8],
            # NULL in the database comes back as an empty string, as it was before saving.
            asr_model=row[10] or "",
            model_version=row[11] or "",
            transcript_language=row[12] or "",
            asr_confidence=row[13],
        )

    def saved_at(self, session_id: str) -> str:
        """When the consultation was saved (UTC, ISO format), for exports."""
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise StoreError("session_not_found")
        return row[0]

    def summaries(self) -> list[tuple[str, str, str]]:
        """(session id, saved at in UTC, finalized by) for every saved consultation, newest
        first: what the records list shows. No clinical text."""
        with self._vault.connect() as conn:
            # Plain tuples are returned so the caller does not depend on the database row type.
            return [
                tuple(r)
                for r in conn.execute(
                    "SELECT session_id, created_at, finalized_by FROM sessions"
                    " ORDER BY created_at DESC, rowid DESC"
                )
            ]

    def session_ids(self) -> list[str]:
        # Ordered by insertion order (rowid) so the oldest session comes first.
        with self._vault.connect() as conn:
            return [r[0] for r in conn.execute("SELECT session_id FROM sessions ORDER BY rowid")]
