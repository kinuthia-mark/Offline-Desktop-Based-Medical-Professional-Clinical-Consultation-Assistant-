"""Session Records (FR-16, wireframe navigation): browse saved consultations, read only, and
export one as a PDF (FR-17, ui/export.py).

Each saved consultation shows the clinician's final note first, then the model's draft and the
approved transcript, so it is always clear what the clinician wrote and what the model wrote.

The list shows the newest first, with when it was saved (this computer's time) and who saved it,
and can be narrowed by typing part of a date, a name or a session id. The search looks only at
those three, never at what was said or written.
"""

# This file is the Session Records tab for clinicians. It lists saved consultations on the
# left and shows the chosen one as read-only text on the right. It never edits a record;
# it only reads from the encrypted store and can hand one to the PDF exporter.
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code


# Build the one-line "which models made this record" text for the detail view.
def models_used(record) -> str:
    """Which models produced the record, in words: "speech: faster-whisper-small (en, 91%
    confidence); note: medgemma:4b". Typed transcripts and notes written by hand say so."""
    # An empty asr_model means the transcript was typed, not spoken.
    if record.asr_model:
        speech = record.asr_model
        details = [record.transcript_language] if record.transcript_language else []
        # Confidence is 0 to 1 and can be 0, so test `is not None`, not just whether it is set.
        if record.asr_confidence is not None:
            # `:.0%` shows 0.91 as 91%.
            details.append(f"{record.asr_confidence:.0%} confidence")
        if details:
            speech += f" ({', '.join(details)})"
    else:
        speech = "none (typed transcript)"
    note = record.model_version or "none (written by hand)"
    return f"speech: {speech}; note: {note}"


# Stored times are UTC. `astimezone()` with no argument converts to this computer's zone.
def local_time(utc_iso: str) -> str:
    """A stored UTC time as this computer's local time, for example "22 Oct 2026 10:14"."""
    return datetime.fromisoformat(utc_iso).astimezone().strftime("%d %b %Y %H:%M")


# Turn a record into the plain text shown on the right. The clinician's note comes first
# and the AI draft second, so it is always clear who wrote what.
def describe(record, name_of: Callable[[str], str] = str) -> str:
    """The saved consultation as plain text, clinician's note first. `name_of(user_id)` gives
    the clinician's name."""
    # `note` is what the clinician approved; `draft` is what the model first wrote.
    note, draft = record.final_note, record.draft
    lines = [
        f"Finalized by: {name_of(record.finalized_by)}",
        f"Assessment written: {record.assessment_origin.replace('_', ' ')}",
        f"Model attempts: {record.generation_attempts}   Draft source: {draft.source}",
        f"Models used: {models_used(record)}",
        "",
        "CLINICIAN'S NOTE",
        f"Subjective: {note.subjective}",
        f"Objective: {note.objective}",
        f"Assessment: {note.assessment}",
        f"Plan: {note.plan}",
        "",
        "MODEL'S DRAFT (AI-generated)",
        f"Subjective: {draft.subjective}",
        f"Objective: {draft.objective}",
        f"Assessment: {draft.ai_assessment}",
        f"Plan: {draft.plan}",
    ]
    # Flags are advisory warnings from the draft step; add them only if there are any.
    if draft.flags:
        lines.append("Advisory flags: " + ", ".join(draft.flags))
    lines += ["", "APPROVED TRANSCRIPT", record.transcript]
    return "\n".join(lines)


