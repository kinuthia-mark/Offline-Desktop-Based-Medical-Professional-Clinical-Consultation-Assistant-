"""Audit, accounts, and backup and restore, for administrators (FR-09, FR-10a, FR-10c, FR-10d).

- The audit log, newest first, with a button that checks the whole hash chain and shows the
  newest entry's number and fingerprint. Writing those two down somewhere off the PC (for example
  in a paper register each evening) is what makes deleting the newest entries detectable later.
- Creating accounts, and turning an account off or back on.
- Making a backup of the encrypted vault to a file, and restoring one (security/backup.py).
- Turning the Windows Firewall rules off and on, so other programs on this PC can install
  things without the rules getting in the way (app.OfflineProtection). The app itself stays
  offline either way: its own network guard does not depend on the rules.
"""

# This file is the whole screen for the System Administrator role. It is one tab in the
# main window, shown only to admins. Admins manage the app (accounts, backups, the model,
# the firewall, the audit log) and never see clinical text, so nothing here reads notes.
# The screen only draws buttons and tables; the real work is done by the services passed in
# (auth, auditor, backups, models, protection).
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from clinassist.domain import ADMIN, ROLE_LABELS, ROLES
from clinassist.ui.messages import message_for
from clinassist.ui.workers import error_code, run_in_background


