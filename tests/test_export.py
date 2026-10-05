"""PDF export of one finalized note (FR-17): what is in it, what is left out, and that the file
is a real PDF written without half-files."""

from __future__ import annotations

import os
from html import escape

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from clinassist.domain import (  # noqa: E402
    AiSuggestion,
    Draft,
    HistoryChecklist,
    SessionRecord,
    SoapNote,
)
from clinassist.ui.export import (  # noqa: E402
    CONFIDENTIAL,
    ExportDetails,
    default_file_name,
    note_html,
    write_pdf,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


DETAILS = ExportDetails(
    saved_at="2026-10-05T09:30:00+00:00",
    finalized_by="Dr Synthetic",
    exported_by="Synthetic Admin",
    exported_at="2026-10-05T10:00:00+00:00",
)


def _record() -> SessionRecord:
    draft = Draft(
        "Fever.",
        "T 38.6",
        "Rest.",
        ai_assessment="MODEL-ONLY-TEXT",
        suggestions=(
            AiSuggestion("Malaria", "fever and chills", "test, treat if positive", 1),
            AiSuggestion("Typhoid", "fever", "blood culture", 2),
        ),
    )
    return SessionRecord(
        session_id="1a2b3c4d5e6f",
        transcript="Patient: <script>alert(1)</script> fever for three days.",
        transcript_approved_by="u1",
        finalized_by="u1",
        draft=draft,
        final_note=SoapNote("Fever 3 days.", "T 38.6", "Malaria, clinical.", "Malaria test."),
        accepted_suggestions=(0,),
        assessment_origin="clinician_manual",
        checklist=HistoryChecklist(True, True, True),
        generation_attempts=1,
    )


def test_the_pdf_holds_the_clinicians_note_and_accepted_suggestions_only():
    html = note_html(_record(), DETAILS)
    for text in ("Fever 3 days.", "Malaria, clinical.", "Malaria test.", "Dr Synthetic"):
        assert text in html
    assert "Malaria" in html and "Typhoid" not in html  # only the accepted suggestion
    assert "MODEL-ONLY-TEXT" not in html  # the raw model draft stays in the vault
    assert "fever for three days" not in html  # no transcript unless asked for
    assert escape(CONFIDENTIAL) in html and "Synthetic Admin" in html
    assert "allergies, current medications, pertinent negatives" in html


def test_transcript_is_included_only_when_asked_and_escaped():
    details = ExportDetails(**{**DETAILS.__dict__, "include_transcript": True})
    html = note_html(_record(), details)
    assert "fever for three days" in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_file_name_has_no_patient_details():
    assert default_file_name("1a2b3c4d5e6f", DETAILS.saved_at) == (
        "consultation-2026-10-05-1A2B3C4D.pdf"
    )


def test_write_pdf_makes_a_real_pdf_and_no_part_file(qapp, tmp_path):
    saved = write_pdf(note_html(_record(), DETAILS), tmp_path / "note")
    assert saved.name == "note.pdf"
    data = saved.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 1000
    assert not list(tmp_path.glob("*.part"))
