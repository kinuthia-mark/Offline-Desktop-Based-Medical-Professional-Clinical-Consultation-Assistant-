"""The Reports tab, for the health records officer: how the facility is working.

Four charts answer the questions a facility manager or the county health office asks: when the
facility is busiest (by hour and by day, for staffing), how many consultations are documented
each day, and which conditions it sees most (disease surveillance, as in the monthly MOH 705
return). Beside them, the table: the officer picks a period (the last 7 days, 30 days or
everything) and sees how many
consultations were started, saved and discarded, how the notes were written, how often the
AI's text was kept as it was, how often diagnosis suggestions were accepted, the median time
to draft a note, notes per clinician, per model and per day, and failed logins. The report can
be saved as a CSV file for a spreadsheet; saving is written to the audit log.

No patient text is shown or saved: reports.py reads only counts, codes and times.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.domain import RECORDS_OFFICER
from clinassist.reports import PERIODS, period_text, summary_rows
from clinassist.ui.messages import message_for
from clinassist.ui.theme import DARK, LIGHT, is_dark, mark, tone
from clinassist.ui.workers import error_code

# Chart labels only; the table and the CSV file keep the full names.
SHORT_NAMES = {
    "Upper respiratory tract infection": "URTI",
    "Urinary tract infection": "UTI",
    "Diarrhoea or gastroenteritis": "Diarrhoea",
    "Bronchitis or other chest infection": "Bronchitis",
    "Other conditions": "Other",
}


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

        # Charts: the reason the report exists. Each title says what the facility uses it for.
        self.charts = QGridLayout()
        self.chart_views: dict[str, QChartView] = {}
        for i, key in enumerate(("hours", "days", "daily", "conditions")):
            view = QChartView()
            view.setRenderHint(QPainter.RenderHint.Antialiasing)
            view.setMinimumHeight(220)
            self.chart_views[key] = view
            self.charts.addWidget(view, i // 2, i % 2)

        body = QHBoxLayout()
        charts = QWidget()
        charts.setLayout(self.charts)
        body.addWidget(charts, 3)
        body.addWidget(self.table, 2)
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.period_label)
        layout.addLayout(body, 1)
        layout.addWidget(note)
        layout.addWidget(self.message)

    def reload(self) -> None:
        try:
            self._auth.require(self._admin(), RECORDS_OFFICER)
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
        self._draw_charts(self.report)

    def _draw_charts(self, r) -> None:
        # Short labels (8 for 08:00, 3 for the 3rd), so they fit under each bar.
        busiest_hours = {str(h): n for h, n in r.per_hour.items() if 7 <= h <= 19}
        self._bar("hours", "Busiest hours of the day (plan staffing)", busiest_hours)
        self._bar("days", "Busiest days of the week", r.per_weekday)
        daily = {str(int(day[8:])): n for day, n in list(r.per_day.items())[-14:]}
        self._bar("daily", "Consultations saved per day (last 14 days)", daily)
        conditions = {SHORT_NAMES.get(label, label): n for label, n in r.conditions.items()}
        self._bar("conditions", "Conditions seen (disease surveillance)", conditions, sideways=True)

    def _bar(self, key: str, title: str, data: dict, sideways: bool = False) -> None:
        """One bar chart in the app's colours. `data` maps a label to a count."""
        c = DARK if is_dark() else LIGHT
        if sideways:  # Qt draws the first bar at the bottom; put the most common on top
            data = dict(reversed(list(data.items())))
        bars = QBarSet("count")
        bars.setColor(QColor(c["primary"]))
        bars.setBorderColor(QColor(c["primary"]))
        for value in data.values():
            bars.append(value)
        series = QHorizontalBarSeries() if sideways else QBarSeries()
        series.append(bars)
        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(title)
        chart.legend().setVisible(False)
        chart.setBackgroundBrush(QColor(c["surface"]))
        chart.setTitleBrush(QColor(c["text"]))
        labels = QBarCategoryAxis()
        labels.append(list(data) or ["no data"])
        counts = QValueAxis()
        counts.setRange(0, max([*data.values(), 1]))
        counts.setLabelFormat("%d")
        counts.applyNiceNumbers()  # ticks on round numbers (0, 10, 20), not 7, 15, 23
        for axis in (labels, counts):
            axis.setLabelsColor(QColor(c["muted"]))
            axis.setGridLineColor(QColor(c["border"]))
        category_side, value_side = (
            (Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignBottom)
            if sideways
            else (Qt.AlignmentFlag.AlignBottom, Qt.AlignmentFlag.AlignLeft)
        )
        chart.addAxis(labels, category_side)
        chart.addAxis(counts, value_side)
        series.attachAxis(labels)
        series.attachAxis(counts)
        self.chart_views[key].setChart(chart)

    def save_csv(self) -> None:
        if self.report is None:
            return
        try:
            self._auth.require(self._admin(), RECORDS_OFFICER)
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
