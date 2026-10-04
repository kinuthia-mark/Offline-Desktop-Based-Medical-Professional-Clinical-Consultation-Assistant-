"""SessionStore backed by the encrypted vault (FR-07, NFR-05).

`save` writes one session in a single transaction: either every row is stored or none is. On
failure it raises StoreError with a code, and the controller stays in DRAFTED, so the clinician
loses nothing (see ConsultationController.finalize).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from clinassist.domain import AiSuggestion, Draft, HistoryChecklist, SessionRecord, SoapNote
from clinassist.security.vault import Vault


class StoreError(RuntimeError):
    """Raised with a stable code. Never carries transcript or note text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VaultSessionStore:
    def __init__(self, vault: Vault, clock=lambda: datetime.now(UTC)) -> None:
        self._vault = vault
        self._clock = clock

    def save(self, record: SessionRecord) -> None:
        from sqlcipher3 import dbapi2

        draft, note, ticks = record.draft, record.final_note, record.checklist
        accepted = set(record.accepted_suggestions)
        try:
            with self._vault.connect() as conn:
                with conn:  # one transaction: commit on success, roll back on any error
                    conn.execute(
                        "INSERT INTO sessions (session_id, created_at, transcript,"
                        " transcript_approved_by, finalized_by, draft_source, assessment_origin,"
                        " allergies_confirmed, medications_confirmed, negatives_confirmed,"
                        " generation_attempts, guardrail_flags)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            record.session_id,
                            self._clock().isoformat(timespec="seconds"),
                            record.transcript,
                            record.transcript_approved_by,
                            record.finalized_by,
                            draft.source,
                            record.assessment_origin,
                            int(ticks.allergies),
                            int(ticks.medications),
                            int(ticks.pertinent_negatives),
                            record.generation_attempts,
                            json.dumps(list(draft.flags)),
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
                                int(i in accepted),
                            )
                            for i, s in enumerate(draft.suggestions)
                        ],
                    )
        except dbapi2.IntegrityError as exc:
            duplicate = "UNIQUE" in str(exc) and "sessions.session_id" in str(exc)
            raise StoreError("duplicate_session" if duplicate else "rejected_by_schema") from None
        except dbapi2.DatabaseError:
            raise StoreError("storage_failed") from None

    def load(self, session_id: str) -> SessionRecord:
        """Read a stored session back. Used by history views and by the round-trip tests."""
        with self._vault.connect() as conn:
            row = conn.execute(
                "SELECT transcript, transcript_approved_by, finalized_by, draft_source,"
                " assessment_origin, allergies_confirmed, medications_confirmed,"
                " negatives_confirmed, generation_attempts, guardrail_flags"
                " FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise StoreError("session_not_found")
            notes = {
                kind: (s, o, a, p)
                for kind, s, o, a, p in conn.execute(
                    "SELECT kind, subjective, objective, assessment, plan FROM notes"
                    " WHERE session_id = ?",
                    (session_id,),
                )
            }
            suggestion_rows = conn.execute(
                "SELECT position, rank, diagnosis, rationale, management, accepted"
                " FROM suggestions WHERE session_id = ? ORDER BY position",
                (session_id,),
            ).fetchall()

        ds, do, da, dp = notes["model_draft"]
        draft = Draft(
            subjective=ds,
            objective=do,
            plan=dp,
            ai_assessment=da,
            suggestions=tuple(
                AiSuggestion(d, r, m, rank) for _, rank, d, r, m, _ in suggestion_rows
            ),
            source=row[3],
            flags=tuple(json.loads(row[9])),
        )
        return SessionRecord(
            session_id=session_id,
            transcript=row[0],
            transcript_approved_by=row[1],
            finalized_by=row[2],
            draft=draft,
            final_note=SoapNote(*notes["clinician_final"]),
            accepted_suggestions=tuple(pos for pos, *_, acc in suggestion_rows if acc),
            assessment_origin=row[4],
            checklist=HistoryChecklist(bool(row[5]), bool(row[6]), bool(row[7])),
            generation_attempts=row[8],
        )

    def session_ids(self) -> list[str]:
        with self._vault.connect() as conn:
            return [r[0] for r in conn.execute("SELECT session_id FROM sessions ORDER BY rowid")]
