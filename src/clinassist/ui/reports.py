"""The Reports tab, for clinicians: how the facility's clinical work is going.

Reading conditions and how notes were written needs a clinical background, so the report belongs
to the clinicians, not the system administrator, whose screens are technical only (AMD-50).

Four charts answer the questions a facility manager or the county health office asks: when the
facility is busiest (by hour and by day, for staffing), how many consultations are documented
each day, and which conditions it sees most (disease surveillance, as in the monthly MOH 705
return). Beside them, the table: the officer picks a period (the last 7 days, 30 days or
everything) and sees how many
consultations were started, saved and discarded, how the notes were written, how often the
AI's text was kept as it was, how often diagnosis suggestions were accepted, the median time
to draft a note, and notes per clinician, per model and per day. The report can
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
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from clinassist.domain import CLINICIAN
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
    "Hypertension": "HTN",
    "Other conditions": "Other",
}


class ReportsView(QWidget):
    def __init__(
        self,
        reports,
        auth,
        session: Callable[[], object],
        ask_save_path: Callable[[str], str] | None = None,
    ) -> None:
        """`reports` is app.Reports; `ask_save_path(suggested)` returns where to save, or ""."""
        super().__init__()
        self._reports, self._auth, self._session = reports, auth, session
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
        # The measure takes the spare width and wraps, so the value column always stays in view.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        note = QLabel(
            "Counts and times only: no patient details are shown or saved. Times are measured "
            "from the audit log on this computer."
        )
        note.setWordWrap(True)
        tone(note, "quiet")
        self.message = QLabel()
        self.message.setWordWrap(True)

        # Charts: the reason the report exists. Each title says what the facility uses it for.
        # Two rows; in the second, the conditions chart takes two thirds because its labels are
        # the longest.
        self.charts = QVBoxLayout()
        self.chart_views: dict[str, QChartView] = {}
        rows = (((("hours", 1), ("days", 1))), (("daily", 1), ("conditions", 2)))
        for row in rows:
            line = QHBoxLayout()
            for key, stretch in row:
                view = QChartView()
                view.setRenderHint(QPainter.RenderHint.Antialiasing)
                view.setMinimumHeight(220)
                self.chart_views[key] = view
                line.addWidget(view, stretch)
            self.charts.addLayout(line)

        # Charts get the full width (labels need it); the figures behind them are one tab away.
        charts = QWidget()
        charts.setLayout(self.charts)
        self.views = QTabWidget()
        self.views.addTab(charts, "Charts")
        self.views.addTab(self.table, "Figures")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addLayout(bar)
        layout.addWidget(self.period_label)
        layout.addWidget(self.views, 1)
        layout.addWidget(note)
        layout.addWidget(self.message)

    def reload(self) -> None:
        try:
            self._auth.require(self._session(), CLINICIAN)
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
        self.table.resizeRowsToContents()  # long measures wrap onto a second line
        self._draw_charts(self.report)

    def _draw_charts(self, r) -> None:
        # Short labels (8 for 08:00, 3 for the 3rd), so they fit under each bar.
        # The clinic day (7:00 to 19:00), stretched to include any hour that had consultations,
        # so an evening or night clinic is never left off the chart.
        busy = [h for h, n in r.per_hour.items() if n]
        first, last = min([7, *busy]), max([19, *busy])
        busiest_hours = {str(h): r.per_hour.get(h, 0) for h in range(first, last + 1)}
        self._bar("hours", "Busiest hours of the day (plan staffing)", busiest_hours)
        days = {day[:2]: n for day, n in r.per_weekday.items()}  # "Mo", "Tu": fit narrow bars
        self._bar("days", "Busiest days of the week", days)
        daily = {str(int(day[8:])): n for day, n in list(r.per_day.items())[-14:]}
        self._bar("daily", "Consultations saved per day (last 14 days)", daily)
        conditions = {SHORT_NAMES.get(label, label): n for label, n in r.conditions.items()}
        self._bar("conditions", "Conditions seen (disease surveillance)", conditions)

    def _bar(self, key: str, title: str, data: dict) -> None:
        """One upright bar chart in the app's colours. `data` maps a label to a count."""
        c = DARK if is_dark() else LIGHT
        bars = QBarSet("count")
        bars.setColor(QColor(c["primary"]))
        bars.setBorderColor(QColor(c["primary"]))
        for value in data.values():
            bars.append(value)
        series = QBarSeries()
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
        top = max([*data.values(), 1])
        counts.setLabelFormat("%d")
        counts.setRange(0, top)
        if top <= 10:  # one tick per whole count, so small numbers never read "0 0 0 1"
            counts.setTickCount(top + 1)
        else:
            counts.applyNiceNumbers()  # ticks on round numbers (0, 10, 20), not 7, 15, 23
        small = QFont("Segoe UI", 8)
        for axis in (labels, counts):
            axis.setLabelsFont(small)
            axis.setLabelsColor(QColor(c["muted"]))
            axis.setGridLineColor(QColor(c["border"]))
        chart.addAxis(labels, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(counts, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(labels)
        series.attachAxis(counts)
        self.chart_views[key].setChart(chart)

    def save_csv(self) -> None:
        if self.report is None:
            return
        try:
            self._auth.require(self._session(), CLINICIAN)
            path = self._ask_save_path(f"clinassist-report-{date.today().isoformat()}.csv")
            if not path:
                return
            self._reports.save_csv(self.report, path, self._session().user_id)
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.setText(f"Report saved to {path}.")

    def _dialog_save_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the report", suggested, "CSV file (*.csv)"
        )
        return path
