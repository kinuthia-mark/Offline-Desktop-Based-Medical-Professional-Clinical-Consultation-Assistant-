"""Export one finalized consultation note as a PDF (FR-17, AMD-36).

The PDF is meant to be printed for the patient's paper file or attached to a referral. It holds
the clinician's final note, the AI suggestions the clinician accepted (labelled as such), the
confirmed history checklist, who finalized the note and who exported it. The model's raw draft
is left out; it stays in the vault. The transcript is included only when asked for.

A PDF leaves the encrypted vault, so every page says it contains confidential patient
information, and each export is written to the audit log by the caller.

The PDF is drawn by Qt's own PDF writer (QPdfWriter), which is already part of the program: no
extra library and nothing online. Every piece of text from the record is HTML-escaped, so
anything typed into a note or transcript is printed as text and cannot change the layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

CONFIDENTIAL = (
    "Confidential patient information. Store and share this document only as your clinic's "
    "rules for patient records allow."
)
AI_NOTICE = (
    "This note was drafted with the help of an AI model running offline on this computer, then "
    "reviewed, edited and approved by the clinician named above. The assessment is the "
    "clinician's own."
)


@dataclass(frozen=True)
class ExportDetails:
    """What the PDF needs besides the record itself."""

    saved_at: str  # when the note was finalized (UTC, ISO format)
    finalized_by: str  # full name of the clinician who finalized it
    exported_by: str  # full name of the person exporting
    exported_at: str  # when (UTC, ISO format)
    include_transcript: bool = False


def default_file_name(session_id: str, saved_at: str) -> str:
    """For example consultation-2026-10-05-1A2B3C4D.pdf: the date and the session's short id,
    never the patient's name."""
    return f"consultation-{saved_at[:10]}-{session_id[:8].upper()}.pdf"


def note_html(record, details: ExportDetails) -> str:
    """The note as simple HTML for Qt's text engine (tables and basic styles only)."""
    e = _text
    note = record.final_note
    accepted = [
        s for pos, s in enumerate(record.draft.suggestions) if pos in record.accepted_suggestions
    ]
    checklist = record.checklist
    confirmed = [
        label
        for label, done in (
            ("allergies", checklist.allergies),
            ("current medications", checklist.medications),
            ("pertinent negatives", checklist.pertinent_negatives),
        )
        if done
    ]

    parts = [
        "<html><body style='font-family: Arial, sans-serif; font-size: 10pt;'>",
        "<h2 style='margin-bottom: 0;'>Consultation note</h2>",
        f"<p style='color: #555;'>{e(CONFIDENTIAL)}</p>",
        "<table cellspacing='0' cellpadding='3' style='margin-bottom: 8px;'>",
        _row("Session", record.session_id[:8].upper()),
        _row("Finalized", f"{details.saved_at[:16].replace('T', ' ')} UTC"),
        _row("Finalized by", details.finalized_by),
        _row("History confirmed", ", ".join(confirmed) if confirmed else "none recorded"),
        "</table>",
    ]
    for title, text in (
        ("Subjective", note.subjective),
        ("Objective", note.objective),
        ("Assessment (clinician)", note.assessment),
        ("Plan", note.plan),
    ):
        parts.append(f"<h3 style='margin-bottom: 2px;'>{e(title)}</h3>")
        parts.append(f"<p style='margin-top: 0;'>{e(text) or '&nbsp;'}</p>")

    if accepted:
        parts.append(
            "<h3 style='margin-bottom: 2px;'>AI suggestions accepted by the clinician</h3>"
        )
        parts.append("<ol style='margin-top: 0;'>")
        for s in accepted:
            parts.append(
                f"<li><b>{e(s.diagnosis)}</b><br/><i>Reason:</i> {e(s.rationale)}<br/>"
                f"<i>Suggested management:</i> {e(s.management)}</li>"
            )
        parts.append("</ol>")

    if details.include_transcript:
        parts.append("<h3 style='margin-bottom: 2px;'>Approved transcript</h3>")
        parts.append(f"<p style='margin-top: 0;'>{e(record.transcript)}</p>")

    parts += [
        "<hr/>",
        f"<p style='color: #555; font-size: 8pt;'>{e(AI_NOTICE)}</p>",
        f"<p style='color: #555; font-size: 8pt;'>Exported "
        f"{e(details.exported_at[:16].replace('T', ' '))} UTC by {e(details.exported_by)}. "
        f"{e(CONFIDENTIAL)}</p>",
        "</body></html>",
    ]
    return "\n".join(parts)


def write_pdf(html: str, path: Path | str) -> Path:
    """Draw the HTML onto A4 pages and save it. Writes to a temporary name first, so a failed
    export never leaves half a file under the chosen name."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        path = path.with_name(path.name + ".pdf")
    tmp = path.with_name(path.name + ".part")
    writer = QPdfWriter(str(tmp))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)
    writer.setTitle("Consultation note")
    writer.setCreator("Offline Clinical Consultation Assistant")
    document = QTextDocument()
    document.setHtml(html)
    document.print_(writer)
    del writer  # closes the file; Windows cannot rename it while it is open
    tmp.replace(path)
    return path


def _row(label: str, value: str) -> str:
    return f"<tr><td style='color: #555;'>{_text(label)}</td><td>{_text(value)}</td></tr>"


def _text(value: str) -> str:
    """Escaped text with line breaks kept."""
    return escape(value or "").replace("\n", "<br/>")
