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

# This file is the administrator's Database tab (a Qt widget). It is a window into the encrypted
# database for checking, not for editing. The data comes from an inspector object that
# knows how to read the vault safely. Every error is shown through messages.py.
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

from clinassist.domain import ADMIN
from clinassist.ui.messages import message_for
from clinassist.ui.theme import tone
from clinassist.ui.workers import error_code


# Admin-only tab. It only reads from the inspector, so it cannot change the database.
class DatabaseView(QWidget):
    def __init__(self, inspector, auth, admin_session: Callable[[], object]) -> None:
        """`inspector` is app.DatabaseInspector; `admin_session` returns the logged-in session."""
        super().__init__()
        # admin_session is a function, so the current login is looked up each time it is used.
        self._inspector, self._auth, self._admin = inspector, auth, admin_session
        self._tables: list[dict] = []  # table details from the last reload()

        # The file on disk
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        self.header_label = QLabel()
        self.header_label.setWordWrap(True)
        # A fixed-width font, so the hex bytes line up.
        self.header_label.setStyleSheet("font-family: Consolas, monospace;")
        self.encryption_label = QLabel()
        self.encryption_label.setStyleSheet("font-weight: bold;")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        disk = QGroupBox("The database file")
        d = QVBoxLayout(disk)
        # Put the three labels into the box in order.
        for w in (self.file_label, self.header_label, self.encryption_label):
            d.addWidget(w)
        d.addWidget(refresh)

        # Tables and their structure
        # The table list has two columns, cannot be edited, selects whole rows and has no row
        # numbers.
        self.table_list = QTableWidget(0, 2)
        self.table_list.setHorizontalHeaderLabels(["Table", "Rows"])
        self.table_list.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_list.verticalHeader().setVisible(False)
        self.table_list.horizontalHeader().setStretchLastSection(True)
        # Show the structure when the selected row changes. *_ ignores the signal's arguments.
        self.table_list.currentCellChanged.connect(lambda *_: self._show_structure())
        self.structure = QPlainTextEdit()
        self.structure.setReadOnly(True)
        self.structure.setStyleSheet("font-family: Consolas, monospace;")
        self.rows_button = QPushButton("Show the first rows of this table")
        self.rows_button.clicked.connect(self.show_rows)
        # The rows grid gets its columns later, once a table is chosen.
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
        # The right-hand panel gets twice the width of the left one.
        top.setStretchFactor(1, 2)

        rows_box = QGroupBox("Rows (read-only; viewing is recorded in the audit log)")
        rb = QVBoxLayout(rows_box)
        rb.addWidget(self.rows_button)
        rb.addWidget(self.rows, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(disk)
        # The numbers are stretch factors: the two tables take most of the height.
        layout.addWidget(top, 2)
        layout.addWidget(rows_box, 2)
        layout.addWidget(self.message)

    # Reloads everything on the tab: the file facts, the table list and the structure.
    def reload(self) -> None:
        try:
            # Only an administrator may look. require() raises an error if the user is not one.
            self._auth.require(self._admin(), ADMIN)
            # The file facts and the table list both come from the inspector.
            info = self._inspector.summary()
            self._tables = self._inspector.tables()
        # Any failure becomes a short code, which is shown as a plain sentence.
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.message.clear()
        # The :, in the size puts thousands separators in the number.
        self.file_label.setText(
            f"File: {info['path']}\nSize: {info['size_bytes']:,} bytes   "
            f"Schema version: {info['schema_version']}   "
            f"SQLCipher: {info['cipher_version'] or 'unknown'}"
        )
        self.header_label.setText(
            f"First 16 bytes on disk:      {info['first_bytes_hex']}\n"
            f'An unencrypted SQLite file:  {info["plain_header_hex"]}  ("SQLite format 3")'
        )
        # If the file can be opened without the key it is not encrypted, so warn loudly.
        if info["readable_without_key"]:
            self.encryption_label.setText("WARNING: the file starts like an unencrypted database.")
            tone(self.encryption_label, "error")
        else:
            self.encryption_label.setText(
                "Encrypted: the file does not start like a normal database, and opening it in a "
                "database tool without the key fails."
            )
            tone(self.encryption_label, "ok")
        # Fill the table list, one row per table.
        self.table_list.setRowCount(len(self._tables))
        for row, t in enumerate(self._tables):
            self.table_list.setItem(row, 0, QTableWidgetItem(t["name"]))
            self.table_list.setItem(row, 1, QTableWidgetItem(str(t["rows"])))
        # Select the first table. This also calls _show_structure through the signal.
        if self._tables:
            self.table_list.setCurrentCell(0, 0)
        # Called directly as well, so the panel is cleared when there are no tables.
        self._show_structure()

    # The table dict for the highlighted row, or None when nothing is selected.
    def _selected(self) -> dict | None:
        row = self.table_list.currentRow()
        return self._tables[row] if 0 <= row < len(self._tables) else None

    # Shows the columns and the CREATE statement of the chosen table.
    def _show_structure(self) -> None:
        table = self._selected()
        # Clear the rows left over from the previously selected table.
        self.rows.setRowCount(0)
        self.rows.setColumnCount(0)
        if table is None:
            self.structure.clear()
            return
        # One line per column: its name and type.
        columns = "\n".join(f"  {name}  {kind}" for name, kind in table["columns"])
        self.structure.setPlainText(
            f"{table['name']}: {table['rows']} row(s)\n\nColumns:\n{columns}\n\n{table['sql']}"
        )

    # Button handler: shows the first rows of the chosen table, read-only.
    def show_rows(self) -> None:
        table = self._selected()
        if table is None:
            return
        try:
            self._auth.require(self._admin(), ADMIN)
            # The inspector shortens long text, hides sensitive columns and records this view in
            # the audit log.
            columns, rows = self._inspector.rows(table["name"], self._admin().user_id)
        except Exception as exc:
            self.message.setText(message_for(error_code(exc)))
            return
        self.rows.setColumnCount(len(columns))
        self.rows.setHorizontalHeaderLabels(columns)
        self.rows.setRowCount(len(rows))
        # r is the row number and c is the column number.
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                self.rows.setItem(r, c, QTableWidgetItem(value))
        # Rows come back newest first and limited, so say how many are shown out of the total.
        shown = f"Showing {len(rows)} of {table['rows']} row(s), newest first."
        self.message.setText(shown)
