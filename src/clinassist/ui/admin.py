"""Audit, accounts, and backup and restore, for administrators (FR-09, FR-10a, FR-10c, FR-10d).

- The audit log, newest first, with a button that checks the whole hash chain and shows the
  newest entry's number and fingerprint. Writing those two down somewhere off the PC (for example
  in a paper register each evening) is what makes deleting the newest entries detectable later.
- Creating accounts, and turning an account off or back on.
- Making a backup of the encrypted vault to a file, and restoring one (security/backup.py).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code


class AdminView(QWidget):
    def __init__(
        self,
        auditor,
        auth,
        admin_session: Callable[[], object],
        backups=None,
        on_restored: Callable[[], None] | None = None,
        ask_save_path: Callable[[str], str] | None = None,
        ask_open_path: Callable[[], str] | None = None,
        ask_secret: Callable[[], str] | None = None,
        confirm: Callable[[str], bool] | None = None,
        ask_temporary_password: Callable[[], str] | None = None,
    ) -> None:
        """`backups` (app.Backups) enables backup and restore. `on_restored` is called after a
        restore, when the program must close. The `ask_*` and `confirm` callables show the file
        dialogs and questions; tests replace them."""
        super().__init__()
        self._auditor, self._auth, self._admin = auditor, auth, admin_session
        self._backups, self._on_restored = backups, on_restored or (lambda: None)
        self._ask_save_path = ask_save_path or self._dialog_save_path
        self._ask_open_path = ask_open_path or self._dialog_open_path
        self._ask_secret = ask_secret or self._dialog_secret
        self._confirm = confirm or self._dialog_confirm
        self._ask_temporary = ask_temporary_password or self._dialog_temporary_password

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
        self.reset_button = QPushButton("Reset password")
        self.reset_button.clicked.connect(self.reset_password)
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
        for b in (disable, enable, unlock, self.reset_button):
            buttons.addWidget(b)
        form.addRow(buttons)
        form.addRow(self.account_message)

        # Backup and restore (FR-10c)
        self.backup_button = QPushButton("Make a backup...")
        self.restore_button = QPushButton("Restore from a backup...")
        self.backup_button.clicked.connect(self.make_backup)
        self.restore_button.clicked.connect(self.restore)
        self.backup_message = QLabel()
        self.backup_message.setWordWrap(True)
        backups = QGroupBox("Backup and restore")
        b = QVBoxLayout(backups)
        explain = QLabel(
            "A backup is one encrypted file. Keep it on a USB drive away from this PC. "
            "Restoring needs the passphrase the vault had when the backup was made, or the "
            "recovery code. The current vault is moved aside, never deleted."
        )
        explain.setWordWrap(True)
        b.addWidget(explain)
        row = QHBoxLayout()
        row.addWidget(self.backup_button)
        row.addWidget(self.restore_button)
        b.addLayout(row)
        b.addWidget(self.backup_message)
        backups.setVisible(self._backups is not None)

        right = QVBoxLayout()
        right.addWidget(accounts, 3)
        right.addWidget(backups, 1)
        layout = QHBoxLayout(self)
        layout.addWidget(audit, 3)
        layout.addLayout(right, 2)

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

    def reset_password(self) -> None:
        """For a user who forgot their password: set a temporary one to tell them in person.
        They must replace it at their next login."""
        user_id = self._selected_user()
        if not user_id:
            self.account_message.setText("Select an account first.")
            return
        temporary = self._ask_temporary()
        if not temporary:
            return
        try:
            self._auth.reset_password(self._admin(), user_id, temporary)
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText(
            "Password reset. Tell the user the temporary password in person; they must choose "
            "a new one when they next log in."
        )
        self._reload_users()

    def _dialog_temporary_password(self) -> str:
        text, ok = QInputDialog.getText(
            self,
            "Reset password",
            "Temporary password (at least 12 characters). The user replaces it at next login:",
            QLineEdit.EchoMode.Normal,  # shown, so the administrator can read it out correctly
        )
        return text if ok else ""

    def unlock_account(self) -> None:
        try:
            self._auth.unlock_account(self._admin(), self._selected_user())
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText("Account unlocked.")
        self._reload_users()

    # ----- backup and restore -----
    def make_backup(self) -> None:
        try:
            self._auth.require(self._admin(), "admin")
            path = self._ask_save_path(self._backups.default_name())
            if not path:
                return
            info = self._backups.make(path, self._admin().user_id)
        except Exception as exc:
            self.backup_message.setText(message_for(error_code(exc)))
            return
        self.backup_message.setText(
            f"Backup saved ({info.created_at} UTC, {info.audit_entries} audit entries). "
            "Copy it to a drive kept away from this PC."
        )

    def restore(self) -> None:
        try:
            self._auth.require(self._admin(), "admin")
            path = self._ask_open_path()
            if not path:
                return
            secret = self._ask_secret()
            if not secret:
                return
            # Check first and say what the backup holds, before asking to replace anything.
            info = self._backups.check(path, secret)
            question = (
                f"This backup is from {info.created_at} UTC and holds {info.sessions} saved "
                "consultation(s). Consultations saved since then will not be in the restored "
                "vault; the current vault is moved aside, not deleted. The program will close "
                "afterwards. Restore it?"
            )
            if not self._confirm(question):
                return
            self._backups.restore(path, secret, self._admin().user_id)
        except Exception as exc:
            self.backup_message.setText(message_for(error_code(exc)))
            return
        self.backup_message.setText("Restored. The program will now close.")
        self._on_restored()

    def _dialog_save_path(self, suggested: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save the backup", suggested, "ClinAssist backup (*.clinbak)"
        )
        return path

    def _dialog_open_path(self) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a backup", "", "ClinAssist backup (*.clinbak)"
        )
        return path

    def _dialog_secret(self) -> str:
        text, ok = QInputDialog.getText(
            self,
            "Open the backup",
            "The passphrase the vault had when the backup was made, or the recovery code:",
            QLineEdit.EchoMode.Password,
        )
        return text if ok else ""

    def _dialog_confirm(self, question: str) -> bool:
        answer = QMessageBox.question(self, "Restore a backup", question)
        return answer == QMessageBox.StandardButton.Yes
