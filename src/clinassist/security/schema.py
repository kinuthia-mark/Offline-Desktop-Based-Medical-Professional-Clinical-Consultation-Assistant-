"""Schema migrations for the vault database, tracked with PRAGMA user_version.

Each migration runs as one transaction together with its version bump, so a failure leaves the
database at the previous version. Migrations are append-only: never edit a released one.

The CHECK constraints repeat the controller's gates (FR-12, FR-14, FR-15) inside the database,
so a bug that bypassed the controller still could not store an unconfirmed note.
"""

from __future__ import annotations

MIGRATIONS: tuple[str, ...] = (
    # v1: sessions, the model draft and the clinician's note kept apart (AMD-12, AMD-19).
    """
    CREATE TABLE sessions (
        session_id             TEXT PRIMARY KEY CHECK (length(session_id) > 0),
        created_at             TEXT NOT NULL,
        transcript             TEXT NOT NULL CHECK (length(trim(transcript)) > 0),
        transcript_approved_by TEXT NOT NULL CHECK (length(transcript_approved_by) > 0),
        finalized_by           TEXT NOT NULL CHECK (length(finalized_by) > 0),
        draft_source           TEXT NOT NULL CHECK (draft_source IN ('model', 'manual')),
        assessment_origin      TEXT NOT NULL CHECK (assessment_origin IN
                                   ('clinician_manual', 'clinician_edited',
                                    'ai_text_accepted_verbatim')),
        allergies_confirmed    INTEGER NOT NULL CHECK (allergies_confirmed = 1),
        medications_confirmed  INTEGER NOT NULL CHECK (medications_confirmed = 1),
        negatives_confirmed    INTEGER NOT NULL CHECK (negatives_confirmed = 1),
        generation_attempts    INTEGER NOT NULL CHECK (generation_attempts >= 0),
        guardrail_flags        TEXT NOT NULL DEFAULT '[]',
        asr_model              TEXT,
        model_version          TEXT
    );
    CREATE TABLE notes (
        session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        kind        TEXT NOT NULL CHECK (kind IN ('model_draft', 'clinician_final')),
        subjective  TEXT NOT NULL,
        objective   TEXT NOT NULL,
        assessment  TEXT NOT NULL,
        plan        TEXT NOT NULL,
        PRIMARY KEY (session_id, kind),
        CHECK (kind = 'model_draft' OR length(trim(assessment)) > 0)
    );
    CREATE TABLE suggestions (
        session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        position    INTEGER NOT NULL CHECK (position >= 0),
        rank        INTEGER NOT NULL,
        diagnosis   TEXT NOT NULL,
        rationale   TEXT NOT NULL,
        management  TEXT NOT NULL,
        accepted    INTEGER NOT NULL CHECK (accepted IN (0, 1)),
        PRIMARY KEY (session_id, position)
    );
    """,
    # v2: user accounts and the hash-chained audit log (FR-08, FR-09, AMD-12).
    """
    CREATE TABLE users (
        user_id         TEXT PRIMARY KEY CHECK (length(user_id) > 0),
        username        TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(username) > 0),
        display_name    TEXT NOT NULL,
        role            TEXT NOT NULL CHECK (role IN ('clinician', 'admin')),
        password_hash   TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
        failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
        locked_until    TEXT,
        active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        created_at      TEXT NOT NULL
    );
    CREATE TABLE audit_logs (
        seq         INTEGER PRIMARY KEY CHECK (seq >= 1),
        ts          TEXT NOT NULL,
        event       TEXT NOT NULL,
        session_id  TEXT NOT NULL,
        user_id     TEXT,
        prev_hash   TEXT NOT NULL CHECK (length(prev_hash) = 64),
        entry_hash  TEXT NOT NULL UNIQUE CHECK (length(entry_hash) = 64)
    );
    """,
)

LATEST = len(MIGRATIONS)


class SchemaError(RuntimeError):
    """The database is newer than this program understands. Message is a stable code."""


def current_version(conn) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn) -> int:
    """Bring the database up to LATEST. Returns the version it ended at."""
    # The database remembers its own version number. A new vault starts at 0 and runs every
    # migration; a vault made by an older version of the app runs only the ones it is missing.
    version = current_version(conn)
    # A vault made by a newer version of the app is refused rather than damaged.
    if version > LATEST:
        raise SchemaError("schema_newer_than_program")
    for target in range(version + 1, LATEST + 1):
        # executescript commits any open transaction first; BEGIN...COMMIT makes the
        # migration and its version bump one unit. A failing statement leaves the
        # transaction open, so roll it back explicitly.
        try:
            conn.executescript(
                f"BEGIN;\n{MIGRATIONS[target - 1]}\nPRAGMA user_version = {target};\nCOMMIT;"
            )
        except Exception:
            conn.rollback()
            raise
    return current_version(conn)
