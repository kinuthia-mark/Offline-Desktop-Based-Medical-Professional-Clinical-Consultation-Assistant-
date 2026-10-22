"""System reports for administrators: counts and times only, never patient text."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from clinassist import reports  # noqa: E402
from clinassist.adapters.store import VaultSessionStore  # noqa: E402
from clinassist.domain import (  # noqa: E402
    AiSuggestion,
    Draft,
    HistoryChecklist,
    SessionRecord,
    SoapNote,
)
from clinassist.security.audit import HashChainAuditor  # noqa: E402
from clinassist.security.crypto import TEST_KDF  # noqa: E402
from clinassist.security.vault import Vault  # noqa: E402

SECRET = "SECRET-PHI-4471"  # put in every clinical column; must never reach a report
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def vault(tmp_path):
    v, _ = Vault.create(tmp_path / "v", "a long synthetic passphrase 42", kdf=TEST_KDF)
    with v.connect() as conn:
        conn.execute(
            "INSERT INTO users (user_id, username, display_name, role, password_hash, created_at)"
            " VALUES ('dr-a', 'dra', 'Dr A', 'clinician', '$argon2id$x', '2026-01-01')"
        )
        conn.commit()
    return v


def _record(session_id: str, **changes) -> SessionRecord:
    draft = Draft(
        subjective=f"S {SECRET}",
        objective=f"O {SECRET}",
        plan=f"P {SECRET}",
        ai_assessment=f"A {SECRET}",
        suggestions=(
            AiSuggestion(f"Dx {SECRET}", f"why {SECRET}", f"do {SECRET}", 1),
            AiSuggestion(f"Dx2 {SECRET}", f"why {SECRET}", f"do {SECRET}", 2),
        ),
        flags=("number_mismatch", "medicine_not_in_transcript"),
    )
    base = SessionRecord(
        session_id=session_id,
        transcript=f"Patient says {SECRET}",
        transcript_approved_by="dr-a",
        finalized_by="dr-a",
        draft=draft,
        final_note=SoapNote(f"S {SECRET}", f"O {SECRET}", f"A {SECRET}", f"P {SECRET}"),
        accepted_suggestions=(0,),
        assessment_origin="clinician_edited",
        checklist=HistoryChecklist(True, True, True),
        generation_attempts=1,
    )
    return replace(base, **changes)


def _consultation(vault, clock, sid, minutes_to_draft=2, **changes):
    """Write a consultation's audit events and saved note the way the program does."""
    auditor = HashChainAuditor(vault, clock=clock)
    store = VaultSessionStore(vault, clock=clock)
    auditor.record("recording_started", sid, None)
    clock.at += timedelta(minutes=5)
    auditor.record("transcript_approved", sid, "dr-a")
    clock.at += timedelta(minutes=minutes_to_draft)
    auditor.record("draft_generated", sid, "dr-a")
    clock.at += timedelta(minutes=3)
    store.save(_record(sid, **changes))
    auditor.record("finalized", sid, "dr-a")


@pytest.fixture
def filled(vault):
    """Three saved notes and one discarded consultation in the last week, one old note."""
    clock = Clock(NOW - timedelta(days=60))
    _consultation(vault, clock, "old1")
    clock.at = NOW - timedelta(days=2)
    _consultation(vault, clock, "s1", minutes_to_draft=1)
    _consultation(vault, clock, "s2", minutes_to_draft=2, generation_attempts=2)
    _consultation(
        vault,
        clock,
        "s3",
        minutes_to_draft=3,
        draft=Draft(source="manual"),
        accepted_suggestions=(),
        assessment_origin="clinician_manual",
    )
    auditor = HashChainAuditor(vault, clock=clock)
    auditor.record("recording_started", "s4", None)
    auditor.record("session_discarded", "s4", None)
    auditor.record("login_failed", "", None)
    auditor.record("account_locked", "", "dr-a")
    return vault


def test_counts_only_the_chosen_period(filled):
    week = reports.build_report(filled, "Last 7 days", now=NOW, tz=UTC)
    every = reports.build_report(filled, "All time", now=NOW, tz=UTC)
    assert week.finalized == 3 and every.finalized == 4
    assert week.started == 4 and week.discarded == 1


def test_how_notes_were_written(filled):
    r = reports.build_report(filled, "Last 7 days", now=NOW, tz=UTC)
    assert (r.from_model_draft, r.written_by_hand) == (2, 1)
    assert (r.assessment_edited, r.assessment_by_clinician, r.assessment_ai_verbatim) == (2, 1, 0)
    assert r.drafts_retried == 1
    assert (r.notes_with_flags, r.flags_total) == (2, 4)  # the manual note has no flags
    assert (r.suggestions_shown, r.suggestions_accepted) == (4, 2)


def test_drafting_and_consultation_times_are_medians(filled):
    r = reports.build_report(filled, "Last 7 days", now=NOW, tz=UTC)
    assert r.median_draft_seconds == 120  # 1, 2 and 3 minutes
    assert r.median_consultation_minutes == 10  # 5 + 2 + 3 for the middle one


def test_breakdowns_and_accounts(filled):
    r = reports.build_report(filled, "Last 7 days", now=NOW, tz=UTC)
    assert r.per_clinician == {"Dr A": 3}
    assert r.per_day == {"2026-10-20": 3}
    assert (r.failed_logins, r.lockouts) == (2, 1)


def test_an_empty_vault_gives_zeros_not_errors(vault):
    r = reports.build_report(vault, "Last 30 days", now=NOW, tz=UTC)
    assert r.finalized == 0 and r.median_draft_seconds is None
    assert ("Time", "Median time to draft a note", "-") in reports.summary_rows(r)


def test_no_patient_text_reaches_the_report_or_its_csv(filled):
    """Safety rule 3: administrators never see clinical text, even through a report."""
    r = reports.build_report(filled, "All time", now=NOW, tz=UTC)
    text = repr(r) + reports.to_csv(r) + repr(reports.summary_rows(r))
    assert SECRET not in text
    assert "Dx" not in text  # not even the diagnosis names


def test_csv_has_a_header_and_every_measure(filled):
    r = reports.build_report(filled, "Last 7 days", now=NOW, tz=UTC)
    lines = reports.to_csv(r).splitlines()
    assert lines[3] == "Section,Measure,Value"
    assert len(lines) == 4 + len(reports.summary_rows(r))
    assert "Last 7 days: from 2026-10-15 to 2026-10-22 (this computer's time)" in lines[1]


def test_unknown_period_is_refused(vault):
    with pytest.raises(ValueError):
        reports.build_report(vault, "Last decade", now=NOW, tz=UTC)


def test_days_are_counted_in_the_clinics_time_zone(vault):
    """A note saved at 22:30 UTC is the next day in Nairobi (UTC+3)."""
    from datetime import timezone

    clock = Clock(datetime(2026, 10, 21, 22, 20, tzinfo=UTC))
    _consultation(vault, clock, "late")
    nairobi = timezone(timedelta(hours=3))
    assert reports.build_report(vault, "All time", now=NOW, tz=UTC).per_day == {"2026-10-21": 1}
    assert reports.build_report(vault, "All time", now=NOW, tz=nairobi).per_day == {"2026-10-22": 1}