# The administrator's screen. It builds the widgets once, then reload() fills them with data.
# It takes the services as arguments (dependency injection), so tests can pass fakes.
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
        models=None,
        ask_folder: Callable[[], str] | None = None,
        protection=None,
    ) -> None:
        """`backups` (app.Backups) enables backup and restore. `on_restored` is called after a
        restore, when the program must close. The `ask_*` and `confirm` callables show the file
        dialogs and questions; tests replace them."""
        # Keep the services passed in. Each `ask_*` falls back to the real dialog method below,
        # so tests can pass fakes and never open a window.
        super().__init__()
        self._auditor, self._auth, self._admin = auditor, auth, admin_session
        # `on_restored or (lambda: None)` means: do nothing if no callback was given.
        self._backups, self._on_restored = backups, on_restored or (lambda: None)
        self._ask_save_path = ask_save_path or self._dialog_save_path
        self._ask_open_path = ask_open_path or self._dialog_open_path
        self._ask_secret = ask_secret or self._dialog_secret
        self._confirm = confirm or self._dialog_confirm
        self._ask_temporary = ask_temporary_password or self._dialog_temporary_password
        self._models = models  # app.ModelUpdates: offline language-model update (FR-10b)
        self._ask_folder = ask_folder or self._dialog_folder
        self._protection = protection  # app.OfflineProtection: the firewall rules
        self._protection_on = True  # read from Windows each time the tab opens

        # Audit log
        # The table has 5 columns, matching the header labels set on the next line.
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Time (UTC)", "Event", "Session", "User"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # The "#" column already numbers the entries; Qt's row numbers would repeat it.
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.verify_result = QLabel()
        self.verify_result.setWordWrap(True)
        # Buttons are wired to methods with `clicked.connect`: Qt calls the method on click.
        reload_button = QPushButton("Refresh")
        verify_button = QPushButton("Check the whole log")
        reload_button.clicked.connect(self.reload)
        verify_button.clicked.connect(self.verify)
        audit = QGroupBox("Audit log")
        # `a` is the vertical layout inside the audit box. The `1` gives the table the spare space.
        a = QVBoxLayout(audit)
        a.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(reload_button)
        row.addWidget(verify_button)
        a.addLayout(row)
        a.addWidget(self.verify_result)

        # Accounts
        # Fields for a new account. The password box hides what is typed.
        self.username = QLineEdit()
        self.display_name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.role = QComboBox()
        # Fill the role list from the fixed set of roles. The label is shown, the code is stored.
        for code in ROLES:
            self.role.addItem(ROLE_LABELS[code], code)
        create = QPushButton("Create account")
        create.clicked.connect(self.create_user)
        self.users = QTableWidget(0, 5)
        self.users.setHorizontalHeaderLabels(["Username", "Name", "Role", "On", "Locked"])
        self.users.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.users.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.users.verticalHeader().setVisible(False)
        self.users.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.users.horizontalHeader().setStretchLastSection(True)
        self.users.setMinimumHeight(150)  # the list must stay readable however full the column
        self._user_ids: list[str] = []
        self._usernames: dict[str, str] = {}  # user id -> username, for the audit log
        disable = QPushButton("Turn account off")
        enable = QPushButton("Turn account on")
        unlock = QPushButton("Unlock after wrong passwords")
        # The lambdas pass True or False to one shared method, so there is one code path.
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
        buttons = QGridLayout()
        # Two rows of two, so the column never needs scrolling sideways.
        for i, b in enumerate((disable, enable, unlock, self.reset_button)):
            buttons.addWidget(b, i // 2, i % 2)
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
        # Hide the whole backup box if no backup service was given.
        backups.setVisible(self._backups is not None)

        # `right` is the column of panels on the right. The numbers are how much space each gets.
        right = QVBoxLayout()
        right.addWidget(accounts, 3)
        right.addWidget(backups, 1)

        # Offline update of the language model (FR-10b)
        self.update_button = QPushButton("Update the AI model from a folder...")
        self.update_button.clicked.connect(self.update_model)
        self.update_message = QLabel()
        self.update_message.setWordWrap(True)
        updates = QGroupBox("AI model update")
        u = QVBoxLayout(updates)
        about = QLabel(
            "Install a new copy of the language model from a model bundle, for example on a USB "
            "drive. Every file is checked before anything is copied. Only the model this "
            "program was evaluated with is accepted, recognised by its fingerprint."
        )
        about.setWordWrap(True)
        u.addWidget(about)
        u.addWidget(self.update_button)
        u.addWidget(self.update_message)
        updates.setVisible(models is not None)
        right.addWidget(updates, 1)

        # Firewall rules off and on (NFR-01, ADR-010)
        self.protection_status = QLabel()
        self.protection_status.setWordWrap(True)
        self.protection_button = QPushButton()
        self.protection_button.clicked.connect(self.switch_protection)
        self.protection_message = QLabel()
        self.protection_message.setWordWrap(True)
        offline = QGroupBox("Offline protection")
        o = QVBoxLayout(offline)
        about_offline = QLabel(
            "Windows Firewall rules stop this program and the AI model service from reaching the "
            "internet. Turn them off only while installing software on this PC, then turn them "
            "back on. The program refuses network use itself either way."
        )
        about_offline.setWordWrap(True)
        o.addWidget(about_offline)
        o.addWidget(self.protection_status)
        o.addWidget(self.protection_button)
        o.addWidget(self.protection_message)
        offline.setVisible(protection is not None)
        right.addWidget(offline, 1)
        # The right column scrolls, so adding a panel never squeezes the accounts list.
        column = QWidget()
        column.setLayout(right)
        scroll = QScrollArea()
        scroll.setWidget(column)
        scroll.setWidgetResizable(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(audit, 3)
        layout.addWidget(scroll, 2)

    # Refresh the whole screen: the user list, the firewall status and the newest 500 audit rows.
    def reload(self) -> None:
        self._reload_users()
        self._show_protection()
        events = self._auditor.events(500)
        self.table.setRowCount(len(events))
        # Each event is a tuple of: entry number, time, event name, session id, user id.
        for row, (seq, ts, event, session_id, user_id) in enumerate(events):
            # The audit log stores ids only (no names in the hash chain); the screen shows the
            # username so an administrator can see who did what.
            user = self._usernames.get(user_id, user_id) if user_id else ""
            # Readable at a glance: the time to the second, and the short session id the
            # clinician's screen shows. The stored entry keeps the full values.
            when = ts[:19].replace("T", " ")
            short = session_id[:8].upper()
            # Fill one table cell per column. Qt cells need text, so each value becomes a string.
            for col, value in enumerate((seq, when, event, short, user)):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

    # Run the hash chain check and show the result. Writing down the head (newest entry's
    # number and fingerprint) off the PC is what lets later deletion of entries be spotted.
    def verify(self) -> None:
        result = self._auditor.verify()
        # `head` is the newest entry. Only the first 16 characters of its hash are shown.
        head = self._auditor.head()
        # `result.ok` is False when any entry was edited, removed or moved.
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

    # Load the account list into the table. `self._admin()` gives the admin's current session,
    # so the auth service can check the caller really is an administrator.
    def _reload_users(self) -> None:
        try:
            users = self._auth.list_users(self._admin())
        # Any failure (for example the session ended) is turned into a plain message for the screen.
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        # Remember the ids in table order, so a selected row can be mapped back to a user id.
        self._user_ids = [u["user_id"] for u in users]
        self._usernames = {u["user_id"]: u["username"] for u in users}
        self.users.setRowCount(len(users))
        for row, u in enumerate(users):
            values = (
                u["username"],
                u["display_name"],
                ROLE_LABELS.get(u["role"], u["role"]),
                "yes" if u["active"] else "no",
                "yes" if u["locked"] else "",
            )
            for col, value in enumerate(values):
                self.users.setItem(row, col, QTableWidgetItem(value))

    # The user id of the highlighted row, or an empty string if nothing is selected.
    def _selected_user(self) -> str:
        row = self.users.currentRow()
        return self._user_ids[row] if 0 <= row < len(self._user_ids) else ""

    # Create an account from the form. The auth service checks the password rules and the role.
    def create_user(self) -> None:
        try:
            self._auth.create_user(
                self._admin(),
                self.username.text(),
                self.password.text(),
                self.display_name.text(),
                self.role.currentData(),
            )
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        # Clear the password box so it does not stay on screen after use.
        self.account_message.setText(f"Account '{self.username.text().strip()}' created.")
        self.password.clear()
        self._reload_users()

    # Turn the selected account on or off. The auth service refuses it if the caller is not an
    # administrator.
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

    # Pops up a box asking for the temporary password. Returns "" if the admin cancels.
    def _dialog_temporary_password(self) -> str:
        text, ok = QInputDialog.getText(
            self,
            "Reset password",
            "Temporary password (at least 12 characters). The user replaces it at next login:",
            QLineEdit.EchoMode.Normal,  # shown, so the administrator can read it out correctly
        )
        return text if ok else ""

    # Clear the lock that wrong passwords put on the selected account.
    def unlock_account(self) -> None:
        try:
            self._auth.unlock_account(self._admin(), self._selected_user())
        except Exception as exc:
            self.account_message.setText(message_for(error_code(exc)))
            return
        self.account_message.setText("Account unlocked.")
        self._reload_users()

    # ----- backup and restore -----
    # Save the encrypted vault to a file. The admin check is repeated here as well as in the
    # backup service, so a non-admin can never get as far as the file dialog.
    def make_backup(self) -> None:
        try:
            self._auth.require(self._admin(), ADMIN)
            path = self._ask_save_path(self._backups.default_name())
            # An empty path means the admin cancelled the file dialog.
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

    # Restore a backup in three steps: pick the file, give the passphrase or recovery code,
    # then confirm. The program closes afterwards because the open vault has been replaced.
    def restore(self) -> None:
        try:
            self._auth.require(self._admin(), ADMIN)
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

    # The next four methods are the real Qt dialogs. Tests swap them for fakes.
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
        answer = QMessageBox.question(self, "Please confirm", question)
        return answer == QMessageBox.StandardButton.Yes

    # ----- offline model update (FR-10b) -----
    # Install a new model from a folder. The bundle is checked first, and only the model the
    # program was evaluated with (matched by fingerprint) is accepted.
    def update_model(self) -> None:
        try:
            self._auth.require(self._admin(), ADMIN)
            folder = self._ask_folder()
            if not folder:
                return
            # Check first and say what the bundle holds, before asking to install anything.
            check = self._models.check(folder)
            if check.already_installed:
                self.update_message.setText(
                    f"Every file checked. This is the {check.llm} model already installed: "
                    "nothing to update."
                )
                return
            # Bytes to gigabytes (1 GB = 1e9 bytes) for the question text.
            size_gb = check.total_bytes / 1e9
            question = (
                f"Every file in the bundle checked out. It holds {check.llm} ({check.files} "
                f"files, {size_gb:.1f} GB, {check.new_files} new to this PC). Install it? The "
                "next note will use the new model."
            )
            if not self._confirm(question):
                return
            self._models.apply(folder, self._admin().user_id)
        except Exception as exc:
            self.update_message.setText(message_for(error_code(exc)))
            return
        self.update_message.setText(
            "Model updated and checked. The next note will use it. To go back, apply the "
            "previous bundle again."
        )

    def _dialog_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Choose the model bundle folder")

    # ----- offline protection (firewall rules) -----
    # Ask Windows whether the firewall rules are set, without freezing the screen.
    def _show_protection(self) -> None:
        # Reading the rules starts PowerShell (about 1.6 s), so it runs off the screen's thread.
        if self._protection is not None:
            run_in_background(self._protection.is_on, self._shown_protection, lambda exc: None)

    # Called when the background check finishes. Shows the status and the matching button text.
    def _shown_protection(self, on: bool) -> None:
        self._protection_on = on
        self.protection_status.setText(
            "Status: on. The firewall rule for this program is set."
            if on
            else "Status: off. Other programs can use the internet. Turn it back on when you "
            "are finished."
        )
        self.protection_button.setText(
            "Turn offline protection off..." if on else "Turn offline protection on"
        )

    # Turn the firewall rules off or on. Turning off asks for confirmation first, because it
    # leaves other programs free to use the internet. Turning on needs no question.
    def switch_protection(self) -> None:
        try:
            self._auth.require(self._admin(), ADMIN)
            turn_on = not self._protection_on
            if not turn_on and not self._confirm(
                "Turn offline protection off? Other programs on this PC will be able to reach "
                "the internet until you turn it back on. Windows will ask you to confirm."
            ):
                return
            # `sent` is False if the Windows permission prompt was refused.
            sent = self._protection.switch(turn_on, self._admin().user_id)
        except Exception as exc:
            self.protection_message.setText(message_for(error_code(exc)))
            return
        self.protection_message.setText(
            "Windows is asking for permission. When you have answered, the status above updates."
            if sent
            else "Windows did not run the change (permission was refused). Nothing changed."
        )
        # The elevated script runs on its own; read the rules again once it has had time to run.
        QTimer.singleShot(4000, self, self._show_protection)  # cancelled if the screen closes
