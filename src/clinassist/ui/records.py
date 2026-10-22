"""Session Records (FR-16, wireframe navigation): browse saved consultations, read only, and
export one as a PDF (FR-17, ui/export.py).

Each saved consultation shows the clinician's final note first, then the model's draft and the
approved transcript, so it is always clear what the clinician wrote and what the model wrote.

The list shows the newest first, with when it was saved (this computer's time) and who saved it,
and can be narrowed by typing part of a date, a name or a session id. The search looks only at
those three, never at what was said or written.
"""

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


def models_used(record) -> str:
    """Which models produced the record, in words: "speech: faster-whisper-small (en, 91%
    confidence); note: medgemma:4b". Typed transcripts and notes written by hand say so."""
    if record.asr_model:
        speech = record.asr_model
        details = [record.transcript_language] if record.transcript_language else []
        if record.asr_confidence is not None:
            details.append(f"{record.asr_confidence:.0%} confidence")
        if details:
            speech += f" ({', '.join(details)})"
    else:
        speech = "none (typed transcript)"
    note = record.model_version or "none (written by hand)"
    return f"speech: {speech}; note: {note}"


def local_time(utc_iso: str) -> str:
    """A stored UTC time as this computer's local time, for example "22 Oct 2026 10:14"."""
    return datetime.fromisoformat(utc_iso).astimezone().strftime("%d %b %Y %H:%M")


def describe(record, name_of: Callable[[str], str] = str) -> str:
    """The saved consultation as plain text, clinician's note first. `name_of(user_id)` gives
    the clinician's name."""
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
    if draft.flags:
        lines.append("Advisory flags: " + ", ".join(draft.flags))
    lines += ["", "APPROVED TRANSCRIPT", record.transcript]
    return "\n".join(lines)


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
        self._store = store
        self._before_action = before_action
        self._export = export
        self._ask_pdf_path = ask_pdf_path or self._dialog_pdf_path
        self._name_of = name_of or str
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by date, clinician or session id")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.session_table = QTableWidget(0, 3)
        self.session_table.setHorizontalHeaderLabels(["Saved", "Clinician", "Session"])
        self.session_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.session_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.session_table.verticalHeader().setVisible(False)
        self.session_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.session_table.horizontalHeader().setStretchLastSection(True)
        self.session_table.currentCellChanged.connect(
            lambda row, *_: self.show_session(self._session_at(row))
        )
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.message = QLabel()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("Saved consultations, newest first"))
        lv.addWidget(self.search)
        lv.addWidget(self.session_table, 1)
        lv.addWidget(refresh)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
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

    def reload(self) -> None:
        try:
            self._before_action()
            rows = [
                (sid, local_time(saved), self._name_of(by))
                for sid, saved, by in self._store.summaries()
            ]
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.session_table.setRowCount(len(rows))
        for r, (sid, saved, name) in enumerate(rows):
            for c, text in enumerate((saved, name, sid[:8].upper())):
                item = QTableWidgetItem(text)
                item.setData(256, sid)  # Qt.UserRole: the full id, used to load the record
                self.session_table.setItem(r, c, item)
        self.message.setText(f"{len(rows)} saved.")
        self._filter(self.search.text())

    def _session_at(self, row: int) -> str:
        item = self.session_table.item(row, 0) if row >= 0 else None
        return item.data(256) if item is not None else ""

    def _filter(self, text: str) -> None:
        """Show only rows whose date, clinician or session id contains the typed text."""
        needle = text.strip().lower()
        for r in range(self.session_table.rowCount()):
            cells = (
                " ".join(self.session_table.item(r, c).text() for c in range(3)).lower()
                + " "
                + self._session_at(r).lower()
            )
            self.session_table.setRowHidden(r, bool(needle) and needle not in cells)

    def show_session(self, session_id: str) -> None:
        if not session_id:
            self.detail.clear()
            return
        try:
            self._before_action()
            self.detail.setPlainText(describe(self._store.load(session_id), self._name_of))
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))

    def export_pdf(self) -> None:
        session_id = self._session_at(self.session_table.currentRow())
        if not session_id:
            self.message.setText("Select a saved consultation first.")
            return
        try:
            self._before_action()
            from clinassist.ui.export import default_file_name

            suggested = default_file_name(session_id, self._store.saved_at(session_id))
            path = self._ask_pdf_path(suggested)
            if not path:
                return
            saved = self._export(session_id, path, self.include_transcript.isChecked())
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.setText(
            f"Saved {saved}. It contains patient information: store it as your clinic's "
            "rules require."
        )

    def _dialog_pdf_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(self, "Export as PDF", suggested, "PDF (*.pdf)")
        return path
