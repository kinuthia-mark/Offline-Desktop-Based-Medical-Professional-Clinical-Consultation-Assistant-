"""Session Records (FR-16, wireframe navigation): browse saved consultations, read only, and
export one as a PDF (FR-17, ui/export.py).

Each saved consultation shows the clinician's final note first, then the model's draft and the
approved transcript, so it is always clear what the clinician wrote and what the model wrote.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code


def describe(record) -> str:
    """The saved consultation as plain text, clinician's note first."""
    note, draft = record.final_note, record.draft
    lines = [
        f"Finalized by: {record.finalized_by}",
        f"Assessment written: {record.assessment_origin.replace('_', ' ')}",
        f"Model attempts: {record.generation_attempts}   Draft source: {draft.source}",
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
    ) -> None:
        """`export(session_id, path, include_transcript)` writes the PDF and returns where it
        was saved; `ask_pdf_path(suggested_name)` shows the save dialog (tests replace it)."""
        super().__init__()
        self._store = store
        self._before_action = before_action
        self._export = export
        self._ask_pdf_path = ask_pdf_path or self._dialog_pdf_path
        self.session_list = QListWidget()
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.message = QLabel()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        self.session_list.currentTextChanged.connect(self.show_session)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("Saved consultations, oldest first"))
        lv.addWidget(self.session_list, 1)
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
            ids = self._store.session_ids()
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.session_list.clear()
        self.session_list.addItems(ids)
        self.message.setText(f"{len(ids)} saved.")

    def show_session(self, session_id: str) -> None:
        if not session_id:
            self.detail.clear()
            return
        try:
            self._before_action()
            self.detail.setPlainText(describe(self._store.load(session_id)))
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))

    def export_pdf(self) -> None:
        item = self.session_list.currentItem()
        if item is None:
            self.message.setText("Select a saved consultation first.")
            return
        session_id = item.text()
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
