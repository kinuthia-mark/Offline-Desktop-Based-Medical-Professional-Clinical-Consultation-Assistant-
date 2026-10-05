"""The Database tab, for administrators: a read-only look inside the encrypted vault.

It shows, without any outside database tool:
- that the file on disk is encrypted: its first bytes next to the header every unencrypted
  SQLite file starts with;
- every table with its row count, columns and the exact statement that created it, including
  the CHECK constraints that refuse an unapproved note (security/schema.py);
- the first rows of a chosen table, text cut short and password hashes hidden. Viewing rows is
  written to the audit log.

Nothing on this tab can change the database.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
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


class DatabaseView(QWidget):
    def __init__(self, inspector, auth, admin_session: Callable[[], object]) -> None:
        """`inspector` is app.DatabaseInspector; `admin_session` returns the logged-in session."""
        super().__init__()
        self._inspector, self._auth, self._admin = inspector, auth, admin_session
        self._tables: list[dict] = []

        # The file on disk
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        self.header_label = QLabel()
        self.header_label.setWordWrap(True)
        self.header_label.setStyleSheet("font-family: Consolas, monospace;")
        self.encryption_label = QLabel()
        self.encryption_label.setStyleSheet("font-weight: bold;")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        disk = QGroupBox("The database file")
        d = QVBoxLayout(disk)
        for w in (self.file_label, self.header_label, self.encryption_label):
            d.addWidget(w)
        d.addWidget(refresh)

        # Tables and their structure
        self.table_list = QTableWidget(0, 2)
        self.table_list.setHorizontalHeaderLabels(["Table", "Rows"])
        self.table_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_list.currentCellChanged.connect(lambda *_: self._show_structure())
        self.structure = QPlainTextEdit()
        self.structure.setReadOnly(True)
        self.structure.setStyleSheet("font-family: Consolas, monospace;")
        self.rows_button = QPushButton("Show the first rows of this table")
        self.rows_button.clicked.connect(self.show_rows)
        self.rows = QTableWidget(0, 0)
        self.rows.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.message = QLabel()
        self.message.setWordWrap(True)

        left = QGroupBox("Tables")
        lv = QVBoxLayout(left)
        lv.addWidget(self.table_list)
        right = QGroupBox("Structure (how the table was created, with its rules)")
        rv = QVBoxLayout(right)
        rv.addWidget(self.structure)
        top = QSplitter()
        top.addWidget(left)
        top.addWidget(right)
        top.setStretchFactor(1, 2)

        rows_box = QGroupBox("Rows (read-only; viewing is recorded in the audit log)")
        rb = QVBoxLayout(rows_box)
        rb.addWidget(self.rows_button)
        rb.addWidget(self.rows, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(disk)
        layout.addWidget(top, 2)
        layout.addWidget(rows_box, 2)
        layout.addWidget(self.message)

    def reload(self) -> None:
        try:
            self._auth.require(self._admin(), "admin")
            info = self._inspector.summary()
            self._tables = self._inspector.tables()
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.clear()
        self.file_label.setText(
            f"File: {info['path']}\nSize: {info['size_bytes']:,} bytes   "
            f"Schema version: {info['schema_version']}   "
            f"SQLCipher: {info['cipher_version'] or 'unknown'}"
        )
        self.header_label.setText(
            f"First 16 bytes on disk:      {info['first_bytes_hex']}\n"
            f'An unencrypted SQLite file:  {info["plain_header_hex"]}  ("SQLite format 3")'
        )
        if info["readable_without_key"]:
            self.encryption_label.setText("WARNING: the file starts like an unencrypted database.")
            self.encryption_label.setStyleSheet("color: #e0484d; font-weight: bold;")
        else:
            self.encryption_label.setText(
                "Encrypted: the file does not start like a normal database, and opening it in a "
                "database tool without the key fails."
            )
            self.encryption_label.setStyleSheet("color: #2e9e44; font-weight: bold;")
        self.table_list.setRowCount(len(self._tables))
        for row, t in enumerate(self._tables):
            self.table_list.setItem(row, 0, QTableWidgetItem(t["name"]))
            self.table_list.setItem(row, 1, QTableWidgetItem(str(t["rows"])))
        if self._tables:
            self.table_list.setCurrentCell(0, 0)
        self._show_structure()

    def _selected(self) -> dict | None:
        row = self.table_list.currentRow()
        return self._tables[row] if 0 <= row < len(self._tables) else None

    def _show_structure(self) -> None:
        table = self._selected()
        self.rows.setRowCount(0)
        self.rows.setColumnCount(0)
        if table is None:
            self.structure.clear()
            return
        columns = "\n".join(f"  {name}  {kind}" for name, kind in table["columns"])
        self.structure.setPlainText(
            f"{table['name']}: {table['rows']} row(s)\n\nColumns:\n{columns}\n\n{table['sql']}"
        )

    def show_rows(self) -> None:
        table = self._selected()
        if table is None:
            return
        try:
            self._auth.require(self._admin(), "admin")
            columns, rows = self._inspector.rows(table["name"], self._admin().user_id)
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.rows.setColumnCount(len(columns))
        self.rows.setHorizontalHeaderLabels(columns)
        self.rows.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.rows.setItem(r, c, QTableWidgetItem(value))
        shown = f"Showing {len(rows)} of {table['rows']} row(s), newest first."
        self.message.setText(shown)
