"""The Reports tab, for administrators: how the program is being used, in counts and times.

The administrator picks a period (the last 7 days, 30 days or everything) and sees how many
consultations were started, saved and discarded, how the notes were written, how often the
AI's text was kept as it was, how often diagnosis suggestions were accepted, the median time
to draft a note, notes per clinician, per model and per day, and failed logins. The report can
be saved as a CSV file for a spreadsheet; saving is written to the audit log.

No patient text is shown or saved: reports.py reads only counts, codes and times.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.reports import PERIODS, period_text, summary_rows
from clinassist.ui.messages import message_for
from clinassist.ui.theme import mark, tone
from clinassist.ui.workers import error_code


class ReportsView(QWidget):
    def __init__(
        self,
        reports,
        auth,
        admin_session: Callable[[], object],
        ask_save_path: Callable[[str], str] | None = None,
    ) -> None:
        """`reports` is app.Reports; `ask_save_path(suggested)` returns where to save, or ""."""
        super().__init__()
        self._reports, self._auth, self._admin = reports, auth, admin_session
        self._ask_save_path = ask_save_path or self._dialog_save_path
        self.report = None

        self.period = QComboBox()
        self.period.addItems(list(PERIODS))
        self.period.setCurrentText("Last 30 days")
        self.period.currentTextChanged.connect(lambda _: self.reload())
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        self.save_button = QPushButton("Save as CSV")
        mark(self.save_button, "primary")
        self.save_button.clicked.connect(self.save_csv)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Period:"))
        bar.addWidget(self.period)
        bar.addWidget(refresh)
        bar.addStretch(1)
        bar.addWidget(self.save_button)

        self.period_label = QLabel()
        tone(self.period_label, "quiet")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Section", "Measure", "Value"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        note = QLabel(
            "Counts and times only: no patient details are shown or saved. Times are measured "
            "from the audit log on this computer."
        )
        note.setWordWrap(True)
        tone(note, "quiet")
        self.message = QLabel()
        self.message.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.period_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(note)
        layout.addWidget(self.message)

    def reload(self) -> None:
        try:
            self._auth.require(self._admin(), "admin")
            self.report = self._reports.build(self.period.currentText())
        except Exception as exc:
            self.report = None
            self.table.setRowCount(0)
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.clear()
        self.period_label.setText(period_text(self.report))
        rows = summary_rows(self.report)
        self.table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def save_csv(self) -> None:
        if self.report is None:
            return
        try:
            self._auth.require(self._admin(), "admin")
            path = self._ask_save_path(f"clinassist-report-{date.today().isoformat()}.csv")
            if not path:
                return
            self._reports.save_csv(self.report, path, self._admin().user_id)
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.setText(f"Report saved to {path}.")

    def _dialog_save_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the report", suggested, "CSV file (*.csv)"
        )
        return path
