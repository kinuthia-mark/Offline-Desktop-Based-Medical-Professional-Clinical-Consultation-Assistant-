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

# This file builds the printable PDF of a finalized note. note_html() writes the page as HTML,
# and write_pdf() lets Qt draw that HTML onto A4 pages. The caller (the records screen)
# chooses the path and writes the audit log entry.
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from clinassist.ui.records import models_used

# Fixed wording used in the PDF.
CONFIDENTIAL = (
    "Confidential patient information. Store and share this document only as your clinic's "
    "rules for patient records allow."
)
AI_NOTICE = (
    "This note was drafted with the help of an AI model running offline on this computer, then "
    "reviewed, edited and approved by the clinician named above. The assessment is the "
    "clinician's own."
)


# A read-only bundle of the extra facts that note_html() needs.
@dataclass(frozen=True)
class ExportDetails:
    """What the PDF needs besides the record itself."""

    saved_at: str  # when the note was finalized (UTC, ISO format)
    finalized_by: str  # full name of the clinician who finalized it
    exported_by: str  # full name of the person exporting
    exported_at: str  # when (UTC, ISO format)
    include_transcript: bool = False


# Builds a safe file name from the date and a short id, so no patient name is in it.
def default_file_name(session_id: str, saved_at: str) -> str:
    """For example consultation-2026-10-05-1A2B3C4D.pdf: the date and the session's short id,
    never the patient's name."""
    return f"consultation-{saved_at[:10]}-{session_id[:8].upper()}.pdf"


# Builds the HTML of the whole note. Every value from the record goes through _text() first.
def note_html(record, details: ExportDetails) -> str:
    """The note as simple HTML for Qt's text engine (tables and basic styles only)."""
    # A short name for the escaping function, used on every piece of text from the record.
    e = _text
    note = record.final_note
    # The suggestions the clinician accepted. accepted_suggestions holds their positions in the
    # draft list.
    accepted = [
        s for pos, s in enumerate(record.draft.suggestions) if pos in record.accepted_suggestions
    ]
    checklist = record.checklist
    # The names of the history items that were ticked off.
    confirmed = [
        label
        for label, done in (
            ("allergies", checklist.allergies),
            ("current medications", checklist.medications),
            ("pertinent negatives", checklist.pertinent_negatives),
        )
        if done
    ]

    # The page is built as a list of HTML pieces and joined at the end.
    parts = [
        "<html><body style='font-family: Arial, sans-serif; font-size: 10pt;'>",
        "<h2 style='margin-bottom: 0;'>Consultation note</h2>",
        f"<p style='color: #555;'>{e(CONFIDENTIAL)}</p>",
        "<table cellspacing='0' cellpadding='3' style='margin-bottom: 8px;'>",
        # Only the first 8 characters of the id, in capitals, like the file name.
        _row("Session", record.session_id[:8].upper()),
        # [:16] keeps the date and the minutes, and the T is swapped for a space.
        _row("Finalized", f"{details.saved_at[:16].replace('T', ' ')} UTC"),
        _row("Finalized by", details.finalized_by),
        _row("History confirmed", ", ".join(confirmed) if confirmed else "none recorded"),
        _row("Models used", models_used(record)),
        "</table>",
    ]
    for title, text in (
        ("Subjective", note.subjective),
        ("Objective", note.objective),
        ("Assessment (clinician)", note.assessment),
        ("Plan", note.plan),
    ):
        parts.append(f"<h3 style='margin-bottom: 2px;'>{e(title)}</h3>")
        # &nbsp; stops an empty section collapsing to nothing.
        parts.append(f"<p style='margin-top: 0;'>{e(text) or '&nbsp;'}</p>")

    # This part only appears when the clinician accepted something.
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

    # The transcript is only added when it was asked for.
    if details.include_transcript:
        parts.append("<h3 style='margin-bottom: 2px;'>Approved transcript</h3>")
        parts.append(f"<p style='margin-top: 0;'>{e(record.transcript)}</p>")

    # The footer: the AI notice and who exported it. Then close the HTML.
    parts += [
        "<hr/>",
        f"<p style='color: #555; font-size: 8pt;'>{e(AI_NOTICE)}</p>",
        f"<p style='color: #555; font-size: 8pt;'>Exported "
        f"{e(details.exported_at[:16].replace('T', ' '))} UTC by {e(details.exported_by)}. "
        f"{e(CONFIDENTIAL)}</p>",
        "</body></html>",
    ]
    return "\n".join(parts)


# Turns the HTML into a PDF file on disk and returns its final path.
def write_pdf(html: str, path: Path | str) -> Path:
    """Draw the HTML onto A4 pages and save it. Writes to a temporary name first, so a failed
    export never leaves half a file under the chosen name."""
    path = Path(path)
    # Make sure the file name ends in .pdf.
    if path.suffix.lower() != ".pdf":
        path = path.with_name(path.name + ".pdf")
    # Write to name.pdf.part first and rename it when it is complete.
    tmp = path.with_name(path.name + ".part")
    writer = QPdfWriter(str(tmp))
    # A4 page size and 18 mm margins on every side.
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)
    writer.setTitle("Consultation note")
    writer.setCreator("Offline Clinical Consultation Assistant")
    # QTextDocument lays the HTML out as pages. print_ draws them onto the PDF writer.
    document = QTextDocument()
    document.setHtml(html)
    document.print_(writer)
    del writer  # closes the file; Windows cannot rename it while it is open
    # replace() also overwrites an existing file with the same name.
    tmp.replace(path)
    return path


# One table row: a grey label and its value, both escaped.
def _row(label: str, value: str) -> str:
    return f"<tr><td style='color: #555;'>{_text(label)}</td><td>{_text(value)}</td></tr>"


# Escapes text so it cannot be read as HTML.
def _text(value: str) -> str:
    """Escaped text with line breaks kept."""
    # escape() turns < > & into safe text. replace() keeps line breaks. None becomes empty.
    return escape(value or "").replace("\n", "<br/>")
