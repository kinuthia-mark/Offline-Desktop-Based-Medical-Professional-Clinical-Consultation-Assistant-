"""Audit and accounts, for administrators (FR-09, FR-10a, FR-10d).

- The audit log, newest first, with a button that checks the whole hash chain and shows the
  newest entry's number and fingerprint. Writing those two down somewhere off the PC (for example
  in a paper register each evening) is what makes deleting the newest entries detectable later.
- Creating accounts, and turning an account off or back on.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code


class AdminView(QWidget):
    def __init__(self, auditor, auth, admin_session: Callable[[], object]) -> None:
        super().__init__()
        self._auditor, self._auth, self._admin = auditor, auth, admin_session

        # Audit log
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Time (UTC)", "Event", "Session", "User"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.verify_result = QLabel()
        self.verify_result.setWordWrap(True)
        reload_button = QPushButton("Refresh")
        verify_button = QPushButton("Check the whole log")
        reload_button.clicked.connect(self.reload)
        verify_button.clicked.connect(self.verify)
        audit = QGroupBox("Audit log")
        a = QVBoxLayout(audit)
        a.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(reload_button)
        row.addWidget(verify_button)
        a.addLayout(row)
        a.addWidget(self.verify_result)

        # Accounts
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.role = QComboBox()
        self.role.addItems(["clinician", "admin"])
        create = QPushButton("Create account")
        create.clicked.connect(self.create_user)
        self.users = QTableWidget(0, 5)
        self.users.setHorizontalHeaderLabels(["Username", "Name", "Role", "On", "Locked"])
        self.users.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.users.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._user_ids: list[str] = []
        disable = QPushButton("Turn account off")
        enable = QPushButton("Turn account on")
        unlock = QPushButton("Unlock after wrong passwords")
        disable.clicked.connect(lambda: self._set_active(False))
        enable.clicked.connect(lambda: self._set_active(True))
        unlock.clicked.connect(self.unlock_account)
        self.account_message = QLabel()
        self.account_message.setWordWrap(True)
        accounts = QGroupBox("Accounts")
        form = QFormLayout(accounts)
        form.addRow("Username", self.username)
        form.addRow("Full name", self.display_name)
        form.addRow("Password", self.password)
        form.addRow("Role", self.role)
        form.addRow(create)
        form.addRow(self.users)
        buttons = QHBoxLayout()
        for b in (disable, enable, unlock):
            buttons.addWidget(b)
        form.addRow(buttons)
        form.addRow(self.account_message)

        layout = QHBoxLayout(self)
        layout.addWidget(audit, 3)
        layout.addWidget(accounts, 2)

    def reload(self) -> None:
        self._reload_users()
        events = self._auditor.events(500)
        self.table.setRowCount(len(events))
        for row, (seq, ts, event, session_id, user_id) in enumerate(events):
            for col, value in enumerate((seq, ts, event, session_id, user_id or "")):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def verify(self) -> None:
        result = self._auditor.verify()
        head = self._auditor.head()
        if result.ok:
            self.verify_result.setText(
                f"The log is intact: {result.checked} entries checked.\n"
                f"Write these down off this PC: entry {head.count}, "
                f"fingerprint {head.entry_hash[:16]}"
            )
        else:
            self.verify_result.setText(
                f"The log has been changed at entry {result.first_bad_seq} "
                f"({result.problem.replace('_', ' ')})."
            )

    def _reload_users(self) -> None:
        try:
            users = self._auth.list_users(self._admin())
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self._user_ids = [u["user_id"] for u in users]
        self.users.setRowCount(len(users))
        for row, u in enumerate(users):
            values = (
                u["username"],
                u["display_name"],
                u["role"],
                "yes" if u["active"] else "no",
                "yes" if u["locked"] else "",
            )
            for col, value in enumerate(values):
                self.users.setItem(row, col, QTableWidgetItem(value))

    def _selected_user(self) -> str:
        row = self.users.currentRow()
        return self._user_ids[row] if 0 <= row < len(self._user_ids) else ""

    def create_user(self) -> None:
        try:
            self._auth.create_user(
                self._admin(),
                self.username.text(),
                self.password.text(),
                self.display_name.text(),
                self.role.currentText(),
            )
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText(f"Account '{self.username.text().strip()}' created.")
        self.password.clear()
        self._reload_users()

    def _set_active(self, active: bool) -> None:
        try:
            self._auth.set_active(self._admin(), self._selected_user(), active)
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText("Account turned " + ("on." if active else "off."))
        self._reload_users()

    def unlock_account(self) -> None:
        try:
            self._auth.unlock_account(self._admin(), self._selected_user())
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText("Account unlocked.")
        self._reload_users()