# The Records tab. `store` is the encrypted vault's record store; everything else is optional
# and passed in so tests can replace it.
class RecordsView(QWidget):
    def __init__(
        self,
        store,
        before_action: Callable[[], None] = lambda: None,
        export: Callable[[str, str, bool], str] | None = None,
        ask_pdf_path: Callable[[str], str] | None = None,
        name_of: Callable[[str], str] | None = None,
    ) -> None:
        """`export(session_id, path, include_transcript)` writes the PDF and returns where it
        was saved; `ask_pdf_path(suggested_name)` shows the save dialog (tests replace it);
        `name_of(user_id)` gives a clinician's name."""
        super().__init__()
        # Keep the store and the helpers. `name_of or str` shows the raw user id if no name
        # lookup was given.
        self._store = store
        self._before_action = before_action
        self._export = export
        self._ask_pdf_path = ask_pdf_path or self._dialog_pdf_path
        self._name_of = name_of or str
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by date, clinician or session id")
        self.search.setClearButtonEnabled(True)
        # Every keystroke in the search box re-filters the list.
        self.search.textChanged.connect(self._filter)
        self.session_table = QTableWidget(0, 3)
        self.session_table.setHorizontalHeaderLabels(["Saved", "Clinician", "Session"])
        # Rows cannot be edited. They are picked one whole row at a time.
        self.session_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.session_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.session_table.verticalHeader().setVisible(False)
        self.session_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.session_table.horizontalHeader().setStretchLastSection(True)
        # When the highlighted row changes, show that session. `*_` ignores the extra arguments Qt
        # sends.
        self.session_table.currentCellChanged.connect(
            lambda row, *_: self.show_session(self._session_at(row))
        )
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Choose a consultation on the left to read it here.")
        self.message = QLabel()
        # Wrap long messages (a saved file's full path): unwrapped, they widened the whole window
        # past the screen edge.
        self.message.setWordWrap(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        # Left side: a title, the search box, the table and a Refresh button.
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("Saved consultations, newest first"))
        lv.addWidget(self.search)
        lv.addWidget(self.session_table, 1)
        lv.addWidget(refresh)
        # A splitter lets the user drag the divider. Stretch 1 is the detail pane; it gets 3 shares.
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 980])  # wide enough for the date, the clinician and the session id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(splitter, 1)
        # Export controls stay hidden unless an export function was given.
        self.include_transcript = QCheckBox("Include the transcript")
        self.export_button = QPushButton("Export as PDF...")
        self.export_button.clicked.connect(self.export_pdf)
        self.export_button.setVisible(export is not None)
        self.include_transcript.setVisible(export is not None)
        row = QHBoxLayout()
        row.addWidget(self.message, 1)
        row.addWidget(self.include_transcript)
        row.addWidget(self.export_button)
        layout.addLayout(row)

    # Reload the list from the store. `before_action` is a hook (for example to keep the
    # idle-timeout from logging the user out). Failures show a plain message.
    def reload(self) -> None:
        try:
            self._before_action()
            # One row per saved session: full id, local save time and the clinician's name.
            rows = [
                (sid, local_time(saved), self._name_of(by))
                for sid, saved, by in self._store.summaries()
            ]
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.session_table.setRowCount(len(rows))
        for r, (sid, saved, name) in enumerate(rows):
            # Show only the first 8 letters of the session id, in capitals; the full id is kept in
            # the
            # item for loading.
            for c, text in enumerate((saved, name, sid[:8].upper())):
                item = QTableWidgetItem(text)
                item.setData(256, sid)  # Qt.UserRole: the full id, used to load the record
                self.session_table.setItem(r, c, item)
        self.message.setText(f"{len(rows)} saved.")
        # Apply any text already typed in the search box to the new rows.
        self._filter(self.search.text())

    # The full session id behind a row, or "" if no row is selected (row is -1).
    def _session_at(self, row: int) -> str:
        item = self.session_table.item(row, 0) if row >= 0 else None
        return item.data(256) if item is not None else ""

    # Hide rows that do not match. The search covers only date, name and session id, never
    # the clinical text.
    def _filter(self, text: str) -> None:
        """Show only rows whose date, clinician or session id contains the typed text."""
        needle = text.strip().lower()
        for r in range(self.session_table.rowCount()):
            # All three visible cells joined with spaces, plus the full session id, in lower case.
            cells = (
                " ".join(self.session_table.item(r, c).text() for c in range(3)).lower()
                + " "
                + self._session_at(r).lower()
            )
            self.session_table.setRowHidden(r, bool(needle) and needle not in cells)

    # Load the chosen record and show it. Nothing is shown if the selection was cleared.
    def show_session(self, session_id: str) -> None:
        if not session_id:
            self.detail.clear()
            return
        try:
            self._before_action()
            self.detail.setPlainText(describe(self._store.load(session_id), self._name_of))
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))

    # Export the selected consultation as a PDF. The transcript is included only if the box
    # is ticked.
    def export_pdf(self) -> None:
        session_id = self._session_at(self.session_table.currentRow())
        if not session_id:
            self.message.setText("Select a saved consultation first.")
            return
        try:
            self._before_action()
            # Imported here, inside the method, so the PDF code is loaded only when it is used.
            from clinassist.ui.export import default_file_name

            suggested = default_file_name(session_id, self._store.saved_at(session_id))
            path = self._ask_pdf_path(suggested)
            if not path:
                return
            saved = self._export(session_id, path, self.include_transcript.isChecked())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        # The warning is shown because the PDF holds patient information.
        self.message.setText(
            f"Saved {saved}. It contains patient information: store it as your clinic's "
            "rules require."
        )

    # The real Windows save dialog. Tests swap it for a fake.
    def _dialog_pdf_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, "Export as PDF", suggested, "PDF (*.pdf)")
        return path
